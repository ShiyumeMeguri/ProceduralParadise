"""
Blade kit (``WPN.Blade``): a curved blade lofted between three lines
traced on the sheet -- its back, the line where its grind starts and its
cutting edge.

The blade is swept along the grind line.  Its cross-section is a closed
template: down the front from the back to the grind line (the flat), on
down the grind to the edge, round the edge and back up the far side; the
loop closes over the back.  Every sample of the grind line finds the
nearest points of the back and of the edge, and every point of the
template sits between them: the flat keeps the thickness of the back,
tapering from ``Back Thickness`` at the root to ``Tip Thickness`` at the
tip; the grind thins from there to ``Edge Thickness`` (straight for a
``Grind Shape`` of 1, convex below 1, hollow above).  The flat and the
grind take their own materials.  The object's strands are, in order, the
back, the grind line and the edge (open, root to tip), then closed
outlines cut through the blade: notches, holes, the room left for parts
it is fitted into.
"""
from __future__ import annotations

from Core.gn import GN, asset
from . import materials as M
from .solids import STRAND, SMOOTH, filled, off_drawing, onto_drawing, strands, upward

FLAT_ROWS = 4
GRIND_ROWS = 10
ACROSS = "blade_across"
SIDE = "blade_side"
ALONG = "blade_along"
CUTTER_DEPTH = 0.2


def strand_curve(graph, curves, index):
    node = graph.n("GeometryNodeSeparateGeometry", Geometry=curves,
                   Selection=graph.compare(graph.named(STRAND, "INT"), index, "EQUAL", "INT"), props={"domain": "CURVE"})
    return node["Selection"]


def nearest_on(graph, curve, position):
    """Nearest point of ``curve`` to ``position``."""
    wire = graph.n("GeometryNodeCurveToMesh", Curve=curve).o
    return graph.n("GeometryNodeProximity", Geometry=wire, Sample_Position=position,
                   props={"target_element": "EDGES"})["Position"]


def template(graph):
    """Closed cross-section template: front from the back (across 0) over
    the grind line (1) to the edge (2), then the far side back up."""
    half = FLAT_ROWS + GRIND_ROWS + 1
    count = half * 2
    points = graph.n("GeometryNodeMeshLine", Count=count, Offset=(0.0, 0.0, 0.0)).o
    index = graph.index()
    far = graph.compare(index, half, "GREATER_EQUAL", "INT")
    step = graph.switch(far, index, (count - 1) - index, "FLOAT")
    across = graph.switch(graph.compare(step, FLAT_ROWS, "LESS_EQUAL"),
                          1.0 + (step - FLAT_ROWS) / GRIND_ROWS, step / FLAT_ROWS, "FLOAT")
    points = graph.store(points, ACROSS, across)
    points = graph.store(points, SIDE, graph.switch(far, -1.0, 1.0, "FLOAT"))
    loop = graph.n("GeometryNodePointsToCurves", Points=graph.mesh_to_points(points), Weight=graph.index()).o
    return graph.n("GeometryNodeSetSplineCyclic", Geometry=loop, Cyclic=True).o


@asset("WPN.Blade", "Solids")
def blade():
    """A curved blade lofted between its back, grind line and edge (see
    the module notes), with closed outlines cut through it."""
    graph = GN("WPN.Blade", blade.__doc__, modifier=True)
    geometry = graph.inp("Geometry", "GEOMETRY")
    back_thickness = graph.inp("Back Thickness", default=0.006, min=0.0, subtype="DISTANCE")
    tip_thickness = graph.inp("Tip Thickness", default=0.001, min=0.0, subtype="DISTANCE")
    edge_thickness = graph.inp("Edge Thickness", default=0.0004, min=0.0, subtype="DISTANCE")
    shape = graph.inp("Grind Shape", default=1.0, min=0.05)
    samples = graph.inp("Samples", "INT", default=480, min=8)
    flat_material = graph.inp("Flat Material", "MATERIAL", default=M.get("WPN.Blackened"))
    grind_material = graph.inp("Grind Material", "MATERIAL", default=M.get("WPN.Steel"))
    curves = strands(graph, geometry, False)
    back = strand_curve(graph, curves, 0)
    grind = graph.resample(strand_curve(graph, curves, 1), samples)
    edge = strand_curve(graph, curves, 2)
    position = graph.position()
    grind = graph.store(grind, "blade_grind", position, "FLOAT_VECTOR")
    grind = graph.store(grind, "blade_back", nearest_on(graph, back, position), "FLOAT_VECTOR")
    grind = graph.store(grind, "blade_edge", nearest_on(graph, edge, position), "FLOAT_VECTOR")
    grind = graph.store(grind, ALONG, graph.index() / (samples - 1))
    body = graph.n("GeometryNodeCurveToMesh", Curve=grind, Profile_Curve=template(graph), Fill_Caps=True).o
    across = graph.named(ACROSS)
    on_flat = graph.compare(across, 1.0, "LESS_EQUAL")
    flat_point = graph.mix(graph.clamp01(across), graph.named("blade_back", "FLOAT_VECTOR"), graph.named("blade_grind", "FLOAT_VECTOR"), "VECTOR")
    grind_point = graph.mix(graph.clamp01(across - 1.0), graph.named("blade_grind", "FLOAT_VECTOR"), graph.named("blade_edge", "FLOAT_VECTOR"), "VECTOR")
    point = graph.switch(on_flat, grind_point, flat_point, "VECTOR")
    flat_half = graph.mix(graph.named(ALONG), back_thickness, tip_thickness) * 0.5
    thinning = graph.math("POWER", graph.clamp01(across - 1.0), shape)
    half = graph.switch(on_flat, graph.mix(thinning, flat_half, edge_thickness * 0.5), flat_half, "FLOAT")
    x, _, z = graph.sep(point)
    body = graph.set_pos(body, pos=graph.vec(x, graph.named(SIDE) * half, z))
    body = graph.merge(body, 1e-6)
    cutters = graph.n("GeometryNodeSeparateGeometry", Geometry=curves,
                      Selection=graph.compare(graph.named(STRAND, "INT"), 3, "GREATER_EQUAL", "INT"), props={"domain": "CURVE"})["Selection"]
    cutters = graph.n("GeometryNodeSetSplineCyclic", Geometry=cutters, Cyclic=True).o
    cutter = upward(graph, filled(graph, onto_drawing(graph, cutters)))
    cutter = off_drawing(graph, graph.solid(graph.move(cutter, z=CUTTER_DEPTH * -0.5), CUTTER_DEPTH))
    cut = graph.n("GeometryNodeMeshBoolean", Mesh_1=body, Mesh_2=cutter, props={"operation": "DIFFERENCE", "solver": "EXACT"})["Mesh"]
    body = graph.switch(graph.compare(graph.domain_size(cutter)["Face Count"], 0, "GREATER_THAN", "INT"), body, cut)
    grind_face = graph.compare(graph.on_domain(graph.named(ACROSS), "FACE"), 1.0, "GREATER_THAN")
    body = graph.mat(graph.mat(body, flat_material), grind_material, sel=grind_face)
    graph.result(graph.smooth_by_angle(body, SMOOTH))
    return graph
