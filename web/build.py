"""Build the reader simulator for the browser (WebAssembly) with Emscripten.

  python -I build.py [link]     (emsdk in ../tools/emsdk; source copy in work/; page ready in build/out/)

Reads work/compile_commands.json (made by `pio run -e x4-pro-simulator -t compiledb`
with bin/ on PATH, so sdl2-config gives placeholder flags), recompiles every file
with emcc/em++ and links build/out/index.js + .wasm. Fixes live in compat/.
shortcut: a .o is rebuilt only when its source is newer; after header changes delete build/obj.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
OBJ = os.path.join(HERE, "build", "obj")
OUT = os.path.join(HERE, "build", "out")
EMDIR = os.path.join(HERE, "..", "tools", "emsdk", "upstream", "emscripten")
# The firmware folder the compile database was generated in; its paths are rewritten to work/.
ORIG_ROOT = os.environ.get("RSIM_FIRMWARE_SRC", "")
if not ORIG_ROOT:
    sys.exit("Set RSIM_FIRMWARE_SRC to the firmware source folder the compile database was made from.")
os.environ["EM_CONFIG"] = os.path.join(HERE, "..", "tools", "emsdk", ".emscripten")

COMMON = ["-DtskNO_AFFINITY=0x7FFFFFFF", "-DportNUM_PROCESSORS=1", "-sUSE_SDL=2", "-pthread", "-O2", "-w", "-I" + os.path.join(HERE, "compat"),
          "-include", os.path.join(HERE, "compat", "web_prelude.h")]
LINK = ["-Wl,--allow-multiple-definition",  # uzlib checksums: simulator stubs = same code
        "-sUSE_SDL=2", "-pthread", "-O2", "-sASYNCIFY", "-sASYNCIFY_STACK_SIZE=131072",
        "-sALLOW_MEMORY_GROWTH", "-sINITIAL_MEMORY=64MB", "-sSTACK_SIZE=1MB", "-sDEFAULT_PTHREAD_STACK_SIZE=1MB",
        "-sPTHREAD_POOL_SIZE=8", "-sEXIT_RUNTIME=0", "-sFORCE_FILESYSTEM", "-lidbfs.js",
        "-sEXPORTED_RUNTIME_METHODS=FS,ENV,IDBFS,callMain", "-sENVIRONMENT=web,worker"]


def jobs():
    db = json.load(open(os.path.join(WORK, "compile_commands.json"), encoding="utf-8"))
    seen = set()
    for i, e in enumerate(db):
        src = e["file"].replace(ORIG_ROOT, WORK)
        if src.endswith(".S") or src in seen:  # ESP32 SIMD assembly: not used off the chip
            continue
        seen.add(src)
        cmd = e["command"].replace(ORIG_ROOT, WORK)
        cmd = cmd.replace('\\"', "\0").replace("\\", "/").replace("\0", '\\"')
        argv = shlex.split(cmd)
        cc = os.path.join(EMDIR, "em++.exe" if "g++" in argv[0] else "emcc.exe")
        args, skip = [], False
        for a in argv[1:-1]:  # last word is the source file
            if skip:
                skip = False
            elif a == "-o":
                skip = True
            elif "__EMSDL" not in a and a != "-c":
                args.append(a)
        obj = os.path.join(OBJ, "%03d_%s.o" % (i, os.path.basename(src)))
        yield src, [cc, "-c", src, "-o", obj] + args + COMMON, obj


def compile_one(job):
    src, cmd, obj = job
    full = src if os.path.isabs(src) else os.path.join(WORK, src)
    if os.path.exists(obj) and os.path.getmtime(obj) > os.path.getmtime(full):
        return obj, ""
    r = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (obj if r.returncode == 0 else None), "" if r.returncode == 0 else "== %s\n%s\n" % (src, r.stderr[-4000:])


def main():
    os.makedirs(OBJ, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    all_jobs = list(jobs())
    with ThreadPoolExecutor(os.cpu_count()) as pool:
        results = list(pool.map(compile_one, all_jobs))
    errors = "".join(e for _, e in results)
    open(os.path.join(HERE, "logs", "compile-errors.log"), "w", encoding="utf-8").write(errors)
    bad = sum(1 for o, _ in results if o is None)
    print("compiled %d files, %d failed (logs/compile-errors.log)" % (len(results), bad))
    if bad or "link" not in sys.argv:
        return 1 if bad else 0
    objs = [o for o, _ in results]
    names = ["--profiling-funcs"] if os.environ.get("NAMES") else []  # NAMES=1: readable stacks (probe.mjs)
    cmd = [os.path.join(EMDIR, "em++.exe")] + objs + LINK + names + ["-o", os.path.join(OUT, "sim.js")]
    r = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True, encoding="utf-8", errors="replace")
    open(os.path.join(HERE, "logs", "link.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    print("link", "ok" if r.returncode == 0 else "FAILED (logs/link.log)")
    # the page around the simulator, and the frame (our own artwork, dev/device-frames)
    os.makedirs(os.path.join(OUT, "frame"), exist_ok=True)
    for name in ("index.html", "coi-sw.js"):
        shutil.copy(os.path.join(HERE, "page", name), OUT)
    for name in ("x4-pro.png", "x4-pro.keys"):
        shutil.copy(os.path.join(HERE, "..", "..", "device-frames", "frames", name), os.path.join(OUT, "frame"))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
