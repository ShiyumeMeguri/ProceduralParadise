"""
Crystal kit -- geometry-node groups (``CF.Crystal.*``).

Local frames: a crystal grows from the origin along +Z; a pendant hangs
from the origin (its suspension point) down -Z; a gem sits table-up with
its girdle on z = 0.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset
from Fractals import phyllotaxis as PHY, recursion as REC
from .. import REALM
from . import materials as M

TAU = math.tau


@asset("CF.Crystal.Quartz", "Crystals")
def quartz():
    """Single quartz point: a six-sided prism with a pyramidal termination,
    the convex hull of jittered corner points -- every seed grows its own
    facets.  Foot at the origin, growing along +Z."""
    graph = GN("CF.Crystal.Quartz", quartz.__doc__)
    length = graph.inp("Length", default=1.0, subtype="DISTANCE")
    radius = graph.inp("Radius", default=0.12, subtype="DISTANCE")
    tip = graph.inp("Tip", default=1.7, desc="Height of the termination in radii")
    taper = graph.inp("Taper", default=0.12, min=0.0, max=0.9)
    irregularity = graph.inp("Irregularity", default=0.3, min=0.0, max=1.0)
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Crystal"))
    index = graph.index()
    ring = graph.math("FLOOR", index / 6.0)
    corner = graph.math("MODULO", index, 6.0)
    angle = corner * (TAU / 6.0) + graph.random(-0.3, 0.3, seed) * irregularity
    swell = 1.0 + graph.random(-0.4, 0.4, seed + 1) * irregularity
    height = graph.index_switch(ring, [0.0, length - radius * tip, length], "FLOAT")
    girth = radius * graph.index_switch(ring, [1.0, 1.0 - taper, 0.0], "FLOAT") * swell
    position = graph.vec(girth * graph.cos(angle), girth * graph.sin(angle), height)
    apex = graph.math("GREATER_THAN", ring, 1.5)
    shift = graph.random(-1.0, 1.0, seed + 2, dtype="FLOAT_VECTOR")
    position = position + shift * (apex * radius * 0.35 * irregularity)
    hull = graph.n("GeometryNodeConvexHull", graph.points(13, position)).o
    graph.result(graph.mat(hull, material))
    return graph


@asset("CF.Crystal.Druse", "Crystals")
def druse():
    """Druse: quartz points radiating from a common root on the golden-angle
    cap lattice, longest at the centre.  At every level the root sprouts
    smaller copies of the whole druse around its foot, so the cluster is
    self-similar (``Levels`` 0..2)."""
    graph = GN("CF.Crystal.Druse", druse.__doc__)
    count = graph.inp("Count", "INT", default=9, min=1, max=64)
    spread = graph.inp("Spread", default=math.radians(55.0), subtype="ANGLE")
    length = graph.inp("Length", default=0.5, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.11, desc="Crystal radius per unit of length")
    falloff = graph.inp("Falloff", default=0.55, min=0.0, max=0.95, desc="How much shorter the outer crystals are")
    levels = graph.inp("Levels", "INT", default=1, min=0, max=2)
    children = graph.inp("Children", "INT", default=6, min=1, max=24)
    child_scale = graph.inp("Child Scale", default=0.4, min=0.05, max=0.9)
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Crystal"))

    shapes = [graph.group(get_asset("CF.Crystal.Quartz"), Length=1.0, Radius=thickness, Seed=seed * 7 + variant,
                          Material=material).o for variant in range(4)]
    variants = graph.n("GeometryNodeGeometryToInstance", Geometry=shapes).o

    roots = PHY.cap_points(graph, count, spread)
    t = PHY.read_t(graph)
    rotation = graph.random_spin(graph.align_rotation(graph.position()), seed + 3)
    size = length * (1.0 - falloff * t) * graph.random(0.6, 1.0, seed + 4)
    roots = graph.set_pos(roots, pos=graph.position() * (length * 0.04))
    cluster = graph.iop(roots, variants, rot=rotation, scale=size, pick=True,
                        index=graph.random(0, 3, seed + 5, dtype="INT"))

    frames = PHY.cap_points(graph, children, math.radians(105.0), start_angle=math.radians(50.0))
    frames = graph.set_pos(frames, pos=graph.position() * (length * 0.14))
    frame_rotation = graph.random_spin(graph.align_rotation(graph.position()), seed + 6)
    frame_size = child_scale * graph.random(0.7, 1.1, seed + 7)

    def spawn(geometry):
        return graph.iop(frames, geometry, rot=frame_rotation, scale=frame_size)

    graph.result(REC.pick_level(graph, REC.levels(graph, cluster, spawn, 2), levels))
    return graph


@asset("CF.Crystal.Pendant", "Crystals")
def pendant():
    """Hanging crystal: an elongated bipyramid on a silver cap and a fine
    thread, hung from the origin."""
    graph = GN("CF.Crystal.Pendant", pendant.__doc__)
    size = graph.inp("Size", default=0.3, subtype="DISTANCE", desc="Length of the crystal")
    width = graph.inp("Width", default=0.26, desc="Radius per unit of length")
    sides = graph.inp("Sides", "INT", default=8, min=3, max=16)
    upper = graph.inp("Upper", default=0.3, min=0.05, max=0.95, desc="Share of the length above the girdle")
    drop = graph.inp("Drop", default=1.0, subtype="DISTANCE", desc="Thread length")
    crystal_material = graph.inp("Crystal Material", "MATERIAL", default=M.get("CF.CrystalBlue"))
    metal_material = graph.inp("Metal Material", "MATERIAL", default=M.get("CF.Silver"))
    thread_material = graph.inp("Thread Material", "MATERIAL", default=M.get("CF.Thread"))

    cap_height = size * 0.07
    top = -drop - cap_height
    girdle = top - size * upper
    index = graph.index()
    angle = index * TAU / sides
    ring = graph.vec(graph.cos(angle) * size * width, graph.sin(angle) * size * width, girdle)
    apex = graph.switch(graph.compare(index, sides, "EQUAL", "INT"), graph.vec(0.0, 0.0, top - size),
                        graph.vec(0.0, 0.0, top), "VECTOR")
    position = graph.switch(graph.compare(index, sides, "LESS_THAN", "INT"), apex, ring, "VECTOR")
    crystal = graph.n("GeometryNodeConvexHull", graph.points(sides + 2, position)).o
    cap = graph.move(graph.n("GeometryNodeMeshCone", Vertices=16, Radius_Top=size * width * 0.12,
                             Radius_Bottom=size * width * 0.3, Depth=cap_height)["Mesh"], z=-drop - cap_height * 0.5)
    thread = graph.rod((0.0, 0.0, 0.0), graph.vec(0.0, 0.0, -drop), 0.0012, 6)
    graph.result(graph.join(graph.mat(crystal, crystal_material),
                            graph.smooth(graph.mat(cap, metal_material)),
                            graph.mat(thread, thread_material)))
    return graph


@asset("CF.Crystal.Brilliant", "Crystals")
def brilliant():
    """Round brilliant cut as the convex hull of its facet corners (table,
    star points, girdle, lower-girdle points, culet; proportions from
    ``Realm.json``).  Table up, girdle on z = 0."""
    graph = GN("CF.Crystal.Brilliant", brilliant.__doc__)
    diameter = graph.inp("Diameter", default=0.12, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Crystal"))
    cut = REALM["gems"]["brilliant"]
    corners = []
    for ring in cut["rings"]:
        for k in range(ring["count"]):
            angle = TAU * (k + ring.get("offset", 0.0)) / ring["count"]
            corners.append((ring["radius"] * math.cos(angle), ring["radius"] * math.sin(angle), ring["z"]))
    corners.append((0.0, 0.0, cut["culet"]))
    points = graph.points(len(corners), graph.index_switch(graph.index(), corners, "VECTOR"))
    hull = graph.n("GeometryNodeConvexHull", points).o
    graph.result(graph.mat(graph.transform(hull, s=graph.vec(diameter, diameter, diameter)), material))
    return graph


@asset("CF.Crystal.Coral", "Crystals")
def coral():
    """Botryoidal crystal coral: a sphere budding smaller spheres on the
    golden-angle lattice, generation after generation (a sphereflake)."""
    graph = GN("CF.Crystal.Coral", coral.__doc__)
    radius = graph.inp("Radius", default=0.15, subtype="DISTANCE")
    levels = graph.inp("Levels", "INT", default=3, min=0, max=3)
    children = graph.inp("Children", "INT", default=9, min=1, max=24)
    child_scale = graph.inp("Child Scale", default=0.42, min=0.1, max=0.8)
    spread = graph.inp("Spread", default=math.radians(115.0), subtype="ANGLE")
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.CrystalBlue"))

    bead = graph.smooth(graph.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=3)["Mesh"])
    frames = PHY.cap_points(graph, children, spread)
    frames = graph.set_pos(frames, pos=graph.position() * (1.0 + child_scale * 0.8))
    frame_rotation = graph.random_spin(graph.align_rotation(graph.position()), seed)
    frame_size = child_scale * graph.random(0.8, 1.1, seed + 1)

    def spawn(geometry):
        return graph.iop(frames, geometry, rot=frame_rotation, scale=frame_size)

    body = REC.pick_level(graph, REC.levels(graph, bead, spawn, 3), levels)
    graph.result(graph.mat(graph.transform(body, s=graph.vec(radius, radius, radius)), material))
    return graph
