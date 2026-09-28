"""
Flora kit -- geometry-node groups (``CF.Flora.*``): flowers and plants grown
by phyllotaxis.

A blade (petal or leaf) is a grid bent into shape: a width profile along
its length, cupped across, curled along.  A flower sets its blades on the
golden-angle cap lattice -- inner petals small and upright, outer ones large
and open -- so one generator and a preset (``Realm.json``) give dahlias,
camellias, roses, lotus and hydrangea florets.  A plant is an L-system
unrolled two generations deep: a curved stem with leaves on the golden-angle
spiral, whose branches are smaller copies of the whole plant.

Local frames: everything grows from the origin along +Z.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset
from Fractals import phyllotaxis as PHY, recursion as REC
from .. import FLOWERS
from ..values import apply
from . import materials as M

UP = (0.0, 0.0, 1.0)
FLOWER_KINDS = list(FLOWERS)


def blade(graph, length, width, cup, curl, roundness, prefix, resolution=(7, 12)):
    """Blade along +Z from the origin, width along X, cupped towards +Y and
    curling back towards -Y at the tip.  Stores ``<prefix>_u`` (0 at the
    base, 1 at the tip) and ``<prefix>_v`` (-1..1 across)."""
    grid = graph.grid(1.0, 1.0, resolution[0], resolution[1])
    x, y, _ = graph.sep(graph.position())
    u = y + 0.5
    v = x * 2.0
    grid = graph.store(grid, f"{prefix}_u", u)
    grid = graph.store(grid, f"{prefix}_v", v)
    swell = graph.max(graph.sin(graph.math("POWER", u, 0.7) * math.pi), 0.0)
    half = graph.math("POWER", swell, roundness) * width * 0.5
    lift = cup * half * v * v - curl * length * u * u
    return graph.smooth(graph.set_pos(grid, pos=graph.vec(v * half, lift, u * length)))


def flower_node(graph, kind, overrides):
    """Group node of ``CF.Flora.Flower`` set to the preset ``kind`` of
    ``Realm.json``, then to ``overrides`` (values or sockets)."""
    node = graph.group(get_asset("CF.Flora.Flower"))
    apply(graph, node, FLOWERS[kind])
    return apply(graph, node, overrides)


@asset("CF.Flora.Flower", "Flora")
def flower():
    """Flower on the 3D Fibonacci lattice: petal k of n sits at t = (k+1/2)/n
    on the spherical cap of the receptacle (equal-area height, golden-angle
    azimuth), leans out by its polar angle times ``Openness`` plus ``Tilt``
    and grows from ``Size Min`` to full size along the spiral.  Petals carry
    ``petal_u``/``petal_v``, ``petal_t`` (position on the spiral) and the
    flower's two colours for the petal shader."""
    graph = GN("CF.Flora.Flower", flower.__doc__)
    count = graph.inp("Count", "INT", default=60, min=1, max=400)
    divergence = graph.inp("Divergence", default=PHY.GOLDEN_ANGLE, subtype="ANGLE")
    cap = graph.inp("Cap Angle", default=math.radians(100.0), subtype="ANGLE")
    openness = graph.inp("Openness", default=1.0)
    tilt = graph.inp("Tilt", default=math.radians(8.0), subtype="ANGLE")
    receptacle = graph.inp("Receptacle", default=0.015, subtype="DISTANCE")
    length = graph.inp("Petal Length", default=0.08, subtype="DISTANCE")
    width = graph.inp("Petal Width", default=0.035, subtype="DISTANCE")
    size_min = graph.inp("Size Min", default=0.3, min=0.0, max=1.0)
    size_power = graph.inp("Size Power", default=0.7, min=0.05)
    cup = graph.inp("Cup", default=1.0)
    curl = graph.inp("Curl", default=0.15)
    roundness = graph.inp("Roundness", default=0.6, min=0.1)
    center = graph.inp("Center Radius", default=0.0, subtype="DISTANCE")
    jitter = graph.inp("Jitter", default=0.06)
    inner = graph.inp("Inner Color", "COLOR", default=M.color("violet"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("pink"))
    seed = graph.inp("Seed", "INT", default=0)
    petal_material = graph.inp("Petal Material", "MATERIAL", default=M.get("CF.Petal"))
    center_material = graph.inp("Center Material", "MATERIAL", default=M.get("CF.FlowerCenter"))

    petal = blade(graph, length, width, cup, curl, roundness, "petal")
    t, azimuth = PHY.spiral(graph, count, divergence)
    polar = PHY.cap_polar(graph, t, cap)
    bases = graph.points(count, PHY.direction(graph, polar, azimuth) * receptacle)
    bases = graph.store(bases, "petal_t", t)
    lean = polar * openness + tilt + graph.random(-1.0, 1.0, seed) * jitter
    turn = azimuth + math.pi * 0.5 + graph.random(-1.0, 1.0, seed + 1) * jitter
    size = size_min + (1.0 - size_min) * graph.math("POWER", t, size_power)
    petals = graph.realize(graph.iop(bases, petal, rot=graph.vec(lean, 0.0, turn), scale=size))
    petals = graph.store(petals, "petal_inner", inner, "FLOAT_COLOR")
    petals = graph.store(petals, "petal_outer", outer, "FLOAT_COLOR")

    florets = PHY.disc_points(graph, 90, center, dome=center * 0.45)
    bead = graph.n("GeometryNodeMeshIcoSphere", Radius=center * 0.13, Subdivisions=1)["Mesh"]
    heart = graph.smooth(graph.realize(graph.iop(florets, bead)))
    heart = graph.switch(graph.compare(center, 0.0005, "GREATER_THAN"), None, heart)
    graph.result(graph.join(graph.mat(petals, petal_material), graph.mat(heart, center_material)))
    return graph


@asset("CF.Flora.Hydrangea", "Flora")
def hydrangea():
    """Hydrangea head: four-sepal florets (the ``floret`` flower preset) on
    the golden-angle lattice of a dome -- a Fibonacci flower made of
    Fibonacci flowers."""
    graph = GN("CF.Flora.Hydrangea", hydrangea.__doc__)
    radius = graph.inp("Radius", default=0.14, subtype="DISTANCE")
    count = graph.inp("Florets", "INT", default=180, min=1, max=800)
    cap = graph.inp("Cap Angle", default=math.radians(80.0), subtype="ANGLE")
    floret_scale = graph.inp("Floret Scale", default=1.0)
    inner = graph.inp("Inner Color", "COLOR", default=M.color("azure"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("cyan"))
    seed = graph.inp("Seed", "INT", default=0)
    petal_material = graph.inp("Petal Material", "MATERIAL", default=M.get("CF.Petal"))

    floret = flower_node(graph, "floret", {"Inner Color": inner, "Outer Color": outer, "Seed": seed,
                                           "Petal Material": petal_material})
    frames = PHY.cap_points(graph, count, cap, radius)
    rotation = graph.random_spin(graph.align_rotation(graph.position()), seed)
    size = floret_scale * graph.random(0.75, 1.2, seed + 1)
    graph.result(graph.iop(frames, floret.o, rot=rotation, scale=size))
    return graph


@asset("CF.Flora.Plant", "Flora")
def plant():
    """Leafy plant grown like an L-system: a curved, tapering stem carries
    leaves on the golden-angle spiral and branches that are smaller copies
    of the whole plant (``Generations`` 0..2).  A flower preset (``Flower``:
    0 none, then the presets of ``Realm.json`` in order) may crown every
    tip."""
    graph = GN("CF.Flora.Plant", plant.__doc__)
    height = graph.inp("Height", default=0.5, subtype="DISTANCE")
    bend = graph.inp("Bend", default=0.25)
    stem_radius = graph.inp("Stem Radius", default=0.006, subtype="DISTANCE")
    leaves = graph.inp("Leaves", "INT", default=9, min=0, max=64)
    leaf_length = graph.inp("Leaf Length", default=0.12, subtype="DISTANCE")
    leaf_width = graph.inp("Leaf Width", default=0.04, subtype="DISTANCE")
    leaf_angle = graph.inp("Leaf Angle", default=math.radians(55.0), subtype="ANGLE")
    leaf_fold = graph.inp("Leaf Fold", default=0.35)
    leaf_curl = graph.inp("Leaf Curl", default=0.25)
    branches = graph.inp("Branches", "INT", default=3, min=0, max=12)
    branch_scale = graph.inp("Branch Scale", default=0.62)
    branch_angle = graph.inp("Branch Angle", default=math.radians(38.0), subtype="ANGLE")
    generations = graph.inp("Generations", "INT", default=2, min=0, max=2)
    leaf_color = graph.inp("Leaf Color", "COLOR", default=M.color("leaf_blue"))
    kind = graph.inp("Flower", "INT", default=0, min=0, max=len(FLOWER_KINDS))
    flower_scale = graph.inp("Flower Scale", default=1.0)
    inner = graph.inp("Inner Color", "COLOR", default=M.color("violet"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("pink"))
    seed = graph.inp("Seed", "INT", default=0)
    leaf_material = graph.inp("Leaf Material", "MATERIAL", default=M.get("CF.Leaf"))
    stem_material = graph.inp("Stem Material", "MATERIAL", default=M.get("CF.Stem"))
    petal_material = graph.inp("Petal Material", "MATERIAL", default=M.get("CF.Petal"))

    def stem_point(u):
        return graph.vec(bend * height * u * u, 0.0, height * u)

    line = graph.resample(graph.curve_line((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), 12)
    axis = graph.set_pos(line, pos=stem_point(graph.sep(graph.position())[2]))
    taper = 1.0 - graph.n("GeometryNodeSplineParameter")["Factor"] * 0.55
    stem = graph.n("GeometryNodeCurveToMesh", Curve=axis, Profile_Curve=graph.circle(stem_radius, 8),
                   Scale=taper, Fill_Caps=True).o

    leaf = blade(graph, leaf_length, leaf_width, leaf_fold, leaf_curl, 0.9, "leaf", (7, 14))
    leaf = graph.store(leaf, "leaf_color", leaf_color, "FLOAT_COLOR")
    index = graph.index()
    u = 0.18 + (index + 0.5) / leaves * 0.78
    azimuth = index * PHY.GOLDEN_ANGLE + seed * 1.3
    lean = leaf_angle * (1.25 - u * 0.5)
    outward = PHY.direction(graph, lean, azimuth)
    facing = graph.align_rotation(UP, graph.align_rotation(outward), axis="Y", pivot="Z")
    foliage = graph.iop(graph.points(leaves, stem_point(u)), leaf, rot=facing,
                        scale=(1.15 - u * 0.55) * graph.random(0.85, 1.1, seed + 2))

    blooms = [None] + [flower_node(graph, name, {"Inner Color": inner, "Outer Color": outer, "Seed": seed,
                                                 "Petal Material": petal_material}).o for name in FLOWER_KINDS]
    bloom = graph.index_switch(kind, blooms, "GEOMETRY")
    crown = graph.transform(bloom, t=stem_point(1.0),
                            r=graph.align_rotation(graph.vec(bend * 2.0 * height, 0.0, height)),
                            s=graph.vec(flower_scale, flower_scale, flower_scale))
    twig = graph.join(graph.mat(graph.smooth(stem), stem_material), graph.mat(foliage, leaf_material), crown)

    branch = graph.index()
    along = 0.35 + (branch + 0.5) / branches * 0.45
    heading = PHY.direction(graph, branch_angle, branch * PHY.GOLDEN_ANGLE + 0.9 + seed * 0.7)
    forks = graph.points(branches, stem_point(along))
    fork_rotation = graph.random_spin(graph.align_rotation(heading), seed + 3)
    fork_size = branch_scale * (1.1 - along * 0.4)

    def spawn(geometry):
        return graph.iop(forks, geometry, rot=fork_rotation, scale=fork_size)

    graph.result(REC.pick_level(graph, REC.levels(graph, twig, spawn, 2), generations))
    return graph


@asset("CF.Flora.OrbPlant", "Flora")
def orb_plant():
    """Orb plant: slender stalks rise from a rosette of leaves (golden-angle
    spiral), each bending out and carrying a galaxy orb that grows from it
    like a dewdrop."""
    graph = GN("CF.Flora.OrbPlant", orb_plant.__doc__)
    stalks = graph.inp("Stalks", "INT", default=3, min=1, max=12)
    height = graph.inp("Height", default=0.9, subtype="DISTANCE")
    spread = graph.inp("Spread", default=0.3, subtype="DISTANCE")
    orb_radius = graph.inp("Orb Radius", default=0.12, subtype="DISTANCE")
    leaves = graph.inp("Leaves", "INT", default=14, min=0, max=64)
    leaf_length = graph.inp("Leaf Length", default=0.32, subtype="DISTANCE")
    leaf_width = graph.inp("Leaf Width", default=0.07, subtype="DISTANCE")
    leaf_color = graph.inp("Leaf Color", "COLOR", default=M.color("leaf_blue"))
    seed = graph.inp("Seed", "INT", default=0)
    leaf_material = graph.inp("Leaf Material", "MATERIAL", default=M.get("CF.Leaf"))
    stem_material = graph.inp("Stem Material", "MATERIAL", default=M.get("CF.Stem"))

    leaf = blade(graph, leaf_length, leaf_width, 0.4, 0.35, 0.9, "leaf", (7, 14))
    leaf = graph.store(leaf, "leaf_color", leaf_color, "FLOAT_COLOR")
    t, azimuth = PHY.spiral(graph, leaves)
    lean = math.radians(35.0) + t * math.radians(45.0)
    rosette = graph.iop(graph.points(leaves),
                        leaf, rot=graph.align_rotation(UP, graph.align_rotation(PHY.direction(graph, lean, azimuth)),
                                                       axis="Y", pivot="Z"),
                        scale=0.6 + t * 0.6)

    index = graph.index()
    heading = index * PHY.GOLDEN_ANGLE + seed * 0.9
    tall = height * graph.random(0.65, 1.0, seed)
    reach = spread * graph.random(0.5, 1.0, seed + 1)
    tip = graph.vec(reach * graph.cos(heading), reach * graph.sin(heading), tall)
    unit_stalk = graph.n("GeometryNodeCurvePrimitiveBezierSegment", Resolution=16, Start=(0.0, 0.0, 0.0),
                         Start_Handle=(0.0, 0.0, 0.5), End_Handle=(0.4, 0.0, 0.7), End=(1.0, 0.0, 1.0)).o
    paths = graph.realize(graph.iop(graph.points(stalks), unit_stalk, rot=graph.vec(0.0, 0.0, heading),
                                    scale=graph.vec(reach, reach, tall)))
    stems = graph.mat(graph.smooth(graph.sweep(paths, graph.circle(0.006, 8), True)), stem_material)
    orb = apply(graph, graph.group(get_asset("CF.Vessel.Orb")), {"Radius": 1.0, "Tail": True, "Seed": seed}).o
    orbs = graph.iop(graph.points(stalks, tip + graph.vec(0.0, 0.0, orb_radius * 1.35)), orb,
                     rot=graph.vec(graph.random(-0.15, 0.15, seed + 2), graph.random(-0.15, 0.15, seed + 3), 0.0),
                     scale=orb_radius * graph.random(0.8, 1.2, seed + 4))
    graph.result(graph.join(graph.mat(rosette, leaf_material), stems, orbs))
    return graph
