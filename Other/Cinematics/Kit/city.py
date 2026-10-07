"""
City kit (``CIN.City.*``): the high-rise district round a set, built by geometry nodes.

``CIN.City.Field``: tower blocks on the cells of a grid ``Spacing`` metres square over the
rectangle ``Origin`` +- ``Extent`` (``Count`` draws, one block to a cell), none within
``Clear`` metres of ``Keep`` (the set's own buildings stand there).  A block fills its cell
but for the street (``Street`` metres) -- between ``Narrow`` and that much of the cell on
each side -- and stands between ``Low`` and ``High`` metres tall, drawn towards the low end
by ``Skew``; a share ``Crown`` of them carry a narrower top ``Storey`` * 2-5 storeys high,
and every roof its plant room.  Blocks stand square to the grid.

Every block keeps where it stands (``origin``) and a draw of its own (``variant``), and every
point of it its place on the block (``facade``: metres from the foot of the block's middle):
``CIN.Facade`` lays the block's storeys and bays by them, so a block's windows are its own
wherever it stands.
"""
from __future__ import annotations

from Core.gn import GN, asset
from . import materials as M

SEEDS = {"x": 1.0, "y": 2.0, "width": 3.0, "depth": 4.0, "height": 5.0, "crown": 6.0, "crown height": 7.0,
         "plant x": 8.0, "plant y": 9.0, "plant size": 10.0, "variant": 11.0}


@asset("CIN.City.Field", "City")
def field():
    """Tower blocks on a grid round the set (see the module notes)."""
    graph = GN("CIN.City.Field", field.__doc__)
    count = graph.inp("Count", "INT", default=400, min=0)
    seed = graph.inp("Seed", "INT", default=0)
    origin = graph.inp("Origin", "VECTOR", default=(0.0, 0.0, 0.0), subtype="TRANSLATION")
    extent = graph.inp("Extent", "VECTOR", default=(800.0, 800.0, 0.0), subtype="TRANSLATION")
    spacing = graph.inp("Spacing", default=48.0, min=1.0, subtype="DISTANCE")
    street = graph.inp("Street", default=14.0, min=0.0, subtype="DISTANCE")
    keep = graph.inp("Keep", "VECTOR", default=(0.0, 0.0, 0.0), subtype="TRANSLATION")
    clear = graph.inp("Clear", default=120.0, min=0.0, subtype="DISTANCE")
    low = graph.inp("Low", default=30.0, min=0.0, subtype="DISTANCE")
    high = graph.inp("High", default=140.0, min=0.0, subtype="DISTANCE")
    skew = graph.inp("Skew", default=1.6, min=0.1, desc="Above 1 draws the heights towards Low")
    narrow = graph.inp("Narrow", default=0.55, min=0.05, max=1.0, desc="Least share of the cell a block fills")
    crown = graph.inp("Crown", default=0.35, min=0.0, max=1.0, desc="Share of the blocks with a narrower top")
    storey = graph.inp("Storey", default=3.6, min=0.5, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Facade"))

    def draw(key, low_value=0.0, high_value=1.0):
        return graph.random(low_value, high_value, seed * 43 + int(SEEDS[key]), ID=graph.index())

    points = graph.new_points(count)
    spread = origin + graph.vec(draw("x", -1.0, 1.0), draw("y", -1.0, 1.0), 0.0) * extent
    cell = graph.vec(graph.floor(spread.x / spacing) + 0.5, graph.floor(spread.y / spacing) + 0.5, 0.0) * spacing
    points = graph.set_pos(points, pos=graph.vec(cell.x, cell.y, origin.z))
    points = graph.n("GeometryNodeMergeByDistance", Geometry=points, Distance=spacing * 0.25).o
    away = graph.vec(graph.position().x - keep.x, graph.position().y - keep.y, 0.0).length()
    points = graph.delete(points, graph.compare(away, clear, "LESS_THAN"))
    room = graph.max(spacing - street, 1.0)
    width = room * draw("width", narrow, 1.0)
    depth = room * draw("depth", narrow, 1.0)
    height = low + (high - low) * (draw("height") ** skew)
    points = graph.store(points, "origin", graph.position(), "FLOAT_VECTOR")
    points = graph.store(points, "variant", draw("variant"))
    foot = graph.position()
    crowned = graph.compare(draw("crown"), crown, "LESS_THAN")
    crown_height = storey * graph.floor(draw("crown height", 2.0, 6.0))
    plant = graph.vec(draw("plant x", -0.25, 0.25) * width, draw("plant y", -0.25, 0.25) * depth, 0.0)
    plant_size = draw("plant size", 3.0, 8.0)
    top = graph.switch(crowned, height, height + crown_height, "FLOAT")
    unit = graph.cube((1.0, 1.0, 1.0))

    def blocks(centre, size, selection=None):
        return graph.iop(graph.set_pos(points, pos=centre), unit, scale=size, sel=selection)

    body = blocks(foot + graph.vec(0.0, 0.0, height * 0.5), graph.vec(width, depth, height))
    upper = blocks(foot + graph.vec(0.0, 0.0, height + crown_height * 0.5), graph.vec(width * 0.68, depth * 0.68, crown_height), crowned)
    room_on_roof = blocks(foot + plant + graph.vec(0.0, 0.0, top + 1.6), graph.vec(plant_size, plant_size * 0.7, 3.2))
    city = graph.realize(graph.join(body, upper, room_on_roof))
    city = graph.store(city, "facade", graph.position() - graph.named("origin", "FLOAT_VECTOR"), "FLOAT_VECTOR")
    graph.result(graph.mat(city, material))
    return graph
