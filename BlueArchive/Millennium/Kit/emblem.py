"""
Millennium emblem and signage lettering as geometry nodes.

* ``MIL.Emblem``  -- the slanted "7 + Pi" school mark, 1 m tall, centred,
  lying in the XY plane (+Y up), extruded along +Z.
* ``MIL.Wordmark`` -- the letter-spaced "MILLENNIUM" wordmark built from a
  tiny stroke font (only the glyphs the academy signage needs), 1 m cap height.

Vertex data was read off BG_Milleniumclub (logo at ~1:7 zoom) and regularised.
"""
from __future__ import annotations

from Core.gn import GN, asset

# emblem outline points in reference pixels (image x right, y down)
_EMB_BBOX = (903.3, 387.9, 994.3, 459.3)   # x0, y0, x1, y1
_SEVEN = [(903.3, 391.7), (953.6, 390.0), (919.7, 459.3), (910.4, 447.9),
          (927.1, 408.3), (913.9, 408.3)]
_PI = [(959.3, 390.0), (993.9, 387.9), (994.3, 405.7), (967.1, 458.6), (958.3, 447.1),
       (977.1, 406.4), (969.3, 406.4), (942.9, 458.9), (933.6, 445.0)]


def _to_emblem(pts):
    x0, y0, x1, y1 = _EMB_BBOX
    cx, cy, s = (x0 + x1) * 0.5, (y0 + y1) * 0.5, (y1 - y0)
    return [((x - cx) / s, -(y - cy) / s, 0.0) for x, y in pts]


SEVEN = _to_emblem(_SEVEN)
PI = _to_emblem(_PI)
EMBLEM_ASPECT = (_EMB_BBOX[2] - _EMB_BBOX[0]) / (_EMB_BBOX[3] - _EMB_BBOX[1])


@asset("MIL.Emblem", "Signage")
def emblem():
    """Millennium school mark (1 m tall, centred at origin, XY plane)."""
    g = GN("MIL.Emblem", emblem.__doc__)
    depth = g.inp("Depth", default=0.0, subtype="DISTANCE",
                  desc="Extrusion along +Z (0 = flat)")
    m = g.inp("Material", "MATERIAL")
    shapes = g.join(g.polyline(SEVEN, cyclic=True), g.polyline(PI, cyclic=True))
    face = g.fill(shapes, mode="TRIANGLES")
    solid = g.extrude(face, depth, direction=(0, 0, 1))
    has = g.compare(depth, 0.00001, "GREATER_THAN")
    out = g.switch(has, face, solid)
    g.result(g.mat(out, m))
    return g


# ---------------------------------------------------------------- stroke font
# Glyphs: list of polylines in a box of width w and cap height 1.
GLYPHS = {
    "M": (0.74, [[(0, 0), (0, 1), (0.37, 0.38), (0.74, 1), (0.74, 0)]]),
    "I": (0.0, [[(0, 0), (0, 1)]]),
    "L": (0.46, [[(0, 1), (0, 0), (0.46, 0)]]),
    "E": (0.48, [[(0.48, 1), (0, 1), (0, 0), (0.48, 0)], [(0, 0.5), (0.42, 0.5)]]),
    "N": (0.6, [[(0, 0), (0, 1), (0.6, 0), (0.6, 1)]]),
    "U": (0.6, [[(0, 1), (0, 0.16), (0.1, 0), (0.5, 0), (0.6, 0.16), (0.6, 1)]]),
    " ": (0.4, []),
}


def layout_text(text, tracking=0.28):
    """Return (polylines, total_width) for ``text`` in cap-height units,
    horizontally centred on x = 0, baseline at y = -0.5 (so the block is
    centred vertically too)."""
    x = 0.0
    lines = []
    for ch in text.upper():
        w, strokes = GLYPHS[ch]
        for s in strokes:
            lines.append([(x + px, py) for px, py in s])
        x += w + tracking
    width = x - tracking
    out = [[(px - width * 0.5, py - 0.5, 0.0) for px, py in s] for s in lines]
    return out, width


@asset("MIL.Wordmark", "Signage")
def wordmark():
    """'MILLENNIUM' wordmark, 1 m cap height, centred at origin (XY plane)."""
    g = GN("MIL.Wordmark", wordmark.__doc__)
    weight = g.inp("Stroke Weight", default=0.13, desc="stroke width / cap height")
    m = g.inp("Material", "MATERIAL")
    lines, width = layout_text("MILLENNIUM")
    curves = [g.polyline(l) for l in lines]
    crv = g.join(*curves)
    crv = g.n("GeometryNodeSetCurveNormal", crv, props={"mode": "Z_UP"}).o \
        if _has_z_up() else crv
    prof = g.rect(weight, 0.002)
    ribbon = g.sweep(crv, prof, True)
    g.result(g.mat(ribbon, m))
    return g


def _has_z_up():
    import bpy
    ng = bpy.data.node_groups.new("__probe", "GeometryNodeTree")
    try:
        n = ng.nodes.new("GeometryNodeSetCurveNormal")
        ok = "Z_UP" in [i.identifier for i in n.bl_rna.properties["mode"].enum_items]
    except Exception:
        ok = False
    bpy.data.node_groups.remove(ng)
    return ok


WORDMARK_WIDTH = layout_text("MILLENNIUM")[1]
