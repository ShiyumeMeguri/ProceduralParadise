"""
Shape kit: the hand-held props and the bodies the simulations start from.

Local frames: a stick grows from its tip at the origin along +Z; the spray
wand's nozzle is at the origin and it sprays along -Z (its handle rises
along +Z); a balloon is centred on the origin, a slime sits on z = 0.
Bodies carry the
attributes their simulation reads: a balloon's ``knot`` (the tied-off tip)
and ``neck`` (unstretched rubber around it), a slime's face anchors
``left_eye``, ``right_eye`` and ``mouth`` (1 on the one vertex that faces
each anchor direction).
"""
from __future__ import annotations

from Core.gn import GN, asset
from . import materials as M

KNOT = "knot"
NECK = "neck"
FACE = ("left_eye", "right_eye", "mouth")


def elongated_sphere(graph, radius, length, segments=32, rings=16):
    """UV sphere whose upper half is lifted by ``length``: a capsule from
    z = 0 to z = 2 radius + length."""
    sphere = graph.n("GeometryNodeMeshUVSphere", Segments=segments, Rings=rings, Radius=radius)["Mesh"]
    upper = graph.compare(graph.position().z, 1e-6, "GREATER_THAN")
    return graph.set_pos(sphere, offset=graph.vec(0.0, 0.0, graph.switch(upper, 0.0, length, "FLOAT") + radius))


@asset("Props.Stick", "Shapes")
def stick():
    """Round wooden stick with its tip at the origin, pointing down -Z from
    the handle; the tip is whittled to fresh wood (``whittled``), the rest
    keeps its bark."""
    graph = GN("Props.Stick", stick.__doc__)
    radius = graph.inp("Radius", default=0.006, min=0.0005, subtype="DISTANCE")
    length = graph.inp("Length", default=0.24, min=0.0, subtype="DISTANCE")
    whittled = graph.inp("Whittled Length", default=0.014, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("Props.Wood"))
    body = graph.n("GeometryNodeTriangulate", Mesh=elongated_sphere(graph, radius, length)).o
    body = graph.store(body, "whittled", graph.switch(graph.compare(graph.position().z, whittled, "LESS_THAN"), 0.0, 1.0, "FLOAT"))
    body = graph.store(body, "wood_coordinate", graph.position(), "FLOAT_VECTOR")
    graph.result(graph.mat(graph.smooth(body), material))
    return graph


@asset("Props.Wand", "Shapes")
def wand():
    """Spray wand: a brass nozzle cone at the origin and a wooden handle above
    it.  Liquid leaves the nozzle along -Z."""
    graph = GN("Props.Wand", wand.__doc__)
    handle_radius = graph.inp("Handle Radius", default=0.009, min=0.001, subtype="DISTANCE")
    handle_length = graph.inp("Handle Length", default=0.18, min=0.0, subtype="DISTANCE")
    nozzle_length = graph.inp("Nozzle Length", default=0.03, min=0.001, subtype="DISTANCE")
    nozzle_radius = graph.inp("Nozzle Radius", default=0.0075, min=0.0005, subtype="DISTANCE")
    wood = graph.inp("Handle Material", "MATERIAL", default=M.get("Props.Wood"))
    brass = graph.inp("Nozzle Material", "MATERIAL", default=M.get("Props.Brass"))
    nozzle = graph.n("GeometryNodeMeshCone", Vertices=32, Radius_Top=handle_radius * 0.8, Radius_Bottom=nozzle_radius,
                     Depth=nozzle_length, props={"fill_type": "NGON"})["Mesh"]
    nozzle = graph.mat(graph.smooth_by_angle(graph.move(nozzle, z=nozzle_length * 0.5), 0.6), brass)
    handle = elongated_sphere(graph, handle_radius, handle_length)
    handle = graph.move(handle, z=nozzle_length - handle_radius * 0.4)
    handle = graph.store(handle, "wood_coordinate", graph.position(), "FLOAT_VECTOR")
    graph.result(graph.join(nozzle, graph.mat(graph.smooth(handle), wood)))
    return graph


@asset("Props.Balloon.Shape", "Shapes")
def balloon():
    """Teardrop balloon: a sphere about the origin drawn up into a neck at +Z.
    ``knot`` is 1 at the tied-off tip, ``neck`` marks the unstretched rubber
    around it."""
    graph = GN("Props.Balloon.Shape", balloon.__doc__, modifier=True)
    radius = graph.inp("Radius", default=0.045, min=0.001, subtype="DISTANCE")
    subdivisions = graph.inp("Subdivisions", "INT", default=4, min=1, max=7)
    neck_height = graph.inp("Neck Height", default=0.006, min=0.0, subtype="DISTANCE")
    neck_radius = graph.inp("Neck Radius", default=0.02, min=0.0, subtype="DISTANCE")
    sphere = graph.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=subdivisions)["Mesh"]
    x, y, z = graph.sep(graph.position().normalized())
    marked = graph.store(sphere, KNOT, graph.map_range(z, 0.955, 0.99, interp="SMOOTHSTEP"))
    marked = graph.store(marked, NECK, graph.map_range(z, 0.9, 0.97, interp="SMOOTHSTEP"))
    top = graph.map_range(z, 0.45, 1.0, interp="SMOOTHSTEP")
    squeeze = 1.0 - (1.0 - neck_radius / radius) * (top * top)
    lift = neck_height / radius * (top * top * top)
    shaped = graph.set_pos(marked, pos=graph.vec(x * squeeze, y * squeeze, z + lift) * radius)
    graph.result(graph.smooth(shaped))
    return graph


@asset("Props.Slime.Shape", "Shapes")
def slime():
    """Slime drop: a flattened bottom, a bulging base and a soft peak, lowest
    point on z = 0.  ``left_eye``, ``right_eye`` and ``mouth`` are 1 on the
    vertex facing each anchor direction from the body's centre line."""
    graph = GN("Props.Slime.Shape", slime.__doc__, modifier=True)
    radius = graph.inp("Radius", default=0.05, min=0.001, subtype="DISTANCE")
    subdivisions = graph.inp("Subdivisions", "INT", default=4, min=1, max=7)
    flatten = graph.inp("Bottom Flatten", default=0.42, min=0.0, max=1.0, desc="Height of the lower half relative to the upper")
    peak = graph.inp("Peak", default=0.35, min=0.0, desc="Extra height of the soft point on top, in radii")
    bulge = graph.inp("Bulge", default=0.12, min=0.0, desc="How much wider the base is than the top")
    anchors = [graph.inp(name.replace("_", " ").title(), "VECTOR", default=default, desc="Direction from the centre line")
               for name, default in zip(FACE, ((-0.34, -0.9, 0.34), (0.34, -0.9, 0.34), (0.0, -0.97, 0.06)))]
    sphere = graph.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=subdivisions)["Mesh"]
    x, y, z = graph.sep(graph.position().normalized())
    spread = 1.0 + bulge * (1.0 - z) * 0.5
    upper = graph.compare(z, 0.0, "GREATER_THAN")
    crown = graph.map_range(z, 0.78, 1.0, interp="SMOOTHSTEP")
    height = z * graph.switch(upper, flatten, 1.0, "FLOAT") + peak * (crown * crown)
    shaped = graph.set_pos(sphere, pos=graph.vec(x * spread, y * spread, height) * radius)
    shaped = graph.set_pos(shaped, offset=graph.vec(0.0, 0.0, graph.statistic(shaped, graph.position().z)["Min"] * -1.0))
    center = graph.vec(0.0, 0.0, graph.statistic(shaped, graph.position().z)["Mean"])
    for name, direction in zip(FACE, anchors):
        facing = (graph.position() - center).normalized().dot(direction.normalized())
        best = graph.statistic(shaped, facing)["Max"]
        shaped = graph.store(shaped, name, graph.switch(graph.compare(facing, best, "GREATER_EQUAL"), 0.0, 1.0, "FLOAT"))
    graph.result(graph.smooth(shaped))
    return graph
