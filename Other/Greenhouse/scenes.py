"""
Greenhouse scene builder -- a small interpreter of ``scene.json``.

``build_scene(scene_dir)`` makes the sky, places the scene's objects and
lamps; it knows no particular asset.  The file is pure data::

    {"id": "GlassAtrium", "fps": 24,
     "defaults": {"shot": "..."},
     "materials": {"color:steel": [r, g, b], ...},    (look parameters, palette overrides)
     "sky": {...},                                     (Kit.materials.world)
     "library": {"Shrubs": [item, ...], ...},          (prototypes: built, never rendered)
     "collections": {"Frame": [item, ...], ...},
     "lights": [lamp, ...]}

An item is one object: ``name``, ``loc``, ``rot`` (degrees) or ``aim``
(the direction its +Z points), ``scale``, an optional data ``mesh`` the
object starts from, and either an ``asset`` with its ``inputs`` (one
geometry-nodes modifier) or a ``stack`` of modifiers -- ``{"asset",
"inputs"}`` or ``{"modifier": TYPE, "settings": {...}}``.  A ``preset``
(a plant of ``Greenhouse.json``) supplies inputs the item may override.

A data mesh is written as any of::

    "vertices": [[x, y, z], ...], "edges": [[i, j], ...], "faces": [[i, j, k, ...], ...]
    "segments": [[[x, y, z], [x, y, z]], ...]                      (loose edges)
    "polyline": [[x, y, z], ...]                                   (a chain of edges)
    "grid": {"plane": "XY" | "XZ" | "YZ", "u": [...], "v": [...], "w": w,
             "edges": true, "faces": true}                         (lines at the listed coordinates)

so a frame is a list of lines and a glazing grid a list of mullion
positions.  With ``at`` -- ``[[x, y, z(, turn)], ...]`` -- an item is
copied to every spot; ``vary`` gives per-copy inputs (``[low, high]``
uniform, ``{"pick": [...]}``, ``{"cycle": [...]}`` or ``"index"``) and
``turn`` / ``size`` vary the placement the same way, seeded by the name.

Inputs are written as data: degrees for angles, palette names for colours,
library names for materials, object and collection names for objects and
collections.  A ``library`` collection holds prototypes that planting
scatters (``GH.Garden.Planting`` names it as ``<id>.<name>``); it is
excluded from the view layer, so only its instances are seen.

A lamp is ``{"name", "light": "SUN" | "AREA" | "POINT" | "SPOT", "power",
"color", "angle" (sun disc, degrees), "size", "loc", and its aim: "target"
(a point), "direction" (towards the light) or "rot"; "hidden"}``.
"""
from __future__ import annotations

import math
import os
import random

import bpy
from mathutils import Vector

from Core import jsonio, scene as SC, values as V
from Core.gn import get_asset
from . import PALETTE, PLANTS
from .Kit import materials as M

__all__ = ["load_scene", "build_scene", "data_mesh"]

PLANES = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (1, 2, 0)}


def load_scene(scene_dir):
    return jsonio.load(os.path.join(scene_dir, "scene.json"))


def _vector(value, default=(0.0, 0.0, 0.0)):
    return Vector([float(component) for component in (value if value is not None else default)])


def _rotation(item, turn=0.0):
    if "aim" in item:
        rotation = _vector(item["aim"]).to_track_quat("Z", "Y").to_euler()
    else:
        rotation = Vector([math.radians(angle) for angle in item.get("rot", (0.0, 0.0, 0.0))])
    rotation.z += turn
    return rotation


def _scale(value):
    if value is None:
        return Vector((1.0, 1.0, 1.0))
    if isinstance(value, (int, float)):
        return Vector((value, value, value))
    return _vector(value)


def _rgb(value):
    return tuple(PALETTE[value]) if isinstance(value, str) else tuple(value)


def _grid(spec, vertices, edges, faces):
    u_axis, v_axis, w_axis = PLANES[spec.get("plane", "XY")]
    us, vs = spec["u"], spec["v"]
    start = len(vertices)
    for v in vs:
        for u in us:
            point = [0.0, 0.0, 0.0]
            point[u_axis], point[v_axis], point[w_axis] = u, v, spec.get("w", 0.0)
            vertices.append(point)

    def index(i, j):
        return start + j * len(us) + i

    if spec.get("edges", True):
        edges += [(index(i, j), index(i + 1, j)) for j in range(len(vs)) for i in range(len(us) - 1)]
        edges += [(index(i, j), index(i, j + 1)) for j in range(len(vs) - 1) for i in range(len(us))]
    if spec.get("faces", False):
        faces += [(index(i, j), index(i + 1, j), index(i + 1, j + 1), index(i, j + 1))
                  for j in range(len(vs) - 1) for i in range(len(us) - 1)]


def data_mesh(name, spec):
    """Mesh data-block from a data mesh ``spec`` (see the module notes)."""
    vertices = [list(map(float, vertex)) for vertex in spec.get("vertices", [])]
    edges = [tuple(edge) for edge in spec.get("edges", [])]
    faces = [tuple(face) for face in spec.get("faces", [])]
    for first, second in spec.get("segments", []):
        edges.append((len(vertices), len(vertices) + 1))
        vertices += [list(map(float, first)), list(map(float, second))]
    if "polyline" in spec:
        start = len(vertices)
        vertices += [list(map(float, point)) for point in spec["polyline"]]
        edges += [(start + index, start + index + 1) for index in range(len(spec["polyline"]) - 1)]
    for grid in spec.get("grids", [spec["grid"]] if "grid" in spec else []):
        _grid(grid, vertices, edges, faces)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, edges if not faces else [edge for edge in edges if not _in_faces(edge, faces)], faces)
    mesh.update()
    return mesh


def _in_faces(edge, faces):
    for face in faces:
        count = len(face)
        for index in range(count):
            if {face[index], face[(index + 1) % count]} == set(edge):
                return True
    return False


def _draw(rule, index, generator):
    if rule == "index":
        return index
    if isinstance(rule, dict) and "cycle" in rule:
        return rule["cycle"][index % len(rule["cycle"])]
    if isinstance(rule, dict):
        return generator.choice(rule["pick"])
    return generator.uniform(rule[0], rule[1])


def _unique(created, name):
    if created.name != name:
        raise ValueError(f"'{name}' is not unique in the scene (Blender named it '{created.name}')")
    return created


class SceneBuilder:
    def __init__(self, scene_dir):
        self.dir = scene_dir
        self.data = load_scene(scene_dir)
        self.id = self.data["id"]
        self.pending = []

    def build(self):
        scene = bpy.context.scene
        scene.name = self.id
        scene.render.fps = self.data.get("fps", 24)
        scene.render.fps_base = 1.0
        M.world(self.data["sky"])
        root = SC.collection(self.id)
        for name, items in self.data.get("library", {}).items():
            collection = _unique(SC.collection(f"{self.id}.{name}", parent=root), f"{self.id}.{name}")
            for item in items:
                self.place(item, collection)
            self.exclude(collection)
        for name, items in self.data.get("collections", {}).items():
            collection = _unique(SC.collection(f"{self.id}.{name}", parent=root), f"{self.id}.{name}")
            for item in items:
                self.place(item, collection)
        lights = SC.collection(f"{self.id}.Lights", parent=root)
        for item in self.data.get("lights", []):
            self.lamp(item, lights)
        self.connect()
        return self

    @staticmethod
    def exclude(collection):
        def walk(layer):
            if layer.collection == collection:
                layer.exclude = True
                return True
            return any(walk(child) for child in layer.children)
        walk(bpy.context.view_layer.layer_collection)

    def spots(self, item):
        if "at" not in item:
            return [(_vector(item.get("loc")), 0.0)]
        return [(_vector(entry[:3]), math.radians(entry[3]) if len(entry) > 3 else 0.0) for entry in item["at"]]

    def place(self, item, collection):
        spots = self.spots(item)
        generator = random.Random(f"{self.id}/{item['name']}")
        for index, (location, turn) in enumerate(spots):
            name = item["name"] if len(spots) == 1 else f"{item['name']}.{index:03d}"
            mesh = data_mesh(name, item["mesh"]) if "mesh" in item else bpy.data.meshes.new(name)
            obj = _unique(bpy.data.objects.new(name, mesh), name)
            collection.objects.link(obj)
            obj.location = location
            extra_turn = math.radians(_draw(item["turn"], index, generator)) if "turn" in item else 0.0
            obj.rotation_euler = _rotation(item, turn + extra_turn)
            obj.scale = _scale(item.get("scale")) * (_draw(item["size"], index, generator) if "size" in item else 1.0)
            varied = {key: _draw(rule, index, generator) for key, rule in item.get("vary", {}).items()}
            for entry in item.get("stack") or [{"asset": item["asset"], "inputs": item.get("inputs", {}), "preset": item.get("preset")}]:
                self.modifier(obj, entry, varied)
            for ray, visible in item.get("visible", {}).items():
                setattr(obj, f"visible_{ray}", visible)

    def modifier(self, obj, entry, varied):
        if "asset" in entry:
            group = get_asset(entry["asset"])
            modifier = obj.modifiers.new(entry.get("name", entry["asset"].split(".")[-1]), "NODES")
            modifier.node_group = group
            values = dict(PLANTS[entry["preset"]]) if entry.get("preset") else {}
            values.update(entry.get("inputs", {}))
            values.update({key: value for key, value in varied.items() if key in self.inputs(group)})
            self.pending.append((modifier, values))
            return modifier
        modifier = obj.modifiers.new(entry.get("name", entry["modifier"].title()), entry["modifier"])
        for key, value in entry.get("settings", {}).items():
            setattr(modifier, key, value)
        return modifier

    @staticmethod
    def inputs(group):
        return {entry.name: entry for entry in group.interface.items_tree
                if getattr(entry, "in_out", None) == "INPUT" and entry.item_type == "SOCKET"}

    def converted(self, group, values):
        sockets = self.inputs(group)
        result = {}
        for name, value in values.items():
            if name not in sockets:
                raise KeyError(f"{group.name}: no input '{name}'. Inputs: {list(sockets)}")
            kind = sockets[name].socket_type
            if kind == "NodeSocketObject":
                result[name] = bpy.data.objects[value]
            elif kind == "NodeSocketCollection":
                result[name] = bpy.data.collections[value]
            elif kind == "NodeSocketMaterial":
                result[name] = M.get(value)
            else:
                result[name] = V.socket_value(sockets[name], value, PALETTE)
        return result

    def connect(self):
        for modifier, values in self.pending:
            SC.set_gn_inputs(modifier, self.converted(modifier.node_group, values))

    def lamp(self, item, collection):
        data = bpy.data.lights.new(item["name"], item["light"])
        data.energy = item["power"]
        data.color = _rgb(item.get("color", (1.0, 1.0, 1.0)))
        if item["light"] == "SUN":
            data.angle = math.radians(item.get("angle", 0.53))
        elif item["light"] == "AREA":
            data.shape = item.get("shape", "RECTANGLE")
            data.size, data.size_y = item.get("size", (1.0, 1.0))
            data.spread = math.radians(item.get("spread", 180.0))
        elif item["light"] == "SPOT":
            data.spot_size = math.radians(item.get("spot", 45.0))
            data.spot_blend = item.get("blend", 0.5)
        if item["light"] in ("POINT", "SPOT"):
            data.shadow_soft_size = item.get("radius", 0.1)
        obj = _unique(bpy.data.objects.new(item["name"], data), item["name"])
        collection.objects.link(obj)
        obj.location = _vector(item.get("loc"))
        if "target" in item:
            obj.rotation_euler = (_vector(item["target"]) - obj.location).to_track_quat("-Z", "Y").to_euler()
        elif "direction" in item:
            obj.rotation_euler = (-_vector(item["direction"])).to_track_quat("-Z", "Y").to_euler()
        else:
            obj.rotation_euler = _rotation(item)
        if item.get("hidden"):
            for ray in ("camera", "glossy", "transmission"):
                setattr(obj, f"visible_{ray}", False)
        return obj


def build_scene(scene_dir):
    return SceneBuilder(scene_dir).build()
