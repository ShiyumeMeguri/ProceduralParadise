"""
Geometry overlay for the TeaHouse: build the room, render occlusion-correct
model lines from the painting's camera and draw them (red) over the
reference (its own edges in cyan).

    python BlueArchive/Shanhaijing/Rooms/TeaHouse/calibration/overlay.py [out.png] [--crop x0,y0,x1,y1] [--scale 2]

Runs in Blender's Python or with the ``bpy`` module.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOM = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(ROOM, "..", "..", "..", ".."))
for p in (ROOT, os.path.join(ROOT, "BlueArchive")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402


def main(argv):
    import build as B
    from Core import compare as C
    out = argv[0] if argv and not argv[0].startswith("--") else os.path.join(ROOM, "Renders", "overlay.png")
    args = B.parse(["x", "Shanhaijing/Rooms/TeaHouse", "--no-save", "--no-look", "--animation", "none"])
    ctx = B.build(args)
    B.activate_still(ctx)
    lines = C.edge_map(hide=("TeaHouse.Glass",))
    ref = C.load_image(os.path.join(ROOM, "Reference", "BG_ShanTeaHouse_Night.webp"),
                       size=(lines.shape[1], lines.shape[0]))
    C.overlay(ref, lines, out, dim=0.6)
    np.save(os.path.splitext(out)[0] + "_lines.npy", lines)
    print("overlay ->", out)


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(a)
