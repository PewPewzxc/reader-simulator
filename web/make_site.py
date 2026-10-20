"""Assemble the web site from the finished builds (build/<id>/sim.js + sim.wasm + build.json).

  python -I make_site.py [release tag]       (default tag: web-builds-<today>)

Writes into ../site/:
  web/site/                  small files for git (repo folder web/site/): page, frames, builds.json, licences
  release-assets/<id>.js|.wasm   big files, uploaded as assets of the GitHub release <tag>
  preview/                   the whole site as Pages will serve it (for local tests; not for git)
Refuses files that contain a local path or user name, and checks the size limits.
"""
import datetime
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.normpath(os.path.join(HERE, "..", "site"))
SMALL = os.path.join(SITE, "web", "site")
ASSETS = os.path.join(SITE, "release-assets")
PREVIEW = os.path.join(SITE, "preview")
# Words that must never end up in published files: this PC's user name and folder, plus RSIM_PRIVATE_WORDS
# (space separated). Read from the environment so the list itself publishes nothing.
FORBIDDEN = [w.lower().encode() for w in [os.environ.get("USERNAME", ""), *os.environ.get("RSIM_PRIVATE_WORDS", "").split()]
             if len(w) >= 3] + [b"c:\\users", b"c:/users"]  # checked lower-case


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def licence_name(text):
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    for key, name in (("MIT", "MIT"), ("GNU GENERAL PUBLIC LICENSE", "GPL"), ("Apache", "Apache-2.0"), ("BSD", "BSD")):
        if key.lower() in first.lower():
            return name
    return "see LICENSE"


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "web-builds-" + datetime.date.today().isoformat()
    shutil.rmtree(ASSETS, ignore_errors=True)
    shutil.rmtree(os.path.join(SMALL, "builds"), ignore_errors=True)
    os.makedirs(ASSETS)
    index = json.load(open(os.path.join(HERE, "..", "release-staging", "index.local.json"), encoding="utf-8"))
    extra = json.load(open(os.path.join(HERE, "extra_builds.json"), encoding="utf-8"))  # web-only builds
    order = [b["id"] for b in index["builds"]] + [b["id"] for b in extra["builds"]]
    out = []
    for build_id in order:
        d = os.path.join(HERE, "build", build_id)
        if not all(os.path.isfile(os.path.join(d, f)) for f in ("build.json", "sim.js", "sim.wasm")):
            print("skipped (not built):", build_id)
            continue
        meta = json.load(open(os.path.join(d, "build.json"), encoding="utf-8"))
        fw = os.path.join(HERE, "fw")
        src = next(os.path.join(fw, x) for x in os.listdir(fw)
                   if open(os.path.join(fw, x, ".rsim-name"), encoding="utf-8").read().strip() == meta["repo"] + "@" + meta["ref"])
        lic = open(os.path.join(src, "LICENSE"), encoding="utf-8", errors="replace").read()
        small = os.path.join(SMALL, "builds", build_id)
        os.makedirs(small)
        open(os.path.join(small, "LICENSE-firmware.txt"), "w", encoding="utf-8", newline="\n").write(lic)
        files = []
        for name in ("sim.js", "sim.wasm"):
            p = os.path.join(d, name)
            data = open(p, "rb").read().lower()
            bad = [w.decode() for w in FORBIDDEN if w in data]
            if bad:
                sys.exit("REFUSED %s/%s: contains %s" % (build_id, name, bad))
            asset = build_id + os.path.splitext(name)[1]
            shutil.copy(p, os.path.join(ASSETS, asset))
            files.append({"name": name, "asset": asset, "size": os.path.getsize(p), "sha256": sha256(p)})
        meta.pop("env", None)
        meta.update(licence=licence_name(lic), files=files)
        out.append(meta)
    builds = {"schema": 1, "release": tag, "repo": "PewPewzxc/reader-simulator",
              "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "builds": out}
    json.dump(builds, open(os.path.join(SMALL, "builds.json"), "w", encoding="utf-8", newline="\n"), indent=1)

    # the site exactly as Pages will serve it
    shutil.rmtree(PREVIEW, ignore_errors=True)
    shutil.copytree(SMALL, PREVIEW)
    for b in out:
        for f in b["files"]:
            shutil.copy(os.path.join(ASSETS, f["asset"]), os.path.join(PREVIEW, "builds", b["id"], f["name"]))

    total, biggest = 0, ("", 0)
    for root, _, names in os.walk(PREVIEW):
        for n in names:
            p = os.path.join(root, n)
            size = os.path.getsize(p)
            total += size
            biggest = max(biggest, (n, size), key=lambda x: x[1])
            if any(w in open(p, "rb").read().lower() for w in FORBIDDEN):
                sys.exit("REFUSED: %s contains a local path or user name" % p)
    assert biggest[1] < 100e6 and total < 1e9, (biggest, total)
    small_total = sum(os.path.getsize(os.path.join(r, n)) for r, _, ns in os.walk(SMALL) for n in ns)
    print("%d builds, release %s; site %.0f MB (git part %.2f MB), biggest file %s %.1f MB" %
          (len(out), tag, total / 1e6, small_total / 1e6, biggest[0], biggest[1] / 1e6))


if __name__ == "__main__":
    main()
