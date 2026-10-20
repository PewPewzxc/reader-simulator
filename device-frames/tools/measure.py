"""Measure a front photo: body box, screen box and dark key bumps outside the body edges.
python -I measure.py <photo.png> <body width mm> <body height mm>
Prints millimetres (from the body's top-left corner) using the official body size."""
import subprocess
import sys


def gray(path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    w, h = map(int, probe.stdout.strip().split(","))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return w, h, raw


def runs(flags):
    """[(start, end)] of True runs."""
    out, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def main():
    path, bw_mm, bh_mm = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    w, h, px = gray(path)
    at = lambda x, y: px[y * w + x]
    dark = lambda v: v < 90
    # body: the longest dark run through the middle row / column
    mid_row = [dark(at(x, h // 2)) for x in range(w)]
    mid_col = [dark(at(w // 2, y)) for y in range(h)]
    x0 = min(x for x in range(w) if mid_row[x]); x1 = max(x for x in range(w) if mid_row[x])
    y0 = min(y for y in range(h) if mid_col[y]); y1 = max(y for y in range(h) if mid_col[y])
    # the side keys stick out past the body edge, so use the body edge at the very middle row
    row_runs = runs(mid_row)
    x0, x1 = row_runs[0][0], row_runs[-1][1]
    sx = bw_mm / (x1 - x0 + 1); sy = bh_mm / (y1 - y0 + 1)
    mm = lambda vx, vy: (round((vx - x0) * sx, 1), round((vy - y0) * sy, 1))
    # screen: light run in the middle row/column inside the body
    # screen: rows / columns inside the body where a quarter of the pixels are light (text never fills that much)
    light = lambda v: v > 150
    rows = [sum(light(at(x, y)) for x in range(x0, x1)) > 0.25 * (x1 - x0) for y in range(y0, y1)]
    cols = [sum(light(at(x, y)) for y in range(y0, y1)) > 0.25 * (y1 - y0) for x in range(x0, x1)]
    lr = max(runs(cols), key=lambda r: r[1] - r[0]); lc = max(runs(rows), key=lambda r: r[1] - r[0])
    print(f"photo {w}x{h}px, body {x1 - x0 + 1}x{y1 - y0 + 1}px, ratio {(y1 - y0 + 1) / (x1 - x0 + 1):.3f} (official {bh_mm / bw_mm:.3f})")
    print("screen mm: x %.1f-%.1f  y %.1f-%.1f" % (lr[0] * sx, lr[1] * sx, lc[0] * sy, lc[1] * sy))
    # side keys: dark pixels just outside the left/right body edges (2 px out)
    for name, x in (("left", x0 - 2), ("right", x1 + 2)):
        if 0 <= x < w:
            for a, b in runs([dark(at(x, y)) for y in range(h)]):
                if b - a > 3:
                    print(f"{name} key y {mm(0, a)[1]}-{mm(0, b)[1]} mm")
    for a, b in runs([dark(at(x, y0 - 2)) for x in range(w)]) if y0 >= 2 else []:
        if b - a > 3:
            print(f"top key x {mm(a, 0)[0]}-{mm(b, 0)[0]} mm")


if __name__ == "__main__":
    main()
