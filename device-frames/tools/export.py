"""Export frames/<model>.svg to frames/<model>.png (transparent, 1:1) with headless Chrome.
python -I export.py <frames dir>"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = os.environ.get("CHROME") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"

frames = sys.argv[1]
for name in ("x3", "x4-classic", "x4-pro"):
    W, H = json.load(open(os.path.join(frames, name + ".json")))["size"]
    svg = Path(frames, name + ".svg").resolve().as_uri()
    html = f'<!doctype html><style>html,body{{margin:0;background:transparent}}</style><img src="{svg}" width="{W}" height="{H}">'
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
    out = os.path.abspath(os.path.join(frames, name + ".png"))
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--default-background-color=00000000", "--allow-file-access-from-files",
                    f"--screenshot={out}", f"--window-size={W},{H}", Path(f.name).as_uri()], check=True, capture_output=True)
    os.unlink(f.name)
    print("exported", out)
