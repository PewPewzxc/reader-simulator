"""The web site's build list and files in GitHub Actions (Linux). builds.json lists every build on the page; each
build's files are assets of the GitHub release named in its "release" (so earlier builds stay where they are).
  python -I ci_site.py normalize <builds.json> <out>          give every build its own "release" (older lists
                                                              named one release for all)
  python -I ci_site.py entries <builds dir> <tag> <assets dir> <out json>
                                                              new builds (ci_build.py output) as builds.json entries;
                                                              their files go to <assets dir> as <id>.js/.wasm/.LICENSE-firmware.txt
  python -I ci_site.py samples <out dir>                      ../samples/sd-card + manifest.json (the page copies it
                                                              onto each new SD card)
  python -I ci_site.py preview <builds dir> <out dir>         the page with only these builds, for testing
  python -I ci_site.py fit <builds.json> <MB>                 drop the oldest versions until the site fits in MB
                                                              (GitHub Pages: 1 GB)
  python -I ci_site.py capmem <builds folder>                 cap each sim.js's shared memory at 512 MB (see capmem)"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
SAMPLES = os.path.join(os.path.dirname(HERE), "samples", "sd-card")
FILES = [("sim.js", ".js"), ("sim.wasm", ".wasm"), ("LICENSE-firmware.txt", ".LICENSE-firmware.txt")]
SAMPLES_ALLOWANCE = 20e6  # page, frames and sample card, for fit
ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,98}[a-z0-9])?")  # the app's rule for build ids (Feed.ValidId)
MODELS = {"X4 Pro": "x4-pro", "X4 Classic": "x4-classic", "X3": "x3"}


def sha256(path):  # as make_site.py (which only runs on the PC it was written on)
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def licence_name(text):  # as make_site.py
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    for key, name in (("MIT", "MIT"), ("GNU GENERAL PUBLIC LICENSE", "GPL"), ("Apache", "Apache-2.0"), ("BSD", "BSD")):
        if key.lower() in first.lower():
            return name
    return "see LICENSE"


def write(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1)
        f.write("\n")


def normalize(src, out):
    feed = json.load(open(src, encoding="utf-8"))
    for b in feed["builds"]:
        b.setdefault("release", feed.get("release"))
    write(out, {"schema": 1, "builds": feed["builds"]})


def entries(builds_dir, tag, assets, out):
    os.makedirs(assets, exist_ok=True)
    found = []
    for bid in sorted(os.listdir(builds_dir)):
        d = os.path.join(builds_dir, bid)
        if not os.path.isfile(os.path.join(d, "build.json")):
            continue
        meta = json.load(open(os.path.join(d, "build.json"), encoding="utf-8"))
        # the build jobs run the firmwares' own code: trust nothing from them that ends up in paths or the page
        if not ID_RE.fullmatch(bid) or meta.get("id") != bid or meta.get("model") not in MODELS:
            print(f"ci_site: {bid!r}: not a well-formed build, left out")
            continue
        meta.pop("env", None)
        lic = open(os.path.join(d, "LICENSE-firmware.txt"), encoding="utf-8", errors="replace").read()
        files = []
        for name, ext in FILES:
            p = os.path.join(d, name)
            shutil.copy(p, os.path.join(assets, bid + ext))
            files.append({"name": name, "asset": bid + ext, "size": os.path.getsize(p), "sha256": sha256(p)})
        found.append(meta | {"licence": licence_name(lic), "release": tag, "files": files})
    write(out, {"schema": 1, "builds": found})
    print(f"ci_site: {len(found)} new builds for release {tag}")


def samples(out):
    files = []
    for root, _, names in os.walk(SAMPLES):
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(root, n), SAMPLES).replace(os.sep, "/")
            dst = os.path.join(out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(os.path.join(root, n), dst)
            files.append({"path": rel, "size": os.path.getsize(dst)})
    write(os.path.join(out, "manifest.json"), {"files": sorted(files, key=lambda f: f["path"])})
    print(f"ci_site: {len(files)} sample files")


def preview(builds_dir, out):
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(SITE, out, ignore=lambda d, names: {"builds", "builds.json"} & set(names) if d == SITE else set())
    samples(os.path.join(out, "samples"))
    tmp = os.path.join(out, ".entries.json")
    entries(builds_dir, "local", os.path.join(out, ".assets"), tmp)
    listed = json.load(open(tmp, encoding="utf-8"))["builds"]
    for b in listed:
        dst = os.path.join(out, "builds", b["id"])
        os.makedirs(dst, exist_ok=True)
        for f in b["files"]:
            shutil.copy(os.path.join(builds_dir, b["id"], f["name"]), os.path.join(dst, f["name"]))
    write(os.path.join(out, "builds.json"), {"schema": 1, "builds": listed})
    capmem(os.path.join(out, "builds"))
    shutil.rmtree(os.path.join(out, ".assets"))
    os.remove(tmp)


MEMORY_RE = re.compile(r"new WebAssembly\.Memory\(\{initial:(\d+),maximum:(\d+),shared:(?:true|!0)\}\)")
MAX_PAGES = 8192  # 512 MB in 64 KB pages, as build.py's -sMAXIMUM_MEMORY


def capmem(folder):
    """Builds made before -sMAXIMUM_MEMORY reserve 2 GB of shared memory, which iPad/iPhone Safari (and some
    Android tablets) refuse, so the firmware never starts there. A smaller maximum is valid for the same wasm:
    an imported memory may have a lower maximum than the module declares."""
    for bid in sorted(os.listdir(folder)):
        p = os.path.join(folder, bid, "sim.js")
        if not os.path.isfile(p):
            continue
        js = open(p, encoding="utf-8").read()
        m = MEMORY_RE.search(js)
        if m and int(m.group(2)) > MAX_PAGES and int(m.group(1)) <= MAX_PAGES:
            js = js[:m.start(2)] + str(MAX_PAGES) + js[m.end(2):]
            open(p, "w", encoding="utf-8", newline="").write(js)
            print(f"ci_site: {bid}: shared memory capped at {MAX_PAGES * 64 // 1024} MB")


def fit(path, mb):
    feed = json.load(open(path, encoding="utf-8"))
    size = lambda bs: sum(f["size"] for b in bs for f in b["files"])
    builds = feed["builds"]
    while size(builds) + SAMPLES_ALLOWANCE > mb * 1e6:
        # the oldest version (last in each firmware's newest-first list) of the firmware with the most versions
        versions = {}
        for b in builds:
            versions.setdefault(b["repo"], [])
            if b["ref"] not in versions[b["repo"]]:
                versions[b["repo"]].append(b["ref"])
        repo, refs = max(versions.items(), key=lambda kv: len(kv[1]))
        if len(refs) < 2:
            sys.exit(f"ci_site: the newest versions alone are {size(builds) / 1e6:.0f} MB, over {mb} MB")
        print(f"ci_site: over {mb} MB, leaving out {repo} {refs[-1]}")
        builds = [b for b in builds if not (b["repo"] == repo and b["ref"] == refs[-1])]
    feed["builds"] = builds
    write(path, feed)
    print(f"ci_site: {len(builds)} builds, {size(builds) / 1e6:.0f} MB")


if __name__ == "__main__":
    cmds = {"normalize": (normalize, 2), "entries": (entries, 4), "samples": (samples, 1), "preview": (preview, 2),
            "fit": (lambda p, mb: fit(p, float(mb)), 2), "capmem": (capmem, 1)}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds or len(sys.argv) - 2 != cmds[sys.argv[1]][1]:
        sys.exit(__doc__)
    cmds[sys.argv[1]][0](*sys.argv[2:])
