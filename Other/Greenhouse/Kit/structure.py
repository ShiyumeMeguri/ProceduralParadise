"""
Structure kit -- geometry-node groups (``GH.Structure.*``): the steel and
glass the conservatory is built of.

The building is data: a scene gives its frame as a wire mesh (every edge a
member) and its glazing as faces (every face a pane), and these assets turn
edges into bars and faces into panes.  So a post, a floor beam, a mullion or
a rail is only a line in the scene file, and any layout -- regular grid or
not -- is built by the same four assets.

Local frames: members and panes stay where their edges and faces are; a
balustrade stands on its path; a stair rises along +Y from the origin, its
first riser on the X axis.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, set_mode
from . import materials as M

UP = (0.0, 0.0, 1.0)


def member_rotation(graph, direction):
    """Rotation taking a unit cube's +Z along ``direction`` with its faces
    square to the building: horizontal members keep a vertical face,
    vertical ones face the X axis."""
    upright = graph.compare(graph.abs(direction.normalized().z), 0.9, "GREATER_THAN")
    reference = graph.switch(upright, graph.vec(0.0, 0.0, 1.0), graph.vec(1.0, 0.0, 0.0), "VECTOR")
    along = graph.align_rotation(direction, axis="Z")
    return graph.align_rotation(reference, rotation=along, axis="X", pivot="Z")


@asset("GH.Structure.Members", "Structure")
def members():
    """Every edge of the mesh becomes a bar centred on it: a box ``Width``
    by ``Depth`` (``Round``: a tube of diameter ``Width``) running the edge's
    length plus ``Overrun`` at each end, so members meet without gaps."""
    graph = GN("GH.Structure.Members", members.__doc__)
    mesh = graph.inp("Geometry", "GEOMETRY")
    width = graph.inp("Width", default=0.06, min=0.0, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.06, min=0.0, subtype="DISTANCE")
    overrun = graph.inp("Overrun", default=0.0, subtype="DISTANCE")
    rounded = graph.inp("Round", "BOOL", default=False)
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Steel"))

    ends = graph.n("GeometryNodeInputMeshEdgeVertices")
    mesh, fields = graph.capture(mesh, "EDGE", span=ends["Position 2"] - ends["Position 1"])
    span = fields["span"]
    points = graph.n("GeometryNodeMeshToPoints", Mesh=mesh, props={"mode": "EDGES"}).o
    length = span.length() + overrun * 2.0
    box = graph.cube((1.0, 1.0, 1.0))
    tube = graph.smooth(graph.cylinder(0.5, 1.0, 16))
    bar = graph.switch(rounded, box, tube)
    bars = graph.iop(points, bar, rot=member_rotation(graph, span), scale=graph.vec(width, graph.switch(rounded, depth, width, "FLOAT"), length))
    graph.result(graph.mat(graph.realize(bars), material))
    return graph


@asset("GH.Structure.Panes", "Structure")
def panes():
    """Every face of the mesh becomes a pane ``Thickness`` thick, shrunk by
    ``Margin`` on every side (the rebate the frame hides) and lifted by
    ``Offset`` along its normal.  ``See Through`` marks the panes as glass
    for the ink pass."""
    graph = GN("GH.Structure.Panes", panes.__doc__)
    mesh = graph.inp("Geometry", "GEOMETRY")
    thickness = graph.inp("Thickness", default=0.012, min=0.0, subtype="DISTANCE")
    margin = graph.inp("Margin", default=0.0, min=0.0, subtype="DISTANCE")
    offset = graph.inp("Offset", default=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Glass"))
    see_through = graph.inp("See Through", "BOOL", default=True)

    faces = graph.n("GeometryNodeSplitEdges", Mesh=mesh).o
    area = graph.n("GeometryNodeInputMeshFaceArea").o
    side = graph.math("SQRT", area)
    factor = graph.max(1.0 - margin * 2.0 / graph.max(side, 0.001), 0.0)
    faces = graph.n("GeometryNodeScaleElements", Geometry=faces, Scale=factor, props={"domain": "FACE"}).o
    faces = graph.set_pos(faces, offset=graph.normal() * offset)
    slabs = graph.extrude(faces, thickness, individual=True)
    bottoms = graph.n("GeometryNodeFlipFaces", faces).o
    graph.result(M.glazed(graph, graph.merge(graph.join(slabs, bottoms), 0.00001), material, see_through))
    return graph


@asset("GH.Structure.Balustrade", "Structure")
def balustrade():
    """Balustrade along the edges of the mesh (its path, at floor level):
    square posts every ``Post Spacing`` (and at both ends), a flat top rail
    at ``Height``, ``Rails`` round intermediate rails evenly spaced between
    ``Rail Bottom`` and the top rail, and a glass infill panel."""
    graph = GN("GH.Structure.Balustrade", balustrade.__doc__)
    path = graph.inp("Geometry", "GEOMETRY")
    height = graph.inp("Height", default=1.05, subtype="DISTANCE")
    spacing = graph.inp("Post Spacing", default=1.2, min=0.1, subtype="DISTANCE")
    post = graph.inp("Post Size", default=0.04, subtype="DISTANCE")
    top_width = graph.inp("Top Rail Width", default=0.05, subtype="DISTANCE")
    top_depth = graph.inp("Top Rail Depth", default=0.03, subtype="DISTANCE")
    rails = graph.inp("Rails", "INT", default=4, min=0)
    rail_bottom = graph.inp("Rail Bottom", default=0.12, subtype="DISTANCE")
    rail_size = graph.inp("Rail Size", default=0.012, subtype="DISTANCE")
    glass_on = graph.inp("Glass", "BOOL", default=True)
    steel = graph.inp("Material", "MATERIAL", default=M.get("GH.Steel"))
    glass_material = graph.inp("Glass Material", "MATERIAL", default=M.get("GH.Glass"))

    curve = graph.n("GeometryNodeMeshToCurve", path).o
    curve = graph.n("GeometryNodeCurveSplineType", curve, props={"spline_type": "POLY"}).o
    upright = graph.n("GeometryNodeSetCurveNormal", curve)
    set_mode(upright, "Z_UP")
    curve = upright.o
    stations = graph.n("GeometryNodeResampleCurve", Curve=curve)
    set_mode(stations, "LENGTH")
    graph.assign(graph._in_socket(stations.n, "Length"), spacing)
    points = graph.n("GeometryNodeCurveToPoints", Curve=stations.o, props={"mode": "EVALUATED"})["Points"]
    posts = graph.iop(points, graph.move(graph.cube((1.0, 1.0, 1.0)), z=0.5), scale=graph.vec(post, post, height - top_depth))

    top = graph.sweep(graph.set_pos(curve, offset=graph.vec(0.0, 0.0, height - top_depth * 0.5)), graph.rect(top_width, top_depth), True)
    step = (height - top_depth - rail_bottom) / graph.max(rails, 1)
    levels = graph.mesh_line(rails, graph.vec(0.0, 0.0, rail_bottom), graph.vec(0.0, 0.0, step))
    rail_curves = graph.realize(graph.iop(graph.mesh_to_points(levels), curve))
    rail_mesh = graph.smooth(graph.sweep(rail_curves, graph.circle(rail_size * 0.5, 10), True))

    extrude = graph.n("GeometryNodeExtrudeMesh", Mesh=path, Offset=graph.vec(0.0, 0.0, 1.0), Offset_Scale=height - top_depth - 0.05)
    set_mode(extrude, "EDGES")
    wall = graph.set_pos(extrude["Mesh"], offset=graph.vec(0.0, 0.0, 0.03))
    glass_panel = graph.switch(glass_on, None, graph.group(get_asset("GH.Structure.Panes"), Geometry=wall, Thickness=0.01, Offset=-0.005, Material=glass_material).o)
    metal = graph.mat(graph.realize(graph.join(posts, top, rail_mesh)), steel)
    graph.result(graph.join(metal, glass_panel))
    return graph


@asset("GH.Structure.Stair", "Structure")
def stair():
    """Straight flight rising along +Y: ``Steps`` stone treads of ``Rise``
    and ``Going`` on two glass stringers, open risers.  The first tread's
    nosing is on the X axis, the flight centred on it."""
    graph = GN("GH.Structure.Stair", stair.__doc__)
    steps = graph.inp("Steps", "INT", default=12, min=1)
    rise = graph.inp("Rise", default=0.175, subtype="DISTANCE")
    going = graph.inp("Going", default=0.28, subtype="DISTANCE")
    width = graph.inp("Width", default=1.2, subtype="DISTANCE")
    thickness = graph.inp("Tread Thickness", default=0.05, subtype="DISTANCE")
    stringer = graph.inp("Stringer Height", default=0.3, subtype="DISTANCE")
    stringer_thickness = graph.inp("Stringer Thickness", default=0.024, subtype="DISTANCE")
    tread_material = graph.inp("Tread Material", "MATERIAL", default=M.get("GH.Tread"))
    glass_treads = graph.inp("Glass Treads", "BOOL", default=False)
    glass_material = graph.inp("Glass Material", "MATERIAL", default=M.get("GH.GlassJade"))

    stations = graph.mesh_line(steps, graph.vec(0.0, going * 0.5, rise - thickness * 0.5), graph.vec(0.0, going, rise))
    tread = graph.cube(graph.vec(width, going + 0.02, thickness))
    treads = M.glazed(graph, graph.realize(graph.iop(graph.mesh_to_points(stations), tread)), tread_material, glass_treads)

    run = going * steps
    total = rise * steps
    slope = graph.math("ARCTAN2", total, run)
    length = graph.vec(run, total, 0.0).length()
    plate = graph.cube(graph.vec(stringer_thickness, length + going, stringer))
    plate = graph.transform(plate, r=graph.vec(slope, 0.0, 0.0))
    center_y = run * 0.5
    center_z = total * 0.5 - stringer * 0.35
    left = graph.transform(plate, t=graph.vec(width * -0.5 + stringer_thickness * 0.5, center_y, center_z))
    right = graph.transform(plate, t=graph.vec(width * 0.5 - stringer_thickness * 0.5, center_y, center_z))
    graph.result(graph.join(treads, M.glazed(graph, graph.join(left, right), glass_material)))
    return graph
