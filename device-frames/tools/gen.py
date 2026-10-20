"""Draw the device frames (our own artwork) from measured millimetres.
python -I gen.py <out dir>  ->  <model>.svg (frame only, transparent screen hole),
                                <model>.json (screen rect + clickable key areas, frame pixels)
Measurements: reference photos + official sizes (see ../README.md). Pixels per mm are chosen so
the screen hole is exactly the panel's resolution, so the simulator screen sits in it 1:1."""
import json
import os
import sys

# x/y in mm from the body's top-left corner; keys: (name, side, start, end).
# v2/v3: numbers and colours from two rounds of three reviews against the photos (REVIEWS.md).
MODELS = {
    "x3": dict(
        body=(63.7, 97.6), radius=3.6, panel=(528, 792), screen=(5.5, 5.0, 57.8, 83.5), key_out=0.8,
        keys=[("UP", "left", 16.4, 31.9), ("DOWN", "right", 16.5, 31.9), ("POWER", "top", 47.5, 55.2)],
        bars=[(11.2, 30.2), (32.9, 52.2)], bar_y=(93.6, 95.4), home=None,
        # two-part shell: dark edge, light lip, then a groove where the front plate starts; a step above the bars
        look=dict(face=("#38383a", "#2a2a2c"), face_dir=(1, .25), edge=("#141415", 0.3), lip=("#404043", 0.45, 0.9),
                  seam=None, keys=("#1a1a1b", "#2e2e30"), bar=("#333335", "#0c0c0d"), well="#1f1f20", hole_r=0.6,
                  seam_path=dict(color="#19191a", width=0.2, top=1.1, side=1.45, bottom=1.2, r=2.4,
                                 notch=(10.5, 53.2, 92.7, 1.0)))),
    "x4-classic": dict(
        body=(69.0, 114.0), radius=3.8, panel=(480, 800), screen=(6.6, 5.8, 62.2, 97.5), key_out=0.55,
        keys=[("UP", "left", 25.3, 40.5), ("POWER", "right", 9.8, 16.3), ("DOWN", "right", 25.8, 40.5)],
        bars=[(11.9, 31.9), (37.1, 57.1)], bar_y=(110.5, 112.6), home=None,
        # matte mid-grey, lit from the top; a dark line just inside the edge, no light lip
        look=dict(face=("#545457", "#38383b"), face_dir=(.25, 1), edge=("#141415", 0.3), lip=None,
                  seam=("#1e1e1f", 0.7, 0.2), keys=("#262628", "#5c5c5e"),
                  bar=("#3a3a3c", "#1e1e1f"), well="#2e2e30", hole_r=0.5)),
    "x4-pro": dict(
        body=(69.0, 111.0), radius=4.0, panel=(480, 800), screen=(6.6, 5.6, 62.3, 97.5), key_out=0.6,
        keys=[("UP", "left", 25.6, 40.6), ("POWER", "right", 10.1, 16.7), ("DOWN", "right", 25.6, 40.6)],
        bars=[], bar_y=None, home=(34.5, 104.0, 3.95),
        # cool near-black; a near-black band round the glass with a hair of light at the very edge
        look=dict(face=("#2c2d2f", "#212124"), face_dir=(1, 1), edge=("#0b0b0c", 0.8), lip=("#313336", 0.8, 0.95),
                  seam=None, keys=("#08080a", "#2c2c2f"), bar=None, well="#18181a", hole_r=0.5,
                  home=("#38393c", "#2e2f32"))),
}
KEY_HIT_IN = 4.0   # mm of the body next to a key that also counts as pressing it
KEY_HIT_PAD = 1.0  # mm added along a key's length, so short keys are easy to hit
MARGIN = 1.5       # mm of transparent space around the body for the keys
INSET = 2          # px of panel edge the bezel covers (the simulator draws only the inner part too)


def build(name, m):
    bw, bh = m["body"]
    sx0, sy0, sx1, sy1 = m["screen"]
    pw, ph = m["panel"]
    look, out = m["look"], m["key_out"]
    s = pw / (sx1 - sx0)                        # px per mm, from the screen width
    scr_h_mm = ph / s                           # keep the panel aspect, centred on the measured box
    sy0 = (sy0 + sy1) / 2 - scr_h_mm / 2
    W, H = round((bw + 2 * MARGIN) * s), round((bh + 2 * MARGIN) * s)
    X = lambda mm: round((mm + MARGIN) * s, 2)
    L = lambda mm: round(mm * s, 2)
    panel = dict(x=round(X(sx0)), y=round(X(sy0)), w=pw, h=ph)
    screen = dict(x=panel["x"] + INSET, y=panel["y"] + INSET, w=pw - 2 * INSET, h=ph - 2 * INSET)
    hit, parts = {}, []

    # side keys first, so the body covers their inner part
    for key, side, a, b in m["keys"]:
        if side == "top":
            x, y, w, h, grad = X(a), X(-out), L(b - a), L(out + 1), "keyv"
            hit[key] = [X(a - KEY_HIT_PAD), 0, L(b - a + 2 * KEY_HIT_PAD), L(MARGIN + KEY_HIT_IN)]
        else:
            x = X(-out) if side == "left" else X(bw - 1)
            y, w, h, grad = X(a), L(out + 1), L(b - a), "key"
            hx = 0 if side == "left" else X(bw - KEY_HIT_IN)
            hit[key] = [hx, X(a - KEY_HIT_PAD), L(KEY_HIT_IN + MARGIN), L(b - a + 2 * KEY_HIT_PAD)]
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{L(0.5)}" fill="url(#{grad})"/>')

    r = L(m["radius"])

    def inset_rect(d, **attrs):
        extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        return (f'<rect x="{X(d)}" y="{X(d)}" width="{L(bw - 2 * d)}" height="{L(bh - 2 * d)}" '
                f'rx="{round(max(r - L(d), 0), 2)}" {extra}/>')

    parts.append(inset_rect(0, fill="url(#body)"))
    edge, ew = look["edge"]
    parts.append(inset_rect(ew / 2, fill="none", stroke=edge, stroke_width=L(ew)))
    if look["lip"]:
        lip, a, b = look["lip"]
        parts.append(inset_rect((a + b) / 2, fill="none", stroke=lip, stroke_width=L(b - a)))
    if look["seam"]:
        seam, d, sw = look["seam"]
        parts.append(inset_rect(d, fill="none", stroke=seam, stroke_width=L(sw)))
    if look.get("seam_path"):
        # X3 front plate: inset seam that steps up around both bottom bars (one recess)
        sp = look["seam_path"]
        lx, rx_, ty, by, rr = sp["side"], bw - sp["side"], sp["top"], bh - sp["bottom"], sp["r"]
        a, b, ys, f = sp["notch"]
        P = lambda x, y: f"{X(x)},{X(y)}"
        A = f"A{L(rr)},{L(rr)} 0 0 1 "
        d = (f"M{P(lx + rr, ty)} H{X(rx_ - rr)} {A}{P(rx_, ty + rr)} V{X(by - rr)} {A}{P(rx_ - rr, by)} "
             f"H{X(b + f)} Q{P(b, by)} {P(b, by - f)} V{X(ys + f)} Q{P(b, ys)} {P(b - f, ys)} "
             f"H{X(a + f)} Q{P(a, ys)} {P(a, ys + f)} V{X(by - f)} Q{P(a, by)} {P(a - f, by)} "
             f"H{X(lx + rr)} {A}{P(lx, by - rr)} V{X(ty + rr)} {A}{P(lx + rr, ty)} Z")
        parts.append(f'<path d="{d}" fill="none" stroke="{sp["color"]}" stroke-width="{L(sp["width"])}"/>')
    # screen well: a hair of darker face round the panel, then the hole
    g = L(0.2)
    parts.append(f'<rect x="{screen["x"] - g}" y="{screen["y"] - g}" width="{screen["w"] + 2 * g}" '
                 f'height="{screen["h"] + 2 * g}" rx="{L(look["hole_r"] + 0.2)}" fill="{look["well"]}"/>')

    chin_top = X(sy0 + scr_h_mm + 1)
    bottom = X(bh) + L(MARGIN)
    bars = m["bars"]
    for i, (a, b) in enumerate(bars):
        y0, y1 = m["bar_y"]
        fill, stroke = look["bar"]
        parts.append(f'<rect x="{X(a)}" y="{X(y0)}" width="{L(b - a)}" height="{L(y1 - y0)}" rx="{L((y1 - y0) / 2)}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="{L(0.15)}"/>')
        mid = (a + b) / 2  # each bar is a rocker: two keys
        gap = (bars[0][1] + bars[1][0]) / 2  # click areas meet in the middle of the gap, never overlap
        lo, hi = (a - 1.5, gap) if i == 0 else (gap, b + 1.5)
        left, right = (("BACK", "ENTER"), ("LEFT", "RIGHT"))[i]
        hit[left] = [X(lo), chin_top, L(mid - lo), round(bottom - chin_top, 2)]
        hit[right] = [X(mid), chin_top, L(hi - mid), round(bottom - chin_top, 2)]
    if m["home"]:
        cx, cy, rr = m["home"]
        parts.append(f'<circle cx="{X(cx)}" cy="{X(cy)}" r="{L(rr)}" fill="url(#home)"/>')
        hit["HOME"] = [X(cx - rr - 4), chin_top, L(2 * rr + 8), round(bottom - chin_top, 2)]

    fx, fy = look["face_dir"]
    k0, k1 = look["keys"]
    h0, h1 = look.get("home", ("#000", "#000"))
    defs = f"""<defs>
<linearGradient id="body" x1="0" y1="0" x2="{fx}" y2="{fy}"><stop offset="0" stop-color="{look['face'][0]}"/><stop offset="1" stop-color="{look['face'][1]}"/></linearGradient>
<linearGradient id="key" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{k0}"/><stop offset=".5" stop-color="{k1}"/><stop offset="1" stop-color="{k0}"/></linearGradient>
<linearGradient id="keyv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{k0}"/><stop offset=".5" stop-color="{k1}"/><stop offset="1" stop-color="{k0}"/></linearGradient>
<radialGradient id="home" cx=".45" cy=".42" r=".75"><stop offset="0" stop-color="{h0}"/><stop offset="1" stop-color="{h1}"/></radialGradient>
<mask id="hole"><rect width="{W}" height="{H}" fill="#fff"/><rect x="{screen['x']}" y="{screen['y']}" width="{screen['w']}" height="{screen['h']}" rx="{L(look['hole_r'])}" fill="#000"/></mask>
</defs>"""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{defs}'
           f'<g mask="url(#hole)">' + "".join(parts) + "</g></svg>\n")
    info = dict(model=name, size=[W, H], px_per_mm=round(s, 3), screen=screen, panel=panel,
                keys={k: [round(v) for v in r] for k, r in hit.items()})
    return svg, info


def check(info):
    W, H = info["size"]
    sc = info["screen"]
    assert sc["x"] > 0 and sc["y"] > 0 and sc["x"] + sc["w"] < W and sc["y"] + sc["h"] < H, "screen inside frame"
    for k, (x, y, w, h) in info["keys"].items():
        assert w > 0 and h > 0 and x >= 0 and y >= 0 and x + w <= W + 1 and y + h <= H + 1, k
        assert not (x < sc["x"] + sc["w"] and x + w > sc["x"] and y < sc["y"] + sc["h"] and y + h > sc["y"]), \
            f"{k} key area overlaps the screen (taps there must reach the touchscreen)"


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for name, m in MODELS.items():
        svg, info = build(name, m)
        check(info)
        open(os.path.join(out, name + ".svg"), "w").write(svg)
        json.dump(info, open(os.path.join(out, name + ".json"), "w"), indent=1)
        # the simulator reads this plain form (frame pixels): size, screen, one line per key
        sc = info["screen"]
        lines = [f"size {info['size'][0]} {info['size'][1]}", f"screen {sc['x']} {sc['y']} {sc['w']} {sc['h']}"]
        lines += [f"key {k} {x} {y} {w} {h}" for k, (x, y, w, h) in info["keys"].items()]
        open(os.path.join(out, name + ".keys"), "w", newline="\n").write("\n".join(lines) + "\n")
        print(name, info["size"], "screen", info["screen"], "keys", ", ".join(info["keys"]))
