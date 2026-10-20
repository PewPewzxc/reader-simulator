"""Which firmwares can the simulator run? Reads each repo's platformio.ini from GitHub.
python -I survey.py repos.txt > survey.tsv     (repos.txt: 'name owner/repo' per line)"""
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENVS = {"x4-pro-simulator": "X4 Pro", "x4-classic-simulator": "X4 Classic", "simulator": "X4",
        "simulator-X3": "X3", "simulator_x3": "X3"}


def ini(repo):
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/platformio.ini"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "reader-simulator"}),
                                    timeout=20) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def classify(line):
    name, repo = line.split()
    text = ini(repo)
    if text is None:
        return name, repo, "no platformio.ini (not a PlatformIO firmware)", ""
    envs = sorted({ENVS[e] for e in re.findall(r"^\[env:([^\]]+)\]", text, re.M) if e in ENVS})
    lib = re.search(r"github\.com/([\w-]+/[\w-]*simulator[\w-]*)(#\w+)?", text)
    if envs:
        kind = "has simulator" + (f" ({lib.group(1)}{' pinned' if lib.group(2) else ', not pinned'})" if lib else "")
    elif re.search(r"^platform\s*=\s*espressif32", text, re.M):
        kind = "ESP32 firmware, no simulator setup"
    else:
        kind = "PlatformIO, other"
    return name, repo, kind, "/".join(envs)


if __name__ == "__main__":
    lines = [l for l in open(sys.argv[1]).read().splitlines() if l.strip()]
    with ThreadPoolExecutor(8) as pool:
        for row in pool.map(classify, lines):
            print("\t".join(row))
