"""
Shanhaijing emblem as geometry nodes.

``SHJ.Emblem`` -- the tea house mark: 山海經 in brush script with the
"Shan hai jing" romanisation inside an ensō brush circle.  The outlines were
traced on BG_ShanTeaHouse_Night after rectifying the logo wall onto its own
plane (the wall's pose was solved from four independent cues, see the
TeaHouse README), so the mark keeps its true proportions from any angle.
Data: ``Kit/data/shanhaijing_emblem.json`` (metres, origin = ensō centre,
XY plane, +Y up).
"""
from __future__ import annotations

import json
import os

from Core.gn import GN, asset
from .architecture import STAND

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "shanhaijing_emblem.json")


def load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


@asset("SHJ.Emblem", "Signage")
def emblem():
    """Shanhaijing tea house emblem, centred on the origin in the XZ plane,
    facing -Y, raised by Depth.  Diameter scales the traced mark."""
    E = load()
    g = GN("SHJ.Emblem", emblem.__doc__)
    dia = g.inp("Diameter", default=E["diameter"], subtype="DISTANCE")
    depth = g.inp("Depth", default=0.002, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    curves = [g.polyline([(x, y, 0.0) for x, y in E["ring"]], cyclic=True)]
    for gl in E["glyphs"]:
        if len(gl["pts"]) >= 3:
            curves.append(g.polyline([(x, y, 0.0) for x, y in gl["pts"]], cyclic=True))
    face = g.fill(g.join(*curves), mode="TRIANGLES")
    k = dia / E["diameter"]
    face = g.transform(face, s=g.vec(k, k, 1.0))
    body = g.extrude(face, depth, direction=(0, 0, 1))
    body = g.transform(body, r=STAND)
    g.result(g.mat(body, m))
    return g
