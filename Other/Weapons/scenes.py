"""
Weapons builder -- a small interpreter of a weapon's ``weapon.json``.

``build_scene(folder)`` puts up the studio of ``Weapons.json`` and builds
the weapon's parts; it knows no particular asset.  The file is pure data::

    {"id": "Scythe",
     "defaults": {"shot": "Sheet"},
     "sheet": {"origin": [u, v], "metres_per_unit": k},  (the drawing the weapon is measured on)
     "materials": {"color:housing": [r, g, b], ...},     (look parameters, palette overrides)
     "parts": {"Head": [part, ...], ...},                (one collection per group of parts)
     "lights": [lamp, ...],
     "views": {...}}                                     (free cameras, metres)

Everything is measured in the sheet's units -- pixels of the scanned design
sheet, ``k`` metres each: the sheet pixel ``(u, v)`` at depth ``y`` is the
point ``((u - u0) k, y k, (v0 - v) k)``, so the sheet looks along +Y with
its right +X and its up +Z.  Lengths given to assets (their ``DISTANCE``
inputs) are sheet units too.

A part is one object: ``name``, ``at`` ([u, y, v], default the origin),
``rot`` (degrees), ``outline`` and either an ``asset`` with its ``inputs``
or a ``stack`` of modifiers -- ``{"asset", "inputs"}`` or ``{"modifier":
TYPE, "settings": {...}}``.  The ``outline`` is the object's own mesh: the
strands its asset grows from, each the name of an outline in
``trace.json`` (``{"trace": name}`` or a list of names, each a list of
strands traced on the sheet), a list of sheet points (``{"points": [[u,
v], ...]}``, after them), and ``y``, the depth they lie at; every point
keeps its strand and the entry of the list it comes from.  Inputs are
written as data: degrees for angles, palette names for colours, library
names for materials.

A lamp is ``{"name", "light": "AREA" | "SUN" | "POINT" | "SPOT", "power",
"color", "size", "at" ([u, y, v]) and "target" ([u, y, v]), "diffuse",
"specular" (its factors), "twin"}``: a twin lamp has its mirror image in
the weapon's mid-plane Y = 0 as well, so the weapon -- the same on both
sides -- is lit the same from behind.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

from Core import jsonio, scene as SC, values as V
from Core.gn import get_asset
from . import PALETTE, STUDIO
from .Kit import materials as M, solids

__all__ = ["load_scene", "build_scene"]

WEAPON = "weapon.json"
TRACE = "trace.json"


def load_scene(folder):
    return jsonio.load(os.path.join(folder, WEAPON))


def _unique(created, name):
    if created.name != name:
        raise ValueError(f"'{name}' is not unique in the weapon (Blender named it '{created.name}')")
    return created


class Sheet:
    """The drawing a weapon is measured on: sheet units to metres."""

    def __init__(self, spec):
        self.u0, self.v0 = spec["origin"]
        self.scale = spec["metres_per_unit"]

    def point(self, u, v, y=0.0):
        return Vector(((u - self.u0) * self.scale, y * self.scale, (self.v0 - v) * self.scale))

    def at(self, value):
        u, y, v = value if value is not None else (self.u0, 0.0, self.v0)
        return self.point(u, v, y)


class WeaponBuilder:
    def __init__(self, folder):
        self.dir = folder
        self.data = load_scene(folder)
        self.id = self.data["id"]
        self.sheet = Sheet(self.data["sheet"])
        trace_path = os.path.join(folder, TRACE)
        self.traces = jsonio.load(trace_path) if os.path.exists(trace_path) else {}
        self.pending = []

    def build(self):
        scene = bpy.context.scene
        scene.name = self.id
        M.studio_world({**STUDIO["world"], **self.data.get("studio", {})})
        root = SC.collection(self.id)
        for name, parts in self.data.get("parts", {}).items():
            collection = _unique(SC.collection(f"{self.id}.{name}", parent=root), f"{self.id}.{name}")
            for part in parts:
                self.place(part, collection)
        lights = SC.collection(f"{self.id}.Lights", parent=root)
        for lamp in self.data.get("lights", []):
            self.lamp(lamp, lights)
            if lamp.get("twin"):
                u, y, v = lamp["at"]
                tu, ty, tv = lamp["target"]
                self.lamp({**lamp, "name": f"{lamp['name']} Twin", "at": [u, -y, v], "target": [tu, -ty, tv]}, lights)
        self.connect()
        return self

    def strands(self, spec):
        """The strands of an ``outline``: (entry, sheet points) pairs."""
        names = [spec["trace"]] if isinstance(spec.get("trace"), str) else spec.get("trace", [])
        found = []
        for entry, name in enumerate(names):
            if name not in self.traces:
                raise KeyError(f"no outline '{name}' in {TRACE}")
            found += [(entry, points) for points in self.traces[name]]
        if "points" in spec:
            found.append((len(names), spec["points"]))
        return found

    def outline_mesh(self, name, spec, origin):
        """Mesh of the points of an ``outline``, relative to the object's
        origin, each storing its strand and the entry it comes from."""
        vertices, strand, source = [], [], []
        depth = spec.get("y", 0.0)
        for index, (entry, points) in enumerate(self.strands(spec)):
            for u, v in points:
                vertices.append(tuple(self.sheet.point(u, v, depth) - origin))
                strand.append(index)
                source.append(entry)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], [])
        for attribute_name, values in ((solids.STRAND, strand), (solids.SOURCE, source)):
            mesh.attributes.new(attribute_name, "INT", "POINT").data.foreach_set("value", values)
        mesh.update()
        return mesh

    def place(self, part, collection):
        name = part["name"]
        origin = self.sheet.at(part.get("at"))
        mesh = self.outline_mesh(name, part["outline"], origin) if "outline" in part else bpy.data.meshes.new(name)
        obj = _unique(bpy.data.objects.new(name, mesh), name)
        collection.objects.link(obj)
        obj.location = origin
        obj.rotation_euler = [math.radians(angle) for angle in part.get("rot", (0.0, 0.0, 0.0))]
        for entry in part.get("stack") or [{"asset": part["asset"], "inputs": part.get("inputs", {})}]:
            self.modifier(obj, entry)
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
            socket = sockets[name]
            if socket.socket_type == "NodeSocketMaterial":
                result[name] = M.get(value)
            elif getattr(socket, "subtype", "") == "DISTANCE":
                result[name] = value * self.sheet.scale
            else:
                result[name] = V.socket_value(socket, value, PALETTE)
        return result

    def connect(self):
        for modifier, values in self.pending:
            SC.set_gn_inputs(modifier, self.converted(modifier.node_group, values))

    def lamp(self, item, collection):
        data = bpy.data.lights.new(item["name"], item["light"])
        data.energy = item["power"]
        data.color = tuple(PALETTE[item["color"]]) if isinstance(item.get("color"), str) else tuple(item.get("color", (1.0, 1.0, 1.0)))
        data.use_shadow_jitter = True
        data.diffuse_factor = item.get("diffuse", 1.0)
        data.specular_factor = item.get("specular", 1.0)
        if item["light"] == "AREA":
            data.shape = item.get("shape", "RECTANGLE")
            data.size, data.size_y = (value * self.sheet.scale for value in item["size"])
            data.spread = math.radians(item.get("spread", 180.0))
        obj = _unique(bpy.data.objects.new(item["name"], data), item["name"])
        collection.objects.link(obj)
        obj.location = self.sheet.at(item["at"])
        obj.rotation_euler = (self.sheet.at(item["target"]) - obj.location).to_track_quat("-Z", "Y").to_euler()
        if item.get("hidden"):
            obj.visible_camera = False
        return obj


def build_scene(folder):
    return WeaponBuilder(folder).build()
