"""
Frame buildings as data: a grid of column lines and floor levels whose
faces are filled with panels, each panel a module of ``Cinematics.json``.

A frame (an item's ``"frame"``) is::

    {"x": [0, 9.5, 19.0, ...],      column lines along X (metres, the grid's own frame)
     "y": [0, 9.5, ...],            column lines along Y
     "z": {"start": 0, "step": 3.3, "count": 40},   floor levels (top of slab); any of the three
                                    may be a list or such a run of equal steps
     "sections": {"column": {...}, "edge_beam": {...}, "brace": {...}, ...},
     "columns": "column",           section of the columns at every grid point
     "beams": "edge_beam",          section of the beams under every floor, round the edge and along every grid line
     "beam_drop": 0.6,              how far below a floor's top the beams' tops are (the slab between)
     "slab": 0.3,                   thickness of the floors (0: none)
     "slab_edge": 0.11,             how far outwards from the outer column lines the floors reach
     "faces": {"front": {"rows": [...], "default": "X M X"}, ...},
     "spandrels": [{"face": "front", "levels": [5, 6], "section": "spandrel"}],
     "modules": {...}}              (modules of this frame, added to the design system's)

The faces are ``front`` (Y = y[0], looking out along -Y), ``back`` (Y =
y[-1], +Y), ``left`` (X = x[0], -X) and ``right`` (X = x[-1], +X); seen
from outside, a face's bays run left to right and its storeys bottom to
top.  ``rows`` gives one row of panel codes per storey from the bottom
(codes separated by spaces, one per bay); storeys past the list take the
row ``cycle[storey % len(cycle)]`` (alternating patterns) or ``default``,
``"-"`` is an empty bay and ``"+"`` joins modules in one bay.  A spandrel
that ``replaces_beam`` stands in for the edge beam of its face on its
levels.
A section is ``{"shape": "box" | "I" | "round", "width", "depth",
"finish": "concrete" | "steel", "offset"}``: ``width`` is its size in the
plane of its face across the member (a beam's height, a column's
breadth), ``depth`` its size out of that plane and ``offset`` how far
outwards from the column line it sits (a spandrel hung in front of the
frame; negative: set back into the building).  The beams' ``offset``
moves the outer beams outwards the same way.

A module is a panel in unit coordinates -- u across the bay from the face
of its left column to the face of its right one, v up the storey from the
floor to the underside of the beam above -- with ``members`` (``{"from":
[u, v], "to": [u, v], "section"}``) and ``glazing`` (``[[u0, v0, u1, v1],
...]`` panes ``glass_offset`` metres outwards from the column line).

:func:`frame_layout` is plain Python (it runs outside Blender too: the
calibration fits a frame to the reference with it); :func:`frame_meshes`
turns a layout into the meshes the ``CIN.Structure`` assets build on.
"""
from __future__ import annotations

__all__ = ["lines", "frame_layout", "frame_meshes", "FACES", "SHAPES", "FINISHES"]

SHAPES = {"box": 0, "I": 1, "round": 2}
FINISHES = {"concrete": 0, "steel": 1}
FACES = ("front", "back", "left", "right")


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(a):
    return (a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) ** 0.5


def lines(value):
    """Grid lines written out (``[a, b, ...]``) or as ``{"start", "step",
    "count"}`` (``count`` steps, so ``count + 1`` lines)."""
    if isinstance(value, dict):
        return [float(value["start"]) + float(value["step"]) * index for index in range(int(value["count"]) + 1)]
    return [float(component) for component in value]


def face_corners(xs, ys):
    """Each face: its bay corners left to right as seen from outside, and
    its outward normal."""
    return {"front": ([(x, ys[0], 0.0) for x in xs], (0.0, -1.0, 0.0)),
            "back": ([(x, ys[-1], 0.0) for x in reversed(xs)], (0.0, 1.0, 0.0)),
            "left": ([(xs[0], y, 0.0) for y in reversed(ys)], (-1.0, 0.0, 0.0)),
            "right": ([(xs[-1], y, 0.0) for y in ys], (1.0, 0.0, 0.0))}


def _row(face, storey):
    rows = face.get("rows", [])
    if storey < len(rows):
        text = rows[storey]
    elif "cycle" in face:
        text = face["cycle"][storey % len(face["cycle"])]
    else:
        text = face.get("default", "")
    return text.split()


def frame_layout(name, frame, modules):
    """Members ``(start, end, section, facing)``, glazing quads and floor
    quads of ``frame``; ``modules`` are the design system's panel modules."""
    xs, ys, zs = lines(frame["x"]), lines(frame["y"]), lines(frame["z"])
    modules = {**modules, **frame.get("modules", {})}
    sections = frame["sections"]
    members = []
    glazing = []

    def member(start, end, section, facing):
        if _length(_sub(end, start)) > 1e-4:
            members.append((start, end, section, facing))

    column = sections[frame["columns"]]
    beam = sections[frame["beams"]]
    beam_height = float(beam["width"])
    beam_drop = float(frame.get("beam_drop", 0.0))
    beam_shift = float(beam.get("offset", 0.0))
    half_column = float(column["width"]) * 0.5
    for x in xs:
        for y in ys:
            member((x, y, zs[0]), (x, y, zs[-1]), column, (0.0, -1.0, 0.0))
    replaced = {(spandrel["face"], level) for spandrel in frame.get("spandrels", []) if spandrel.get("replaces_beam")
                for level in spandrel["levels"]}
    for level_index, level in enumerate(zs[1:], start=1):
        height = level - beam_drop - beam_height * 0.5
        for y in ys:
            if (y == ys[0] and ("front", level_index) in replaced) or (y == ys[-1] and ("back", level_index) in replaced):
                continue
            shift = -beam_shift if y == ys[0] else (beam_shift if y == ys[-1] else 0.0)
            member((xs[0], y + shift, height), (xs[-1], y + shift, height), beam, (0.0, -1.0, 0.0))
        for x in xs:
            shift = -beam_shift if x == xs[0] else (beam_shift if x == xs[-1] else 0.0)
            member((x + shift, ys[0], height), (x + shift, ys[-1], height), beam, (-1.0, 0.0, 0.0))
    corners_of = face_corners(xs, ys)
    for spandrel in frame.get("spandrels", []):
        corners, normal = corners_of[spandrel["face"]]
        section = sections[spandrel["section"]]
        offset = _scale(normal, float(section.get("offset", 0.0)))
        for level in spandrel["levels"]:
            height = zs[level] - float(section["width"]) * 0.5
            member(_add(_add(corners[0], offset), (0.0, 0.0, height)), _add(_add(corners[-1], offset), (0.0, 0.0, height)),
                   section, normal)
    for face_name, face in frame.get("faces", {}).items():
        corners, normal = corners_of[face_name]
        for storey in range(len(zs) - 1):
            codes = _row(face, storey)
            bottom = zs[storey]
            top = zs[storey + 1] - beam_drop - beam_height
            for bay, code in enumerate(codes[:len(corners) - 1]):
                if code == "-":
                    continue
                parts = code.split("+")
                missing = [part for part in parts if part not in modules]
                if missing:
                    raise KeyError(f"{name}: face {face_name} storey {storey} bay {bay}: no module {missing}")
                left, right = corners[bay], corners[bay + 1]
                width = _length(_sub(right, left))
                across = _scale(_sub(right, left), 1.0 / width)
                start = _add(left, _scale(across, half_column))
                span = width - 2.0 * half_column

                def point(u, v, offset):
                    return _add(_add(_add(start, _scale(across, u * span)), (0.0, 0.0, bottom + v * (top - bottom))),
                                _scale(normal, offset))

                for module in (modules[part] for part in parts):
                    for item in module.get("members", []):
                        section = sections[item["section"]]
                        offset = float(section.get("offset", 0.0))
                        member(point(*item["from"], offset), point(*item["to"], offset), section, normal)
                    glass_offset = float(module.get("glass_offset", 0.0))
                    for u0, v0, u1, v1 in module.get("glazing", []):
                        glazing.append([point(u0, v0, glass_offset), point(u1, v0, glass_offset),
                                        point(u1, v1, glass_offset), point(u0, v1, glass_offset)])
    floors = []
    overhang = float(frame.get("slab_edge", half_column))
    if frame.get("slab", 0.0) > 0.0:
        for level in zs[1:]:
            floors.append([(xs[0] - overhang, ys[0] - overhang, level), (xs[-1] + overhang, ys[0] - overhang, level),
                           (xs[-1] + overhang, ys[-1] + overhang, level), (xs[0] - overhang, ys[-1] + overhang, level)])
    return {"members": members, "glazing": glazing, "floors": floors}


def frame_meshes(name, frame, modules):
    """The members (a wire mesh: every edge one member, its section in edge
    attributes), glazing and floors (face meshes) of ``frame``."""
    import bpy
    layout = frame_layout(name, frame, modules)
    vertices, edges = [], []
    section_index, width, depth, facing, finish = [], [], [], [], []
    for start, end, section, normal in layout["members"]:
        index = len(vertices)
        vertices += [start, end]
        edges.append((index, index + 1))
        section_index.append(SHAPES[section["shape"]])
        width.append(float(section["width"]))
        depth.append(float(section["depth"]))
        facing.extend(normal)
        finish.append(FINISHES[section.get("finish", "concrete")])
    wire = bpy.data.meshes.new(f"{name}.Members")
    wire.from_pydata(vertices, edges, [])
    for attribute, kind, values in (("section", "INT", section_index), ("width", "FLOAT", width),
                                    ("depth", "FLOAT", depth), ("finish", "INT", finish)):
        wire.attributes.new(attribute, kind, "EDGE").data.foreach_set("value", values)
    wire.attributes.new("facing", "FLOAT_VECTOR", "EDGE").data.foreach_set("vector", facing)
    wire.update()

    def quads(mesh_name, items):
        points, faces = [], []
        for quad in items:
            index = len(points)
            points += list(quad)
            faces.append(tuple(range(index, index + 4)))
        mesh = bpy.data.meshes.new(mesh_name)
        mesh.from_pydata(points, [], faces)
        mesh.update()
        return mesh

    return wire, quads(f"{name}.Glazing", layout["glazing"]), quads(f"{name}.Floors", layout["floors"])
