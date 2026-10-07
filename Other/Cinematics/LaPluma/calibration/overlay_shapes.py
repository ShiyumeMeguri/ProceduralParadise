"""
The shapes of a shot's overlay items as the shot draws them (run in Blender, for ``fit_overlays.py``):

    blender -b --factory-startup -P overlay_shapes.py -- <request.json> <out.npz>

The request lists items (``name``, ``asset``, ``inputs``, ``drawing``); each is built as the shot builds it
(``scenes``), its inputs less those that move it, and its mesh -- in the picture's units -- cut into triangles:
``<n>_points`` (x, y) and ``<n>_triangles`` (three point indices) for the n-th item.
"""
import json
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

from Cinematics import drawings as DR, scenes as SCN  # noqa: E402

MOVING = ("Slide In", "Slide Time", "Slide Ease", "Drift", "Slide Out", "Slide Out Time")

arguments = sys.argv[sys.argv.index("--") + 1:]
request = json.load(open(arguments[0], encoding="utf-8"))
collection = bpy.context.scene.collection
arrays = {}
for number, item in enumerate(request["items"]):
    name = f"Shape {number}"
    mesh = DR.drawing_mesh(name, item["drawing"]) if item.get("drawing") else bpy.data.meshes.new(name)
    inputs = {key: value for key, value in item.get("inputs", {}).items() if key not in MOVING}
    obj = SCN._modified_object(name, mesh, item["asset"], inputs, collection)
    bpy.context.view_layer.update()
    shape = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    shape.calc_loop_triangles()
    arrays[f"{number}_points"] = np.array([vertex.co[:2] for vertex in shape.vertices], np.float64)
    arrays[f"{number}_triangles"] = np.array([triangle.vertices[:] for triangle in shape.loop_triangles], np.int32)
    print(f"[shapes] {item['name']}: {len(shape.vertices)} points, {len(shape.loop_triangles)} triangles", flush=True)
np.savez(arguments[1], **arrays)
