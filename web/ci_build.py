"""Browser builds of one firmware version on Linux (GitHub Actions): download, simulator setup, every model.
  python -I ci_build.py <owner/repo> <ref> <out dir>
For each model the firmware has: prep() + build() from build.py, then out/<id>/ gets sim.js, sim.wasm,
build.json and LICENSE-firmware.txt. Prints one line per model: "<id> OK" or "<id> FAILED <reason>".
Needs PlatformIO (~/.platformio/penv) and emsdk (RSIM_EMSDK). The firmware's own files are never changed:
adapter.py and pin_simlib.py only write platformio.local.ini, as on Windows."""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402

SIM = build.SIM_WINDOWS
SRC = os.path.join(HERE, "ci", "src")
MODELS = {"X4 Pro": "x4-pro", "X4 Classic": "x4-classic", "X3": "x3"}  # as launcher.py (Windows only)
ENV_NAMES = {"X4 Pro": ["x4-pro-simulator"], "X4 Classic": ["x4-classic-simulator", "simulator"],
             "X3": ["simulator-X3", "simulator_x3"]}
LICENCES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")


def make_id(repo, ref, model):  # same ids as the Windows builds (tools/make_release.sh)
    s = re.sub(r"[/@ ]", "-", f"{repo}-{ref}-{model}".lower())
    return re.sub(r"[^a-z0-9._-]", "-", s)


def envs_for(folder):  # launcher.envs_for
    ini = ""
    for name in ("platformio.ini", "platformio.local.ini"):
        try:
            ini += open(os.path.join(folder, name), encoding="utf-8").read()
        except OSError:
            pass
    have = set(re.findall(r"^\[env:([^\]]+)\]", ini, re.M))
    return {m: next(e for e in names if e in have) for m, names in ENV_NAMES.items() if have & set(names)}


def version_of(folder, ref):  # as make_release.sh
    try:
        for line in open(os.path.join(folder, "platformio.ini"), encoding="utf-8"):
            m = re.match(r"\s*version\s*=\s*(\S+)", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return ref


def run(*cmd, **kw):
    return subprocess.run(list(cmd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw).returncode


def download(repo, ref):
    """Shallow clone with submodules; without them when one cannot be fetched (as tools/fetch.py)."""
    dest = os.path.join(SRC, make_id(repo, ref, "src"))
    if os.path.isfile(os.path.join(dest, "platformio.ini")):
        return dest
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(SRC, exist_ok=True)
    url = f"https://github.com/{repo}.git"
    if run("git", "clone", "-q", "--depth", "1", "--branch", ref, "--recurse-submodules", "--shallow-submodules", url, dest):
        shutil.rmtree(dest, ignore_errors=True)
        if run("git", "clone", "-q", "--depth", "1", "--branch", ref, url, dest):
            sys.exit(f"ci_build: {repo} {ref}: download failed")
        if run("git", "-C", dest, "submodule", "update", "--init", "--recursive", "--depth", "1"):
            print(f"ci_build: {repo} {ref}: a submodule could not be downloaded, using the source without it")
    open(os.path.join(dest, ".rsim-name"), "w", encoding="utf-8", newline="\n").write(f"{repo}@{ref}\n")
    return dest


def setup(folder, envs, newest=False):
    """Simulator setup: adapter.py for CrossPoint-family firmwares without one, then the dated library."""
    adapter = [sys.executable, "-I", os.path.join(SIM, "adapter.py"), folder] + (["--newest"] if newest else [])
    subprocess.run(adapter, check=False)
    if newest:
        open(os.path.join(folder, "platformio.local.ini.dated"), "w").close()  # pin_simlib.py: use the newest
        return
    for env in envs.values():
        subprocess.run([sys.executable, "-I", os.path.join(SIM, "pin_simlib.py"), folder, env], check=False)


def errors(bid, limit=25):
    """The distinct error lines of a failed attempt, for the job log (CI artifacts may not be at hand)."""
    found = []
    for log in (f"{bid}-compiledb.log", f"{bid}-compile.log", f"{bid}-link.log"):
        p = os.path.join(HERE, "logs", log)
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8", errors="replace"):
                line = line.strip()
                if re.search(r"error:|Error:|undefined symbol|Error \d", line) and line not in found:
                    found.append(line)
    return found[:limit]


def one(info):
    """prep + build; on failure prints the attempt's errors and returns False."""
    try:
        build.prep(info)
        ok = build.build(info) == 0
    except subprocess.CalledProcessError:
        ok = False
    if not ok:
        for line in errors(info["id"]):
            print(f"  {info['id']}: {line[:300]}")
    return ok


def main(repo, ref, out):
    names = {f["repo"]: f["name"] for f in json.load(open(os.path.join(SIM, "firmwares.json"), encoding="utf-8"))["firmwares"]}
    folder = download(repo, ref)
    lic = next((os.path.join(folder, n) for n in LICENCES if os.path.isfile(os.path.join(folder, n))), None)
    setup(folder, envs_for(folder))
    envs = envs_for(folder)  # adapter.py may have added simulator environments
    if not envs:
        return print(f"{make_id(repo, ref, 'x')[:-2]} FAILED no simulator setup")
    commit = subprocess.run(["git", "-C", folder, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
    tried_newest = False
    for model, env in envs.items():
        bid = make_id(repo, ref, model)
        if not lic:
            print(f"{bid} FAILED no LICENSE file in the firmware")
            continue
        info = {"id": bid, "name": names.get(repo, repo), "repo": repo, "ref": ref, "version": version_of(folder, ref),
                "model": model, "frame": MODELS[model], "env": env, "orig": folder, "source_commit": commit,
                "work": os.path.join(HERE, "fw", os.path.basename(folder))}
        ok = one(info)
        local = os.path.join(folder, "platformio.local.ini")
        pinned = os.path.isfile(local) and re.search(r"written by the reader simulator|generated by the reader simulator adapter",
                                                     open(local, encoding="utf-8").read())
        if not ok and pinned and not tried_newest:
            # the library from the firmware's own date is a guess; retry once with the newest (as build.sh)
            print(f"{bid}: failed with the dated simulator library, retrying with the newest one")
            tried_newest = True
            if "adapter" in open(local, encoding="utf-8").read():
                setup(folder, envs, newest=True)
            else:
                os.replace(local, local + ".dated")
            shutil.rmtree(info["work"], ignore_errors=True)  # its libdeps hold the dated library
            shutil.rmtree(os.path.join(HERE, "build", bid), ignore_errors=True)
            ok = one(info)
        if not ok:
            print(f"{bid} FAILED {(errors(bid, 1) or [''])[0][:200]}")
            continue
        dst = os.path.join(out, bid)
        os.makedirs(dst, exist_ok=True)
        for f in ("sim.js", "sim.wasm", "build.json"):
            shutil.copy(os.path.join(HERE, "build", bid, f), os.path.join(dst, f))
        shutil.copy(lic, os.path.join(dst, "LICENSE-firmware.txt"))
        print(f"{bid} OK")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
