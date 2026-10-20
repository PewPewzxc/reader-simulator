"""Versions of each catalogue firmware to offer: its newest releases (newest first), or the default branch if it has none.
python -I tools/latest_refs.py [status ...]      (default statuses: ready untested)
How many releases: the firmware's "versions" in firmwares.json, else RSIM_VERSIONS, else 3. A firmware with "refs"
(branches to follow, e.g. ["dev"]) is built from those instead of its releases.
Prints one tab-separated line per version: repo, ref. Uses GITHUB_TOKEN when set (60 calls an hour without)."""
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_VERSIONS = 3
# tag names come from other people's repos and end up in commands and file names
SAFE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+/-]{0,99}")


def github(url):
    headers = {"User-Agent": "reader-simulator", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.load(r)


def newest(repo, n):
    tags = []
    for r in github(f"https://api.github.com/repos/{repo}/releases?per_page={min(100, n + 5)}"):
        if r.get("draft"):
            continue
        if SAFE_REF.fullmatch(r["tag_name"]):
            tags.append(r["tag_name"])
        else:
            print(f"latest_refs: {repo}: unusual ref name {r['tag_name']!r}, skipped", file=sys.stderr)
    if tags:
        return tags[:n]
    # no release: the default branch, read from git itself (no API call)
    out = subprocess.run(["git", "ls-remote", "--symref", f"https://github.com/{repo}.git", "HEAD"],
                         capture_output=True, text=True).stdout
    branch = out.split("refs/heads/", 1)[1].split()[0]
    if not SAFE_REF.fullmatch(branch):
        raise ValueError(f"unusual ref name {branch!r}")
    return [branch]


def main(statuses):
    default = int(os.environ.get("RSIM_VERSIONS") or DEFAULT_VERSIONS)
    for fw in json.load(open(os.path.join(HERE, "firmwares.json"), encoding="utf-8"))["firmwares"]:
        if fw["repo"] and fw["status"] in statuses:
            try:
                if fw.get("refs"):
                    for ref in fw["refs"]:
                        if SAFE_REF.fullmatch(ref):
                            print(f"{fw['repo']}\t{ref}", flush=True)
                        else:
                            print(f"latest_refs: {fw['repo']}: unusual ref name {ref!r}, skipped", file=sys.stderr)
                    continue
                for ref in newest(fw["repo"], max(1, int(fw.get("versions", default)))):
                    print(f"{fw['repo']}\t{ref}", flush=True)
            except Exception as e:  # one unreachable repo must not stop the list
                print(f"latest_refs: {fw['repo']}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ready", "untested"])
