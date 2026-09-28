"""
Architecture kit -- geometry-node groups (``CF.Arch.*``): the Victorian
glasshouse the crystal garden lives in.

One wall type does all the glazing: ``CF.Arch.Gable`` is a pane on an iron
grid whose outline may end in a semicircular arch and which may be pierced
by an arched opening -- a drum bay of the rotunda, the portal where a nave
meets it, a screen with a doorway, or the end wall of a nave.  Mullions
and transoms are cut to the pane by a boolean, so any outline gets a clean
grid.

Local frames: walls stand on z = 0 in the XZ plane, centred on x = 0, their
pane in the plane y = 0; a nave runs along +Y from the origin, centred on X;
round buildings are centred on the origin.  Floors are at z = 0.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, set_menu, set_mode
from Fractals import phyllotaxis as PHY
from ..values import apply
from . import materials as M

TAU = math.tau
STAND = (math.pi * 0.5, 0.0, 0.0)
ARC_POINTS = 40


def arch_curve(graph, width, spring, rise):
    """Closed outline in the XY plane: the bottom edge of ``width`` on y = 0,
    straight sides up to ``spring``, then a half ellipse of height ``rise``
    (0 gives a flat top)."""
    index = graph.index()
    angle = (index - 2.0) / (ARC_POINTS - 1.0) * math.pi
    top = graph.vec(width * 0.5 * graph.cos(angle), spring + rise * graph.sin(angle), 0.0)
    corner = graph.vec((index - 0.5) * width, 0.0, 0.0)
    position = graph.switch(graph.compare(index, 1.5, "LESS_THAN"), top, corner, "VECTOR")
    line = graph.set_pos(graph.mesh_line(ARC_POINTS + 2), pos=position)
    curve = graph.n("GeometryNodeMeshToCurve", line).o
    return graph.n("GeometryNodeSetSplineCyclic", curve, Cyclic=True).o


def clip(graph, bars, region):
    node = graph.n("GeometryNodeMeshBoolean", props={"operation": "INTERSECT", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(node.n, "Mesh 2"), [bars, region])
    return node["Mesh"]


def bar(graph, start, end, width, depth, normal):
    """Straight bar from ``start`` to ``end``, ``width`` along ``normal``."""
    line = graph.n("GeometryNodeSetCurveNormal", graph.curve_line(start, end))
    set_mode(line, "FREE")
    graph.assign(graph._in_socket(line.n, "Normal"), normal)
    return graph.sweep(line.o, graph.rect(width, depth), True)


@asset("CF.Arch.Gable", "Architecture")
def gable():
    """Glazed wall on an iron grid: outline ``Width`` x ``Spring`` with an
    optional semicircular ``Arch`` on top, optionally pierced by an arched
    opening (``Opening Width`` > 0) that springs at ``Opening Spring``.
    Stands on z = 0 in the XZ plane."""
    graph = GN("CF.Arch.Gable", gable.__doc__)
    width = graph.inp("Width", default=10.0, subtype="DISTANCE")
    spring = graph.inp("Spring", default=6.0, subtype="DISTANCE")
    arch = graph.inp("Arch", "BOOL", default=True)
    opening = graph.inp("Opening Width", default=0.0, subtype="DISTANCE")
    opening_spring = graph.inp("Opening Spring", default=3.0, subtype="DISTANCE")
    spacing = graph.inp("Mullion Spacing", default=1.25, subtype="DISTANCE")
    transoms = graph.inp("Transoms", "INT", default=3, min=0, max=20)
    frame = graph.inp("Frame", default=0.1, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.14, subtype="DISTANCE")
    frame_material = graph.inp("Frame Material", "MATERIAL", default=M.get("CF.Iron"))
    glass_material = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.GlassPane"))

    rise = graph.switch(arch, 0.0, width * 0.5, "FLOAT")
    outline = arch_curve(graph, width, spring, rise)
    hole = arch_curve(graph, opening, opening_spring, opening * 0.5)
    has_hole = graph.compare(opening, 0.01, "GREATER_THAN")
    curves = graph.join(outline, graph.switch(has_hole, None, hole))
    fill = graph.n("GeometryNodeFillCurve", curves)
    set_menu(graph._in_socket(fill.n, "Fill Rule"), "Even-Odd")
    face = fill.o
    pane = graph.move(graph.solid(face, 0.012), z=-0.006)
    region = graph.move(graph.solid(face, depth), z=depth * -0.5)

    top = spring + rise
    count = graph.math("FLOOR", width / spacing) + 1.0
    first = (count - 1.0) * spacing * -0.5
    uprights = graph.iop(graph.mesh_line(count, graph.vec(first, 0.0, 0.0), graph.vec(spacing, 0.0, 0.0)),
                         graph.box(frame * -0.5, -0.1, depth * -0.5, frame * 0.5, top + 0.1, depth * 0.5))
    levels = graph.mesh_line(transoms, graph.vec(0.0, spring / (transoms + 1.0), 0.0),
                             graph.vec(0.0, spring / (transoms + 1.0), 0.0))
    rails = graph.iop(levels, graph.box(width * -0.5 - 0.1, frame * -0.5, depth * -0.5,
                                        width * 0.5 + 0.1, frame * 0.5, depth * 0.5))
    grid = graph.join(clip(graph, graph.realize(uprights), region), clip(graph, graph.realize(rails), region))
    edges = graph.flat_sweep(curves, frame * 1.4, depth * 1.2)
    wall = graph.join(graph.mat(pane, glass_material), graph.mat(graph.join(grid, edges), frame_material))
    graph.result(graph.transform(wall, r=STAND))
    return graph


@asset("CF.Arch.Nave", "Architecture")
def nave():
    """Glasshouse nave: glazed side walls on a stone plinth under a barrel
    vault of glass on iron ribs and purlins, over a stone floor.  Runs along
    +Y from the origin, centred on X; end walls are separate gables."""
    graph = GN("CF.Arch.Nave", nave.__doc__)
    length = graph.inp("Length", default=20.0, subtype="DISTANCE")
    width = graph.inp("Width", default=10.0, subtype="DISTANCE")
    wall = graph.inp("Wall Height", default=6.0, subtype="DISTANCE")
    bay = graph.inp("Bay", default=2.5, subtype="DISTANCE", desc="Rib spacing")
    spacing = graph.inp("Mullion Spacing", default=1.25, subtype="DISTANCE")
    transoms = graph.inp("Transoms", "INT", default=3, min=0, max=12)
    plinth = graph.inp("Plinth Height", default=0.6, subtype="DISTANCE")
    purlins = graph.inp("Purlins", "INT", default=12, min=2, max=48)
    frame = graph.inp("Frame", default=0.1, subtype="DISTANCE")
    rib_depth = graph.inp("Rib Depth", default=0.24, subtype="DISTANCE")
    frame_material = graph.inp("Frame Material", "MATERIAL", default=M.get("CF.Iron"))
    glass_material = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.GlassPane"))
    stone_material = graph.inp("Stone Material", "MATERIAL", default=M.get("CF.Stone"))

    half = width * 0.5
    floor = graph.box(half * -1.0 - 0.3, 0.0, -0.4, half + 0.3, length, 0.0)
    plinths = graph.join(graph.box(half * -1.0 - 0.25, 0.0, 0.0, half * -1.0 + 0.2, length, plinth),
                         graph.box(half - 0.2, 0.0, 0.0, half + 0.25, length, plinth))
    panes = graph.join(graph.box(half * -1.0 - 0.006, 0.0, plinth, half * -1.0 + 0.006, length, wall),
                       graph.box(half - 0.006, 0.0, plinth, half + 0.006, length, wall))
    count = graph.math("FLOOR", length / spacing) + 1.0
    sides = graph.join(graph.mesh_line(count, graph.vec(half * -1.0, 0.0, 0.0), graph.vec(0.0, spacing, 0.0)),
                       graph.mesh_line(count, graph.vec(half, 0.0, 0.0), graph.vec(0.0, spacing, 0.0)))
    uprights = graph.iop(graph.mesh_to_points(sides),
                         graph.box(frame * -0.5, frame * -0.5, plinth, frame * 0.5, frame * 0.5, wall))
    heights = graph.mesh_line(transoms, graph.vec(0.0, 0.0, plinth + (wall - plinth) / (transoms + 1.0)),
                              graph.vec(0.0, 0.0, (wall - plinth) / (transoms + 1.0)))
    rail = graph.join(graph.box(half * -1.0 - frame * 0.5, 0.0, frame * -0.5, half * -1.0 + frame * 0.5, length,
                                frame * 0.5),
                      graph.box(half - frame * 0.5, 0.0, frame * -0.5, half + frame * 0.5, length, frame * 0.5))
    rails = graph.iop(graph.mesh_to_points(heights), rail)
    eaves = graph.join(graph.box(half * -1.0 - 0.12, 0.0, wall - 0.1, half * -1.0 + 0.12, length, wall + 0.12),
                       graph.box(half - 0.12, 0.0, wall - 0.1, half + 0.12, length, wall + 0.12))

    arc = graph.n("GeometryNodeCurveArc", Resolution=48, Radius=half, Start_Angle=0.0, Sweep_Angle=math.pi).o
    arc = graph.transform(arc, t=graph.vec(0.0, 0.0, wall), r=STAND)
    rib_curve = graph.n("GeometryNodeSetCurveNormal", arc)
    set_mode(rib_curve, "FREE")
    graph.assign(graph._in_socket(rib_curve.n, "Normal"), (0.0, 1.0, 0.0))
    rib = graph.sweep(rib_curve.o, graph.rect(frame * 1.6, rib_depth), False)
    rib_count = graph.math("FLOOR", length / bay) + 1.0
    ribs = graph.iop(graph.mesh_to_points(graph.mesh_line(rib_count, (0.0, 0.0, 0.0), graph.vec(0.0, bay, 0.0))),
                     rib)

    vault = graph.grid(1.0, 1.0, 97, 2)
    x, y, _ = graph.sep(graph.position())
    angle = (x + 0.5) * math.pi
    vault = graph.set_pos(vault, pos=graph.vec(half * graph.cos(angle), (y + 0.5) * length,
                                               wall + half * graph.sin(angle)))
    step = math.pi / purlins
    turn = graph.index() * step + step
    placed = graph.points(purlins - 1, graph.vec(half * graph.cos(turn), 0.0, wall + half * graph.sin(turn)))
    purlin = graph.box(frame * -0.6, 0.0, frame * -0.6, frame * 0.6, length, frame * 0.6)
    purlin_set = graph.iop(placed, purlin, rot=graph.vec(0.0, turn * -1.0, 0.0))

    iron = graph.join(uprights, rails, eaves, ribs, purlin_set)
    graph.result(graph.join(graph.mat(graph.join(floor, plinths), stone_material),
                            graph.mat(graph.join(panes, graph.smooth(vault)), glass_material),
                            graph.mat(iron, frame_material)))
    return graph


@asset("CF.Arch.Rotunda", "Architecture")
def rotunda():
    """Rotunda: a polygonal glazed drum under a ribbed glass dome and
    lantern, around a shallow reflecting pool.  Sides are centred on the
    compass directions (side 0 faces +X); an ``Open`` direction removes the
    three sides facing it and closes the gap with a flat portal whose arched
    opening is a nave's section."""
    graph = GN("CF.Arch.Rotunda", rotunda.__doc__)
    radius = graph.inp("Radius", default=9.0, subtype="DISTANCE", desc="Circumradius of the drum")
    sides = graph.inp("Sides", "INT", default=16, min=8, max=48)
    wall = graph.inp("Wall Height", default=12.0, subtype="DISTANCE")
    rise = graph.inp("Dome Rise", default=7.0, subtype="DISTANCE")
    lantern = graph.inp("Lantern Radius", default=1.6, subtype="DISTANCE")
    lantern_height = graph.inp("Lantern Height", default=2.0, subtype="DISTANCE")
    rings = graph.inp("Rings", "INT", default=6, min=1, max=24)
    open_east = graph.inp("Open East", "BOOL", default=True)
    open_north = graph.inp("Open North", "BOOL", default=True)
    open_west = graph.inp("Open West", "BOOL", default=True)
    open_south = graph.inp("Open South", "BOOL", default=True)
    opening = graph.inp("Opening Width", default=10.0, subtype="DISTANCE")
    opening_spring = graph.inp("Opening Spring", default=6.0, subtype="DISTANCE")
    spacing = graph.inp("Mullion Spacing", default=1.2, subtype="DISTANCE")
    transoms = graph.inp("Transoms", "INT", default=5, min=0, max=20)
    frame = graph.inp("Frame", default=0.12, subtype="DISTANCE")
    pool = graph.inp("Pool Depth", default=0.14, subtype="DISTANCE")
    walk = graph.inp("Walkway", default=0.7, subtype="DISTANCE", desc="Width of the dry ring along the drum")
    frame_material = graph.inp("Frame Material", "MATERIAL", default=M.get("CF.Iron"))
    glass_material = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.GlassPane"))
    stone_material = graph.inp("Stone Material", "MATERIAL", default=M.get("CF.Stone"))
    water_material = graph.inp("Water Material", "MATERIAL", default=M.get("CF.PoolWater"))

    sector = TAU / sides
    apothem = radius * graph.cos(sector * 0.5)
    side_width = radius * graph.sin(sector * 0.5) * 2.0
    index = graph.index()
    centre = index * sector

    def facing(direction):
        offset = graph.math("WRAP", centre - direction, math.pi, -math.pi)
        return graph.compare(graph.abs(offset), sector * 1.6, "LESS_THAN")

    opened = graph.bool_or(graph.bool_or(graph.bool_and(open_east, facing(0.0)),
                                         graph.bool_and(open_north, facing(math.pi * 0.5))),
                           graph.bool_or(graph.bool_and(open_west, facing(math.pi)),
                                         graph.bool_and(open_south, facing(math.pi * 1.5))))
    bays = graph.points(sides, graph.vec(apothem * graph.cos(centre), apothem * graph.sin(centre), 0.0))
    bay = apply(graph, graph.group(get_asset("CF.Arch.Gable")),
                {"Width": side_width, "Spring": wall, "Arch": False, "Mullion Spacing": spacing,
                 "Transoms": transoms, "Frame": frame, "Frame Material": frame_material,
                 "Glass Material": glass_material}).o
    drum = graph.iop(bays, bay, sel=graph.bool_not(opened), rot=graph.vec(0.0, 0.0, centre + math.pi * 0.5))

    portal_distance = radius * graph.cos(sector * 1.5)
    portal_width = radius * graph.sin(sector * 1.5) * 2.0
    compass = graph.index() * (math.pi * 0.5)
    wanted = graph.index_switch(graph.index(), [open_east, open_north, open_west, open_south], "BOOLEAN")
    doors = graph.points(4, graph.vec(portal_distance * graph.cos(compass), portal_distance * graph.sin(compass), 0.0))
    portal = apply(graph, graph.group(get_asset("CF.Arch.Gable")),
                   {"Width": portal_width, "Spring": wall, "Arch": False, "Opening Width": opening,
                    "Opening Spring": opening_spring, "Mullion Spacing": spacing, "Transoms": transoms,
                    "Frame": frame, "Frame Material": frame_material, "Glass Material": glass_material}).o
    portals = graph.iop(doors, portal, sel=wanted, rot=graph.vec(0.0, 0.0, compass + math.pi * 0.5))

    corners = graph.points(sides, graph.vec(radius * graph.cos(centre + sector * 0.5),
                                            radius * graph.sin(centre + sector * 0.5), 0.0))
    column = graph.move(graph.cylinder(frame * 1.1, wall, 12), z=wall * 0.5)
    columns = graph.iop(corners, column)
    ring = graph.n("GeometryNodeCurvePrimitiveCircle", Resolution=sides, Radius=radius).o
    ring = graph.transform(ring, t=graph.vec(0.0, 0.0, wall), r=graph.vec(0.0, 0.0, sector * 0.5))
    ring_beam = graph.flat_sweep(ring, 0.35, 0.4)

    profile = graph.n("GeometryNodeCurveArc", Resolution=24, Radius=1.0, Start_Angle=0.0,
                      Sweep_Angle=math.pi * 0.5).o
    meridian = graph.transform(profile, s=graph.vec(radius - lantern, rise, 1.0))
    meridian = graph.transform(meridian, t=graph.vec(lantern, 0.0, 0.0))
    meridian = graph.transform(meridian, r=STAND)
    meridian = graph.move(meridian, z=wall)
    rib_curve = graph.n("GeometryNodeSetCurveNormal", meridian)
    set_mode(rib_curve, "FREE")
    graph.assign(graph._in_socket(rib_curve.n, "Normal"), (0.0, 1.0, 0.0))
    rib = graph.sweep(rib_curve.o, graph.rect(frame * 1.5, 0.3), False)
    ribs = graph.iop(graph.points(sides), rib, rot=graph.vec(0.0, 0.0, centre + sector * 0.5))

    shell = graph.grid(1.0, 1.0, 33, 25)
    u, v, _ = graph.sep(graph.position())
    around = (u + 0.5) * TAU + sector * 0.5
    up = (v + 0.5) * math.pi * 0.5
    reach = lantern + (radius - lantern) * graph.cos(up)
    dome = graph.set_pos(shell, pos=graph.vec(reach * graph.cos(around), reach * graph.sin(around),
                                              wall + rise * graph.sin(up)))
    dome = graph.merge(dome, 0.001)
    latitude = graph.index()
    band_angle = (latitude + 1.0) / (rings + 1.0) * math.pi * 0.5
    band_curve = graph.n("GeometryNodeCurvePrimitiveCircle", Resolution=sides, Radius=1.0).o
    band_curve = graph.transform(band_curve, r=graph.vec(0.0, 0.0, sector * 0.5))
    band_points = graph.points(rings, graph.vec(0.0, 0.0, wall + rise * graph.sin(band_angle)))
    band_size = lantern + (radius - lantern) * graph.cos(band_angle)
    circles = graph.realize(graph.iop(band_points, band_curve, scale=graph.vec(band_size, band_size, 1.0)))
    bands = graph.flat_sweep(circles, 0.08, 0.12)

    crown = wall + rise
    lantern_glass = graph.move(graph.cylinder(lantern, lantern_height, 32, "NONE"), z=crown + lantern_height * 0.5)
    lantern_posts = graph.iop(graph.points(sides, graph.vec(lantern * graph.cos(centre), lantern * graph.sin(centre),
                                                            crown)),
                              graph.box(-0.05, -0.05, 0.0, 0.05, 0.05, lantern_height))
    cap = graph.transform(graph.ellipsoid(1.0, 1.0, 1.0, 32, 16),
                          t=graph.vec(0.0, 0.0, crown + lantern_height),
                          s=graph.vec(lantern + 0.2, lantern + 0.2, lantern * 0.55))
    spire = graph.move(graph.n("GeometryNodeMeshCone", Vertices=16, Radius_Bottom=0.18, Depth=2.4)["Mesh"],
                       z=crown + lantern_height + lantern * 0.55 + 1.1)

    basin_radius = apothem - walk
    basin = graph.move(graph.cylinder(basin_radius, 0.3, 96), z=pool * -1.0 - 0.15)
    walkway = graph.n("GeometryNodeMeshCylinder", props={"fill_type": "NGON"}, Vertices=sides, Radius=radius + 0.4,
                      Depth=0.5).o
    walkway = graph.transform(walkway, t=graph.vec(0.0, 0.0, -0.25), r=graph.vec(0.0, 0.0, sector * 0.5))
    ring_cut = graph.move(graph.cylinder(basin_radius, 1.0, 96), z=0.0)
    node = graph.n("GeometryNodeMeshBoolean", props={"operation": "DIFFERENCE", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(node.n, "Mesh 1"), walkway)
    graph.assign(graph._in_socket(node.n, "Mesh 2"), [ring_cut])
    curb = node["Mesh"]
    water = graph.move(graph.n("GeometryNodeMeshCircle", props={"fill_type": "NGON"}, Vertices=96,
                               Radius=basin_radius + 0.002).o, z=-0.035)

    iron = graph.join(columns, ring_beam, ribs, bands, lantern_posts, graph.smooth(cap), spire)
    graph.result(graph.join(drum, portals,
                            graph.mat(graph.join(graph.smooth(dome), lantern_glass), glass_material),
                            graph.mat(iron, frame_material),
                            graph.mat(graph.join(basin, curb), stone_material),
                            graph.mat(water, water_material)))
    return graph


@asset("CF.Arch.Hoop", "Architecture")
def hoop():
    """Iron hoop hung level on rods -- the ring the rotunda's crystals and
    terraria hang from; the rods rise ``Suspension`` above it."""
    graph = GN("CF.Arch.Hoop", hoop.__doc__)
    radius = graph.inp("Radius", default=6.5, subtype="DISTANCE")
    rods = graph.inp("Rods", "INT", default=8, min=0, max=64)
    suspension = graph.inp("Suspension", default=5.0, subtype="DISTANCE")
    thickness = graph.inp("Bar", default=0.06, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Iron"))
    ring = graph.tube(graph.circle(radius, 128), thickness, 10)
    turn = graph.index() * TAU / rods
    feet = graph.points(rods, graph.vec(radius * graph.cos(turn), radius * graph.sin(turn), 0.0))
    stays = graph.iop(feet, graph.rod((0.0, 0.0, 0.0), graph.vec(0.0, 0.0, suspension), 0.015, 6))
    graph.result(graph.mat(graph.smooth(graph.join(ring, stays)), material))
    return graph


@asset("CF.Arch.Planter", "Architecture")
def planter():
    """Raised planting bed: a stone kerb round a bed of dark blue moss,
    ``Width`` across, running ``Length`` along +Y from the origin."""
    graph = GN("CF.Arch.Planter", planter.__doc__)
    width = graph.inp("Width", default=2.4, subtype="DISTANCE")
    length = graph.inp("Length", default=6.0, subtype="DISTANCE")
    height = graph.inp("Height", default=0.45, subtype="DISTANCE")
    kerb = graph.inp("Kerb", default=0.16, subtype="DISTANCE")
    stone_material = graph.inp("Stone Material", "MATERIAL", default=M.get("CF.Stone"))
    soil_material = graph.inp("Soil Material", "MATERIAL", default=M.get("CF.Soil"))
    half = width * 0.5
    rim = graph.join(graph.box(half * -1.0, 0.0, 0.0, half * -1.0 + kerb, length, height),
                     graph.box(half - kerb, 0.0, 0.0, half, length, height),
                     graph.box(half * -1.0 + kerb, 0.0, 0.0, half - kerb, kerb, height),
                     graph.box(half * -1.0 + kerb, length - kerb, 0.0, half - kerb, length, height))
    bed = graph.box(half * -1.0 + kerb, kerb, 0.0, half - kerb, length - kerb, height - 0.05)
    graph.result(graph.join(graph.mat(rim, stone_material), graph.mat(bed, soil_material)))
    return graph


@asset("CF.Arch.LightPillar", "Architecture")
def light_pillar():
    """Pillar of light: a tall glass tube around a luminous core on a stone
    drum, silver bands around it, motes of light rising inside."""
    graph = GN("CF.Arch.LightPillar", light_pillar.__doc__)
    height = graph.inp("Height", default=18.0, subtype="DISTANCE")
    radius = graph.inp("Radius", default=1.1, subtype="DISTANCE")
    core = graph.inp("Core Radius", default=0.28, subtype="DISTANCE")
    bands = graph.inp("Bands", "INT", default=5, min=0, max=20)
    motes = graph.inp("Motes", "INT", default=500, min=0, max=10000)
    rise = graph.inp("Rise", default=0.9, desc="Metres per second")
    seed = graph.inp("Seed", "INT", default=0)
    glass_material = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.Glass"))
    core_material = graph.inp("Core Material", "MATERIAL", default=M.get("CF.LightCore"))
    stone_material = graph.inp("Stone Material", "MATERIAL", default=M.get("CF.Stone"))
    metal_material = graph.inp("Metal Material", "MATERIAL", default=M.get("CF.Silver"))
    mote_material = graph.inp("Mote Material", "MATERIAL", default=M.get("CF.Mote"))

    wall = 0.035
    section = [(radius - wall, 0.0), (radius, 0.0), (radius, height), (radius - wall, height), (radius - wall, 0.0)]
    tube = graph.smooth_by_angle(graph.lathe(section, 64), 0.7)
    beam = graph.move(graph.cylinder(core, height, 32), z=height * 0.5)
    base = graph.join(graph.move(graph.cylinder(radius + 0.45, 0.55, 64), z=0.0),
                      graph.move(graph.cylinder(radius + 0.3, 0.12, 64), z=0.33))
    hoop = graph.n("GeometryNodeCurvePrimitiveCircle", Resolution=64, Radius=radius + 0.015).o
    hoop = graph.tube(hoop, 0.035, 10)
    levels = graph.mesh_line(bands, graph.vec(0.0, 0.0, height / (bands + 1.0)),
                             graph.vec(0.0, 0.0, height / (bands + 1.0)))
    hoops = graph.iop(graph.mesh_to_points(levels), hoop)

    index = graph.index()
    turn = index * PHY.GOLDEN_ANGLE
    reach = core + 0.06 + graph.math("SQRT", graph.random(0.0, 1.0, seed)) * (radius - wall - core - 0.12)
    seconds = graph.scene_time()
    climb = graph.math("FRACT", graph.random(0.0, 1.0, seed + 1) + seconds * rise / height) * height
    sway = seconds * 0.4 + graph.random(0.0, TAU, seed + 2)
    position = graph.vec(reach * graph.cos(turn + graph.sin(sway) * 0.15),
                         reach * graph.sin(turn + graph.sin(sway) * 0.15), climb)
    size = 0.01 + graph.math("POWER", graph.random(0.0, 1.0, seed + 3), 3.0) * 0.03
    cloud = graph.points(motes, position, size)
    twinkle = 0.55 + graph.sin(seconds * graph.random(1.5, 4.0, seed + 4) + graph.random(0.0, TAU, seed + 5)) * 0.45
    cloud = graph.store(cloud, "glow", twinkle)
    cloud = graph.store(cloud, "hue", graph.random(0.0, 1.0, seed + 6))

    graph.result(graph.join(graph.mat(tube, glass_material), graph.mat(beam, core_material),
                            graph.mat(base, stone_material), graph.mat(graph.smooth(hoops), metal_material),
                            graph.mat(cloud, mote_material)))
    return graph
