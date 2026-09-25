"""
Compare a render of the BG_Milleniumclub shot against the reference painting.

    python BlueArchive/Millennium/Rooms/ClubRoom/verify.py Renders/BG_Milleniumclub.png

Writes ``Renders/metrics.json`` and ``Renders/BG_Milleniumclub_compare.png``
(render | reference) next to the render.  Runs in Blender's Python or with the
``bpy`` module (image IO goes through Blender).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from Core import compare as C  # noqa: E402
from Core.jsonio import dump  # noqa: E402

REFERENCE = os.path.join(HERE, "Reference", "BG_Milleniumclub.webp")

# semantic regions of the reference (x0, y0, x1, y1 in 1280 x 900 pixels)
REGIONS = {
    "sky_upper": (20, 200, 140, 300), "sky_mid": (305, 330, 390, 420),
    "sky_right": (560, 360, 595, 440), "city_twin": (100, 450, 150, 520),
    "ceiling": (800, 20, 1000, 70), "ceiling_back": (900, 225, 1100, 258),
    "back_wall_L": (705, 380, 725, 500), "back_wall_R": (1215, 380, 1232, 520),
    "sign_panel": (800, 400, 880, 440), "sign_top": (800, 356, 1100, 372),
    "floor_sun": (30, 800, 250, 880), "floor_shadow": (850, 705, 1000, 760),
    "floor_mid": (500, 850, 700, 895), "desk_top": (1100, 574, 1200, 586),
    "chair_blue": (975, 540, 1010, 560), "chair_white": (820, 540, 860, 552),
    "window_frame": (145, 300, 165, 500),
}


def region_means(img):
    h, w = img.shape[:2]
    sx, sy = w / 1280.0, h / 900.0
    out = {}
    for k, (x0, y0, x1, y1) in REGIONS.items():
        patch = img[int(y0 * sy):int(y1 * sy), int(x0 * sx):int(x1 * sx)]
        out[k] = patch.reshape(-1, 3).mean(0)
    return out


def luminance_pct(img):
    lum = img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114
    return [round(float(v), 3) for v in np.percentile(lum, [5, 25, 50, 75, 95])]


def verify(render_path):
    ren = C.load_image(render_path)
    ref = C.load_image(REFERENCE, size=(ren.shape[1], ren.shape[0]))
    m = C.metrics(ren, ref)
    rr, rf = region_means(ren), region_means(ref)
    regions = {k: {"render": [round(float(x), 3) for x in rr[k]],
                   "reference": [round(float(x), 3) for x in rf[k]],
                   "abs_diff": round(float(np.abs(rr[k] - rf[k]).mean()), 3)} for k in REGIONS}
    res = {
        "render": os.path.basename(render_path),
        "mae": round(m["mae"], 4),
        "ssim": round(m["ssim"], 4),
        "edge_recall_2px": round(m["edge_recall_2px"], 4),
        "regions_mean_abs_diff": round(float(np.mean([r["abs_diff"] for r in regions.values()])), 4),
        "luminance_pct": {"render": luminance_pct(ren), "reference": luminance_pct(ref)},
        "regions": regions,
    }
    out_dir = os.path.dirname(os.path.abspath(render_path))
    dump(res, os.path.join(out_dir, "metrics.json"))
    C.side_by_side(ren, ref, os.path.join(out_dir, "BG_Milleniumclub_compare.png"))
    return res


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    r = verify(args[0] if args else os.path.join(HERE, "Renders", "BG_Milleniumclub.png"))
    print(json.dumps({k: v for k, v in r.items() if k != "regions"}, indent=1))
