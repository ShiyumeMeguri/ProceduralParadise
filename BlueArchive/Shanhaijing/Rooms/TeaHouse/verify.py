"""
Compare a render of the BG_ShanTeaHouse_Night shot against the reference painting.

    python BlueArchive/Shanhaijing/Rooms/TeaHouse/verify.py Renders/BG_ShanTeaHouse_Night.png

Writes ``metrics.json`` and ``BG_ShanTeaHouse_Night_compare.png`` (render |
reference) next to the render.  Runs in Blender's Python or with the ``bpy``
module (image IO goes through Blender).
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

REFERENCE = os.path.join(HERE, "Reference", "BG_ShanTeaHouse_Night.webp")

# semantic regions of the reference (x0, y0, x1, y1 in 1280 x 900 pixels)
REGIONS = {
    "plaster_left": (300, 20, 420, 60), "plaster_centre": (700, 60, 780, 100),
    "plaster_right": (1050, 90, 1150, 120), "timber_ceiling": (290, 165, 340, 200),
    "timber_ceiling_R": (820, 250, 880, 270), "big_beam": (655, 20, 668, 45),
    "back_panel_L": (180, 390, 195, 470), "back_panel_M": (605, 410, 625, 480),
    "back_planks": (220, 300, 270, 330), "plaque": (420, 325, 500, 340),
    "shelf": (335, 470, 345, 500), "moon_door": (450, 420, 490, 500),
    "floor_near": (500, 820, 700, 880), "floor_mid": (600, 700, 700, 740),
    "floor_right": (1100, 720, 1250, 760), "floor_far": (400, 560, 500, 580),
    "table_top": (250, 562, 420, 568), "cushion": (160, 645, 260, 660),
    "chair_back": (410, 560, 420, 620), "table_leg": (185, 640, 195, 800),
    "column_red": (1250, 420, 1270, 540), "column_left": (5, 200, 20, 500),
    "lantern": (140, 150, 180, 180), "logo_paper": (1000, 400, 1010, 470),
    "cloud_panel": (1140, 420, 1180, 470), "counter": (40, 560, 100, 580),
    "lattice": (40, 340, 80, 400), "architrave": (1000, 275, 1040, 285),
    "lion": (1170, 420, 1200, 460),
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


def verify(render_path, write=True):
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
    if write:
        out_dir = os.path.dirname(os.path.abspath(render_path))
        dump(res, os.path.join(out_dir, "metrics.json"))
        C.side_by_side(ren, ref, os.path.join(out_dir, "BG_ShanTeaHouse_Night_compare.png"))
    return res


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    r = verify(args[0] if args else os.path.join(HERE, "Renders", "BG_ShanTeaHouse_Night.png"),
               write="--no-write" not in args)
    print(json.dumps({k: v for k, v in r.items() if k != "regions"}, indent=1))
    for k, v in r["regions"].items():
        print(f"  {k:18s} ren {v['render']}  ref {v['reference']}  d {v['abs_diff']}")
