"""
Props scene builder -- a small interpreter of ``scene.json``.

``build_scene(scene_dir)`` puts up the studio of ``Props.json`` and places
the scene's objects; it knows no particular asset.  The file is pure data::

    {"id": "Slime", "fps": 24, "frames": [1, 300],
     "defaults": {"shot": "Hero"},
     "materials": {"color:backdrop": [r, g, b], ...},   (look parameters, palette overrides)
     "studio": {"subject": [x, y, z]},                    (where the studio lights aim)
     "collections": {"Slime": [item, ...], ...},
     "choreography": [...],                               (Props.choreography)
     "focus": "Slime"}                                    (the object the properties editor stays on)

An item is one object: ``name``, ``loc``, ``rot`` (degrees) or ``aim`` (the
direction its +Z points), ``scale`` and
either an ``asset`` with its ``inputs`` (one geometry-nodes modifier), a
``stack`` of modifiers -- ``{"asset", "inputs"}`` or ``{"modifier": TYPE,
"settings": {...}}`` -- or an ``empty`` (its display type, ``size``).
Inputs are written as data: degrees for angles, palette names for colours,
library names for materials, object and collection names for objects and
collections.  References are resolved once every object exists, so items may
point at each other; every name must be unique.

Props are simulations: every frame is played (no frame dropping), the 3D
views show the rendered look, and the scene's README.md comes along as the
text ``Guide``.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

from Core import jsonio, scene as SC, values as V
from Core.gn import get_asset
from . import PALETTE, PROPS, choreography
from .Kit import materials as M, studio

__all__ = ["load_scene", "build_scene"]

GUIDE = "Guide"


def load_scene(scene_dir):
    return jsonio.load(os.path.join(scene_dir, "scene.json"))


def _vector(value, default=(0.0, 0.0, 0.0)):
    return Vector([float(component) for component in (value if value is not None else default)])


def _rotation(item):
    """``rot`` (Euler degrees), or ``aim``: the direction the object's +Z points."""
    if "aim" in item:
        return _vector(item["aim"]).to_track_quat("Z", "Y").to_euler()
    return Vector([math.radians(angle) for angle in item.get("rot", (0.0, 0.0, 0.0))])


def _rgb(value):
    return tuple(PALETTE[value]) if isinstance(value, str) else tuple(value)


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
        scene.frame_start, scene.frame_end = self.data["frames"]
        scene.sync_mode = "NONE"
        rig = PROPS["studio"]
        studio.world(rig["world"])
        subject = _vector(self.data["studio"]["subject"])
        backdrop = SC.collection("Studio")
        for item in rig["items"]:
            self.place(item, backdrop)
        for item in rig["lights"]:
            self.lamp(item, subject, backdrop)
        for name, items in self.data.get("collections", {}).items():
            collection = _unique(SC.collection(name), name)
            for item in items:
                self.place(item, collection)
        self.connect()
        choreography.perform(self.data.get("choreography", []))
        self.present()
        scene.frame_set(scene.frame_start)
        return self

    def place(self, item, collection):
        name = item["name"]
        if "empty" in item:
            obj = SC.empty(name, _vector(item.get("loc")), _rotation(item), collection, item["empty"], item.get("size", 0.1))
        else:
            obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
            collection.objects.link(obj)
            obj.location = _vector(item.get("loc"))
            obj.rotation_euler = _rotation(item)
            for entry in item.get("stack") or [{"asset": item["asset"], "inputs": item.get("inputs", {})}]:
                self.modifier(obj, entry)
        _unique(obj, name)
        obj.scale = _vector(item.get("scale"), (1.0, 1.0, 1.0))
        return obj

    def modifier(self, obj, entry):
        if "asset" in entry:
            group = get_asset(entry["asset"])
            modifier = obj.modifiers.new(entry.get("name", entry["asset"].split(".")[-1]), "NODES")
            modifier.node_group = group
            self.pending.append((modifier, entry.get("inputs", {})))
            return modifier
        modifier = obj.modifiers.new(entry.get("name", entry["modifier"].title()), entry["modifier"])
        for key, value in entry.get("settings", {}).items():
            setattr(modifier, key, value)
        return modifier

    def converted(self, group, values):
        sockets = {entry.name: entry for entry in group.interface.items_tree
                   if getattr(entry, "in_out", None) == "INPUT" and entry.item_type == "SOCKET"}
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

    def lamp(self, item, subject, collection):
        data = bpy.data.lights.new(item["name"], item["light"])
        data.energy = item["power"]
        data.color = _rgb(item.get("color", (1.0, 1.0, 1.0)))
        data.use_shadow_jitter = True
        if item["light"] == "AREA":
            data.shape = item.get("shape", "RECTANGLE")
            data.size, data.size_y = item["size"]
            data.spread = math.radians(item.get("spread", 180.0))
        obj = _unique(bpy.data.objects.new(item["name"], data), item["name"])
        collection.objects.link(obj)
        obj.location = subject + _vector(item["offset"])
        obj.rotation_euler = (subject - obj.location).to_track_quat("-Z", "Y").to_euler()
        return obj

    def present(self):
        """The file as it opens: the guide, the rendered look in every 3D
        view and the properties editor held on the ``focus`` object's
        modifiers."""
        path = os.path.join(self.dir, "README.md")
        guide = bpy.data.texts.get(GUIDE) or bpy.data.texts.new(GUIDE)
        guide.clear()
        with open(path, encoding="utf-8") as handle:
            guide.write(handle.read())
        focus = bpy.data.objects[self.data["focus"]]
        bpy.context.view_layer.objects.active = focus
        focus.select_set(True)
        for screen in bpy.data.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "RENDERED"
                    elif space.type == "PROPERTIES":
                        space.pin_id = focus
                        space.use_pin_id = True
                        space.context = "MODIFIER"


def build_scene(scene_dir):
    return SceneBuilder(scene_dir).build()
