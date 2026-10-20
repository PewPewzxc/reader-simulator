"""Download one firmware version like the launcher does; print its folder.
python -I tools/fetch.py <owner/repo> <ref>
If a submodule cannot be cloned (VARAGH 1.2.1 points at a private freeink-sdk repo), clone again without
submodules: the simulator builds usually do not use the device SDK. The build then shows if it was needed."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import launcher  # noqa: E402

import hashlib  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402


def remove(path):
    """rmtree that also removes git's read-only pack files (plain rmtree fails on them on Windows)."""
    shutil.rmtree(path, onexc=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))


repo, ref = sys.argv[1], sys.argv[2]
dest = os.path.join(launcher.DOWNLOADS, hashlib.md5(f"{repo}@{ref}".encode()).hexdigest()[:8])  # as launcher.download
if os.path.isdir(dest) and not os.path.isfile(os.path.join(dest, "platformio.ini")):
    remove(dest)  # a broken earlier download
try:
    print(launcher.download(repo, ref))
except RuntimeError:
    if os.path.isdir(dest):
        remove(dest)
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", ref, f"https://github.com/{repo}.git", dest],
                   check=True, stdout=subprocess.DEVNULL)
    # --shallow-submodules in one go sometimes fails where a separate submodule step works (CrossPDF)
    sub = subprocess.run(["git", "-C", dest, "submodule", "update", "--init", "--recursive", "--depth", "1"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    open(os.path.join(dest, launcher.NAME_FILE), "w", encoding="utf-8", newline="\n").write(repo + "@" + ref + "\n")
    if sub.returncode:
        print(f"fetch: {repo} {ref}: a submodule could not be downloaded, using the source without it", file=sys.stderr)
    print(dest)
