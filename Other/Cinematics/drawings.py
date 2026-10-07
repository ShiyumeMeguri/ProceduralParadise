"""
Drawings: flat artwork kept as data (``Drawings/<name>.json``) -- shapes, each a ``part`` of the drawing (its
``lettering`` or the rest of its ``artwork``) and its ``loops``, an outline and the holes in it, every loop of points
``[x, y, tone]`` in the picture's units -- made into a mesh of the shapes filled, each point carrying its ``tone`` (the
share of the artwork's brightest ink it is drawn in) and whether it is ``lettering``, for an overlay to ink
(``CIN.Overlay.Drawing``).
"""
from __future__ import annotations

import os

from mathutils.geometry import tessellate_polygon

from Core import jsonio

FOLDER = os.path.join(os.path.dirname(__file__), "Drawings")


def drawing_mesh(name, drawing):
    """The drawing ``drawing`` filled, as a new mesh ``name`` with the point attributes ``tone`` and ``lettering``."""
    import bpy
    path = os.path.join(FOLDER, f"{drawing}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no drawing '{drawing}' ({path})")
    points, tones, lettering, triangles = [], [], [], []
    for shape in jsonio.load(path)["shapes"]:
        loops = [[(x, y, 0.0) for x, y, _ in loop] for loop in shape["loops"]]
        start = len(points)
        triangles += [tuple(start + index for index in triangle) for triangle in tessellate_polygon(loops)]
        points += [point for loop in loops for point in loop]
        tones += [tone for loop in shape["loops"] for _, _, tone in loop]
        lettering += [1.0 if shape["part"] == "lettering" else 0.0] * sum(len(loop) for loop in loops)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], triangles)
    mesh.attributes.new("tone", "FLOAT", "POINT").data.foreach_set("value", tones)
    mesh.attributes.new("lettering", "FLOAT", "POINT").data.foreach_set("value", lettering)
    mesh.update()
    return mesh
