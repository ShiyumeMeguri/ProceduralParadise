"""
Fit the Nitia shot's display-referred grade -- per-channel monotone tone
curves that map the cumulative histogram of an ungraded render onto the
painting with the figure removed.  The two share one composition, so
matching distributions carries the painting's tonality over without the
contrast loss of a pixelwise or region-mean regression (which regresses
towards the mean wherever foliage differs leaf by leaf).

    blender -b -P Other/build.py -- Greenhouse/Scenes/GlassAtrium --no-save --no-look --render ungraded.png
    blender -b -P Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_grade.py -- ungraded.png [--write]

``--write`` stores the grade in shots/Nitia.json -> look.grade.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SCENE, "..", "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from Core import compare as C, grade as G  # noqa: E402
from Core.jsonio import dump  # noqa: E402

SHOT = os.path.join(SCENE, "shots", "Nitia.json")
REFERENCE = os.path.join(SCENE, "Reference", "Nitia_clean.webp")


def main(argv):
    render = C.load_image(argv[0])
    reference = C.load_image(REFERENCE, size=(render.shape[1], render.shape[0]))
    grade = G.fit_grade_hist(render, reference, n_knots=17, smooth=0.6, min_slope=0.35, max_slope=3.0)
    grade["highlight_rolloff"] = True
    grade["notes"] = ("Display-referred tone curves matching the histogram of the ungraded render to the "
                      "figure-free painting (calibration/fit_grade.py).")
    graded = G.apply_grade(render, grade)
    print("MAE ungraded %.4f  graded %.4f" % (np.abs(render - reference).mean(), np.abs(graded - reference).mean()))
    if "--write" in argv:
        with open(SHOT, encoding="utf-8") as handle:
            shot = json.load(handle)
        shot.setdefault("look", {})["grade"] = grade
        dump(shot, SHOT)
        print("grade written to", SHOT)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
