"""
Fit the Nitia shot's display grade: per-channel tone curves that carry the
painting's tonality -- its deep teal shade, its saturated greens, its
bright pinks -- onto the render.

The curves map the cumulative histogram of the render onto the painting's
with the figure removed, so they copy the painting's contrast where leaves,
flags and patches of sun line up with the painted ones, and exaggerate the
error where they do not.  So the fitted curves are blended towards identity
by the ``STRENGTHS`` step that minimises the light fit's own objective
(``fit_lights.Target``: the error on blurred display values plus the
distance of the band quantiles).  The render is the shot with its look --
ink, glare -- but without a grade, the image the grade is applied to.

Two steps, because Blender's Python has no OpenCV::

    blender -b -P Other/Greenhouse/GlassAtrium/calibration/fit_grade.py -- ungraded.png [--samples 48] [--scale 0.25]
    python Other/Greenhouse/GlassAtrium/calibration/fit_grade.py ungraded.png [--write]

``--write`` stores the grade in shots/Nitia.json -> look.grade.  Fit it
after the lights (``fit_lights.py``).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SCENE, "..", "..", ".."))
for path in (ROOT, os.path.join(ROOT, "Other"), HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import numpy as np  # noqa: E402

SHOT = os.path.join(SCENE, "shots", "Nitia.json")
REFERENCE = os.path.join(SCENE, "Reference", "Nitia_clean.webp")
STRENGTHS = np.linspace(0.0, 1.0, 21)


def render_ungraded(out, samples, scale):
    import bpy
    ns = {}
    exec(compile(open(os.path.join(ROOT, "Other", "build.py"), encoding="utf-8").read(), "build.py", "exec"), ns)
    context = ns["main"](["x", "--", "Greenhouse/GlassAtrium", "--no-save", "--no-grade", "--samples", str(samples), "--scale", str(scale)])
    from Core import driver
    driver.activate_still(context)
    bpy.context.scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("ungraded ->", out)


def blended(grade, strength):
    """``grade`` with its curves moved ``strength`` of the way from
    identity."""
    curves = {name: [[x, strength * y + (1.0 - strength) * x] for x, y in points] for name, points in grade["curves"].items()}
    return {**grade, "curves": curves}


def main(argv):
    try:
        import bpy  # noqa: F401
    except ImportError:
        bpy = None
    if bpy is not None:
        samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48
        scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.25
        render_ungraded(os.path.abspath(argv[0]), samples, scale)
        return
    import cv2
    from Core import grade as G
    from Core.jsonio import dump
    from fit_lights import Target
    render = cv2.imread(argv[0])[:, :, ::-1].astype(np.float32) / 255.0
    height, width = render.shape[:2]
    reference = cv2.imread(REFERENCE)[:, :, ::-1].astype(np.float32) / 255.0
    target = Target(reference, (width, height))
    full = G.fit_grade_hist(render, target.display, n_knots=17, smooth=0.6, min_slope=0.35, max_slope=3.0)
    scores = []
    for strength in STRENGTHS:
        layout, bands = target.terms(G.apply_grade(render, blended(full, strength)).astype(np.float32))
        scores.append(layout + bands)
        print("strength %.2f: layout %.4f, bands %.4f" % (strength, layout, bands))
    strength = float(STRENGTHS[int(np.argmin(scores))])
    grade = blended(full, strength)
    grade["highlight_rolloff"] = True
    grade["notes"] = ("Display tone curves carrying the painting's tonality onto the render: the histogram of the render "
                      "without a grade matched to the figure-free painting's, blended %.2f of the way from identity -- the "
                      "blend that minimises the light fit's objective (calibration/fit_grade.py)." % strength)
    print("chosen strength %.2f" % strength)
    if "--write" in argv:
        with open(SHOT, encoding="utf-8") as handle:
            shot = json.load(handle)
        shot.setdefault("look", {})["grade"] = grade
        dump(shot, SHOT)
        print("grade written to", SHOT)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
