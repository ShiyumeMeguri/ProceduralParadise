"""
Fit the shot's display-referred grade (per-channel tone curves) by matching
the histogram of an ungraded render of BG_ShanTeaHouse_Night to the painting.

    python BlueArchive/Shanhaijing/Rooms/TeaHouse/calibration/fit_grade.py ungraded.png [--write]

``--write`` stores the curves in shots/BG_ShanTeaHouse_Night.json -> look.grade.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOM = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(ROOM, "..", "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from Core import compare as C, grade as G  # noqa: E402
from Core.jsonio import dump  # noqa: E402

SHOT = os.path.join(ROOM, "shots", "BG_ShanTeaHouse_Night.json")
REF = os.path.join(ROOM, "Reference", "BG_ShanTeaHouse_Night.webp")


def patch_means(img, grid=(24, 18)):
    """Region means: the semantic regions of verify.py plus a coarse grid
    (so the fit sees the whole frame, not only hand-picked areas)."""
    sys.path.insert(0, ROOM)
    import verify as V
    rm = V.region_means(img)
    pts = [rm[k] for k in sorted(rm)]
    h, w = img.shape[:2]
    gx, gy = grid
    for j in range(gy):
        for i in range(gx):
            pts.append(img[j * h // gy:(j + 1) * h // gy, i * w // gx:(i + 1) * w // gx].reshape(-1, 3).mean(0))
    return np.array(pts)


def main(argv):
    ren = C.load_image(argv[0])
    ref = C.load_image(REF, size=(ren.shape[1], ren.shape[0]))
    if "--hist" in argv:
        g = G.fit_grade_hist(ren, ref, n_knots=17, smooth=0.6, min_slope=0.35, max_slope=3.0)
    else:
        # a 24 x 18 grid plus the semantic regions, fairly strong smoothing: the best balance
        # between per-pixel error and the colour of the named regions
        g = G.fit_grade_patches(patch_means(ren), patch_means(ref), n_knots=17, reg=2.0)
    g["highlight_rolloff"] = True        # lamps and lanterns roll off to white, not pink
    g["notes"] = ("Display-referred grade (3x3 colour matrix + per-channel monotone curves) fitted "
                  "on region means of the ungraded render vs the painting (calibration/fit_grade.py).")
    graded = G.apply_grade(ren, g)
    print("MAE ungraded %.4f  graded %.4f" % (np.abs(ren - ref).mean(), np.abs(graded - ref).mean()))
    if "--write" in argv:
        with open(SHOT, encoding="utf-8") as f:
            shot = json.load(f)
        shot.setdefault("look", {})["grade"] = g
        dump(shot, SHOT)
        print("grade written to", SHOT)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
