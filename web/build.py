"""Build reader simulators for the browser (WebAssembly) with Emscripten.

  python -I build.py prep <id>...   copy each firmware source to fw/<folder>, patch its simulator library,
                                    write compile_commands.<env>.json (PlatformIO, one at a time)
  python -I build.py build <id>     compile + link build/<id>/sim.js + sim.wasm, then check them for local paths

<id> is a build from ../release-staging/index.local.json (it passed on Windows). Its source is the download in
%USERPROFILE%/rsim/fw/<folder> whose .rsim-name is "<repo>@<ref>"; the env comes from that build's zip
(build.json). RSIM_FIRMWARE_SRC / RSIM_ENV / RSIM_MODEL override them. Needs emsdk in ../tools/emsdk
(RSIM_EMSDK: another folder). On Linux (GitHub Actions) ci_build.py drives prep() and build() instead.
The owner's unreleased working copies (Crossink/github/*) are refused.
shortcut: a .o is rebuilt only when its source is newer; after header or flag changes delete build/<id>/obj.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
RSIM = os.path.dirname(HERE)
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""
EMSDK = os.environ.get("RSIM_EMSDK") or os.path.join(RSIM, "tools", "emsdk")
EMDIR = os.path.join(EMSDK, "upstream", "emscripten")
FW_DOWNLOADS = os.path.join(os.path.expanduser("~"), "rsim", "fw")
STAGING = os.path.join(RSIM, "release-staging")
# sim-windows sits next to web/ in the repo, and next to the rsim folder on the PC this was first built on
SIM_WINDOWS = next(p for p in (os.path.join(RSIM, "sim-windows"), os.path.join(RSIM, "..", "sim-windows"))
                   if os.path.isdir(p))
# PlatformIO's own Python environment (Scripts on Windows, bin elsewhere)
PIO = os.path.join(os.path.expanduser("~"), ".platformio", "penv", "Scripts" if WINDOWS else "bin")
os.environ["EM_CONFIG"] = os.path.join(EMSDK, ".emscripten")
HOME = os.path.expanduser("~")
JOBS = int(os.environ.get("RSIM_JOBS", os.cpu_count()))

# No local path (user name) may end up in the published files: map every spelling of the home folder.
PREFIX_MAPS = []
for home in {HOME, HOME.replace("\\", "/"), HOME.lower(), HOME.replace("\\", "/").lower()}:
    PREFIX_MAPS += ["-ffile-prefix-map=%s=/src" % home, "-fmacro-prefix-map=%s=/src" % home]
COMMON = ["-DtskNO_AFFINITY=0x7FFFFFFF", "-DportNUM_PROCESSORS=1", "-sUSE_SDL=2", "-pthread", "-O2", "-w",
          "-I" + os.path.join(HERE, "compat"), "-include", os.path.join(HERE, "compat", "web_prelude.h")] + PREFIX_MAPS
LINK = ["-Wl,--allow-multiple-definition",  # uzlib checksums: simulator stubs = same code
        "-sUSE_SDL=2", "-pthread", "-O2", "-sASYNCIFY", "-sASYNCIFY_STACK_SIZE=131072",
        "-sALLOW_MEMORY_GROWTH", "-sINITIAL_MEMORY=64MB",
        "-sMAXIMUM_MEMORY=512MB",  # shared memory is reserved up front: iPad/iPhone Safari refuse the default 2 GB
        "-sSTACK_SIZE=1MB", "-sDEFAULT_PTHREAD_STACK_SIZE=1MB",
        "-sPTHREAD_POOL_SIZE=8", "-sEXIT_RUNTIME=0", "-sFORCE_FILESYSTEM", "-lidbfs.js",
        "-sEXPORTED_RUNTIME_METHODS=FS,ENV,IDBFS,callMain", "-sENVIRONMENT=web,worker"] + PREFIX_MAPS
# Words that must never end up in published files: this PC's user name and folder, plus RSIM_PRIVATE_WORDS
# (space separated). Read from the environment so the list itself publishes nothing.
FORBIDDEN = [w.lower().encode() for w in [os.environ.get("USERNAME", ""), *os.environ.get("RSIM_PRIVATE_WORDS", "").split()]
             if len(w) >= 3] + [b"c:\\users", b"c:/users"]  # checked lower-case


def build_info(build_id):
    """index.local.json entry + env + source folders for one build."""
    index = json.load(open(os.path.join(STAGING, "index.local.json"), encoding="utf-8"))
    extra = json.load(open(os.path.join(HERE, "extra_builds.json"), encoding="utf-8"))  # web-only builds
    b = next((x for x in index["builds"] if x["id"] == build_id), None)
    if b:
        with zipfile.ZipFile(os.path.join(STAGING, "builds", build_id + ".zip")) as z:
            meta = json.loads(z.read("build.json"))
    else:
        b = dict(next(x for x in extra["builds"] if x["id"] == build_id))
        meta = {"env": b.pop("env"), "source_commit": b.pop("source_commit")}
    name = "%s@%s" % (b["repo"], b["ref"])
    orig = os.environ.get("RSIM_FIRMWARE_SRC")
    if not orig:
        for d in os.listdir(FW_DOWNLOADS):
            p = os.path.join(FW_DOWNLOADS, d, ".rsim-name")
            if os.path.isfile(p) and open(p, encoding="utf-8").read().strip() == name:
                orig = os.path.join(FW_DOWNLOADS, d)
    if not orig:
        sys.exit("no download for %s in %s" % (name, FW_DOWNLOADS))
    owner_repos = os.path.normpath(os.path.join(RSIM, "..", "..", "github")).lower()  # Crossink/github
    if os.path.normpath(os.path.abspath(orig)).lower().startswith(owner_repos):
        sys.exit("refused: %s is one of the owner's working copies" % orig)
    b.update(env=os.environ.get("RSIM_ENV", meta["env"]), model=os.environ.get("RSIM_MODEL", b["model"]),
             orig=orig, work=os.path.join(HERE, "fw", os.path.basename(orig)), source_commit=meta.get("source_commit"))
    return b


def prep(b):
    work, env = b["work"], b["env"]
    if not os.path.isdir(work):
        ignore = shutil.ignore_patterns(".git", ".rsim-out")
        shutil.copytree(b["orig"], work, ignore=lambda d, names: ignore(d, names) | (
            {"build"} if os.path.basename(d) == ".pio" else set()), symlinks=True)
    py = os.path.join(EMSDK, "python", "3.13.3_64bit", "python.exe") if WINDOWS else sys.executable
    libdeps = os.path.join(work, ".pio", "libdeps", env)
    envvars = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                   PATH=os.path.join(HERE, "bin") + os.pathsep + os.environ["PATH"])
    log = open(os.path.join(HERE, "logs", "%s-compiledb.log" % b["id"]), "w", encoding="utf-8")
    # PlatformIO reinstalls the (pinned) libraries in a moved project; patch only after that.
    subprocess.run([os.path.join(PIO, "pio" + EXE), "pkg", "install", "-e", env], cwd=work, env=envvars,
                   stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([py, "-I", os.path.join(SIM_WINDOWS, "patch_libdeps.py"), libdeps], check=True)
    subprocess.run([py, "-I", os.path.join(HERE, "patch_work.py"), libdeps], check=True)
    subprocess.run([os.path.join(PIO, "pio" + EXE), "run", "-e", env, "-t", "compiledb"], cwd=work, env=envvars,
                   stdout=log, stderr=subprocess.STDOUT, check=True)
    os.replace(os.path.join(work, "compile_commands.json"), os.path.join(work, "compile_commands.%s.json" % env))


def jobs(b, obj_dir):
    work = b["work"]
    db = json.load(open(os.path.join(work, "compile_commands.%s.json" % b["env"]), encoding="utf-8"))
    seen = set()
    for i, e in enumerate(db):
        src = e["file"].replace(b["orig"], work)
        if src.endswith(".S") or src in seen:  # ESP32 SIMD assembly: not used off the chip
            continue
        seen.add(src)
        cmd = e["command"].replace(b["orig"], work)
        cmd = cmd.replace('\\"', "\0").replace("\\", "/").replace("\0", '\\"')
        argv = shlex.split(cmd)
        cc = os.path.join(EMDIR, ("em++" if "g++" in argv[0] or "c++" in argv[0] else "emcc") + EXE)
        args, skip = [], False
        for a in argv[1:-1]:  # last word is the source file
            if skip:
                skip = False
            elif a == "-o":
                skip = True
            elif "__EMSDL" not in a and a != "-c":
                args.append(a)
        if "rsim_crosspoint_prelude.h" in " ".join(args):  # CrossPoint adapter's MinGW-only prelude
            i_ = args.index(next(a for a in args if "rsim_crosspoint_prelude.h" in a))
            del args[i_ - 1:i_ + 1]  # "-include <path>"
        obj = os.path.join(obj_dir, "%03d_%s.o" % (i, os.path.basename(src)))
        yield src, [cc, "-c", src, "-o", obj] + args + COMMON, obj


def compile_one(work, job):
    src, cmd, obj = job
    full = src if os.path.isabs(src) else os.path.join(work, src)
    if os.path.exists(obj) and os.path.getmtime(obj) > os.path.getmtime(full):
        return obj, ""
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (obj if r.returncode == 0 else None), "" if r.returncode == 0 else "== %s\n%s\n" % (src, r.stderr[-4000:])


def leaks(path):
    data = open(path, "rb").read().lower()
    return [w.decode() for w in FORBIDDEN if w in data]


def build(b):
    out = os.path.join(HERE, "build", b["id"])
    obj_dir = os.path.join(out, "obj")
    os.makedirs(obj_dir, exist_ok=True)
    with ThreadPoolExecutor(JOBS) as pool:
        results = list(pool.map(lambda j: compile_one(b["work"], j), jobs(b, obj_dir)))
    open(os.path.join(HERE, "logs", "%s-compile.log" % b["id"]), "w", encoding="utf-8").write(
        "".join(e for _, e in results))
    bad = sum(1 for o, _ in results if o is None)
    print("%s: compiled %d files, %d failed" % (b["id"], len(results), bad))
    if bad:
        return 1
    names = ["--profiling-funcs"] if os.environ.get("NAMES") else []  # NAMES=1: readable stacks (probe.mjs)
    rsp = os.path.join(out, "objects.rsp")  # 300+ object paths are too long for one Windows command line
    open(rsp, "w", encoding="utf-8").write("\n".join('"%s"' % o.replace("\\", "/") for o, _ in results))
    cmd = [os.path.join(EMDIR, "em++" + EXE), "@" + rsp] + LINK + names + ["-o", os.path.join(out, "sim.js")]
    r = subprocess.run(cmd, cwd=b["work"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    open(os.path.join(HERE, "logs", "%s-link.log" % b["id"]), "w", encoding="utf-8").write(r.stdout + r.stderr)
    if r.returncode:
        print("%s: link FAILED" % b["id"])
        return 1
    for f in ("sim.js", "sim.wasm"):
        found = leaks(os.path.join(out, f))
        if found:
            os.remove(os.path.join(out, f))
            print("%s: REFUSED, %s contains %s" % (b["id"], f, found))
            return 1
    json.dump({k: b[k] for k in ("id", "name", "repo", "ref", "version", "model", "frame", "env", "source_commit")},
              open(os.path.join(out, "build.json"), "w", encoding="utf-8"), indent=1)
    print("%s: ok, sim.wasm %.1f MB, no local paths" % (b["id"], os.path.getsize(os.path.join(out, "sim.wasm")) / 1e6))
    return 0


if __name__ == "__main__":
    what, ids = sys.argv[1], sys.argv[2:]
    if what == "prep":
        for i in ids:
            prep(build_info(i))
            print("prepared", i)
    else:
        sys.exit(max(build(build_info(i)) for i in ids))
