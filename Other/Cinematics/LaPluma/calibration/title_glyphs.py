"""
The glyphs of lines of type as the overlays set them (run in Blender, for ``fit_title.py``):

    blender -b --factory-startup -P title_glyphs.py -- <font file> <spacing> <out.npz> <text> [<text> ...]

Each text is set in the font at size 1 with the character spacing given, as ``Kit.overlays`` sets a line (Blender's own
text layout), filled and cut into triangles: ``<n>_points`` (x, y) and ``<n>_triangles`` (three point indices) for the
n-th text.
"""
import sys

import bpy
import numpy as np

arguments = sys.argv[sys.argv.index("--") + 1:]
font_path, spacing, out = arguments[0], float(arguments[1]), arguments[2]
font = bpy.data.fonts.load(font_path)
arrays = {}
for number, text in enumerate(arguments[3:]):
    curve = bpy.data.curves.new(f"Line {number}", "FONT")
    curve.font = font
    curve.body = text
    curve.size = 1.0
    curve.space_character = spacing
    curve.fill_mode = "BOTH"
    obj = bpy.data.objects.new(f"Line {number}", curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    mesh.calc_loop_triangles()
    points = np.array([vertex.co[:2] for vertex in mesh.vertices], np.float64)
    triangles = np.array([triangle.vertices[:] for triangle in mesh.loop_triangles], np.int32)
    arrays[f"{number}_points"] = points
    arrays[f"{number}_triangles"] = triangles
    print(f"[glyphs] '{text}': {len(points)} points, {len(triangles)} triangles", flush=True)
np.savez(out, **arrays)
