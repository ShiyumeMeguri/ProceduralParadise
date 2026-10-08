"""
Hall kit (``CIN.Hall.*``): the pieces of a bright interior, built by geometry nodes.

``CIN.Box``: a box between the corners ``Min`` and ``Max`` in ``Material`` -- a slab, a wall, a
pane, a light panel, the dark core of a building seen through its frame.

``CIN.Hall.Halo``: a ring hung from a ceiling, its centre at the object's origin: an annulus
``Outer`` and ``Inner`` metres in radius and ``Depth`` deep, from ``Start`` to ``End``
(degrees about +Z from +X; all the way round by default), a cap over its hole when it goes all
the way round and ``Cap`` asks for one, and round the inside of the hole a band of light
``Glow Width`` high (``Glow Material``; none when 0).

``CIN.Hall.Saucer``: a saucer hung from a ceiling, the foot of its rim at the object's origin:
a rim ``Radius`` round, ``Rim`` high and rounded by ``Round``, under it a belly bulging down to
``Drop`` below the rim's foot at ``Underside`` from the axis, a band ``Band`` deep below that,
and through the band a hole ``Hole`` round, hollowed ``Recess`` up into the saucer: the hollow
glows (``Recess Material``), and so does the foot of its wall ``Glow Width`` high
(``Glow Material``).

``CIN.Hall.Cove``: an upright band ``Height`` high and ``Thickness`` thick standing on the
object's origin's level, round an arc ``Radius`` about the origin from ``Start`` to ``End``
(degrees, the way round from +X to +Y) and on, straight, ``Run`` metres the way the arc
leaves off; a strip of light ``Glow Width`` high along its foot and its top.

``CIN.Hall.Crystal``: a spike hanging point down from the object's origin, ``Length`` long and
``Radius`` across at its root, its girth falling off towards the point as the power ``Taper``
of the share of the length left: a net (``Net Material``) gathered over its upper ``Hem`` of
the length, the hem wandering by ``Wobble`` of the length round it (``Seed``), crumpled by
``Crumple`` metres; below the hem its bare core (``Core Material``).

``CIN.Hall.Chain``: a string of beads ``Bead`` round, ``Pitch`` apart, hanging ``Length`` down
from the object's origin.

``CIN.Hall.Lockers``: a wall of doors on the object's XZ plane (facing -Y): ``Columns`` by
``Rows`` doors ``Door`` (width, height) with ``Gap`` between them and ``Relief`` deep, from the
object's origin up and along +X; a vent ``Vent`` (width, height) by each corner of every door,
``Vent Inset`` (from the door's side, its top, its foot) in from it, and under the foot vents
of the lowest row a slot ``Slot`` (width, height), all in ``Vent Material``.

``CIN.Hall.Stripe``: a line painted on a floor: ``Width`` wide, ``Thickness`` proud, along an
arc about the object's origin of ``Radius`` from ``Start`` to ``End`` (degrees about +Z from
+X) -- a straight run when ``Radius`` is 0, ``Length`` along +X.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, set_mode
from . import materials as M

BELLY = 8
ROUND = 4
SAUCER_SEGMENTS = 160
SPIKE_STEPS = 64
SPIKE_SEGMENTS = 128
SLOT_GAP = 0.012


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


def _quarter(center_r, center_z, radius, start):
    """The points of a quarter turn of radius ``radius`` about (``center_r``, ``center_z``) in a profile, from the
    angle ``start`` (radians) on, the first left out."""
    points = []
    for step in range(1, ROUND + 1):
        angle = start + math.pi * 0.5 * step / ROUND
        points.append((center_r + radius * math.cos(angle), center_z + radius * math.sin(angle)))
    return points


@asset("CIN.Hall.Saucer", "Hall")
def saucer():
    """A saucer hung from a ceiling, its hole hollowed up and glowing (see the module notes)."""
    graph = GN("CIN.Hall.Saucer", saucer.__doc__)
    radius = graph.inp("Radius", default=3.0, min=0.1, subtype="DISTANCE")
    rim = graph.inp("Rim", default=0.3, min=0.01, subtype="DISTANCE")
    rounding = graph.inp("Round", default=0.1, min=0.0, subtype="DISTANCE")
    underside = graph.inp("Underside", default=2.5, min=0.05, subtype="DISTANCE")
    drop = graph.inp("Drop", default=0.35, min=0.0, subtype="DISTANCE")
    band = graph.inp("Band", default=0.2, min=0.0, subtype="DISTANCE")
    hole = graph.inp("Hole", default=2.0, min=0.01, subtype="DISTANCE")
    recess = graph.inp("Recess", default=0.3, min=0.0, subtype="DISTANCE")
    glow_width = graph.inp("Glow Width", default=0.06, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.HallShell"))
    recess_material = graph.inp("Recess Material", "MATERIAL", default=M.get("CIN.HallRecess"))
    glow_material = graph.inp("Glow Material", "MATERIAL", default=M.get("CIN.HallGlow"))
    foot = (drop + band) * -1.0
    lip = 0.03
    profile = [(0.0, foot + recess), (hole, foot + recess), (hole, foot + glow_width), (hole, foot),
               (underside - lip, foot), (underside, foot + lip), (underside, drop * -1.0)]
    for step in range(1, BELLY + 1):
        share = step / BELLY
        profile.append((underside + (radius - rounding - underside) * share, drop * -(1.0 - share * share)))
    profile += _quarter(radius - rounding, rounding, rounding, -math.pi * 0.5)
    profile.append((radius, rim - rounding))
    profile += _quarter(radius - rounding, rim - rounding, rounding, 0.0)
    profile.append((0.0, rim))
    body = graph.smooth_by_angle(graph.lathe(profile, segments=SAUCER_SEGMENTS), math.radians(35.0))
    x, y, z = graph.sep(graph.position())
    inside = graph.compare(graph.vmath("LENGTH", graph.vec(x, y, 0.0)), hole + 0.005, "LESS_THAN")
    lit = graph.bool_and(inside, graph.compare(z, foot + glow_width + 0.001, "LESS_THAN"))
    hollow = graph.bool_and(inside, graph.bool_and(graph.compare(z, foot + glow_width + 0.001, "GREATER_THAN"),
                                                   graph.compare(z, foot + recess + 0.001, "LESS_THAN")))
    body = graph.mat(graph.mat(graph.mat(body, material), recess_material, sel=hollow), glow_material, sel=lit)
    graph.result(body)
    return graph


@asset("CIN.Hall.Cove", "Hall")
def cove():
    """An upright band round an arc and on straight, lit along its foot and top (see the module notes)."""
    graph = GN("CIN.Hall.Cove", cove.__doc__)
    radius = graph.inp("Radius", default=4.3, min=0.1, subtype="DISTANCE")
    height = graph.inp("Height", default=1.2, min=0.01, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.06, min=0.001, subtype="DISTANCE")
    first = graph.inp("Start", default=math.radians(-40.0), subtype="ANGLE")
    last = graph.inp("End", default=math.radians(180.0), subtype="ANGLE")
    run = graph.inp("Run", default=8.0, min=0.0, subtype="DISTANCE")
    glow_width = graph.inp("Glow Width", default=0.04, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.HallShell"))
    glow_material = graph.inp("Glow Material", "MATERIAL", default=M.get("CIN.HallGlow"))
    arc = graph.n("GeometryNodeCurveArc", Resolution=160, Radius=radius, Start_Angle=first, Sweep_Angle=last - first)["Curve"]
    end = graph.vec(graph.math("COSINE", last) * radius, graph.math("SINE", last) * radius, 0.0)
    onward = graph.vec(graph.math("SINE", last) * -1.0, graph.math("COSINE", last), 0.0)
    straight = graph.n("GeometryNodeCurvePrimitiveLine", Start=end, End=end + onward * run)["Curve"]
    path = graph.join(arc, straight)

    def strip(low, high, width, strip_material):
        return graph.mat(graph.move(graph.flat_sweep(path, width, high - low), z=(low + high) * 0.5), strip_material)

    wall = strip(0.0, height, thickness, material)
    lit = graph.compare(glow_width, 0.0, "GREATER_THAN")
    lights = graph.join(strip(-0.002, glow_width, thickness + 0.004, glow_material),
                        strip(height - glow_width, height + 0.002, thickness + 0.004, glow_material))
    graph.result(graph.join(wall, graph.switch(lit, graph.n("GeometryNodeMeshLine", Count=0)["Mesh"], lights)))
    return graph


@asset("CIN.Hall.Crystal", "Hall")
def crystal():
    """A spike hanging point down, a crumpled net gathered over its upper part (see the module notes)."""
    graph = GN("CIN.Hall.Crystal", crystal.__doc__)
    length = graph.inp("Length", default=3.4, min=0.1, subtype="DISTANCE")
    radius = graph.inp("Radius", default=0.4, min=0.01, subtype="DISTANCE")
    taper = graph.inp("Taper", default=0.7, min=0.05)
    hem = graph.inp("Hem", default=0.6, min=0.0, max=1.0)
    wobble = graph.inp("Wobble", default=0.06, min=0.0, max=1.0)
    crumple = graph.inp("Crumple", default=0.015, min=0.0, subtype="DISTANCE")
    seed = graph.inp("Seed", "INT", default=0)
    net_material = graph.inp("Net Material", "MATERIAL", default=M.get("CIN.HallNet"))
    core_material = graph.inp("Core Material", "MATERIAL", default=M.get("CIN.HallCore"))
    profile = [(0.0, length * -1.0)]
    for step in range(1, SPIKE_STEPS + 1):
        share = step / SPIKE_STEPS
        profile.append((radius * graph.math("POWER", share, taper), length * -(1.0 - share)))
    profile.append((0.0, 0.0))
    spike = graph.lathe(profile, segments=SPIKE_SEGMENTS)
    x, y, z = graph.sep(graph.position())
    seeded = graph.vec(x * 2.5, y * 2.5, graph.math("MULTIPLY", seed, 1.37))
    hem_wander = graph.n("ShaderNodeTexNoise", Vector=seeded, Scale=1.0, Detail=2.0, props={"noise_dimensions": "3D"})["Fac"]
    hem_height = length * -1.0 * (hem + (hem_wander - 0.5) * 2.0 * wobble)
    netted = graph.compare(z, hem_height, "GREATER_THAN")
    folds = graph.n("ShaderNodeTexNoise", Vector=graph.vec(x * 9.0, y * 9.0, z * 4.0), Scale=1.0, Detail=3.0, Roughness=0.6,
                    props={"noise_dimensions": "3D"})["Fac"]
    outward = graph.vmath("NORMALIZE", graph.vec(x, y, 0.0))
    spike = graph.set_pos(spike, offset=outward * ((folds - 0.5) * 2.0 * crumple), sel=netted)
    spike = graph.smooth(spike)
    graph.result(graph.mat(graph.mat(spike, core_material), net_material, sel=netted))
    return graph


@asset("CIN.Hall.Chain", "Hall")
def chain():
    """A string of beads hanging from the object's origin (see the module notes)."""
    graph = GN("CIN.Hall.Chain", chain.__doc__)
    length = graph.inp("Length", default=3.0, min=0.01, subtype="DISTANCE")
    bead = graph.inp("Bead", default=0.008, min=0.0005, subtype="DISTANCE")
    pitch = graph.inp("Pitch", default=0.02, min=0.001, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Gold"))
    count = graph.to_int(length / pitch) + 1
    spots = graph.n("GeometryNodeMeshToPoints", Mesh=graph.mesh_line(count, (0.0, 0.0, 0.0), graph.vec(0.0, 0.0, pitch * -1.0))).o
    ball = graph.smooth(graph.n("GeometryNodeMeshIcoSphere", Radius=bead, Subdivisions=1)["Mesh"])
    graph.result(graph.realize(graph.iop(spots, graph.mat(ball, material))))
    return graph


@asset("CIN.Hall.Lockers", "Hall")
def lockers():
    """A wall of doors, a vent by each corner of every door and slots under the lowest row (see the module notes)."""
    graph = GN("CIN.Hall.Lockers", lockers.__doc__)
    columns = graph.inp("Columns", "INT", default=4, min=1)
    rows = graph.inp("Rows", "INT", default=2, min=1)
    door = graph.inp("Door", "VECTOR", default=(0.6, 1.2, 0.0), desc="Width, height")
    gap = graph.inp("Gap", default=0.012, min=0.0, subtype="DISTANCE")
    relief = graph.inp("Relief", default=0.03, min=0.0, subtype="DISTANCE")
    vent = graph.inp("Vent", "VECTOR", default=(0.07, 0.07, 0.0), desc="Width, height")
    inset = graph.inp("Vent Inset", "VECTOR", default=(0.025, 0.1, 0.15), desc="From a door's side, its top, its foot")
    slot = graph.inp("Slot", "VECTOR", default=(0.02, 0.09, 0.0), desc="Width, height")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.HallWall"))
    vent_material = graph.inp("Vent Material", "MATERIAL", default=M.get("CIN.HallVent"))
    width, height = door.x, door.y
    across = graph.n("GeometryNodeMeshLine", Count=columns, Offset=graph.vec(width, 0.0, 0.0)).o
    up = graph.n("GeometryNodeMeshLine", Count=rows, Offset=graph.vec(0.0, 0.0, height)).o
    grid = graph.realize(graph.iop(graph.n("GeometryNodeMeshToPoints", Mesh=across).o, up))
    spots = graph.n("GeometryNodeMeshToPoints", Mesh=grid).o
    spots = graph.set_pos(spots, offset=graph.vec(width * 0.5, 0.0, height * 0.5))
    panel = graph.transform(graph.cube((1.0, 1.0, 1.0)), s=graph.vec(width - gap, relief, height - gap))
    front = relief * -0.5 - 0.002
    side = width * 0.5 - inset.x - vent.x * 0.5
    top = height * 0.5 - inset.y - vent.y * 0.5
    foot = (height * 0.5 - inset.z - vent.y * 0.5) * -1.0
    corners = graph.set_pos(graph.new_points(4), pos=graph.index_switch(graph.index(), [
        graph.vec(side * -1.0, front, top), graph.vec(side, front, top), graph.vec(side * -1.0, front, foot), graph.vec(side, front, foot)]))
    vent_box = graph.mat(graph.transform(graph.cube((1.0, 1.0, 1.0)), s=graph.vec(vent.x, 0.004, vent.y)), vent_material)
    under = foot - vent.y * 0.5 - SLOT_GAP - slot.y * 0.5
    slot_spots = graph.set_pos(graph.new_points(2), pos=graph.index_switch(graph.index(), [
        graph.vec(side * -1.0, front, under), graph.vec(side, front, under)]))
    slot_box = graph.mat(graph.transform(graph.cube((1.0, 1.0, 1.0)), s=graph.vec(slot.x, 0.004, slot.y)), vent_material)
    lowest = graph.compare(graph.sep(graph.position())[2], height, "LESS_THAN")
    doors = graph.iop(spots, graph.mat(panel, material))
    vents = graph.iop(spots, graph.realize(graph.iop(corners, vent_box)))
    slots = graph.iop(spots, graph.realize(graph.iop(slot_spots, slot_box)), sel=lowest)
    graph.result(graph.realize(graph.join(doors, vents, slots)))
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
