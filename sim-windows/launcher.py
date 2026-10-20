"""Reader simulator launcher: pick a model and a firmware, build it, start it in a window
that looks like the real reader (click its keys; on X4 Pro click the screen to touch).
Firmwares come from local source folders or "Get from GitHub" (menu: firmwares.json).
    pythonw launcher.py          (or double-click Simulator.cmd)
    python launcher.py --check   (no window: list what it finds, then exit)"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
CROSSINK = os.path.abspath(os.path.join(HERE, "..", ".."))
FRAMES = os.path.join(HERE, "..", "device-frames", "frames")  # same place here and in the repo
# Short on purpose: some firmware libraries have very deep files, and Windows paths stop at 260 characters.
DOWNLOADS = os.path.join(os.environ.get("USERPROFILE", HERE), "rsim", "fw")
NAME_FILE = ".rsim-name"  # "owner/repo@ref" of a downloaded firmware
CATALOGUE = os.path.join(HERE, "firmwares.json")
BASH = r"C:\Program Files\Git\bin\bash.exe"
SETTINGS = os.path.join(HERE, "launcher.json")
MODELS = {"X4 Pro": "x4-pro", "X4 Classic": "x4-classic", "X3": "x3"}  # shown name -> frame
# PlatformIO simulator environments per model, first match wins. CrossInk-family firmwares
# name all three; CrossPoint-family ones (CrumBLE, YACP) have "simulator" (X4) and "simulator_x3".
ENV_NAMES = {"X4 Pro": ["x4-pro-simulator"], "X4 Classic": ["x4-classic-simulator", "simulator"],
             "X3": ["simulator-X3", "simulator_x3"]}
REPO_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:github\.com/)?([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?(?:[/#?].*)?$")
NO_WINDOW = subprocess.CREATE_NO_WINDOW
try:  # sharp on high-DPI screens, and window positions in real screen pixels
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (AttributeError, OSError):
    pass


def load_settings():
    try:
        return json.load(open(SETTINGS))
    except (OSError, ValueError):
        return {"extra_folders": []}


def envs_for(folder):
    """{model: PlatformIO env} for the simulator setups this firmware has."""
    try:
        ini = open(os.path.join(folder, "platformio.ini"), encoding="utf-8").read()
    except OSError:
        return {}
    have = set(re.findall(r"^\[env:([^\]]+)\]", ini, re.M))
    return {m: next(e for e in names if e in have) for m, names in ENV_NAMES.items() if have & set(names)}


def firmware_name(folder):
    """'varagh-lion-1.3.0 (1.3.0)' from the folder and its platformio.ini version."""
    version = ""
    try:
        for line in open(os.path.join(folder, "platformio.ini"), encoding="utf-8"):
            if line.strip().startswith("version ="):
                version = line.split("=", 1)[1].strip()
                break
    except OSError:
        pass
    try:  # a download: show "owner/repo@ref", not its short folder name
        label = open(os.path.join(folder, NAME_FILE), encoding="utf-8").read().strip()
    except OSError:
        label = os.path.basename(folder)
    return f"{label} ({version})" if version else label


def find_firmwares(extra):
    """Source folders with at least one simulator setup: Crossink/github/*, downloads, added folders."""
    candidates = []
    for parent in (os.path.join(CROSSINK, "github"), DOWNLOADS):
        if os.path.isdir(parent):
            candidates += [os.path.join(parent, d) for d in sorted(os.listdir(parent))]
    return {firmware_name(f): f for f in candidates + list(extra) if envs_for(f)}


def program(folder, env):
    return os.path.join(folder, ".pio", "build", env, "program.exe")


def card_dir(folder, frame):
    return os.path.join(HERE, "cards", f"{os.path.basename(folder)}-{frame}")


def parse_repo(text):
    """'owner/name' from a GitHub link or 'owner/name'; None if it is not one."""
    m = REPO_RE.match(text.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def github_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "reader-simulator", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def versions(repo):
    """Newest releases first, then the default branch (latest code)."""
    info = github_json(f"https://api.github.com/repos/{repo}")
    tags = [r["tag_name"] for r in github_json(f"https://api.github.com/repos/{repo}/releases?per_page=10")
            if not r.get("draft")]
    return tags + [info["default_branch"]]


def rmtree(path):
    """shutil.rmtree that also removes git's read-only files on Windows."""
    def clear_readonly(func, p, _):
        os.chmod(p, 0o666)
        func(p)
    shutil.rmtree(path, onerror=clear_readonly)


def download(repo, ref, on_line=lambda s: None):
    """Shallow clone of one version (with submodules) into rsim/fw/<8 letters>; returns the folder."""
    dest = os.path.join(DOWNLOADS, hashlib.md5(f"{repo}@{ref}".encode()).hexdigest()[:8])
    if os.path.isfile(os.path.join(dest, "platformio.ini")):
        return dest
    if os.path.isdir(dest):
        rmtree(dest)  # a broken earlier download
    os.makedirs(DOWNLOADS, exist_ok=True)
    proc = subprocess.Popen(["git", "clone", "--progress", "--depth", "1", "--branch", ref, "--recurse-submodules",
                             "--shallow-submodules", f"https://github.com/{repo}.git", dest],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                            creationflags=NO_WINDOW)
    for line in proc.stdout:
        on_line(line.strip())
    if proc.wait() != 0:
        rmtree(dest)
        raise RuntimeError(f"Could not download {repo} {ref}.")
    open(os.path.join(dest, NAME_FILE), "w", encoding="utf-8", newline="\n").write(repo + "@" + ref + "\n")
    return dest


class GitHubDialog(tk.Toplevel):
    """Pick a firmware from the menu (or paste any GitHub link), pick a version, download it."""

    def __init__(self, parent, on_done):
        super().__init__(parent)
        self.title("Get a firmware from GitHub")
        self.resizable(False, False)
        self.transient(parent)
        self.on_done = on_done
        self.catalogue = json.load(open(CATALOGUE, encoding="utf-8"))["firmwares"]
        self.repo = None
        self.version = tk.StringVar()
        self.link = tk.StringVar()
        self.status = tk.StringVar(value="Pick a firmware.")
        body = ttk.Frame(self, padding=10)
        body.grid()
        self.list = tk.Listbox(body, width=72, height=min(len(self.catalogue), 14), activestyle="none", exportselection=False)
        for fw in self.catalogue:
            mark = {"ready": "  - tested", "untested": "  - not tested yet", "broken": "  - its simulator setup is broken",
                    "adapter": "  - needs an adapter (not yet)", "unsupported": "  - cannot run here"}
            frame = "" if fw.get("frame") or fw["status"] in ("unsupported", "adapter") else "  (no frame yet)"
            self.list.insert("end", fw["name"] + mark.get(fw["status"], "") + frame)
        self.list.grid(row=0, column=0, columnspan=3, sticky="we")
        self.list.bind("<<ListboxSelect>>", lambda e: self.pick_catalogue())
        ttk.Label(body, text="or any GitHub link:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        entry = ttk.Entry(body, textvariable=self.link, width=44)
        entry.grid(row=1, column=1, sticky="we", pady=(8, 0))
        ttk.Button(body, text="Look up", command=self.pick_link).grid(row=1, column=2, pady=(8, 0), padx=(6, 0))
        ttk.Label(body, text="Version:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.version_box = ttk.Combobox(body, textvariable=self.version, state="readonly", width=42)
        self.version_box.grid(row=2, column=1, sticky="w", pady=(8, 0))
        self.get_btn = ttk.Button(body, text="Download", command=self.get)
        self.get_btn.grid(row=2, column=2, pady=(8, 0), padx=(6, 0))
        ttk.Label(body, textvariable=self.status, wraplength=440, foreground="#555").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def pick_catalogue(self):
        sel = self.list.curselection()
        if not sel:
            return
        fw = self.catalogue[sel[0]]
        if fw["status"] in ("unsupported", "adapter") or not fw["repo"]:
            self.repo = None
            self.version_box.configure(values=[])
            self.version.set("")
            self.status.set(fw["about"])
            return
        self.status.set(fw["about"] + ("  It may not build." if fw["status"] in ("broken", "untested") else ""))
        self.load_versions(fw["repo"])

    def pick_link(self):
        repo = parse_repo(self.link.get())
        if not repo:
            self.status.set("That is not a GitHub repository link (github.com/owner/name).")
            return
        self.list.selection_clear(0, "end")
        self.load_versions(repo)

    def load_versions(self, repo):
        self.repo = repo
        self.status.set(f"Reading versions of {repo}…")

        def run():
            try:
                vs = versions(repo)
                self.after(0, self.show_versions, repo, vs, None)
            except Exception as e:  # network, rate limit, unknown repo
                self.after(0, self.show_versions, repo, [], e)

        threading.Thread(target=run, daemon=True).start()

    def show_versions(self, repo, vs, error):
        if repo != self.repo:
            return
        if error:
            self.status.set(f"Could not read {repo} from GitHub: {error}")
            return
        labels = [v + ("  (latest code)" if i == len(vs) - 1 else "") for i, v in enumerate(vs)]
        self.version_box.configure(values=labels)
        self.version.set(labels[0])
        self.status.set(f"{repo}: {len(vs) - 1} releases. Pick a version and press Download.")

    def get(self):
        if not self.repo or not self.version.get():
            self.status.set("Pick a firmware and a version first.")
            return
        repo, ref = self.repo, self.version.get().split("  ")[0]
        self.get_btn.state(["disabled"])

        def run():
            try:
                folder = download(repo, ref, lambda s: self.after(0, self.status.set, "Downloading… " + s[-70:]))
                self.after(0, self.finished, folder, None)
            except Exception as e:
                self.after(0, self.finished, None, e)

        threading.Thread(target=run, daemon=True).start()

    def finished(self, folder, error):
        self.get_btn.state(["!disabled"])
        if error:
            self.status.set(str(error))
            return
        if not envs_for(folder):
            self.status.set("Downloaded, but this firmware has no simulator setup, so it cannot run here yet.")
            return
        self.on_done(folder)
        self.destroy()


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Reader simulator")
        self.resizable(False, False)
        self.settings = load_settings()
        self.firmwares = find_firmwares(self.settings.get("extra_folders", []))
        self.model = tk.StringVar(value=self.settings.get("model", "X4 Pro"))
        names = list(self.firmwares)
        self.firmware = tk.StringVar(value=self.settings.get("firmware") if self.settings.get("firmware") in names
                                     else (names[0] if names else ""))
        self.battery = tk.IntVar(value=self.settings.get("battery", 80))
        self.usb = tk.BooleanVar(value=self.settings.get("usb", False))
        self.status = tk.StringVar()
        self.previews = {}
        pad = dict(padx=10, pady=4)

        left = ttk.Frame(self, padding=10)
        left.grid(row=0, column=0, sticky="n")
        ttk.Label(left, text="Device").grid(row=0, column=0, sticky="w")
        for i, name in enumerate(MODELS):
            ttk.Radiobutton(left, text=name, value=name, variable=self.model, command=self.refresh).grid(
                row=1 + i, column=0, sticky="w")
        ttk.Label(left, text="Firmware").grid(row=5, column=0, sticky="w", pady=(12, 0))
        self.fw_box = ttk.Combobox(left, textvariable=self.firmware, values=names, state="readonly", width=34)
        self.fw_box.grid(row=6, column=0, sticky="w")
        self.fw_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(left, text="Get from GitHub…", command=lambda: GitHubDialog(self, self.add_firmware)).grid(
            row=7, column=0, sticky="w", **pad)
        ttk.Button(left, text="Add a firmware folder…", command=self.add_folder).grid(row=8, column=0, sticky="w", padx=10)
        ttk.Label(left, text="Battery %").grid(row=9, column=0, sticky="w", pady=(12, 0))
        ttk.Scale(left, from_=0, to=100, variable=self.battery, orient="horizontal", length=200,
                  command=lambda v: self.battery.set(round(float(v)))).grid(row=10, column=0, sticky="w")
        ttk.Label(left, textvariable=self.battery).grid(row=10, column=0, sticky="e")
        ttk.Checkbutton(left, text="USB cable plugged in", variable=self.usb).grid(row=11, column=0, sticky="w")
        buttons = ttk.Frame(left)
        buttons.grid(row=12, column=0, sticky="w", pady=(14, 0))
        self.build_btn = ttk.Button(buttons, text="Build", command=self.build)
        self.build_btn.grid(row=0, column=0)
        self.start_btn = ttk.Button(buttons, text="Start", command=self.start)
        self.start_btn.grid(row=0, column=1, padx=6)
        ttk.Button(left, text="Open SD card folder", command=self.open_card).grid(row=13, column=0, sticky="w", **pad)
        ttk.Button(left, text="Fresh SD card", command=self.fresh_card).grid(row=14, column=0, sticky="w", padx=10)
        ttk.Label(left, textvariable=self.status, wraplength=250, foreground="#555").grid(
            row=15, column=0, sticky="w", pady=(12, 0))
        self.preview = ttk.Label(self, padding=10)
        self.preview.grid(row=0, column=1)
        self.refresh()

    # --- state -----------------------------------------------------------
    def current(self):
        folder = self.firmwares.get(self.firmware.get())
        env = envs_for(folder).get(self.model.get()) if folder else None
        return folder, MODELS[self.model.get()], env

    def refresh(self):
        folder, frame, env = self.current()
        if frame not in self.previews:
            try:  # a small picture of the reader
                self.previews[frame] = tk.PhotoImage(file=os.path.join(FRAMES, frame + ".png")).subsample(2, 2)
            except tk.TclError:
                self.previews[frame] = None
        self.preview.configure(image=self.previews[frame] or "")
        if not folder:
            self.status.set("No firmware yet. Use Get from GitHub or add a source folder.")
        elif not env:
            have = ", ".join(envs_for(folder)) or "none"
            self.status.set(f"This firmware has no {self.model.get()} simulator (it has: {have}).")
        elif os.path.isfile(program(folder, env)):
            self.status.set("Built. Press Start.")
        else:
            self.status.set("Not built yet for this device. Press Build (first build: 5-10 minutes).")
        self.save()

    def save(self):
        self.settings.update(model=self.model.get(), firmware=self.firmware.get(),
                             battery=self.battery.get(), usb=self.usb.get())
        try:
            json.dump(self.settings, open(SETTINGS, "w"), indent=1)
        except OSError:
            pass

    # --- actions ---------------------------------------------------------
    def add_firmware(self, folder):
        self.firmwares = find_firmwares(self.settings.get("extra_folders", []))
        self.fw_box.configure(values=list(self.firmwares))
        self.firmware.set(firmware_name(folder))
        self.refresh()

    def add_folder(self):
        folder = filedialog.askdirectory(title="Firmware source folder (with platformio.ini)")
        if not folder:
            return
        if not envs_for(folder):
            messagebox.showerror("Reader simulator", "That folder has no platformio.ini with a simulator setup.")
            return
        self.settings.setdefault("extra_folders", []).append(folder)
        self.add_firmware(folder)

    def build(self):
        folder, _, env = self.current()
        if not env:
            return
        self.build_btn.state(["disabled"])
        self.start_btn.state(["disabled"])
        self.status.set("Building…")

        def run():
            proc = subprocess.Popen([BASH, os.path.join(HERE, "build.sh"), folder, env], cwd=HERE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
            last = ""
            for line in proc.stdout:
                last = line.strip() or last
                self.after(0, self.status.set, "Building… " + last[-80:])
            ok = proc.wait() == 0
            self.after(0, self.build_done, ok, last)

        threading.Thread(target=run, daemon=True).start()

    def build_done(self, ok, last):
        self.build_btn.state(["!disabled"])
        self.start_btn.state(["!disabled"])
        self.refresh()
        if not ok:
            self.status.set("Build failed: " + last[-160:] + "  (full log: dev\\sim-windows\\build.log)")

    def start(self):
        folder, frame, env = self.current()
        exe = program(folder, env) if env else ""
        if not os.path.isfile(exe):
            self.status.set("Not built yet. Press Build first.")
            return
        card = card_dir(folder, frame)
        os.makedirs(os.path.join(card, "fs_"), exist_ok=True)
        run_env = dict(os.environ, CROSSPOINT_SIM_FRAME=os.path.join(FRAMES, frame).replace("\\", "/"),
                       VARAGH_SIM_BATTERY=str(self.battery.get()), VARAGH_SIM_USB="1" if self.usb.get() else "0")
        subprocess.Popen([exe], cwd=card, env=run_env, creationflags=NO_WINDOW,
                         stdout=open(os.path.join(card, "last-run.log"), "w"), stderr=subprocess.STDOUT)
        self.status.set(f"Started {self.model.get()} with {self.firmware.get()}. Keys: click them, "
                        "or Esc / Enter / arrows / P / H. S = sleep.")
        self.save()

    def open_card(self):
        folder, frame, _ = self.current()
        if folder:
            card = os.path.join(card_dir(folder, frame), "fs_")
            os.makedirs(card, exist_ok=True)
            os.startfile(card)

    def fresh_card(self):
        folder, frame, _ = self.current()
        card = os.path.join(card_dir(folder, frame), "fs_") if folder else ""
        if card and os.path.isdir(card) and messagebox.askyesno(
                "Reader simulator", f"Delete everything on this simulated SD card?\n{card}"):
            shutil.rmtree(card)
            os.makedirs(card)
            self.status.set("SD card is empty again.")


def check():
    """No window: print what the launcher would offer, and build both windows once to catch errors."""
    assert parse_repo("https://github.com/uxjulia/crossink") == "uxjulia/crossink"
    assert parse_repo("github.com/Sichroteph/YACP.git") == "Sichroteph/YACP"
    assert parse_repo("Sichroteph/YACP") == "Sichroteph/YACP"
    assert parse_repo("https://github.com/a/b/tree/main") == "a/b"
    assert parse_repo("https://evil.example/a/b") is None and parse_repo("a/b; rm -rf") is None
    for name, folder in find_firmwares(load_settings().get("extra_folders", [])).items():
        envs = envs_for(folder)
        built = [m for m, env in envs.items() if os.path.isfile(program(folder, env))]
        print(f"{name}: models {', '.join(envs)}; built for {', '.join(built) or 'nothing yet'}")
    for frame in MODELS.values():
        assert os.path.isfile(os.path.join(FRAMES, frame + ".png")), frame + " frame missing"
        assert os.path.isfile(os.path.join(FRAMES, frame + ".keys")), frame + " key map missing"
    app = Launcher()
    GitHubDialog(app, lambda f: None).update()
    app.update()
    app.destroy()
    print("windows build: ok")


def shot(path):
    """Open the launcher and the GitHub window side by side, save a picture of just them, close."""
    app = Launcher()
    app.geometry("+40+40")
    dlg = GitHubDialog(app, lambda f: None)
    for w in (app, dlg):
        w.attributes("-topmost", True)

    def grab():
        app.update()
        dlg.geometry(f"+{app.winfo_rootx() + app.winfo_width()}+{app.winfo_rooty()}")
        dlg.update()
        x0, y0 = app.winfo_rootx(), app.winfo_rooty()
        x1 = dlg.winfo_rootx() + dlg.winfo_width()
        y1 = max(app.winfo_rooty() + app.winfo_height(), dlg.winfo_rooty() + dlg.winfo_height())
        ps = ("Add-Type -AssemblyName System.Drawing; "
              f"$b = New-Object Drawing.Bitmap {x1 - x0},{y1 - y0}; $g = [Drawing.Graphics]::FromImage($b); "
              f"$g.CopyFromScreen({x0},{y0},0,0,$b.Size); $b.Save('{path}'); $g.Dispose(); $b.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW)
        app.destroy()

    dlg.list.selection_set(0)
    dlg.pick_catalogue()
    app.after(4000, grab)  # time for the version list to arrive from GitHub
    app.mainloop()


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    elif "--shot" in sys.argv:
        shot(os.path.abspath(sys.argv[sys.argv.index("--shot") + 1]))
    else:
        Launcher().mainloop()
