"""
Hall kit (``CIN.Hall.*``): the pieces of a bright interior, built by geometry nodes.

``CIN.Box``: a box between the corners ``Min`` and ``Max`` in ``Material`` -- a slab, a wall, a
pane, a light panel, the dark core of a building seen through its frame.

``CIN.Hall.Halo``: a ring hung from a ceiling, its centre at the object's origin: an annulus
``Outer`` and ``Inner`` metres in radius and ``Depth`` deep, from ``Start`` to ``End``
(degrees about +Z from +X; all the way round by default), a cap over its hole when it goes all
the way round and ``Cap`` asks for one, and round the inside of the hole a band of light
``Glow Width`` high (``Glow Material``; none when 0).

``CIN.Hall.Crystal``: a faceted spike hanging point down from the object's origin, ``Length``
long and ``Radius`` across at its root, ``Facets`` faces round, each facet tilted a little by
``Seed`` so the light breaks on them.

``CIN.Hall.Lockers``: a wall of doors on the object's XZ plane (facing -Y): ``Columns`` by
``Rows`` doors ``Door`` (width, height) with ``Gap`` between them and ``Relief`` deep, from the
object's origin up and along +X, a handle on each.

``CIN.Hall.Stripe``: a line painted on a floor: ``Width`` wide, ``Thickness`` proud, along an
arc about the object's origin of ``Radius`` from ``Start`` to ``End`` (degrees about +Z from
+X) -- a straight run when ``Radius`` is 0, ``Length`` along +X.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, set_mode
from . import materials as M


@asset("CIN.Box", "Hall")
def box():
    """A box between ``Min`` and ``Max`` in ``Material``."""
    graph = GN("CIN.Box", box.__doc__)
    low = graph.inp("Min", "VECTOR", default=(-1.0, -1.0, 0.0), subtype="TRANSLATION")
    high = graph.inp("Max", "VECTOR", default=(1.0, 1.0, 1.0), subtype="TRANSLATION")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.HallWall"))
    graph.result(graph.mat(graph.transform(graph.cube((1.0, 1.0, 1.0)), t=(low + high) * 0.5, s=high - low), material))
    return graph


@asset("CIN.Hall.Halo", "Hall")
def halo():
    """A ring hung from a ceiling with a band of light round its hole (see the module notes)."""
    graph = GN("CIN.Hall.Halo", halo.__doc__)
    outer = graph.inp("Outer", default=6.0, min=0.1, subtype="DISTANCE")
    inner = graph.inp("Inner", default=3.6, min=0.05, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.7, min=0.01, subtype="DISTANCE")
    first = graph.inp("Start", default=0.0, subtype="ANGLE")
    last = graph.inp("End", default=math.radians(360.0), subtype="ANGLE")
    capped = graph.inp("Cap", "BOOL", default=True)
    glow_width = graph.inp("Glow Width", default=0.25, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.HallWall"))
    glow_material = graph.inp("Glow Material", "MATERIAL", default=M.get("CIN.HallGlow"))
    segments = 128

    def arc(radius):
        curve = graph.n("GeometryNodeCurveArc", Resolution=segments, Radius=radius, Start_Angle=first, Sweep_Angle=last - first)["Curve"]
        upright = graph.n("GeometryNodeSetCurveNormal", Curve=curve)
        set_mode(upright, "Z_UP")
        return upright.o

    section = graph.n("GeometryNodeCurvePrimitiveQuadrilateral", Width=outer - inner, Height=depth)["Curve"]
    body = graph.n("GeometryNodeCurveToMesh", Curve=arc((outer + inner) * 0.5), Profile_Curve=section, Fill_Caps=True).o
    body = graph.move(body, z=depth * -0.5)
    cap = graph.solid(graph.fill(graph.n("GeometryNodeCurvePrimitiveCircle", Resolution=segments, Radius=inner * 1.02)["Curve"]),
                      depth * 0.25)
    shell = graph.switch(capped, body, graph.join(body, cap))
    strip = graph.n("GeometryNodeCurvePrimitiveLine", Start=graph.vec(0.0, glow_width * -0.5, 0.0),
                    End=graph.vec(0.0, glow_width * 0.5, 0.0))["Curve"]
    band = graph.n("GeometryNodeCurveToMesh", Curve=arc(inner * 0.995), Profile_Curve=strip).o
    band = graph.move(band, z=depth * -0.5)
    lit = graph.compare(glow_width, 0.0, "GREATER_THAN")
    glow = graph.switch(lit, graph.n("GeometryNodeMeshLine", Count=0)["Mesh"], graph.mat(band, glow_material))
    graph.result(graph.join(graph.mat(shell, material), glow))
    return graph


@asset("CIN.Hall.Crystal", "Hall")
def crystal():
    """A faceted spike hanging point down (see the module notes)."""
    graph = GN("CIN.Hall.Crystal", crystal.__doc__)
    length = graph.inp("Length", default=6.0, min=0.1, subtype="DISTANCE")
    radius = graph.inp("Radius", default=0.45, min=0.01, subtype="DISTANCE")
    facets = graph.inp("Facets", "INT", default=7, min=3)
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Gold"))
    spike = graph.n("GeometryNodeMeshCone", Vertices=facets, Radius_Top=radius, Radius_Bottom=0.0, Depth=length,
                    props={"fill_type": "NGON"})["Mesh"]
    spike = graph.set_pos(spike, offset=graph.vec(0.0, 0.0, graph.sep(graph.bound_box(spike)["Max"])[2] * -1.0))
    tilt = graph.random(-0.12, 0.12, seed, ID=graph.index()) * radius
    spike = graph.set_pos(spike, offset=graph.vec(tilt, graph.random(-0.12, 0.12, seed + 7, ID=graph.index()) * radius, 0.0))
    graph.result(graph.mat(graph.n("GeometryNodeSplitEdges", Mesh=spike).o, material))
    return graph


@asset("CIN.Hall.Lockers", "Hall")
def lockers():
    """A wall of doors (see the module notes)."""
    graph = GN("CIN.Hall.Lockers", lockers.__doc__)
    columns = graph.inp("Columns", "INT", default=4, min=1)
    rows = graph.inp("Rows", "INT", default=6, min=1)
    door = graph.inp("Door", "VECTOR", default=(0.6, 0.45, 0.0), desc="Width, height")
    gap = graph.inp("Gap", default=0.012, min=0.0, subtype="DISTANCE")
    relief = graph.inp("Relief", default=0.03, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.HallWall"))
    handle_material = graph.inp("Handle Material", "MATERIAL", default=M.get("CIN.HallMetal"))
    width, height = door.x, door.y
    across = graph.n("GeometryNodeMeshLine", Count=columns, Offset=graph.vec(width, 0.0, 0.0)).o
    up = graph.n("GeometryNodeMeshLine", Count=rows, Offset=graph.vec(0.0, 0.0, height)).o
    grid = graph.realize(graph.iop(graph.n("GeometryNodeMeshToPoints", Mesh=across).o, up))
    spots = graph.n("GeometryNodeMeshToPoints", Mesh=grid).o
    spots = graph.set_pos(spots, offset=graph.vec(width * 0.5, 0.0, height * 0.5))
    panel = graph.transform(graph.cube((1.0, 1.0, 1.0)), s=graph.vec(width - gap, relief, height - gap))
    handle = graph.transform(graph.cube((1.0, 1.0, 1.0)), t=graph.vec(width * 0.38, relief * -0.6, 0.0),
                             s=graph.vec(0.012, relief * 0.6, height * 0.25))
    doors = graph.iop(spots, graph.mat(panel, material))
    handles = graph.iop(spots, graph.mat(handle, handle_material))
    graph.result(graph.realize(graph.join(doors, handles)))
    return graph


@asset("CIN.Hall.Stripe", "Hall")
def stripe():
    """A line painted on a floor (see the module notes)."""
    graph = GN("CIN.Hall.Stripe", stripe.__doc__)
    radius = graph.inp("Radius", default=10.0, min=0.0, subtype="DISTANCE")
    start = graph.inp("Start", default=0.0, subtype="ANGLE")
    end = graph.inp("End", default=math.radians(60.0), subtype="ANGLE")
    length = graph.inp("Length", default=10.0, min=0.0, subtype="DISTANCE")
    width = graph.inp("Width", default=0.12, min=0.001, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.003, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.HallPaint"))
    straight = graph.compare(radius, 0.0001, "LESS_THAN")
    arc = graph.n("GeometryNodeCurveArc", Resolution=128, Radius=radius, Start_Angle=start, Sweep_Angle=end - start)["Curve"]
    line = graph.n("GeometryNodeCurvePrimitiveLine", Start=graph.vec(0.0, 0.0, 0.0), End=graph.vec(length, 0.0, 0.0))["Curve"]
    path = graph.switch(straight, arc, graph.n("GeometryNodeResampleCurve", Curve=line, Count=2).o)
    profile = graph.n("GeometryNodeCurvePrimitiveLine", Start=graph.vec(width * -0.5, 0.0, 0.0),
                      End=graph.vec(width * 0.5, 0.0, 0.0))["Curve"]
    ribbon = graph.n("GeometryNodeCurveToMesh", Curve=path, Profile_Curve=profile).o
    graph.result(graph.mat(graph.solid(ribbon, thickness), material))
    return graph
