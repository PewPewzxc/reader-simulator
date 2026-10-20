"""Newest version of each catalogue firmware: its newest release, or the default branch if it has none.
python -I tools/latest_refs.py [status ...]      (default statuses: ready untested)
Prints one tab-separated line per firmware: repo, ref. Uses GITHUB_TOKEN when set (60 calls an hour without)."""
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def github(url):
    headers = {"User-Agent": "reader-simulator", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.load(r)


def newest(repo):
    tags = [r["tag_name"] for r in github(f"https://api.github.com/repos/{repo}/releases?per_page=5") if not r.get("draft")]
    if tags:
        return tags[0]
    # no release: the default branch, read from git itself (no API call)
    out = subprocess.run(["git", "ls-remote", "--symref", f"https://github.com/{repo}.git", "HEAD"],
                         capture_output=True, text=True).stdout
    return out.split("refs/heads/", 1)[1].split()[0]


def main(statuses):
    for fw in json.load(open(os.path.join(HERE, "firmwares.json"), encoding="utf-8"))["firmwares"]:
        if fw["repo"] and fw["status"] in statuses:
            try:
                ref = newest(fw["repo"])
                # tag names come from other people's repos and end up in commands and file names
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+/-]{0,99}", ref):
                    raise ValueError(f"unusual ref name {ref!r}, skipped")
                print(f"{fw['repo']}\t{ref}", flush=True)
            except Exception as e:  # one unreachable repo must not stop the list
                print(f"latest_refs: {fw['repo']}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ready", "untested"])
