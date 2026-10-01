"""
Greenhouse scene builder -- a small interpreter of ``scene.json``.

``build_scene(scene_dir)`` makes the sky, places the scene's objects and
lamps; it knows no particular asset.  The file is pure data::

    {"id": "GlassAtrium", "fps": 24,
     "defaults": {"shot": "..."},
     "materials": {"color:steel": [r, g, b], ...},    (look parameters, palette overrides)
     "sky": {...},                                     (Kit.materials.world)
     "library": {"Shrubs": [item, ...], ...},          (prototypes: built, never rendered)
     "volumes": {"Hall": {...}, ...},                  (glasshouse volumes the meshes of items refer to)
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
             "edges": true, "faces": true, "skip": [[i, j], ...]}  (lines at the listed coordinates; no face in the skipped cells)
    "file": "data/plan.json", "key": "beds"                        (vertices and faces from a data file of the scene)
    "volume": "Hall"                                               (the frame or the glazing of a glasshouse volume)
    "plinth": {"outline": [[x, y], ...], "top": z, "bottom": z,
               "batter": b}                                        (a solid of ground: top, sloping sides, base)

so a frame is a list of lines and a glazing grid a list of mullion
positions.  A glasshouse volume (``"volumes"``) is a box of glass on
``x`` x ``y`` from ``z[0]`` (its foot) to ``z[1]`` (its eaves): mullions
at ``xs`` / ``ys`` (or every ``bay``), transoms at ``transoms``, a roof
either flat (no ``pitch``) or a gable of ``pitch`` degrees whose ridge runs
along ``ridge`` ("x" or "y") with ``purlins`` rows of glazing bars a slope,
and the gable ends filled up to the roof; ``walls`` names the sides it has
("north", "south", "east", "west" -- a side against another volume is
left out), ``openings`` the doorways in them (``{"east": [[bay, row], ...]}``:
the glazing left out of those cells, counted from the south or west end and
from the foot) and ``gables`` the ends whose triangles it fills; a roof set
on walls built otherwise leaves out its eaves (``"eaves": false``), the
top rail of those walls.  Its frame
(``"edges"``) and its glazing (``"faces"``) are two items built from the
one volume, every bar and pane once.  A plinth's sides lean out by
``batter`` metres a metre of height, its outline convex.  With ``at`` -- ``[[x, y, z(, turn)], ...]`` -- an item is
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


def _patch(rows, vertices, edges, faces, with_edges=True, with_faces=False, skip=()):
    """A sheet of quads over ``rows`` (a list of rows of points): an edge
    between neighbouring points, a face over every cell but the ``skip``
    cells (``(column, row)`` pairs)."""
    start = len(vertices)
    columns = len(rows[0])
    for row in rows:
        vertices += [list(point) for point in row]

    def index(i, j):
        return start + j * columns + i

    if with_edges:
        edges += [(index(i, j), index(i + 1, j)) for j in range(len(rows)) for i in range(columns - 1)]
        edges += [(index(i, j), index(i, j + 1)) for j in range(len(rows) - 1) for i in range(columns)]
    if with_faces:
        skipped = {tuple(cell) for cell in skip}
        faces += [(index(i, j), index(i + 1, j), index(i + 1, j + 1), index(i, j + 1))
                  for j in range(len(rows) - 1) for i in range(columns - 1) if (i, j) not in skipped]


def _grid(spec, vertices, edges, faces):
    u_axis, v_axis, w_axis = PLANES[spec.get("plane", "XY")]
    rows = []
    for v in spec["v"]:
        row = []
        for u in spec["u"]:
            point = [0.0, 0.0, 0.0]
            point[u_axis], point[v_axis], point[w_axis] = u, v, spec.get("w", 0.0)
            row.append(point)
        rows.append(row)
    _patch(rows, vertices, edges, faces, spec.get("edges", True), spec.get("faces", False), spec.get("skip", ()))


def _stations(low, high, spec, key, bay):
    """Positions from ``low`` to ``high``: the listed ``spec[key]`` or every
    ``bay`` (rounded to whole bays)."""
    if key in spec:
        return [float(value) for value in spec[key]]
    count = max(int(math.ceil((high - low) / bay - 1e-6)), 1)
    return [low + (high - low) * index / count for index in range(count + 1)]


def _volume(spec, with_edges, with_faces):
    """Vertices, edges and faces of a glasshouse volume (see the module
    notes), every coincident point and edge once."""
    x0, x1 = spec["x"]
    y0, y1 = spec["y"]
    foot, eaves = spec["z"]
    bay = spec.get("bay", 2.0)
    xs = _stations(x0, x1, spec, "xs", bay)
    ys = _stations(y0, y1, spec, "ys", bay)
    heights = [foot] + [float(z) for z in spec.get("transoms", [])] + [eaves]
    pitch = math.radians(spec.get("pitch", 0.0))
    ridge = spec.get("ridge", "y")
    walls = spec.get("walls", ["north", "south", "east", "west"])
    ends = ("north", "south") if ridge == "y" else ("east", "west")
    gables = spec.get("gables", [wall for wall in walls if wall in ends]) if pitch > 0.0 else []
    middle = (x0 + x1) * 0.5 if ridge == "y" else (y0 + y1) * 0.5
    half = (x1 - x0) * 0.5 if ridge == "y" else (y1 - y0) * 0.5
    rise = math.tan(pitch) * half

    def roof(across):
        return eaves + rise * (1.0 - abs(across - middle) / half)

    sides = {"south": ("x", xs, y0), "north": ("x", xs, y1), "west": ("y", ys, x0), "east": ("y", ys, x1)}

    def point(axis, along, at, z):
        return (along, at, z) if axis == "x" else (at, along, z)

    patches = []
    openings = spec.get("openings", {})
    for wall in walls:
        axis, stations, at = sides[wall]
        patches.append(([[point(axis, along, at, z) for along in stations] for z in heights], openings.get(wall, ())))
    for wall in gables:
        axis, stations, at = sides[wall]
        across = sorted(set(stations) | {middle})
        patches.append(([[point(axis, along, at, eaves) for along in across],
                         [point(axis, along, at, roof(along)) for along in across]], ()))
    rows = spec.get("purlins", 4)
    if pitch > 0.0:
        for edge in (x0, x1) if ridge == "y" else (y0, y1):
            if ridge == "y":
                patches.append(([[(edge + (middle - edge) * row / rows, along, eaves + rise * row / rows) for along in ys]
                                 for row in range(rows + 1)], ()))
            else:
                patches.append(([[(along, edge + (middle - edge) * row / rows, eaves + rise * row / rows) for along in xs]
                                 for row in range(rows + 1)], ()))
    elif spec.get("roof", True):
        patches.append(([[(x, y, eaves) for x in xs] for y in ys], ()))
    vertices, edges, faces = [], [], []
    for rows_of_points, skip in patches:
        _patch(rows_of_points, vertices, edges, faces, with_edges, with_faces, skip)
    vertices, edges, faces = _merged(vertices, edges, faces)
    if not spec.get("eaves", True):
        def on_eaves(index):
            x, y, z = vertices[index]
            return abs(z - eaves) < 1e-5 and (min(abs(x - x0), abs(x - x1)) < 1e-5 or min(abs(y - y0), abs(y - y1)) < 1e-5)
        edges = [edge for edge in edges if not (on_eaves(edge[0]) and on_eaves(edge[1]))]
    return vertices, edges, faces


def _merged(vertices, edges, faces):
    """The mesh with coincident points made one, and the edges and faces
    that this leaves doubled or collapsed dropped."""
    keys, merged, remap = {}, [], []
    for vertex in vertices:
        key = tuple(round(component, 5) for component in vertex)
        if key not in keys:
            keys[key] = len(merged)
            merged.append(list(vertex))
        remap.append(keys[key])
    kept_edges = sorted({tuple(sorted((remap[a], remap[b]))) for a, b in edges if remap[a] != remap[b]})
    kept_faces, seen = [], set()
    for face in faces:
        loop = []
        for index in (remap[corner] for corner in face):
            if not loop or loop[-1] != index:
                loop.append(index)
        if len(loop) > 1 and loop[0] == loop[-1]:
            loop.pop()
        if len(set(loop)) >= 3 and frozenset(loop) not in seen:
            seen.add(frozenset(loop))
            kept_faces.append(tuple(loop))
    return merged, kept_edges, kept_faces


def _plinth(spec):
    """A closed solid of ground: the convex ``outline`` at ``top``, its
    sides leaning out by ``batter`` to ``bottom``."""
    outline = [tuple(map(float, corner)) for corner in spec["outline"]]
    top, bottom = float(spec["top"]), float(spec["bottom"])
    spread = float(spec.get("batter", 0.0)) * (top - bottom)
    count = len(outline)
    sign = 1.0 if sum(outline[i][0] * outline[(i + 1) % count][1] - outline[(i + 1) % count][0] * outline[i][1] for i in range(count)) > 0 else -1.0
    base = []
    for index in range(count):
        previous, current, following = outline[index - 1], outline[index], outline[(index + 1) % count]
        normals = []
        for start, end in ((previous, current), (current, following)):
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            normals.append((sign * dy / length, -sign * dx / length))
        bisector = (normals[0][0] + normals[1][0], normals[0][1] + normals[1][1])
        scale = spread / max(bisector[0] * normals[0][0] + bisector[1] * normals[0][1], 1e-6)
        base.append((current[0] + bisector[0] * scale, current[1] + bisector[1] * scale))
    vertices = [[x, y, top] for x, y in outline] + [[x, y, bottom] for x, y in base]
    ring = list(range(count)) if sign > 0 else list(reversed(range(count)))
    faces = [tuple(ring), tuple(count + index for index in reversed(ring))]
    for position in range(count):
        a, b = ring[position], ring[(position + 1) % count]
        faces.append((a, count + a, count + b, b))
    return vertices, [], faces


def data_mesh(name, spec, folder, volumes=None):
    """Mesh data-block from a data mesh ``spec`` (see the module notes);
    ``folder`` is the scene folder data files are read from, ``volumes``
    the scene's glasshouse volumes."""
    vertices = [list(map(float, vertex)) for vertex in spec.get("vertices", [])]
    edges = [tuple(edge) for edge in spec.get("edges", [])] if isinstance(spec.get("edges"), list) else []
    faces = [tuple(face) for face in spec.get("faces", [])] if isinstance(spec.get("faces"), list) else []
    for kind, built in (("volume", lambda: _volume(volumes[spec["volume"]], spec.get("edges") is True, spec.get("faces") is True)),
                        ("plinth", lambda: _plinth(spec["plinth"]))):
        if kind in spec:
            extra_vertices, extra_edges, extra_faces = built()
            start = len(vertices)
            vertices += extra_vertices
            edges += [(start + a, start + b) for a, b in extra_edges]
            faces += [tuple(start + corner for corner in face) for face in extra_faces]
    if "file" in spec:
        stored = jsonio.load(os.path.join(folder, spec["file"]))
        stored = stored[spec["key"]] if "key" in spec else stored
        start = len(vertices)
        vertices += [list(map(float, vertex)) for vertex in stored["vertices"]]
        faces += [tuple(start + index for index in face) for face in stored["faces"]]
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
            mesh = data_mesh(name, item["mesh"], self.dir, self.data.get("volumes", {})) if "mesh" in item else bpy.data.meshes.new(name)
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
