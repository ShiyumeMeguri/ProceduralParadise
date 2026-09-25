"""
Fit the Kivotos halo ring systems (campus.json -> halo.systems) to the rings
painted in BG_Milleniumclub.

    python BlueArchive/Millennium/Rooms/ClubRoom/calibration/fit_halo.py [--write]

1. Thin bright lines are extracted from the reference (white top-hat on luma
   and red), inside the window's sky area and away from the edges of the
   model's own geometry (mullions, transoms, ceiling), which are rendered
   with ``Core.compare.edge_map`` from the solved camera.
2. Every painted ring family (an image region, see FAMILIES) is searched for
   a common centre and aspect ratio with a concentric-ellipse Hough
   transform; ring radii are the strongest peaks of the elliptical-radius
   histogram.
3. Each family is back-projected from the solved camera onto a ring plane at
   ALTITUDE metres.  The plane is tilted towards the camera so its projected
   aspect ratio matches the painting; radii come from back-projecting the
   ellipse ends.  Tube thickness = THICKNESS_PX at the reference camera.

``--write`` updates centre / normal / thickness / radii in campus.json and
keeps each ring's styling (markers, gaps, dotted) by index.  Needs numpy
only (runs in Blender's Python or with the bpy module).
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOM = os.path.dirname(HERE)
BA = os.path.abspath(os.path.join(ROOM, "..", "..", ".."))
ROOT = os.path.dirname(BA)
for p in (ROOT, BA):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

ALTITUDE = 606.0          # m, ring plane height (world)
THICKNESS_PX = 0.85       # painted line width, px at the reference camera
SKY_ZONE = dict(x_max=700, y_max=430, head=(95.0, 250.0, 700.0))   # window head line (x=0 -> y0, x=x1 -> y1)
# painted ring families: point box, centre search box (px), max radius, rings kept
FAMILIES = [
    {"id": "L", "box": (0, 240, 330, 430), "search": (60, 280, 180, 340), "rmax": 330, "keep": 4},
    {"id": "R", "box": (300, 280, 600, 430), "search": (380, 320, 520, 370), "rmax": 200, "keep": 3},
    {"id": "RR", "box": (540, 290, 700, 430), "search": (590, 310, 670, 350), "rmax": 100, "keep": 2},
    {"id": "T", "box": (150, 160, 330, 270), "search": (200, 190, 300, 240), "rmax": 120, "keep": 2},
    {"id": "TL", "box": (60, 120, 170, 215), "search": (90, 160, 160, 200), "rmax": 80, "keep": 1},
]


# ------------------------------------------------------------ numpy filters
def _window(a, k, fn):
    r = k // 2
    p = np.pad(a, r, mode="edge")
    out = np.full_like(a, np.inf if fn is np.minimum else -np.inf)
    for dy in range(k):
        for dx in range(k):
            out = fn(out, p[dy:dy + a.shape[0], dx:dx + a.shape[1]])
    return out


def _opening(a, k=5):
    return _window(_window(a, k, np.minimum), k, np.maximum)


def _box(a, ky, kx):
    ry, rx = ky // 2, kx // 2
    p = np.pad(a.astype(np.float64), ((ry, ry), (rx, rx)), mode="edge")
    c = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return (c[ky:, kx:] - c[:-ky, kx:] - c[ky:, :-kx] + c[:-ky, :-kx]) / (ky * kx)


# ------------------------------------------------------------ ring pixels
def ring_pixels(ref, geo_edges):
    lum = ref.mean(-1)
    red = ref[..., 0]
    m = ((lum - _opening(lum)) > 0.04) & ((red - _opening(red)) > 0.06)
    H, W = m.shape
    yy, xx = np.mgrid[:H, :W]
    y0, y1, x1 = SKY_ZONE["head"]
    m &= (xx < SKY_ZONE["x_max"]) & (yy < SKY_ZONE["y_max"]) & (yy > y0 + (y1 - y0) * xx / x1 + 8)
    m &= ~(_box(geo_edges, 7, 7) > 0)            # model geometry (dilated 3 px)
    m &= _box(m, 7, 7) < 0.30                    # cloud blobs
    m &= _box(m, 25, 1) < 0.7                    # vertical runs
    ys, xs = np.nonzero(m)
    return np.stack([xs, ys], 1).astype(np.float64)


def _hist(pts, cx, cy, q):
    r = np.sqrt((pts[:, 0] - cx) ** 2 + ((pts[:, 1] - cy) / q) ** 2)
    return np.bincount(np.clip(r, 0, 1999).astype(int), minlength=2000)[:2000].astype(float)


def _score(h):
    h2 = h[0::2] + h[1::2]
    return (h2 ** 2).sum()


def hough_family(pts, fam):
    x0, y0, x1, y1 = fam["box"]
    sel = (pts[:, 0] >= x0) & (pts[:, 0] < x1) & (pts[:, 1] >= y0) & (pts[:, 1] < y1)
    p = pts[sel]
    sx0, sy0, sx1, sy1 = fam["search"]
    best = (-1.0, None)
    for q in np.arange(0.16, 0.56, 0.02):
        for cy in np.arange(sy0, sy1 + 1, 3):
            for cx in np.arange(sx0, sx1 + 1, 3):
                s = _score(_hist(p, cx, cy, q))
                if s > best[0]:
                    best = (s, (cx, cy, q))
    cx, cy, q = best[1]
    for dq in (0.01, 0.005):
        for q_ in np.arange(q - 2 * dq, q + 2.01 * dq, dq):
            for cy_ in np.arange(cy - 3, cy + 3.1, 1):
                for cx_ in np.arange(cx - 3, cx + 3.1, 1):
                    s = _score(_hist(p, cx_, cy_, q_))
                    if s > best[0]:
                        best = (s, (cx_, cy_, q_))
        cx, cy, q = best[1]
    h = _box(_hist(p, cx, cy, q)[None], 1, 3)[0]
    peaks = [i for i in range(3, min(fam["rmax"], 1990)) if h[i] >= h[i - 1] and h[i] > h[i + 1] and h[i] >= 6]
    merged = []
    for i in peaks:
        if merged and i - merged[-1] < 4:
            if h[i] > h[merged[-1]]:
                merged[-1] = i
            continue
        merged.append(i)
    strongest = sorted(sorted(merged, key=lambda i: -h[i])[:fam["keep"]])   # kept rings, inner first
    return float(cx), float(cy), float(q), strongest


# ------------------------------------------------------------ 3D
def back_project(cam, fam_fit):
    """cam = dict(pos, right, up, fwd, f, cx, cy) -> world ring system."""
    u, v, q, radii_px = fam_fit
    def ray(px, py):
        return cam["fwd"] + cam["right"] * ((px - cam["cx"]) / cam["f"]) + cam["up"] * ((cam["cy"] - py) / cam["f"])
    d = ray(u, v)
    C = cam["pos"] + d * ((ALTITUDE - cam["pos"][2]) / d[2])
    vn = d / np.linalg.norm(d)
    h = np.array([vn[0], vn[1], 0.0])
    h /= np.linalg.norm(h)
    tau = math.asin(q) - math.asin(vn[2])       # tilt so |n . view| = aspect
    n = np.array([0.0, 0.0, 1.0]) * math.cos(tau) + h * math.sin(tau)
    radii = []
    for a in radii_px:
        rr = []
        for s in (1, -1):
            dd = ray(u + s * a, v)
            t = ((C - cam["pos"]) @ n) / (dd @ n)
            rr.append(np.linalg.norm(cam["pos"] + t * dd - C))
        radii.append(round(float(np.mean(rr)), 1))
    dist = float(np.linalg.norm(C - cam["pos"]))
    return {"center": [round(float(x), 1) for x in C], "normal": [round(float(x), 4) for x in n],
            "thickness": round(THICKNESS_PX * dist / cam["f"], 1), "radii": radii}


def main():
    write = "--write" in sys.argv
    import build  # BlueArchive/build.py
    from Core import compare as C
    args = build.parse(["x", "Millennium/Rooms/ClubRoom", "--shot", "BG_Milleniumclub",
                        "--no-city", "--no-halo", "--no-look"])
    ctx = build.build(args)
    geo = C.edge_map()
    ref = C.load_image(os.path.join(ROOM, "Reference", "BG_Milleniumclub.webp"))
    cam_ob = ctx["camera"]
    solve = ctx["shot"]["camera"]
    M = np.array(cam_ob.matrix_world)
    cam = {"pos": M[:3, 3], "right": M[:3, 0], "up": M[:3, 1], "fwd": -M[:3, 2],
           "f": solve["focal_px"], "cx": solve["principal_px"][0], "cy": solve["principal_px"][1]}
    pts = ring_pixels(ref, geo)
    systems = []
    for fam in FAMILIES:
        fit = hough_family(pts, fam)
        s = {"id": fam["id"], **back_project(cam, fit)}
        print(fam["id"], "image centre (%.0f, %.0f) aspect %.3f radii_px %s" % (fit[0], fit[1], fit[2], fit[3]),
              "->", json.dumps(s))
        systems.append(s)
    if write:
        from Core.jsonio import dump, load
        path = os.path.join(BA, "Millennium", "Campus", "campus.json")
        campus = load(path)
        old = {s["id"]: s for s in campus["halo"]["systems"]}
        for s in systems:
            o = old.get(s["id"], {"rings": []})
            rings = []
            for i, r in enumerate(s.pop("radii")):
                style = dict(o["rings"][i]) if i < len(o["rings"]) else {}
                style["radius"] = r
                rings.append(style)
            o.update(s)
            o["rings"] = rings
            old[s["id"]] = o
        campus["halo"]["systems"] = [old[f["id"]] for f in FAMILIES]
        dump(campus, path)
        print("written", path)


if __name__ == "__main__":
    main()
