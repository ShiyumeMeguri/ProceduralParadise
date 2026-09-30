"""
Furniture kit -- geometry-node groups (``GH.Furniture.*``): glass furniture
of the gallery.

Local frames: everything stands on z = 0; a chair faces -Y (its back is on
the +Y side); tables are centred on the origin.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset
from . import materials as M

ROD_BOTTOM = [(math.sin(math.pi * 0.5 * k / 8), 1.0 - math.cos(math.pi * 0.5 * k / 8)) for k in range(9)]
ROD_TOP = [(math.cos(math.pi * 0.5 * k / 8), 2.0 + math.sin(math.pi * 0.5 * k / 8)) for k in range(9)]
ROD_PROFILE = ROD_BOTTOM + ROD_TOP


def rounded_slab(graph, width, depth, thickness, radius):
    """Rounded rectangle ``width`` x ``depth`` extruded ``thickness`` up
    from z = 0."""
    outline = graph.fillet(graph.rect(width, depth), radius, 6, True, "POLY")
    return graph.solid(graph.fill(outline), thickness)


def rod(graph, start, end, radius):
    """Glass rod with rounded ends from ``start`` to ``end``: a capsule
    lathed as one closed surface, its upper half moved up to the length."""
    span = end - start
    capsule = graph.lathe(ROD_PROFILE, 24, 1.0)
    x, y, z = graph.sep(graph.position())
    lift = graph.switch(graph.compare(z, 1.5, "GREATER_THAN"), 0.0, span.length() - radius * 3.0, "FLOAT")
    capsule = graph.set_pos(capsule, pos=graph.vec(x * radius, y * radius, z * radius + lift))
    return graph.transform(capsule, r=graph.align_rotation(span, axis="Z"), t=start)


@asset("GH.Furniture.GlassChair", "Furniture")
def glass_chair():
    """Chair of thick jade glass: a rounded seat slab at ``Seat Height``, a
    tall back slab rising from its back edge (leaning back by ``Back
    Lean``), and four round legs from the corners of the seat (``Leg
    Inset`` of the way from the centre) to the floor.  Front feet land
    ``Front Splay`` ahead of their corner, back feet ``Back Splay`` behind
    it, all feet ``Side Splay`` out to the side."""
    graph = GN("GH.Furniture.GlassChair", glass_chair.__doc__)
    width = graph.inp("Width", default=0.44, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.42, subtype="DISTANCE")
    seat_height = graph.inp("Seat Height", default=0.45, subtype="DISTANCE")
    seat_thickness = graph.inp("Seat Thickness", default=0.03, subtype="DISTANCE")
    back_height = graph.inp("Back Height", default=0.62, subtype="DISTANCE")
    back_width = graph.inp("Back Width", default=0.16, subtype="DISTANCE")
    back_thickness = graph.inp("Back Thickness", default=0.045, subtype="DISTANCE")
    back_lean = graph.inp("Back Lean", default=math.radians(8.0), subtype="ANGLE")
    leg_radius = graph.inp("Leg Radius", default=0.018, subtype="DISTANCE")
    inset = graph.inp("Leg Inset", default=0.9, min=0.0, max=1.0)
    front_splay = graph.inp("Front Splay", default=0.0, subtype="DISTANCE")
    back_splay = graph.inp("Back Splay", default=0.09, subtype="DISTANCE")
    side_splay = graph.inp("Side Splay", default=0.0, subtype="DISTANCE")
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassJade"))

    seat = graph.move(rounded_slab(graph, width, depth, seat_thickness, 0.05), z=seat_height - seat_thickness)
    back = rounded_slab(graph, back_width, back_thickness, back_height, back_thickness * 0.45)
    back = graph.transform(back, r=graph.vec(back_lean * -1.0, 0.0, 0.0), t=graph.vec(0.0, depth * 0.5 - back_thickness * 0.5, seat_height - seat_thickness * 0.5))
    legs = []
    for sx, sy in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)):
        corner_x = width * 0.5 * inset * sx
        corner_y = depth * 0.5 * inset * sy
        top = graph.vec(corner_x, corner_y, seat_height - seat_thickness - leg_radius - 0.001)
        reach = front_splay if sy < 0.0 else back_splay
        foot = graph.vec(corner_x + side_splay * sx, corner_y + reach * sy, leg_radius)
        legs.append(rod(graph, top, foot, leg_radius))
    graph.result(M.glazed(graph, graph.join(graph.smooth_by_angle(graph.join(seat, back), 0.6), graph.smooth(graph.join(*legs))), glass))
    return graph


@asset("GH.Furniture.PedestalTable", "Furniture")
def pedestal_table():
    """Round table: a glass top of ``Radius`` at ``Height`` on a slender
    steel column and a round foot plate."""
    graph = GN("GH.Furniture.PedestalTable", pedestal_table.__doc__)
    radius = graph.inp("Radius", default=0.3, subtype="DISTANCE")
    height = graph.inp("Height", default=0.6, subtype="DISTANCE")
    top_thickness = graph.inp("Top Thickness", default=0.012, subtype="DISTANCE")
    column_radius = graph.inp("Column Radius", default=0.012, subtype="DISTANCE")
    foot_radius = graph.inp("Foot Radius", default=0.18, subtype="DISTANCE")
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassJade"))
    metal = graph.inp("Metal", "MATERIAL", default=M.get("GH.GlassJade"))

    top = graph.cylinder(radius, top_thickness, 96)
    top = graph.smooth_by_angle(graph.move(top, z=height - top_thickness * 0.5), 0.8)
    column = graph.smooth(graph.move(graph.cylinder(column_radius, height - top_thickness, 16), z=(height - top_thickness) * 0.5))
    foot = graph.smooth_by_angle(graph.move(graph.cylinder(foot_radius, 0.01, 64), z=0.005), 0.8)
    graph.result(graph.join(M.glazed(graph, top, glass), graph.mat(graph.join(column, foot), metal)))
    return graph


@asset("GH.Furniture.GlassTable", "Furniture")
def glass_table():
    """Round glass table on ``Legs`` round glass legs set in from the rim."""
    graph = GN("GH.Furniture.GlassTable", glass_table.__doc__)
    radius = graph.inp("Radius", default=0.5, subtype="DISTANCE")
    height = graph.inp("Height", default=0.45, subtype="DISTANCE")
    top_thickness = graph.inp("Top Thickness", default=0.019, subtype="DISTANCE")
    legs = graph.inp("Legs", "INT", default=3, min=1)
    leg_radius = graph.inp("Leg Radius", default=0.02, subtype="DISTANCE")
    inset = graph.inp("Leg Inset", default=0.75, min=0.0, max=1.0)
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassJade"))

    top = graph.smooth_by_angle(graph.move(graph.cylinder(radius, top_thickness, 128), z=height - top_thickness * 0.5), 0.8)
    stations = graph.points(legs, (0.0, 0.0, 0.0))
    angle = graph.index() * (math.tau / graph.max(legs, 1))
    stations = graph.set_pos(stations, pos=graph.vec(graph.cos(angle) * radius * inset, graph.sin(angle) * radius * inset, 0.0))
    leg = graph.smooth(graph.move(graph.cylinder(leg_radius, height - top_thickness, 16), z=(height - top_thickness) * 0.5))
    graph.result(M.glazed(graph, graph.join(top, graph.realize(graph.iop(stations, leg))), glass))
    return graph
