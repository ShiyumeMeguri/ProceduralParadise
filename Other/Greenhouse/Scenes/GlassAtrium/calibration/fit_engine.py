"""
Fit the Nitia shot's engine transfer: per-channel tone curves that carry
the render engine's own response onto the look the shot was calibrated on.

The lights, the leaf colours and the grade of the shot were fitted on Cycles
renders, and the Cycles render they made is the accepted look:
``Reference/Anchors/Nitia.png``, the whole shot at the painting's size.
Those weights are locked.  Another engine lights the same scene its own
way -- EEVEE traces no light thrown about between the leaves and the jade
glass, so its shade under the leaves is the sky's lavender where the
anchor's is teal, and its sunlit leaves yellower -- and that difference is
the transfer's, not the scene's: the histogram of the engine's render (with
the look and the grade, without a transfer) matched to the anchor's,
blended towards identity by the ``STRENGTHS`` step that brings the render
nearest the anchor (``fit_lights.Target`` with the anchor as its target).

Two steps, because Blender's Python has no OpenCV::

    blender -b -P Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_engine.py -- untransferred.png [--samples 48] [--scale 0.25]
    python Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_engine.py untransferred.png [--write]

``--write`` stores the curves in shots/Nitia.json -> look.engine_transfer.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SCENE, "..", "..", "..", ".."))
for path in (ROOT, os.path.join(ROOT, "Other"), HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import numpy as np  # noqa: E402

SHOT = os.path.join(SCENE, "shots", "Nitia.json")
ANCHOR = os.path.join(SCENE, "Reference", "Anchors", "Nitia.png")
STRENGTHS = np.linspace(0.0, 1.0, 21)


def render_untransferred(out, samples, scale):
    import bpy
    ns = {}
    exec(compile(open(os.path.join(ROOT, "Other", "build.py"), encoding="utf-8").read(), "build.py", "exec"), ns)
    context = ns["main"](["x", "--", "Greenhouse/Scenes/GlassAtrium", "--no-save", "--no-transfer", "--samples", str(samples), "--scale", str(scale)])
    from Core import driver
    driver.activate_still(context)
    bpy.context.scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("untransferred ->", out)


def main(argv):
    try:
        import bpy  # noqa: F401
    except ImportError:
        bpy = None
    if bpy is not None:
        samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48
        scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.25
        render_untransferred(os.path.abspath(argv[0]), samples, scale)
        return
    import cv2
    from Core import grade as G
    from Core.jsonio import dump
    from fit_grade import blended
    from fit_lights import Target
    render = cv2.imread(argv[0])[:, :, ::-1].astype(np.float32) / 255.0
    height, width = render.shape[:2]
    anchor = cv2.imread(ANCHOR)[:, :, ::-1].astype(np.float32) / 255.0
    target = Target(anchor, (width, height))
    full = G.fit_grade_hist(render, target.display, n_knots=17, smooth=0.6, min_slope=0.35, max_slope=3.0)
    scores = []
    for strength in STRENGTHS:
        layout, bands = target.terms(G.apply_grade(render, blended(full, strength)).astype(np.float32))
        scores.append(layout + bands)
        print("strength %.2f: layout %.4f, bands %.4f" % (strength, layout, bands))
    strength = float(STRENGTHS[int(np.argmin(scores))])
    transfer = blended(full, strength)
    transfer["highlight_rolloff"] = True
    transfer["notes"] = ("Display tone curves carrying this engine's response onto the accepted look of the shot "
                         "(Reference/Anchors/Nitia.png, the Cycles render of the locked lights, leaf colours and grade): "
                         "the histogram of the engine's render with the grade matched to the anchor's, blended %.2f of the "
                         "way from identity -- the blend nearest the anchor (calibration/fit_engine.py)." % strength)
    print("chosen strength %.2f" % strength)
    if "--write" in argv:
        with open(SHOT, encoding="utf-8") as handle:
            shot = json.load(handle)
        shot.setdefault("look", {})["engine_transfer"] = transfer
        dump(shot, SHOT)
        print("engine transfer written to", SHOT)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
