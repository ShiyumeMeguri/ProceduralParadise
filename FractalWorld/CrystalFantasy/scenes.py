"""
Crystal Fantasy scene builder -- a small interpreter of ``scene.json``.

``build_scene(scene_dir)`` reads a scene folder and places kit assets and
lamps; it knows no particular asset.  The file is pure data::

    {"id": "Conservatory", "fps": 30,
     "defaults": {"shot": ..., "animation": ...},
     "world": {...},                               (Fractals.cosmos)
     "collections": {"Architecture": [item, ...], ...},
     "lights": [item, ...]}

An item places one asset (``asset``, ``inputs``, ``loc``, ``rot``,
``scale``) -- or, with a pattern, one object per copy:

    "at":        [[x, y, z(, turn)], ...]
    "ring":      {"center", "radius", "count", "start", "sweep", "face": "in" | "out"}
    "grid":      {"origin", "count": [nx, ny], "step": [dx, dy]}
    "line":      {"from", "to", "count"}
    "sunflower": {"center", "radius", "count", "inner", "start"}   (Vogel disc or annulus)

``inputs`` are the asset's group inputs (degrees for angles, palette names
for colours, library names for materials).  ``vary`` gives per-copy inputs:
``"index"`` (0, 1, 2 ...), ``[low, high]`` (uniform) or ``{"pick": [...]}``;
``turn`` (degrees about Z) and ``size`` (uniform scale) vary the placement
the same way, seeded by the item's name.  ``sway`` [degrees, seconds] hangs
a copy on a slow swing about its origin; ``visible`` sets ray visibility.

A lamp item is ``{"light": "AREA" | "POINT" | "SPOT" | "SUN", "power", "color",
"size", "radius", "angle", "blend", "target", "hidden"}`` with the same
placement keys.
"""
from __future__ import annotations

import math
import os
import random

import bpy
from mathutils import Vector

from Core import anim as ANIM, jsonio, scene as SC
from Core.gn import get_asset
from Fractals import cosmos
from Fractals.phyllotaxis import GOLDEN_ANGLE
from . import PALETTE
from .Kit import materials as M
from .values import socket_value

__all__ = ["load_scene", "build_scene"]


def load_scene(scene_dir):
    return jsonio.load(os.path.join(scene_dir, "scene.json"))


def _vector(value):
    return Vector([float(component) for component in value])


def _rgb(value):
    return tuple(PALETTE[value]) if isinstance(value, str) else tuple(value)


def _at(spec):
    return [(_vector(entry[:3]), math.radians(entry[3]) if len(entry) > 3 else 0.0) for entry in spec]


def _ring(spec):
    center = _vector(spec["center"])
    count = spec["count"]
    sweep = spec.get("sweep", 360.0)
    steps = count if sweep >= 360.0 else max(count - 1, 1)
    face = {"in": math.pi * 0.5, "out": math.pi * -0.5}.get(spec.get("face"))
    placements = []
    for index in range(count):
        angle = math.radians(spec.get("start", 0.0) + sweep * index / steps)
        location = center + Vector((math.cos(angle), math.sin(angle), 0.0)) * spec["radius"]
        placements.append((location, angle + face if face is not None else 0.0))
    return placements


def _grid(spec):
    origin = _vector(spec["origin"])
    columns, rows = spec["count"]
    step_x, step_y = spec["step"]
    return [(origin + Vector((column * step_x, row * step_y, 0.0)), 0.0)
            for row in range(rows) for column in range(columns)]


def _line(spec):
    start, end = _vector(spec["from"]), _vector(spec["to"])
    count = spec["count"]
    return [(start.lerp(end, index / max(count - 1, 1)), 0.0) for index in range(count)]


def _sunflower(spec):
    center = _vector(spec["center"])
    count = spec["count"]
    inner = spec.get("inner", 0.0)
    outer = spec["radius"]
    placements = []
    for index in range(count):
        t = (index + 0.5) / count
        reach = math.sqrt(inner * inner + t * (outer * outer - inner * inner))
        angle = index * GOLDEN_ANGLE + math.radians(spec.get("start", 0.0))
        placements.append((center + Vector((math.cos(angle), math.sin(angle), 0.0)) * reach, 0.0))
    return placements


PATTERNS = {"at": _at, "ring": _ring, "grid": _grid, "line": _line, "sunflower": _sunflower}


def placements(item):
    for key, expand in PATTERNS.items():
        if key in item:
            return expand(item[key])
    return [(_vector(item.get("loc", (0.0, 0.0, 0.0))), 0.0)]


def _draw(rule, index, generator):
    if rule == "index":
        return index
    if isinstance(rule, dict) and "cycle" in rule:
        return rule["cycle"][index % len(rule["cycle"])]
    if isinstance(rule, dict):
        return generator.choice(rule["pick"])
    return generator.uniform(rule[0], rule[1])


def _rotation(value):
    if value is None:
        return Vector((0.0, 0.0, 0.0))
    if isinstance(value, (int, float)):
        return Vector((0.0, 0.0, math.radians(value)))
    return Vector([math.radians(angle) for angle in value])


def _scale(value):
    if value is None:
        return Vector((1.0, 1.0, 1.0))
    if isinstance(value, (int, float)):
        return Vector((value, value, value))
    return _vector(value)


class SceneBuilder:
    def __init__(self, scene_dir):
        self.data = load_scene(scene_dir)
        self.id = self.data["id"]
        self.root = SC.collection(f"SCENE_{self.id}")
        self.fps = self.data.get("fps", 24)
        self.names = {}

    def name(self, base):
        count = self.names.get(base, 0)
        self.names[base] = count + 1
        return base if count == 0 else f"{base}.{count:03d}"

    def build(self):
        bpy.context.scene.render.fps = self.fps
        bpy.context.scene.render.fps_base = 1.0
        cosmos.build_world(self.data["world"])
        for collection_name, items in self.data.get("collections", {}).items():
            collection = SC.collection(f"{self.id}.{collection_name}", parent=self.root)
            for item in items:
                self.place(item, collection)
        lights = SC.collection(f"{self.id}.Lights", parent=self.root)
        for item in self.data.get("lights", []):
            self.lamp(item, lights)
        return self

    def converted(self, group, values):
        sockets = {entry.name: entry for entry in group.interface.items_tree
                   if getattr(entry, "in_out", None) == "INPUT" and entry.item_type == "SOCKET"}
        result = {}
        for name, value in values.items():
            if name not in sockets:
                raise KeyError(f"{group.name}: no input '{name}'. Inputs: {list(sockets)}")
            socket = sockets[name]
            if socket.socket_type == "NodeSocketMaterial":
                result[name] = M.get(value)
            else:
                result[name] = socket_value(socket, value)
        return result

    def place(self, item, collection):
        group = get_asset(item["asset"])
        base = item.get("name", item["asset"].split(".")[-1])
        generator = random.Random(f"{self.id}/{base}")
        spots = placements(item)
        for index, (location, turn) in enumerate(spots):
            values = dict(item.get("inputs", {}))
            for name, rule in item.get("vary", {}).items():
                values[name] = _draw(rule, index, generator)
            rotation = _rotation(item.get("rot"))
            rotation.z += turn + math.radians(_draw(item["turn"], index, generator) if "turn" in item else 0.0)
            scale = _scale(item.get("scale")) * (_draw(item["size"], index, generator) if "size" in item else 1.0)
            obj = SC.gn_object(self.name(f"{self.id}.{base}"), group, self.converted(group, values),
                               location=location, rotation=rotation, scale=scale, collection=collection)
            for ray, visible in item.get("visible", {}).items():
                setattr(obj, f"visible_{ray}", visible)
            if "sway" in item:
                angle, period = item["sway"]
                ANIM.sway(obj, math.radians(angle), period, self.fps, seed=index + len(self.names))

    def lamp(self, item, collection):
        base = item.get("name", item["light"].title())
        for location, turn in placements(item):
            data = bpy.data.lights.new(base, item["light"])
            data.energy = item["power"]
            data.color = _rgb(item.get("color", (1.0, 1.0, 1.0)))
            if item["light"] == "AREA":
                data.shape = "RECTANGLE"
                data.size, data.size_y = item.get("size", (1.0, 1.0))
                data.spread = math.radians(item.get("spread", 180.0))
            elif item["light"] == "SPOT":
                data.spot_size = math.radians(item.get("angle", 45.0))
                data.spot_blend = item.get("blend", 0.5)
            if item["light"] in ("POINT", "SPOT"):
                data.shadow_soft_size = item.get("radius", 0.1)
            obj = bpy.data.objects.new(self.name(f"{self.id}.{base}"), data)
            collection.objects.link(obj)
            obj.location = location
            if "target" in item:
                obj.rotation_euler = (_vector(item["target"]) - location).to_track_quat("-Z", "Y").to_euler()
            else:
                obj.rotation_euler = _rotation(item.get("rot"))
                obj.rotation_euler.z += turn
            if item.get("hidden"):
                for ray in ("camera", "glossy", "transmission"):
                    setattr(obj, f"visible_{ray}", False)


def build_scene(scene_dir):
    return SceneBuilder(scene_dir).build()
