"""
Collision check for the TeaHouse camera animation: builds the room with the
animation, samples the camera position on every frame and reports the
clearance to the nearest rendered surface (BVH of every evaluated mesh).

    python BlueArchive/Shanhaijing/Rooms/TeaHouse/calibration/path_check.py [--animation Showcase] [--min 0.3]

Prints the closest approach per key segment and every frame below ``--min``
metres (exit status 1 if there is one).  Runs in Blender's Python or with the
``bpy`` module.
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


def main(argv):
    import bpy
    from mathutils.bvhtree import BVHTree
    import build as B
    anim = argv[argv.index("--animation") + 1] if "--animation" in argv else "Showcase"
    limit = float(argv[argv.index("--min") + 1]) if "--min" in argv else 0.3
    ctx = B.build(B.parse(["x", "Shanhaijing/Rooms/TeaHouse", "--no-save", "--no-look", "--animation", anim]))
    sc = ctx["scene"]
    a = ctx["animation"]
    cam = a["camera"]
    dg = bpy.context.evaluated_depsgraph_get()
    trees = []
    for ob in sc.objects:
        if ob.type != "MESH" or ob.hide_render:
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        if len(me.polygons):
            verts = [ev.matrix_world @ v.co for v in me.vertices]
            polys = [tuple(p.vertices) for p in me.polygons]
            trees.append((ob.name, BVHTree.FromPolygons(verts, polys)))
        ev.to_mesh_clear()
    keys = [k["frame"] for k in a["spec"]["keys"]]
    worst = {}
    bad = []
    for f in range(min(keys), max(keys) + 1):
        sc.frame_set(f)
        p = cam.matrix_world.translation.copy()
        best = (1e9, "")
        for name, t in trees:
            hit = t.find_nearest(p, best[0])
            if hit[0] is not None and hit[3] < best[0]:
                best = (hit[3], name)
        seg = max(k for k in keys if k <= f)
        if seg not in worst or best[0] < worst[seg][0]:
            worst[seg] = (best[0], best[1], f, tuple(round(c, 2) for c in p))
        if best[0] < limit:
            bad.append((f, round(best[0], 3), best[1]))
    for seg in sorted(worst):
        d, name, f, p = worst[seg]
        print(f"from key {seg:4d}: closest {d:.2f} m to {name} at frame {f} {p}")
    for f, d, name in bad:
        print(f"  frame {f}: {d} m to {name}")
    print("OK" if not bad else f"{len(bad)} frames closer than {limit} m")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
