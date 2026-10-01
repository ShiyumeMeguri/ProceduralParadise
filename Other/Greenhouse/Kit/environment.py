"""
Environment kit -- geometry-node groups (``GH.Garden.*``, ``GH.Env.*``):
the garden floor, the planting and the city outside.

The garden is laid on data meshes: paving flags and deck boards fill the
faces of the object's mesh, planting scatters a collection of plant
prototypes over them.  The city is far enough away to be simple solids.

Local frames: garden assets work in the object's own space on the faces
they are given; the tower stands on z = 0 centred on the origin.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset
from Core.render import INK_QUIET
from . import materials as M


@asset("GH.Garden.Paving", "Garden")
def paving():
    """Stone flags: every face of the mesh is cut into flags of ``Flag
    Size`` with ``Joint`` gaps, each flag ``Thickness`` thick with its own
    ``flag_shade``, bedded on grout (the mesh itself, a little below the
    flags' tops) that shows in the joints.  The paving is quiet for the ink
    pass: a joint is a change of shade, not a drawn line."""
    graph = GN("GH.Garden.Paving", paving.__doc__)
    area = graph.inp("Geometry", "GEOMETRY")
    size = graph.inp("Flag Size", default=0.6, subtype="DISTANCE")
    joint = graph.inp("Joint", default=0.01, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.04, subtype="DISTANCE")
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Paving"))

    bounds = graph.bound_box(area)
    low, high = bounds["Min"], bounds["Max"]
    extent = high - low
    columns = graph.to_int(extent.x / size, "CEILING")
    rows = graph.to_int(extent.y / size, "CEILING")
    grid = graph.grid(1.0, 1.0, columns + 1, rows + 1)
    grid = graph.transform(grid, t=graph.vec(low.x + columns * size * 0.5, low.y + rows * size * 0.5, low.z),
                           s=graph.vec(columns * size, rows * size, 1.0))
    inside = graph.raycast(area, graph.position() + graph.vec(0.0, 0.0, 1.0), graph.vec(0.0, 0.0, -1.0), 2.0)["Is Hit"]
    grid = graph.delete(grid, graph.bool_not(inside), "FACE")
    flags = graph.n("GeometryNodeSplitEdges", Mesh=grid).o
    flags = graph.n("GeometryNodeScaleElements", Geometry=flags, Scale=1.0 - joint / size, props={"domain": "FACE"}).o
    flags = graph.store(flags, "flag_shade", graph.random(0.0, 1.0, seed), "FLOAT", "FACE")
    slabs = graph.extrude(flags, thickness, individual=True)
    grout = graph.store(graph.move(area, z=-0.003), "flag_shade", 0.35, "FLOAT", "FACE")
    paving_mesh = graph.join(graph.move(slabs, z=thickness * -1.0), grout)
    graph.result(graph.mat(graph.store(paving_mesh, INK_QUIET, 1.0, "FLOAT", "FACE"), material))
    return graph


@asset("GH.Garden.Deck", "Garden")
def deck():
    """Timber decking over the faces of the mesh: boards of ``Board Width``
    running along X with ``Gap`` between them, each with its own
    ``board_shade``."""
    graph = GN("GH.Garden.Deck", deck.__doc__)
    area = graph.inp("Geometry", "GEOMETRY")
    board = graph.inp("Board Width", default=0.14, subtype="DISTANCE")
    gap = graph.inp("Gap", default=0.006, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.03, subtype="DISTANCE")
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Deck"))

    bounds = graph.bound_box(area)
    low, high = bounds["Min"], bounds["Max"]
    extent = high - low
    count = graph.to_int(extent.y / board, "CEILING")
    stations = graph.mesh_line(count, graph.vec(low.x + extent.x * 0.5, low.y + board * 0.5, low.z - thickness * 0.5), graph.vec(0.0, board, 0.0))
    plank = graph.cube(graph.vec(extent.x, board - gap, thickness))
    boards = graph.iop(graph.mesh_to_points(stations), plank)
    boards = graph.store(boards, "board_shade", graph.random(0.0, 1.0, seed), "FLOAT", "INSTANCE")
    graph.result(graph.mat(graph.realize(boards), material))
    return graph


@asset("GH.Garden.Bed", "Garden")
def bed():
    """Planting bed over the faces of the mesh (coincident vertices are
    merged, so a bed may be drawn cell by cell): soil filled to ``Soil``
    above the mesh, mounded by ``Mound`` towards the middle, edged by a low
    steel kerb of ``Kerb`` height (none at 0)."""
    graph = GN("GH.Garden.Bed", bed.__doc__)
    area = graph.inp("Geometry", "GEOMETRY")
    soil_height = graph.inp("Soil", default=0.1, subtype="DISTANCE")
    mound = graph.inp("Mound", default=0.1, subtype="DISTANCE")
    kerb = graph.inp("Kerb", default=0.15, subtype="DISTANCE")
    soil_material = graph.inp("Soil Material", "MATERIAL", default=M.get("GH.Soil"))
    kerb_material = graph.inp("Kerb Material", "MATERIAL", default=M.get("GH.Steel"))

    area = graph.merge(area, 0.001)
    surface = graph.subdiv(area, 3)
    center = graph.bound_box(area)
    middle = (center["Min"] + center["Max"]) * 0.5
    reach = (center["Max"] - center["Min"]).length() * 0.5
    closeness = 1.0 - graph.vmath("DISTANCE", graph.position(), middle) / graph.max(reach, 0.001)
    top = graph.set_pos(surface, offset=graph.vec(0.0, 0.0, soil_height + mound * graph.max(closeness, 0.0)))
    soil = graph.mat(graph.smooth(top), soil_material)
    boundary = graph.compare(graph.n("GeometryNodeInputMeshEdgeNeighbors")["Face Count"], 1, "EQUAL", "INT")
    edges = graph.n("GeometryNodeMeshToCurve", Mesh=area, Selection=boundary).o
    kerb_mesh = graph.flat_sweep(graph.move(edges, z=kerb * 0.5), 0.012, kerb)
    kerb_mesh = graph.switch(graph.compare(kerb, 0.001, "GREATER_THAN"), None, graph.mat(kerb_mesh, kerb_material))
    graph.result(graph.join(soil, kerb_mesh))
    return graph


@asset("GH.Garden.Planting", "Garden")
def planting():
    """Plants scattered over the faces of the mesh: instances of the objects
    in ``Plants`` (picked at random) at ``Density`` per square metre, at
    least ``Spacing`` apart, each turned at random and scaled between
    ``Scale Min`` and ``Scale Max``, lifted by ``Lift``."""
    graph = GN("GH.Garden.Planting", planting.__doc__)
    area = graph.inp("Geometry", "GEOMETRY")
    plants = graph.inp("Plants", "COLLECTION")
    density = graph.inp("Density", default=4.0, min=0.0)
    spacing = graph.inp("Spacing", default=0.3, subtype="DISTANCE")
    low = graph.inp("Scale Min", default=0.8)
    high = graph.inp("Scale Max", default=1.2)
    lift = graph.inp("Lift", default=0.0, subtype="DISTANCE")
    seed = graph.inp("Seed", "INT", default=0)

    spots = graph.n("GeometryNodeDistributePointsOnFaces", Mesh=area, Distance_Min=spacing, Density_Max=density, Seed=seed,
                    props={"distribute_method": "POISSON"})["Points"]
    spots = graph.set_pos(spots, offset=graph.vec(0.0, 0.0, lift))
    library = graph.collection_info(plants, True, True)
    rotation = graph.vec(0.0, 0.0, graph.random(0.0, math.tau, seed + 1))
    scale = graph.random(low, high, seed + 2)
    graph.result(graph.iop(spots, library, rot=rotation, scale=scale, pick=True, index=graph.random(0, 1000, seed + 3, dtype="INT")))
    return graph


@asset("GH.Env.Ground", "Environment")
def ground():
    """Ground from a solid of the mesh (a plinth, a terrace): the faces
    turned up more than ``Slope`` (the up component of their normal) are its
    ``Top`` -- lawn, paving -- the rest its ``Sides``, the face of a
    retaining wall or a cliff."""
    graph = GN("GH.Env.Ground", ground.__doc__)
    mesh = graph.inp("Geometry", "GEOMETRY")
    slope = graph.inp("Slope", default=0.7, min=0.0, max=1.0)
    top = graph.inp("Top", "MATERIAL", default=M.get("GH.Lawn"))
    sides = graph.inp("Sides", "MATERIAL", default=M.get("GH.Cliff"))
    _, _, up = graph.sep(graph.normal())
    graph.result(graph.mat(graph.mat(mesh, sides), top, sel=graph.compare(up, slope, "GREATER_THAN")))
    return graph


@asset("GH.Env.Pool", "Environment")
def pool():
    """Raised reflecting pool ``Length`` (along X) by ``Width``, centred on
    the origin on the ground: stone walls ``Coping`` thick rising ``Height``
    round a basin lined with ``Basin``, filled with ``Water`` to
    ``Freeboard`` below their top."""
    graph = GN("GH.Env.Pool", pool.__doc__)
    length = graph.inp("Length", default=12.0, subtype="DISTANCE")
    width = graph.inp("Width", default=4.0, subtype="DISTANCE")
    height = graph.inp("Height", default=0.45, subtype="DISTANCE")
    coping = graph.inp("Coping", default=0.4, subtype="DISTANCE")
    freeboard = graph.inp("Freeboard", default=0.06, subtype="DISTANCE")
    stone = graph.inp("Stone", "MATERIAL", default=M.get("GH.Stone"))
    basin = graph.inp("Basin", "MATERIAL", default=M.get("GH.PoolTile"))
    water = graph.inp("Water", "MATERIAL", default=M.get("GH.PoolWater"))

    outer_x = length * 0.5 + coping
    outer_y = width * 0.5 + coping
    walls = graph.join(
        graph.box(outer_x * -1.0, width * 0.5, 0.0, outer_x, outer_y, height),
        graph.box(outer_x * -1.0, outer_y * -1.0, 0.0, outer_x, width * -0.5, height),
        graph.box(outer_x * -1.0, width * -0.5, 0.0, length * -0.5, width * 0.5, height),
        graph.box(length * 0.5, width * -0.5, 0.0, outer_x, width * 0.5, height))
    shell = graph.box(length * -0.5, width * -0.5, 0.02, length * 0.5, width * 0.5, height)
    _, _, up = graph.sep(graph.normal())
    shell = graph.delete(shell, graph.compare(up, 0.5, "GREATER_THAN"), "FACE")
    surface = graph.transform(graph.grid(1.0, 1.0, 2, 2), t=graph.vec(0.0, 0.0, height - freeboard), s=graph.vec(length, width, 1.0))
    graph.result(graph.join(graph.mat(walls, stone), graph.mat(shell, basin), M.glazed(graph, surface, water)))
    return graph


@asset("GH.Env.Tower", "Environment")
def tower():
    """Office tower of ``Width`` x ``Depth`` x ``Height``: a curtain wall of
    ``Bay`` wide, ``Floor`` high panes, each catching the sky differently
    (``pane_shade``), on a grid of mullions."""
    graph = GN("GH.Env.Tower", tower.__doc__)
    width = graph.inp("Width", default=30.0, subtype="DISTANCE")
    depth = graph.inp("Depth", default=30.0, subtype="DISTANCE")
    height = graph.inp("Height", default=120.0, subtype="DISTANCE")
    bay = graph.inp("Bay", default=1.5, subtype="DISTANCE")
    floor = graph.inp("Floor", default=4.0, subtype="DISTANCE")
    frame = graph.inp("Frame", default=0.12, subtype="DISTANCE")
    seed = graph.inp("Seed", "INT", default=0)

    columns_x = graph.to_int(width / bay, "ROUND") + 1
    columns_y = graph.to_int(depth / bay, "ROUND") + 1
    floors = graph.to_int(height / floor, "ROUND") + 1
    box = graph.cube(graph.vec(width, depth, height), columns_x, columns_y, floors)
    box = graph.move(box, z=height * 0.5)
    walls = graph.delete(box, graph.compare(graph.abs(graph.normal().z), 0.5, "GREATER_THAN"), "FACE")
    panes = graph.store(walls, "pane_shade", graph.random(0.0, 1.0, seed), "FLOAT", "FACE")
    glass_mesh = graph.mat(panes, M.get("GH.TowerGlass"))
    grid_lines = graph.n("GeometryNodeMeshToCurve", Mesh=walls).o
    mullions = graph.sweep(grid_lines, graph.rect(frame, frame), True)
    roof = graph.mat(graph.box(width * -0.5, depth * -0.5, height - 0.1, width * 0.5, depth * 0.5, height + 0.6), M.get("GH.TowerFrame"))
    graph.result(graph.join(glass_mesh, graph.mat(mullions, M.get("GH.TowerFrame")), roof))
    return graph


@asset("GH.Env.Haze", "Environment")
def haze():
    """Box of air between the corners ``Min`` and ``Max`` (in the object's
    space), filled with the smog volume, less the box between ``Hole Min``
    and ``Hole Max`` when that is not empty: a building the haze surrounds
    but does not fill (its faces turned inwards, so a ray leaving the hole
    enters the haze)."""
    graph = GN("GH.Env.Haze", haze.__doc__)
    low = graph.inp("Min", "VECTOR", default=(-5.0, -5.0, 0.0))
    high = graph.inp("Max", "VECTOR", default=(5.0, 5.0, 5.0))
    hole_low = graph.inp("Hole Min", "VECTOR", default=(0.0, 0.0, 0.0))
    hole_high = graph.inp("Hole Max", "VECTOR", default=(0.0, 0.0, 0.0))
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Smog"))
    outer = graph.transform(graph.cube((1.0, 1.0, 1.0)), t=(low + high) * 0.5, s=high - low)
    hole = graph.n("GeometryNodeFlipFaces", graph.transform(graph.cube((1.0, 1.0, 1.0)), t=(hole_low + hole_high) * 0.5, s=hole_high - hole_low)).o
    has_hole = graph.compare((hole_high - hole_low).length(), 0.0001, "GREATER_THAN")
    graph.result(graph.mat(graph.join(outer, graph.switch(has_hole, None, hole)), material))
    return graph
