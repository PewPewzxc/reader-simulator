"""Render comparison pictures with headless Chrome:
python -I render.py <frames dir> <model> <screen.png> <reference photo> <out.png>
Left: the reference photo; middle: our frame with the simulator screen; right: the clickable key areas."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
COLORS = {"UP": "#e4572e", "DOWN": "#e4572e", "POWER": "#f3a712", "HOME": "#29bf12",
          "BACK": "#4f6bed", "ENTER": "#00a6a6", "LEFT": "#a14ded", "RIGHT": "#d6337a"}


def main():
    frames, model, screen, photo, out = sys.argv[1:6]
    info = json.load(open(os.path.join(frames, model + ".json")))
    W, H = info["size"]
    sc = info["screen"]
    uri = lambda p: Path(p).resolve().as_uri()
    frame = uri(os.path.join(frames, model + ".svg"))
    device = (f'<div class="dev" style="width:{W}px;height:{H}px">'
              f'<img src="{uri(screen)}" style="left:{sc["x"]}px;top:{sc["y"]}px;width:{sc["w"]}px;height:{sc["h"]}px">'
              f'<img src="{frame}" style="left:0;top:0;width:{W}px;height:{H}px">')
    keys = "".join(
        f'<div class="hit" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;background:{COLORS[k]}88">'
        f'<span>{k}</span></div>' for k, (x, y, w, h) in info["keys"].items())
    html = f"""<!doctype html><meta charset="utf-8"><style>
body{{margin:0;background:#f2f1ec;font:22px sans-serif;display:flex;gap:40px;padding:30px;align-items:flex-start}}
.dev{{position:relative}} .dev img{{position:absolute}}
.hit{{position:absolute;outline:1px solid #000;display:flex;align-items:center;justify-content:center}}
.hit span{{font:bold 15px sans-serif;color:#fff;text-shadow:0 0 3px #000;writing-mode:horizontal-tb}}
h3{{margin:0 0 10px;font:600 22px sans-serif}}</style>
<div><h3>Photo ({model})</h3><img src="{uri(photo)}" style="height:{H}px"></div>
<div><h3>Our frame</h3>{device}</div></div>
<div><h3>Clickable keys</h3>{device}{keys}</div></div>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
    width = 30 * 2 + 40 * 2 + W * 2 + int(H * 0.72)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                    f"--screenshot={os.path.abspath(out)}", f"--window-size={width},{H + 110}", Path(f.name).as_uri()],
                   check=True, capture_output=True)
    os.unlink(f.name)
    print("saved", out)


if __name__ == "__main__":
    main()
