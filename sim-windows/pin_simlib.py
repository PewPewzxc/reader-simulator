"""Use the simulator library from the firmware's own time.
python -I pin_simlib.py <firmware folder> <env>
Most firmwares name their simulator library without a version, so an older release would
build against today's library and fail. For a downloaded firmware (a git checkout under
firmwares/) this writes platformio.local.ini with the library pinned to its last commit
before the checkout's commit date. It only runs when platformio.ini already loads that
file (extra_configs) and never touches the main config. Prints what it did."""
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LIB_RE = re.compile(r"(https://github\.com/([\w-]+/[\w-]*simulator[\w-]*?))(\.git)?(?=\s|$)")
SHORT_RE = re.compile(r"(https://github\.com/([\w-]+/[\w-]*simulator[\w-]*?)(?:\.git)?)#([0-9a-f]{7,39})(?=\s|$)")


def github(url):
    headers = {"User-Agent": "reader-simulator"}
    if os.environ.get("GITHUB_TOKEN"):  # CI: 1000 calls an hour instead of 60
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:  # follows the redirect of a moved repo
        return json.load(r)


def section_lib_deps(ini, section, depth=0):
    """lib_deps lines of [section] with ${other.lib_deps} expanded, following extends; None if none."""
    m = re.search(r"^\[%s\]\n(.*?)(?=^\[|\Z)" % re.escape(section), ini, re.M | re.S)
    if not m or depth > 5:
        return None
    body = m.group(1)
    deps = re.search(r"^lib_deps\s*=\s*\n((?:[ \t]+.*\n?)+)", body, re.M)
    if not deps:
        ext = re.search(r"^extends\s*=\s*(\S+)", body, re.M)
        return section_lib_deps(ini, ext.group(1), depth + 1) if ext else None
    lines = []
    for line in deps.group(1).splitlines():
        ref = re.match(r"^\s*\$\{([^}]+)\.lib_deps\}\s*$", line)
        lines += (section_lib_deps(ini, ref.group(1), depth + 1) or []) if ref else [line]
    return lines


def env_lib_deps(ini, env):
    return env, section_lib_deps(ini, "env:" + env)


def main(folder, env):
    folder = os.path.abspath(folder)
    if not os.path.isfile(os.path.join(folder, ".rsim-name")):  # written by the launcher's download
        return print("pin_simlib: not a downloaded firmware, left as is")
    if os.path.isfile(os.path.join(folder, "platformio.local.ini.dated")):
        return print("pin_simlib: the dated library failed before (build.sh), using the newest")
    ini = open(os.path.join(folder, "platformio.ini"), encoding="utf-8").read()
    if not re.search(r"^extra_configs\s*=.*platformio\.local\.ini", ini, re.M):
        return print("pin_simlib: this firmware has no platformio.local.ini hook, left as is")
    section, deps = env_lib_deps(ini, env)
    if not deps:
        return print(f"pin_simlib: no lib_deps for {env}, left as is")
    short = next((SHORT_RE.search(l) for l in deps if SHORT_RE.search(l)), None)
    if short:  # pinned to a short commit id: PlatformIO cannot fetch that (git fetch --depth=1 needs the full id)
        sha = github(f"https://api.github.com/repos/{short.group(2)}/commits/{short.group(3)}")["sha"]
        pinned = [SHORT_RE.sub(lambda m: f"{m.group(1)}#{sha}", l) for l in deps]
        return write(folder, section, pinned, f"{env} uses {short.group(2)}@{sha[:8]} (its own short pin, written out)")
    line = next((l for l in deps if LIB_RE.search(l)), None)
    lib = LIB_RE.search(line) if line else None
    if not lib or "#" in line:
        return print("pin_simlib: simulator library already pinned or not found, left as is")
    when = subprocess.run(["git", "-C", folder, "log", "-1", "--format=%cd", "--date=format-local:%Y-%m-%dT%H:%M:%SZ"],
                          capture_output=True, text=True, env=dict(os.environ, TZ="UTC")).stdout.strip()
    if not when:
        return print("pin_simlib: not a git checkout, left as is")
    cache_file = os.path.join(folder, ".rsim-pin.json")  # same answer for every model of this checkout
    try:
        cache = json.load(open(cache_file, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    key = f"{lib.group(2)}@{when}"
    if key not in cache:
        commits = github(f"https://api.github.com/repos/{lib.group(2)}/commits?until={when}&per_page=1")
        cache[key] = commits[0]["sha"] if commits else ""
        json.dump(cache, open(cache_file, "w", encoding="utf-8"))
    if not cache[key]:
        return print(f"pin_simlib: {lib.group(2)} has no commit before {when}, left as is")
    sha = cache[key]
    pinned = [LIB_RE.sub(lambda m: f"{m.group(1)}#{sha}", l) for l in deps]
    write(folder, section, pinned, f"{env} uses {lib.group(2)}@{sha[:8]} (last commit before {when})")


def write(folder, section, pinned, what):
    local = os.path.join(folder, "platformio.local.ini")
    old = open(local, encoding="utf-8").read() if os.path.isfile(local) else ""
    block = f"[env:{section}]\nlib_deps =\n" + "\n".join(pinned) + "\n"
    if block in old:
        return print(f"pin_simlib: already: {what}")
    head = "; written by the reader simulator: simulator library from this firmware's time\n"
    keep = re.sub(r"^\[env:%s\]\n(?:(?!^\[).*\n?)*" % re.escape(section), "", old.replace(head, ""), flags=re.M)
    open(local, "w", encoding="utf-8").write(head + keep.strip("\n") + ("\n\n" if keep.strip() else "") + block)
    print(f"pin_simlib: {what}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
