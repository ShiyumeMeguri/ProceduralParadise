"""
Structure kit -- geometry-node groups (``CIN.Structure.*``): the members,
glazing and floors a frame building is made of.

A building is data: the set's interpreter lays its frame out as a wire mesh
(every edge a member's centre line) and its glazing and floors as faces,
and these assets turn them into solids.  Every edge carries its section:

``section``   0 a box, 1 an I-section (the web along ``width``), 2 a round tube
``width``     size of the section across the member, in the plane it faces
``depth``     size of the section along ``facing``
``facing``    the direction the section's depth runs (a facade's outward normal)
``finish``    0 the concrete finish, 1 the steel finish

so a column, an edge beam, a brace or a mullion differ only in the numbers
on their edge.  (A multi-input socket lists the geometry linked last
first: the shapes are linked tube, I-section, box to come out in section
order.)  A member runs its edge's length plus ``Overrun`` at each
end, so members meet without gaps.  An I-section's flanges are a share
``Flange`` of its width thick and its web a share ``Web`` of its depth.
"""
from __future__ import annotations

from Core.gn import GN, asset, set_mode
from . import materials as M

SECTION = "section"
WIDTH = "width"
DEPTH = "depth"
FACING = "facing"
FINISH = "finish"


def constant(graph, value):
    """A linked constant vector: an input whose unlinked value is an
    implicit field (Extrude's offset is the face normal) ignores its
    default value."""
    return graph.n("FunctionNodeInputVector", props={"vector": tuple(float(component) for component in value)}).o


def i_section(graph, flange, web):
    """Unit I-section prism along +Z (length 1, centred): flanges at
    X = +-0.5 a share ``flange`` thick spanning Y, the web a share ``web``
    of Y thick spanning X."""
    top = graph.transform(graph.cube((1.0, 1.0, 1.0)), t=graph.vec(0.5 - flange * 0.5, 0.0, 0.0), s=graph.vec(flange, 1.0, 1.0))
    bottom = graph.transform(graph.cube((1.0, 1.0, 1.0)), t=graph.vec(-0.5 + flange * 0.5, 0.0, 0.0), s=graph.vec(flange, 1.0, 1.0))
    middle = graph.transform(graph.cube((1.0, 1.0, 1.0)), s=graph.vec(1.0 - 2.0 * flange, web, 1.0))
    return graph.merge(graph.join(top, bottom, middle), 0.00001)


def member_rotation(graph, axis, facing):
    """Rotation taking +Z along ``axis`` and +Y along ``facing`` (made
    square to the axis): a section's width runs along X, its depth along Y."""
    along = graph.align_rotation(axis, axis="Z")
    return graph.align_rotation(facing, rotation=along, axis="Y", pivot="Z")


@asset("CIN.Structure.Members", "Structure")
def members():
    """Every edge of the mesh becomes a member centred on it, its section
    read from the edge (see the module notes)."""
    graph = GN("CIN.Structure.Members", members.__doc__)
    mesh = graph.inp("Geometry", "GEOMETRY")
    overrun = graph.inp("Overrun", default=0.0, subtype="DISTANCE")
    flange = graph.inp("Flange", default=0.1, min=0.01, max=0.45)
    web = graph.inp("Web", default=0.08, min=0.01, max=1.0)
    concrete = graph.inp("Concrete", "MATERIAL", default=M.get("CIN.Concrete"))
    steel = graph.inp("Steel", "MATERIAL", default=M.get("CIN.SteelPaint"))

    ends = graph.n("GeometryNodeInputMeshEdgeVertices")
    mesh, fields = graph.capture(mesh, "EDGE", span=ends["Position 2"] - ends["Position 1"])
    span = fields["span"]
    points = graph.n("GeometryNodeMeshToPoints", Mesh=mesh, props={"mode": "EDGES"}).o
    box = graph.cube((1.0, 1.0, 1.0))
    tube = graph.smooth(graph.cylinder(0.5, 1.0, 16))
    shapes = graph.n("GeometryNodeGeometryToInstance", Geometry=[tube, i_section(graph, flange, web), box]).o
    rotation = member_rotation(graph, span, graph.named(FACING, "FLOAT_VECTOR"))
    scale = graph.vec(graph.named(WIDTH), graph.named(DEPTH), span.length() + overrun * 2.0)
    instances = graph.n("GeometryNodeInstanceOnPoints", Points=points, Instance=shapes, Pick_Instance=True,
                        Instance_Index=graph.named(SECTION, "INT"), Rotation=rotation, Scale=scale).o
    instances = graph.store(instances, FINISH, graph.named(FINISH, "INT"), "INT", "INSTANCE")
    solid = graph.realize(instances)
    steel_faces = graph.compare(graph.named(FINISH, "INT"), 1, "EQUAL", "INT")
    solid = graph.mat(graph.mat(solid, concrete), steel, sel=steel_faces)
    graph.result(graph.remove_attribute(solid, FINISH))
    return graph


@asset("CIN.Structure.Panes", "Structure")
def panes():
    """Every face of the mesh becomes a pane ``Thickness`` thick (outwards
    along its normal), shrunk by ``Margin`` on every side -- the rebate the
    frame hides."""
    graph = GN("CIN.Structure.Panes", panes.__doc__)
    mesh = graph.inp("Geometry", "GEOMETRY")
    thickness = graph.inp("Thickness", default=0.012, min=0.0, subtype="DISTANCE")
    margin = graph.inp("Margin", default=0.0, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Glass"))
    faces = graph.n("GeometryNodeSplitEdges", Mesh=mesh).o
    side = graph.math("SQRT", graph.n("GeometryNodeInputMeshFaceArea").o)
    factor = graph.max(1.0 - margin * 2.0 / graph.max(side, 0.001), 0.0)
    faces = graph.n("GeometryNodeScaleElements", Geometry=faces, Scale=factor, props={"domain": "FACE"}).o
    extrusion = graph.n("GeometryNodeExtrudeMesh")
    set_mode(extrusion, "FACES")
    graph.assign(graph._in_socket(extrusion.n, "Mesh"), faces)
    graph.assign(graph._in_socket(extrusion.n, "Offset Scale"), thickness)
    graph.assign(graph._in_socket(extrusion.n, "Individual"), True)
    back = graph.n("GeometryNodeFlipFaces", faces).o
    graph.result(graph.mat(graph.merge(graph.join(extrusion["Mesh"], back), 0.00001), material))
    return graph


@asset("CIN.Structure.Slabs", "Structure")
def slabs():
    """Every face of the mesh (a floor's outline at its top, facing up)
    becomes a slab ``Thickness`` thick hanging below it."""
    graph = GN("CIN.Structure.Slabs", slabs.__doc__)
    mesh = graph.inp("Geometry", "GEOMETRY")
    thickness = graph.inp("Thickness", default=0.3, min=0.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Concrete"))
    underside = graph.n("GeometryNodeFlipFaces", Mesh=mesh).o
    extrusion = graph.n("GeometryNodeExtrudeMesh")
    set_mode(extrusion, "FACES")
    graph.assign(graph._in_socket(extrusion.n, "Mesh"), underside)
    graph.assign(graph._in_socket(extrusion.n, "Offset Scale"), thickness)
    solid = graph.merge(graph.join(extrusion["Mesh"], mesh), 0.0001)
    graph.result(graph.mat(solid, material))
    return graph
