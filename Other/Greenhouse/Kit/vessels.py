"""
Vessel kit -- geometry-node groups (``GH.Vessel.*``): the glassware and the
small things on the tables.

Glass bodies are closed meshes so the glass material's absorption fills
them: blown vessels are lathed from an outer profile into a wall of
constant thickness (``Core.gn.shell_profile``); the square bottle and the
glass block are one surface of revolution whose cross-section is a
superellipse (a rounded square) that morphs into the round neck.

Local frames: standing things rest on z = 0; a hanging terrarium hangs
from the origin (the end of its wire); the phone lies on z = 0.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, set_menu, shell_profile
from Core.render import INK_QUIET
from . import materials as M

TAU = math.tau


def sphere(graph, radius, segments=48, rings=24):
    return graph.n("GeometryNodeMeshUVSphere", Segments=segments, Rings=rings, Radius=radius)["Mesh"]


def cut_below(graph, solid, level, floor):
    """The part of the closed mesh ``solid`` below the plane z = ``level``."""
    below = graph.box(-10.0, -10.0, floor - 1.0, 10.0, 10.0, level)
    node = graph.n("GeometryNodeMeshBoolean", props={"operation": "INTERSECT", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(node.n, "Mesh 2"), [solid, below])
    return node["Mesh"]


def shell(graph, mesh, thickness):
    """Closed wall from an open surface: the surface pushed out along its
    normals by ``thickness`` plus the original, flipped, as the inside."""
    outer = graph.extrude(mesh, thickness)
    inner = graph.n("GeometryNodeFlipFaces", mesh).o
    return graph.merge(graph.join(outer, inner), 0.00001)


def pebbles(graph, count, radius, size, height, seed, dome=0.0):
    """``count`` rounded pebbles scattered on a disc of ``radius`` at
    ``height`` (heaped by ``dome`` towards the middle), each with its own
    ``pebble_shade``; quiet for the ink pass (a bed of stones, not stones
    drawn one by one)."""
    points = graph.points(count, (0.0, 0.0, 0.0))
    index = graph.index()
    reach = graph.math("SQRT", (index + 0.5) / graph.max(count, 1)) * radius
    angle = index * math.pi * (3.0 - math.sqrt(5.0))
    heap = (1.0 - (reach / graph.max(radius, 0.0001)) * (reach / graph.max(radius, 0.0001))) * dome
    points = graph.set_pos(points, pos=graph.vec(graph.cos(angle) * reach, graph.sin(angle) * reach, height + heap))
    stone = graph.smooth(graph.ellipsoid(1.0, 0.8, 0.55, 10, 6))
    rotation = graph.vec(graph.random(-0.3, 0.3, seed), graph.random(-0.3, 0.3, seed + 1), graph.random(0.0, TAU, seed + 2))
    scattered = graph.iop(points, stone, rot=rotation, scale=size * graph.random(0.6, 1.3, seed + 3))
    scattered = graph.store(scattered, "pebble_shade", graph.random(0.0, 1.0, seed + 4), "FLOAT", "INSTANCE")
    scattered = graph.store(scattered, INK_QUIET, 1.0, "FLOAT", "INSTANCE")
    return graph.mat(graph.realize(scattered), M.get("GH.Pebble"))


def open_sphere(graph, radius, opening, segments=72, rings=36):
    """Sphere of ``radius`` about the origin with a round opening of angular
    radius ``opening`` about +Z: a grid wrapped from the south pole up to
    the rim, so the rim is an exact circle; normals point outwards."""
    grid = graph.grid(1.0, 1.0, segments + 1, rings + 1)
    x, y, _ = graph.sep(graph.position())
    azimuth = (x + 0.5) * TAU
    polar = math.pi - (y + 0.5) * (math.pi - opening)
    ring = graph.sin(polar) * radius
    grid = graph.set_pos(grid, pos=graph.vec(graph.cos(azimuth) * ring, graph.sin(azimuth) * ring, graph.cos(polar) * radius))
    return graph.merge(grid, radius * 0.0005)


@asset("GH.Vessel.Orb", "Vessels")
def orb():
    """Hanging glass terrarium: a blown sphere of ``Radius`` with a round
    opening of ``Opening`` (its angular radius) cut on the side facing
    ``Facing``, a bed of white pebbles filled to ``Fill`` of the height --
    as many pebbles of ``Pebble Size`` as cover the bed -- and above it the
    glass loop and the wire it hangs from.  The origin is the top of the
    wire; the sphere's centre is ``Drop`` below it."""
    graph = GN("GH.Vessel.Orb", orb.__doc__)
    radius = graph.inp("Radius", default=0.16, subtype="DISTANCE")
    wall = graph.inp("Wall", default=0.003, subtype="DISTANCE")
    opening = graph.inp("Opening", default=math.radians(40.0), subtype="ANGLE")
    facing = graph.inp("Facing", "VECTOR", default=(0.0, -1.0, 0.35))
    fill = graph.inp("Fill", default=0.3, min=0.0, max=0.9)
    pebble_size = graph.inp("Pebble Size", default=0.006, subtype="DISTANCE")
    drop = graph.inp("Drop", default=1.0, subtype="DISTANCE")
    loop = graph.inp("Loop Radius", default=0.014, subtype="DISTANCE")
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassClear"))
    wire_material = graph.inp("Wire Material", "MATERIAL", default=M.get("GH.Steel"))

    ball = open_sphere(graph, radius - wall, opening)
    body = graph.smooth(shell(graph, ball, wall))
    body = graph.transform(body, r=graph.align_rotation(graph.vmath("NORMALIZE", facing), axis="Z"))
    body = M.glazed(graph, body, glass)

    level = radius * (fill * 2.0 - 1.0)
    bed_radius = graph.math("SQRT", graph.max(radius * radius - level * level, 0.0)) - wall * 1.5
    bed = cut_below(graph, sphere(graph, radius - wall * 1.2, 48, 24), level, radius * -2.0)
    bed = graph.mat(graph.store(bed, INK_QUIET, 1.0, "FLOAT", "FACE"), M.get("GH.Pebble"))
    pebble_count = graph.to_int(graph.math("POWER", bed_radius / graph.max(pebble_size * 0.8, 0.0001), 2.0), "CEILING")
    stones = pebbles(graph, pebble_count, bed_radius * 0.96, pebble_size, level, seed, dome=radius * 0.04)

    ring = graph.n("GeometryNodeCurvePrimitiveCircle", Resolution=24, Radius=loop).o
    ring = graph.transform(ring, r=graph.vec(math.pi * 0.5, 0.0, 0.0), t=graph.vec(0.0, 0.0, radius + loop))
    ring = graph.smooth(graph.sweep(ring, graph.circle(0.0025, 8), False))
    wire_length = drop - radius - loop * 2.0
    wire = graph.rod(graph.vec(0.0, 0.0, radius + loop * 2.0), graph.vec(0.0, 0.0, radius + loop * 2.0 + wire_length), 0.0008, 6)
    hanging = graph.join(M.glazed(graph, ring, glass), graph.mat(wire, wire_material))
    graph.result(graph.move(graph.join(body, bed, stones, hanging), z=drop * -1.0))
    return graph


def squircle_body(graph, width, depth, height, neck_radius, shoulder, bevel, power, rings=48):
    """Solid surface of revolution along +Z from z = 0 to ``height``: a
    rounded rectangle (superellipse of ``power``, ``width`` by ``depth``)
    domed over the top ``shoulder`` of the height -- a quarter ellipse from
    the upright sides to a level top round a circle of ``neck_radius``; the
    foot is chamfered by ``bevel``.  The rings crowd into the dome: it takes
    four times its share of the height in rings, up to half of them."""
    body = graph.cylinder(1.0, 1.0, 96, "NGON", rings)
    x, y, z = graph.sep(graph.position())
    ring = z + 0.5
    start = 1.0 - shoulder
    share = graph.min(shoulder * 4.0, 0.5)
    split = 1.0 - share
    u = graph.min(ring, split) / split * start + graph.max(ring - split, 0.0) / graph.max(share, 0.000001) * shoulder
    angle = graph.math("ARCTAN2", y, x)
    c = graph.abs(graph.cos(angle))
    s = graph.abs(graph.sin(angle))
    ax = width * 0.5
    ay = depth * 0.5
    superellipse = graph.math("POWER", graph.math("POWER", c / ax, power) + graph.math("POWER", s / ay, power), -1.0 / power)
    along = graph.map_range(u, start, 1.0, 0.0, 1.0)
    dome = graph.math("SQRT", graph.max(1.0 - along * along, 0.0))
    radial = neck_radius + (superellipse - neck_radius) * dome
    foot = graph.min(u * height / graph.max(bevel, 0.000001), 1.0)
    radial = radial * (1.0 - (1.0 - foot) * 0.25)
    radius_xy = graph.vec(x, y, 0.0).length()
    scale = radial / graph.max(radius_xy, 0.00001)
    return graph.smooth_by_angle(graph.set_pos(body, pos=graph.vec(x * scale, y * scale, u * height)), 1.0)


@asset("GH.Vessel.SquareBottle", "Vessels")
def square_bottle():
    """Square-shouldered glass bottle, or with no neck a glass block: a
    solid rounded-square body ``Width`` x ``Depth`` rising ``Height``,
    rounding over the top ``Shoulder`` into a neck of ``Neck Radius`` and
    ``Neck Length`` with a lip; a bore of ``Bore`` radius and ``Bore Depth``
    is drilled down from the top.  With a ``Wall`` the body is blown hollow:
    a cavity that thick inside every side, on a ``Base`` that thick, opening
    into the bore, filled with ``Liquid`` to ``Fill`` of the body's height
    (the liquid stands a fraction of a millimetre into the glass, so the two
    dielectrics meet without a film of air)."""
    graph = GN("GH.Vessel.SquareBottle", square_bottle.__doc__)
    width = graph.inp("Width", default=0.2, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.2, subtype="DISTANCE")
    height = graph.inp("Height", default=1.2, subtype="DISTANCE")
    shoulder = graph.inp("Shoulder", default=0.15, min=0.0, max=1.0)
    neck_radius = graph.inp("Neck Radius", default=0.04, subtype="DISTANCE")
    neck_length = graph.inp("Neck Length", default=0.05, subtype="DISTANCE")
    bore = graph.inp("Bore", default=0.028, subtype="DISTANCE")
    bore_depth = graph.inp("Bore Depth", default=0.1, subtype="DISTANCE")
    bevel = graph.inp("Bevel", default=0.02, subtype="DISTANCE")
    power = graph.inp("Squareness", default=6.0, min=2.0)
    wall = graph.inp("Wall", default=0.0, min=0.0, subtype="DISTANCE")
    base = graph.inp("Base", default=0.01, min=0.0, subtype="DISTANCE")
    fill = graph.inp("Fill", default=0.0, min=0.0, max=1.0)
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassJade"))
    liquid = graph.inp("Liquid", "MATERIAL", default=M.get("GH.Water"))

    body = squircle_body(graph, width, depth, height, neck_radius, shoulder, bevel, power)
    neck = graph.n("GeometryNodeMeshCylinder", Vertices=48, Side_Segments=1, Radius=1.0, Depth=1.0, props={"fill_type": "NGON"})["Mesh"]
    neck = graph.transform(neck, t=graph.vec(0.0, 0.0, height + neck_length * 0.5 - 0.002), s=graph.vec(neck_radius, neck_radius, neck_length + 0.004))
    lip = graph.n("GeometryNodeMeshCylinder", Vertices=48, Side_Segments=1, Radius=1.0, Depth=1.0, props={"fill_type": "NGON"})["Mesh"]
    lip = graph.transform(lip, t=graph.vec(0.0, 0.0, height + neck_length - 0.006), s=graph.vec(neck_radius * 1.12, neck_radius * 1.12, 0.012))
    hole = graph.n("GeometryNodeMeshCylinder", Vertices=48, Side_Segments=1, Radius=1.0, Depth=1.0, props={"fill_type": "NGON"})["Mesh"]
    top = height + neck_length
    hole = graph.transform(hole, t=graph.vec(0.0, 0.0, top - bore_depth * 0.5 + 0.01), s=graph.vec(bore, bore, bore_depth + 0.02))
    has_neck = graph.compare(neck_length, 0.001, "GREATER_THAN")
    neck = graph.switch(has_neck, None, graph.join(neck, lip))
    solid = graph.n("GeometryNodeMeshBoolean", props={"operation": "UNION", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(solid.n, "Mesh 2"), [body, neck])
    bored = graph.n("GeometryNodeMeshBoolean", Mesh_1=solid["Mesh"], props={"operation": "DIFFERENCE", "solver": "MANIFOLD"})
    hollow = graph.compare(wall, 0.0001, "GREATER_THAN")
    cavity = squircle_body(graph, width - wall * 2.0, depth - wall * 2.0, height - base, bore, shoulder, 0.0, power)
    cavity = graph.switch(hollow, None, graph.move(cavity, z=base))
    graph.assign(graph._in_socket(bored.n, "Mesh 2"), [hole, cavity])
    body_glass = M.glazed(graph, graph.smooth_by_angle(bored["Mesh"], 0.9), glass)
    overlap = 0.0004
    contents = squircle_body(graph, width - wall * 2.0 + overlap * 2.0, depth - wall * 2.0 + overlap * 2.0, height - base + overlap, bore, shoulder, 0.0, power)
    contents = cut_below(graph, graph.move(contents, z=base - overlap), height * fill, -1.0)
    filled = graph.bool_and(hollow, graph.compare(fill, 0.001, "GREATER_THAN"))
    contents = graph.switch(filled, None, M.glazed(graph, contents, liquid))
    graph.result(graph.join(body_glass, contents))
    return graph


@asset("GH.Vessel.Planter", "Vessels")
def planter():
    """Tapered round planter of ``Radius`` (at the rim) and ``Height`` with a
    rolled lip, filled with soil ``Fill`` of the way up."""
    graph = GN("GH.Vessel.Planter", planter.__doc__)
    radius = graph.inp("Radius", default=0.25, subtype="DISTANCE")
    height = graph.inp("Height", default=0.45, subtype="DISTANCE")
    fill = graph.inp("Fill", default=0.9, min=0.0, max=1.0)
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Planter"))
    outer = [(0.0, 0.0), (0.72, 0.0), (0.76, 0.02), (0.96, 0.9), (1.0, 0.94), (1.0, 1.0)]
    body = graph.lathe(shell_profile(outer, 0.06), 64, 1.0)
    body = graph.transform(body, s=graph.vec(radius, radius, height))
    soil = graph.transform(graph.cylinder(1.0, 1.0, 64), t=graph.vec(0.0, 0.0, height * fill * 0.5),
                           s=graph.vec(radius * (0.72 + 0.2 * fill), radius * (0.72 + 0.2 * fill), height * fill))
    graph.result(graph.join(graph.mat(graph.smooth_by_angle(body, 0.8), material), graph.mat(soil, M.get("GH.Soil"))))
    return graph


@asset("GH.Vessel.Flask", "Vessels")
def flask():
    """Round-bottomed flask: a blown spheroid of ``Radius`` across and
    ``Squash`` times that in height (1 for a sphere, less for a flat onion
    flask) with a straight neck, lathed as a wall of constant thickness,
    standing on its curve; filled with water to ``Fill`` of the body's
    height (the water stands a fraction of a millimetre into the glass, so
    the two dielectrics meet without a film of air)."""
    graph = GN("GH.Vessel.Flask", flask.__doc__)
    radius = graph.inp("Radius", default=0.16, subtype="DISTANCE")
    neck_radius = graph.inp("Neck Radius", default=0.035, subtype="DISTANCE")
    neck_length = graph.inp("Neck Length", default=0.12, subtype="DISTANCE")
    squash = graph.inp("Squash", default=1.0, min=0.2, max=2.0)
    fill = graph.inp("Fill", default=0.0, min=0.0, max=1.0)
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassClear"))
    liquid = graph.inp("Liquid", "MATERIAL", default=M.get("GH.Water"))

    steps = 24
    neck_angle = math.asin(0.22)
    outer = []
    for index in range(steps + 1):
        theta = -math.pi * 0.5 + (math.pi - neck_angle) * index / steps
        outer.append((math.cos(theta), 1.0 + math.sin(theta)))
    top = outer[-1][1]
    outer += [(0.22, top + 0.2), (0.22, top + 0.72), (0.25, top + 0.75)]
    profile = shell_profile(outer, 0.018)
    body = graph.lathe(profile, 64, 1.0)
    x, y, z = graph.sep(graph.position())
    neck_scale = neck_radius / graph.max(radius * 0.22, 0.0001)
    above = graph.compare(z, top, "GREATER_THAN")
    widened = graph.switch(above, radius, radius * neck_scale, "FLOAT")
    stretch = graph.switch(above, z * radius * squash, top * radius * squash + (z - top) * neck_length / 0.75, "FLOAT")
    body = graph.set_pos(body, pos=graph.vec(x * widened, y * widened, stretch))
    wall = 0.018 * radius
    water = graph.smooth(sphere(graph, radius - wall + 0.0004, 64, 32))
    water = graph.transform(water, t=graph.vec(0.0, 0.0, radius * squash), s=graph.vec(1.0, 1.0, squash))
    water = cut_below(graph, water, radius * squash * 2.0 * fill, -1.0)
    water = graph.switch(graph.compare(fill, 0.001, "GREATER_THAN"), None, M.glazed(graph, water, liquid))
    graph.result(graph.join(M.glazed(graph, graph.smooth_by_angle(body, 1.2), glass), water))
    return graph


@asset("GH.Vessel.BudVase", "Vessels")
def bud_vase():
    """Bud vase: a slender dark bronze cone on a wide shallow brass
    saucer."""
    graph = GN("GH.Vessel.BudVase", bud_vase.__doc__)
    saucer = graph.inp("Saucer Radius", default=0.075, subtype="DISTANCE")
    height = graph.inp("Height", default=0.1, subtype="DISTANCE")
    base = graph.inp("Base Radius", default=0.03, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Brass"))
    vase_material = graph.inp("Vase Material", "MATERIAL", default=M.get("GH.Bronze"))
    plate = graph.lathe([(0.0, 0.0), (0.92, 0.0), (1.0, 0.06), (0.98, 0.08), (0.2, 0.05), (0.0, 0.05)], 64, 1.0)
    plate = graph.transform(plate, s=graph.vec(saucer, saucer, saucer))
    cone = graph.lathe([(0.0, 0.0), (1.0, 0.0), (0.4, 0.9), (0.28, 0.97), (0.22, 1.0), (0.16, 0.99), (0.16, 0.8), (0.0, 0.8)], 48, 1.0)
    cone = graph.transform(cone, t=graph.vec(0.0, 0.0, saucer * 0.05), s=graph.vec(base, base, height))
    graph.result(graph.join(graph.mat(graph.smooth_by_angle(plate, 0.7), material), graph.mat(graph.smooth_by_angle(cone, 0.7), vase_material)))
    return graph


@asset("GH.Vessel.Ball", "Vessels")
def ball():
    """Solid glass ball resting on z = 0."""
    graph = GN("GH.Vessel.Ball", ball.__doc__)
    radius = graph.inp("Radius", default=0.035, subtype="DISTANCE")
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassClear"))
    graph.result(M.glazed(graph, graph.smooth(graph.move(sphere(graph, radius, 48, 24), z=radius)), glass))
    return graph


def rounded_face(graph, width, length, radius, z):
    """Rounded rectangle ``width`` (X) by ``length`` (Y) filled flat at
    height ``z``."""
    outline = graph.fillet(graph.rect(width, length), radius, 6, True, "POLY")
    return graph.move(graph.fill(outline), z=z)


def centred_text(graph, text, size):
    """Curve instances of ``text`` centred on the origin."""
    node = graph.n("GeometryNodeStringToCurves", String=text, Size=size)
    set_menu(graph._in_socket(node.n, "Align X"), "Center")
    set_menu(graph._in_socket(node.n, "Align Y"), "Middle")
    return node["Curve Instances"]


@asset("GH.Vessel.Phone", "Vessels")
def phone():
    """Phone lying face up, its long side along Y: a rounded slab ``Width``
    x ``Length`` x ``Thickness`` in its case, the screen inset by ``Bezel``
    showing a photo over the +Y ``Photo`` fraction of its length and the
    ``Title`` with a ``Caption`` line below the photo.  The title reads
    along -X with its letters' tops towards -Y."""
    graph = GN("GH.Vessel.Phone", phone.__doc__)
    width = graph.inp("Width", default=0.075, subtype="DISTANCE")
    length = graph.inp("Length", default=0.16, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.009, subtype="DISTANCE")
    corner = graph.inp("Corner", default=0.008, subtype="DISTANCE")
    bezel = graph.inp("Bezel", default=0.004, subtype="DISTANCE")
    photo = graph.inp("Photo", default=0.62, min=0.0, max=1.0)
    title = graph.inp("Title", "STRING", default="KEW")
    title_size = graph.inp("Title Size", default=0.012, subtype="DISTANCE")
    caption = graph.inp("Caption", "STRING", default="ROYAL BOTANIC GARDENS")
    body_material = graph.inp("Body", "MATERIAL", default=M.get("GH.PhoneBody"))
    screen_material = graph.inp("Screen", "MATERIAL", default=M.get("GH.PhoneScreen"))
    photo_material = graph.inp("Photo Material", "MATERIAL", default=M.get("GH.PhonePhoto"))

    body = graph.solid(rounded_face(graph, width, length, corner, 0.0), thickness)
    inner_width = width - bezel * 2.0
    inner_length = length - bezel * 2.0
    screen = rounded_face(graph, inner_width, inner_length, graph.max(corner - bezel, 0.001), thickness + 0.0002)
    margin = inner_width * 0.08
    photo_length = inner_length * photo
    picture = rounded_face(graph, inner_width - margin * 2.0, photo_length - margin * 2.0, margin * 0.6, thickness + 0.0004)
    picture = graph.move(picture, y=inner_length * 0.5 - photo_length * 0.5)
    text_centre = inner_length * 0.5 - photo_length - (inner_length - photo_length) * 0.45
    letters = graph.fill(graph.realize(centred_text(graph, title, title_size)))
    letters = graph.transform(letters, r=graph.vec(0.0, 0.0, math.pi), t=graph.vec(0.0, text_centre, thickness + 0.0006))
    small = graph.fill(graph.realize(centred_text(graph, caption, title_size * 0.18)))
    small = graph.transform(small, r=graph.vec(0.0, 0.0, math.pi), t=graph.vec(0.0, text_centre + title_size * 0.75, thickness + 0.0006))
    graph.result(graph.join(graph.mat(graph.smooth_by_angle(body, 0.6), body_material), graph.mat(screen, screen_material),
                            graph.mat(picture, photo_material), graph.mat(graph.join(letters, small), M.get("GH.Ink"))))
    return graph
