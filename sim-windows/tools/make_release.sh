#!/bin/bash
# Package the simulator builds that passed into release zips and write the download feed.
#   tools/make_release.sh [results.tsv] [out dir]     package every passing build, then write the feed
#   tools/make_release.sh --index-only [out dir]       only write the feed from the zips already in out dir (CI)
# results.tsv: lines from try_all.sh; for each (repo, ref, model) the LAST line counts, and only an OK line is packaged.
# out dir (default dev/rsim/release-staging) gets builds/<id>.zip, index.json (GitHub release URLs, with
# OWNER/REPO placeholders unless RSIM_REPO=owner/name is set) and index.local.json (file: URLs, for local tests).
# Release tag: RSIM_TAG, default builds-<today, UTC>.
O="$(cd "$(dirname "$0")/.." && pwd)"
PY="$HOME/.platformio/penv/Scripts/python.exe"; [ -x "$PY" ] || PY=python
if [ "$1" = "--index-only" ]; then results=""; out="${2:-$O/../rsim/release-staging}"
else results="${1:-$O/logs/results.tsv}"; out="${2:-$O/../rsim/release-staging}"; fi
mkdir -p "$out/builds"
exec "$PY" -I - "$O" "$results" "$(cd "$out" && pwd -W 2>/dev/null || pwd)" <<'EOF'
import datetime, hashlib, json, os, re, subprocess, sys, zipfile
O, results, out = sys.argv[1:4]
sys.path.insert(0, O)
FILES = ["program.exe", "SDL2.dll", "libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"]
builds = os.path.join(out, "builds")
names = {f["repo"]: f["name"] for f in json.load(open(os.path.join(O, "firmwares.json"), encoding="utf-8"))["firmwares"]}

def make_id(repo, ref, model):
    s = f"{repo}-{ref}-{model}".lower()
    s = re.sub(r"[/@ ]", "-", s)
    return re.sub(r"[^a-z0-9._-]", "-", s)  # also '+' etc.: release asset names must stay plain in a URL

def version_of(folder, ref):
    try:
        for line in open(os.path.join(folder, "platformio.ini"), encoding="utf-8"):
            m = re.match(r"\s*version\s*=\s*(\S+)", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return ref

def licence(folder):
    for n in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"):
        if os.path.isfile(os.path.join(folder, n)):
            return os.path.join(folder, n)

def private_words():
    """This PC's user name etc.: none may be inside a published build (paths from __FILE__, debug info).
    Not written here (this script is published): the Windows user name, the part of git's e-mail before
    the @ (git's user name is the public GitHub name, which firmwares rightly contain), RSIM_PRIVATE_WORDS
    (comma-separated)."""
    # On GitHub's machines the account ("runner", "runneradmin") is public, and "runner" is in firmware code (LuaRunner).
    words = set() if os.environ.get("GITHUB_ACTIONS") == "true" else \
        {os.environ.get("USERNAME", ""), os.path.basename(os.environ.get("USERPROFILE", "") or os.path.expanduser("~"))}
    email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
    words.add(email.split("@")[0])
    words.update(os.environ.get("RSIM_PRIVATE_WORDS", "").split(","))
    return sorted({w.strip().lower().encode() for w in words if len(w.strip()) >= 4})

PRIVATE = private_words()

def private_hits(data):
    low = data.lower()
    return [w.decode() for w in PRIVATE if w in low]

def package(repo, ref, env, line):
    import launcher  # here, not at the top: --index-only runs on Linux, where tkinter may be missing
    folder = launcher.download(repo, ref)
    model = next(m for m, e in launcher.envs_for(folder).items() if e == env)
    used = re.search(r"OK \((\d+) frame\)", line)
    bid = make_id(repo, ref, model)
    lic = licence(folder)
    if not lic:
        return print(f"make_release: {bid}: no LICENSE file in the firmware, not packaged")
    bdir = os.path.join(folder, ".rsim-out", env)  # kept by try_firmware.sh right after the build
    missing = [f for f in FILES if not os.path.isfile(os.path.join(bdir, f))]
    if missing:
        return print(f"make_release: {bid}: {missing[0]} missing in {bdir}, not packaged")
    leaks = {f: private_hits(open(os.path.join(bdir, f), "rb").read()) for f in FILES}
    if any(leaks.values()):
        return print(f"make_release: {bid}: {next(f for f in leaks if leaks[f])} contains this PC's user name, not packaged")
    commit = subprocess.run(["git", "-C", folder, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    info = {"id": bid, "name": names.get(repo, repo), "repo": repo, "ref": ref, "version": version_of(folder, ref),
            "model": model, "env": env, "frame": launcher.MODELS[model] if used and int(used.group(1)) else None,
            "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_commit": commit}
    path = os.path.join(builds, bid + ".zip")
    with zipfile.ZipFile(path + ".part", "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(os.path.join(bdir, f), f)
        z.write(lic, "LICENSE-firmware.txt")
        z.writestr("build.json", json.dumps(info, indent=1) + "\n")
    os.replace(path + ".part", path)
    print(f"make_release: {bid}.zip")

if results:
    last = {}
    for row in open(results, encoding="utf-8"):
        p = row.rstrip("\n").split("\t")
        if len(p) >= 5 and p[2] != "-":
            last[(p[0], p[1], p[2])] = p  # per version: several versions of one firmware can be in one results.tsv
    for f in os.listdir(builds):  # only what passed this time
        if f.endswith(".zip"):
            os.remove(os.path.join(builds, f))
    for repo, ref, env, status, line in (p[:5] for p in last.values()):
        if status == "OK":
            package(repo, ref, env, line)

tag = os.environ.get("RSIM_TAG") or "builds-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
gh = os.environ.get("RSIM_REPO", "OWNER/REPO")
entries = []
for f in sorted(os.listdir(builds)):
    if not f.endswith(".zip"):
        continue
    path = os.path.join(builds, f)
    with zipfile.ZipFile(path) as z:
        info = json.loads(z.read("build.json"))
        assert sorted(z.namelist()) == sorted(FILES + ["LICENSE-firmware.txt", "build.json"]), f
    data = open(path, "rb").read()
    with zipfile.ZipFile(path) as z:
        leaks = [n for n in FILES if private_hits(z.read(n))]
    if leaks:  # also zips packed earlier: never into a feed
        print(f"make_release: {f}: {leaks[0]} contains this PC's user name, removed")
        os.remove(path)
        continue
    entries.append({k: info[k] for k in ("id", "name", "repo", "ref", "version", "model", "frame")} |
                   {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "file": f})
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
for name, url in (("index.json", lambda e: f"https://github.com/{gh}/releases/download/{tag}/{e['file']}"),
                  ("index.local.json", lambda e: "file:///" + os.path.join(builds, e["file"]).replace("\\", "/").lstrip("/"))):
    feed = {"schema": 1, "generated": now,
            "builds": [{k: v for k, v in e.items() if k != "file"} | {"url": url(e)} for e in entries]}
    with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(feed, fh, indent=1)
        fh.write("\n")
print(f"make_release: {len(entries)} builds in {os.path.join(out, 'index.json')} and index.local.json (tag {tag})")
EOF
