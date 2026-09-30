"""
Furniture kit -- geometry-node groups (``GH.Furniture.*``): glass furniture
of the gallery.

Local frames: everything stands on z = 0; tables are centred on the
origin.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset
from . import materials as M


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
    """Round table on ``Legs`` round glass legs set in from the rim: a top
    of ``Top Material`` (milk glass by default) with a clear glass edge."""
    graph = GN("GH.Furniture.GlassTable", glass_table.__doc__)
    radius = graph.inp("Radius", default=0.5, subtype="DISTANCE")
    height = graph.inp("Height", default=0.45, subtype="DISTANCE")
    top_thickness = graph.inp("Top Thickness", default=0.019, subtype="DISTANCE")
    legs = graph.inp("Legs", "INT", default=3, min=1)
    leg_radius = graph.inp("Leg Radius", default=0.02, subtype="DISTANCE")
    inset = graph.inp("Leg Inset", default=0.75, min=0.0, max=1.0)
    glass = graph.inp("Glass", "MATERIAL", default=M.get("GH.GlassJade"))
    top_material = graph.inp("Top Material", "MATERIAL", default=M.get("GH.MilkGlass"))

    top = graph.smooth_by_angle(graph.move(graph.cylinder(radius, top_thickness, 128), z=height - top_thickness * 0.5), 0.8)
    edge = graph.cylinder(radius + 0.004, top_thickness * 0.8, 128)
    ring = graph.n("GeometryNodeMeshBoolean", Mesh_1=edge, props={"operation": "DIFFERENCE", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(ring.n, "Mesh 2"), [graph.cylinder(radius - 0.012, top_thickness, 128)])
    edge = graph.move(ring["Mesh"], z=height - top_thickness * 0.5)
    stations = graph.points(legs, (0.0, 0.0, 0.0))
    angle = graph.index() * (math.tau / graph.max(legs, 1))
    stations = graph.set_pos(stations, pos=graph.vec(graph.cos(angle) * radius * inset, graph.sin(angle) * radius * inset, 0.0))
    leg = graph.smooth(graph.move(graph.cylinder(leg_radius, height - top_thickness, 16), z=(height - top_thickness) * 0.5))
    top = graph.mat(graph.move(graph.cylinder(radius - 0.012, top_thickness * 0.6, 128), z=height - top_thickness * 0.5), top_material)
    graph.result(graph.join(top, M.glazed(graph, graph.join(edge, graph.realize(graph.iop(stations, leg))), glass)))
    return graph
