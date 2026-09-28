"""
Display kit -- geometry-node groups (``CF.Display.*``): how the conservatory
shows its treasures.

* vitrine towers: glass cases stacked on overhanging glass shelves, each
  case turned a little against the one below, a flower in every case;
* etageres: glass plates on a slender rod, each plate smaller than the one
  below by a constant ratio, bearing orbs, gems and crystals;
* a Wardian case: the Victorian glass plant cabinet on an iron stand.

Local frames: everything stands on z = 0, centred on the origin.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, shell_profile
from Fractals import phyllotaxis as PHY
from .. import PROFILES
from ..values import apply
from . import materials as M
from .flora import FLOWER_KINDS

TAU = math.tau


def group(graph, name, values):
    return apply(graph, graph.group(get_asset(name)), values)


def hollow_box(graph, width, depth, height, wall):
    """Four glass walls of a case: a box minus a taller, thinner box."""
    outer = graph.box(width * -0.5, depth * -0.5, 0.0, width * 0.5, depth * 0.5, height)
    inner = graph.box(width * -0.5 + wall, depth * -0.5 + wall, -1.0, width * 0.5 - wall, depth * 0.5 - wall,
                      height + 1.0)
    node = graph.n("GeometryNodeMeshBoolean", props={"operation": "DIFFERENCE", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(node.n, "Mesh 1"), outer)
    graph.assign(graph._in_socket(node.n, "Mesh 2"), [inner])
    return node["Mesh"]


def rounded_slab(graph, width, depth, thickness, radius):
    outline = graph.fillet(graph.rect(width, depth), radius, 4)
    return graph.solid(graph.fill(outline), thickness)


@asset("CF.Display.Vitrine", "Displays")
def vitrine():
    """Tower of glass display cases: every tier is a glass case on a thick
    glass shelf that overhangs it, turned and shifted a little against the
    tier below; a flowering plant (``Flower`` preset, 0 none) stands in
    every case and a last shelf caps the tower."""
    graph = GN("CF.Display.Vitrine", vitrine.__doc__)
    tiers = graph.inp("Tiers", "INT", default=4, min=1, max=10)
    width = graph.inp("Width", default=0.85, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.85, subtype="DISTANCE")
    tier_height = graph.inp("Tier Height", default=0.95, subtype="DISTANCE")
    shelf = graph.inp("Shelf Thickness", default=0.045, subtype="DISTANCE")
    overhang = graph.inp("Overhang", default=0.07, subtype="DISTANCE")
    wall = graph.inp("Wall Thickness", default=0.012, subtype="DISTANCE")
    twist = graph.inp("Twist", default=math.radians(6.0), subtype="ANGLE")
    shift = graph.inp("Shift", default=0.04, subtype="DISTANCE")
    kind = graph.inp("Flower", "INT", default=1, min=0, max=len(FLOWER_KINDS))
    flower_scale = graph.inp("Flower Scale", default=2.2)
    plant_height = graph.inp("Plant Height", default=0.3, subtype="DISTANCE")
    inner = graph.inp("Inner Color", "COLOR", default=M.color("violet"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("magenta"))
    leaf_color = graph.inp("Leaf Color", "COLOR", default=M.color("leaf_teal"))
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.Glass"))

    slab = rounded_slab(graph, width + overhang * 2.0, depth + overhang * 2.0, shelf, 0.03)
    case = graph.move(hollow_box(graph, width, depth, tier_height - shelf, wall), z=shelf)
    tier = graph.mat(graph.smooth_by_angle(graph.join(slab, case), 0.5), glass)
    plants = [group(graph, "CF.Flora.Plant", {"Height": plant_height, "Bend": 0.1, "Leaves": 5, "Leaf Length": 0.14,
                                               "Leaf Width": 0.05, "Generations": 0, "Flower": kind,
                                               "Flower Scale": flower_scale, "Inner Color": inner,
                                               "Outer Color": outer, "Leaf Color": leaf_color,
                                               "Seed": seed * 3 + variant}).o for variant in range(3)]
    plant_set = graph.n("GeometryNodeGeometryToInstance", Geometry=plants).o

    index = graph.index()
    floors = graph.points(tiers, graph.vec(graph.random(-1.0, 1.0, seed) * shift, graph.random(-1.0, 1.0, seed + 1) * shift,
                                           index * tier_height))
    turn = graph.vec(0.0, 0.0, graph.random(-1.0, 1.0, seed + 2) * twist)
    stack = graph.iop(floors, tier, rot=turn)
    blooms = graph.iop(graph.set_pos(floors, offset=graph.vec(0.0, 0.0, shelf)), plant_set,
                       rot=graph.vec(0.0, 0.0, graph.random(0.0, TAU, seed + 3)), pick=True,
                       index=graph.random(0, 2, seed + 4, dtype="INT"))
    lid = graph.move(graph.mat(graph.smooth_by_angle(slab, 0.5), glass), z=tiers * tier_height)
    graph.result(graph.join(stack, blooms, lid))
    return graph


@asset("CF.Display.Etagere", "Displays")
def etagere():
    """Tiered glass stand: plates on a slender glass rod, each plate smaller
    than the one below by ``Ratio`` (a geometric series), each bearing
    ``Items`` treasures on the golden-angle disc -- galaxy and marble orbs,
    brilliant-cut gems, druses and single points."""
    graph = GN("CF.Display.Etagere", etagere.__doc__)
    height = graph.inp("Height", default=2.6, subtype="DISTANCE")
    plates = graph.inp("Plates", "INT", default=4, min=1, max=8)
    base_radius = graph.inp("Base Radius", default=0.42, subtype="DISTANCE")
    ratio = graph.inp("Ratio", default=0.82, min=0.4, max=1.0)
    rod = graph.inp("Rod Radius", default=0.02, subtype="DISTANCE")
    items = graph.inp("Items", "INT", default=3, min=0, max=9)
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.Glass"))

    plate_profile = PROFILES["plate"]
    plate = graph.lathe(shell_profile(plate_profile["outer"], plate_profile["thickness"]), 48)
    foot = graph.transform(graph.lathe(PROFILES["foot"]["outer"], 48), s=graph.vec(base_radius * 0.9, base_radius * 0.9,
                                                                                   base_radius * 0.9))
    spine = graph.move(graph.cylinder(rod, height, 16), z=height * 0.5)
    knob = graph.move(graph.ellipsoid(rod * 2.4, rod * 2.4, rod * 2.4, 16, 8), z=height)

    level = graph.index()
    rise = (height - 0.65) / graph.max(plates - 1.0, 1.0)
    shrink = graph.math("POWER", ratio, level)
    tiers = graph.points(plates, graph.vec(0.0, 0.0, level * rise + 0.45))
    dishes = graph.iop(tiers, plate, scale=base_radius * shrink)

    treasures = [
        graph.move(group(graph, "CF.Vessel.Orb", {"Radius": 0.13, "Seed": seed}).o, z=0.13),
        graph.move(group(graph, "CF.Vessel.Orb", {"Radius": 0.11, "Style": 1, "Seed": seed + 1}).o, z=0.11),
        graph.move(group(graph, "CF.Crystal.Brilliant", {"Diameter": 0.16}).o, z=0.069),
        group(graph, "CF.Crystal.Druse", {"Count": 7, "Length": 0.3, "Levels": 1, "Children": 5, "Seed": seed}).o,
        group(graph, "CF.Crystal.Quartz", {"Length": 0.3, "Radius": 0.04, "Seed": seed + 2,
                                           "Material": M.get("CF.CrystalBlue")}).o,
    ]
    choices = graph.n("GeometryNodeGeometryToInstance", Geometry=treasures).o
    index = graph.index()
    tier = graph.math("FLOOR", index / items)
    slot = index - tier * items
    tier_radius = base_radius * graph.math("POWER", ratio, tier)
    t = (slot + 0.5) / items
    angle = slot * PHY.GOLDEN_ANGLE + tier * 2.1 + seed
    reach = graph.math("SQRT", t) * tier_radius * 0.55
    spots = graph.points(plates * items, graph.vec(reach * graph.cos(angle), reach * graph.sin(angle),
                                                   tier * rise + 0.45 + tier_radius * plate_profile["thickness"]))
    load = graph.iop(spots, choices, rot=graph.vec(0.0, 0.0, graph.random(0.0, TAU, seed + 3)),
                     scale=0.75 + tier_radius / base_radius * 0.25, pick=True,
                     index=graph.random(0, len(treasures) - 1, seed + 4, dtype="INT"))
    stand = graph.smooth_by_angle(graph.join(foot, spine, knob, graph.realize(dishes)), 0.6)
    graph.result(graph.join(graph.mat(stand, glass), load))
    return graph


@asset("CF.Display.WardianCase", "Displays")
def wardian_case():
    """Wardian case: a glass cabinet with a pitched glass roof on an iron
    stand, its edges framed in slender iron."""
    graph = GN("CF.Display.WardianCase", wardian_case.__doc__)
    width = graph.inp("Width", default=1.6, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.9, subtype="DISTANCE")
    height = graph.inp("Height", default=1.3, subtype="DISTANCE", desc="Glass walls")
    stand = graph.inp("Stand Height", default=0.75, subtype="DISTANCE")
    roof = graph.inp("Roof Height", default=0.4, subtype="DISTANCE")
    frame = graph.inp("Frame", default=0.022, subtype="DISTANCE")
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.GlassPane"))
    iron = graph.inp("Frame Material", "MATERIAL", default=M.get("CF.Iron"))

    walls = graph.move(hollow_box(graph, width, depth, height, 0.01), z=stand)
    top = stand + height
    ridge = graph.n("GeometryNodeMeshCube", Size=graph.vec(width, depth, roof), Vertices_X=2, Vertices_Y=3,
                    Vertices_Z=2)["Mesh"]
    x, y, z = graph.sep(graph.position())
    peak = graph.compare(z, 0.0, "GREATER_THAN")
    roof_shape = graph.set_pos(ridge, pos=graph.vec(x, y * graph.switch(peak, 1.0, 0.0, "FLOAT"), z))
    roof_shape = graph.merge(roof_shape, 0.0005)
    cover = graph.move(roof_shape, z=top + roof * 0.5)
    base = graph.box(width * -0.5 - 0.04, depth * -0.5 - 0.04, stand - 0.08, width * 0.5 + 0.04, depth * 0.5 + 0.04, stand)
    corners = graph.points(4, graph.vec(graph.switch(graph.compare(graph.math("MODULO", graph.index(), 2.0), 0.5,
                                                                   "GREATER_THAN"), width * -0.5, width * 0.5, "FLOAT"),
                                        graph.switch(graph.compare(graph.index(), 1.5, "GREATER_THAN"),
                                                     depth * -0.5, depth * 0.5, "FLOAT"), 0.0))
    legs = graph.iop(corners, graph.box(-0.025, -0.025, 0.0, 0.025, 0.025, stand))
    box_edges = graph.n("GeometryNodeMeshToCurve",
                        graph.n("GeometryNodeMeshCube", Size=graph.vec(width, depth, height))["Mesh"]).o
    box_frame = graph.move(graph.sweep(box_edges, graph.rect(frame, frame), True), z=stand + height * 0.5)
    roof_edges = graph.n("GeometryNodeMeshToCurve", cover).o
    roof_frame = graph.sweep(roof_edges, graph.rect(frame, frame), True)
    graph.result(graph.join(graph.mat(graph.join(walls, cover), glass),
                            graph.mat(graph.join(base, graph.realize(legs), box_frame, roof_frame), iron)))
    return graph
