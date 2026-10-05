"""
Solids kit (``WPN.*``): the parts of a weapon as solids grown from outlines
traced on its design sheet.

A weapon is drawn on a sheet seen from -Y: the sheet's right is +X, its
up +Z, and every part is an outline in that plane given a depth along Y.
A traced object carries its outlines as points of its own mesh: each point
stores the ``strand`` (the outline) it belongs to and the ``source``, the
entry of the part's outline list it was traced for, and the points of a
strand follow each other in index order.  :func:`strands` turns them back
into curves.  ``Front`` and ``Back`` are the Y of a part's two faces --
the front is the one the sheet shows -- and ``Mirror`` adds the part's
mirror image in the plane Y = 0, for the far side of a symmetric weapon.
The entries from ``Pockets From`` on are pockets: sunk ``Pocket Depth``
into both faces, for the windows, lamps and engraved marks set into a part
(the part filling a pocket's floor is a part of its own).
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, set_menu
from . import materials as M

STRAND = "strand"
SOURCE = "source"
SHARP = math.radians(40.0)
SMOOTH = math.radians(35.0)
WELD = 1e-6
NO_POCKETS = 1 << 30


def strands(graph, geometry, cyclic, sel=None):
    """Curves through the points of ``geometry`` (those of ``sel``), one
    per ``strand``, in index order."""
    points = graph.mesh_to_points(geometry, sel)
    curves = graph.n("GeometryNodePointsToCurves", Points=points, Curve_Group_ID=graph.named(STRAND, "INT"),
                     Weight=graph.index()).o
    return graph.n("GeometryNodeSetSplineCyclic", Geometry=curves, Cyclic=cyclic).o


def onto_drawing(graph, geometry):
    """Sheet space (X, Y, Z) to drawing space (X, Z, -Y): the sheet's plane
    becomes XY, depth runs along -Z."""
    x, y, z = graph.sep(graph.position())
    return graph.set_pos(geometry, pos=graph.vec(x, z, y * -1.0))


def off_drawing(graph, geometry):
    """Drawing space back to sheet space (a quarter turn about X)."""
    return graph.transform(geometry, r=(math.pi * 0.5, 0.0, 0.0))


def filled(graph, curves):
    """The faces inside closed ``curves``, filled even-odd as triangles: an
    n-gon fill bridges a hole to its outline by a slit, and the renderer's
    triangulation of such a face runs across the hole."""
    return graph.fill(curves, "TRIANGLES")


def upward(graph, mesh):
    """``mesh`` with every face turned to face +Z."""
    return graph.n("GeometryNodeFlipFaces", Mesh=mesh, Selection=graph.compare(graph.normal().z, 0.0, "LESS_THAN")).o


def slab(graph, face, front, back):
    """Closed solid of the upward ``face`` between the drawing depths of the
    sheet depths ``back`` and ``front``."""
    return graph.solid(graph.move(face, z=back * -1.0), back - front)


def chamfered(graph, mesh, chamfer):
    """``mesh`` with every edge sharper than :data:`SHARP` bevelled by
    ``chamfer`` (left as it is for no chamfer)."""
    node = graph.n("GeometryNodeMeshBevel", Mesh=mesh, Offset=chamfer, Start_Left_Offset=chamfer, Start_Right_Offset=chamfer,
                   End_Left_Offset=chamfer, End_Right_Offset=chamfer,
                   Selection=graph.compare(graph.n("GeometryNodeInputMeshEdgeAngle")["Unsigned Angle"], SHARP, "GREATER_THAN"))
    set_menu(graph._in_socket(node.n, "Affect Kind"), "Edges")
    return graph.switch(graph.compare(chamfer, 0.0, "GREATER_THAN"), mesh, node["Mesh"])


def mirrored(graph, mesh, mirror):
    """``mesh`` and, with ``mirror``, its mirror image in the plane Y = 0."""
    image = graph.n("GeometryNodeFlipFaces", Mesh=graph.transform(mesh, s=(1.0, -1.0, 1.0))).o
    return graph.switch(mirror, mesh, graph.join(mesh, image))


def dressed(graph, solid, material, mirror):
    """``solid`` (with its mirror image) shaded smooth but for its sharp
    edges, in ``material``."""
    return graph.mat(graph.smooth_by_angle(mirrored(graph, solid, mirror), SMOOTH), material)


def depth_inputs(graph, front=-0.01, back=0.01, chamfer=0.0004):
    return (graph.inp("Front", default=front, subtype="DISTANCE", desc="Y of the face the sheet shows"),
            graph.inp("Back", default=back, subtype="DISTANCE", desc="Y of the far face"),
            graph.inp("Chamfer", default=chamfer, min=0.0, subtype="DISTANCE"),
            graph.inp("Mirror", "BOOL", default=False, desc="also the mirror image in Y = 0"))


def pocket_inputs(graph, first):
    return (graph.inp("Pockets From", "INT", default=first, min=0, desc="the first entry of the outline that is a pocket"),
            graph.inp("Pocket Depth", default=0.0, min=0.0, subtype="DISTANCE"))


def in_pocket(graph, first):
    """Whether an outline point belongs to a pocket."""
    return graph.compare(graph.named(SOURCE, "INT"), first, "GREATER_EQUAL", "INT")


def pocketed(graph, body, geometry, first, depth, front, back):
    """``body`` (drawing space) with the pockets of the outline
    ``geometry`` sunk ``depth`` into the faces at the sheet depths
    ``front`` and ``back``.  A chamfer wide against a narrow part leaves
    the bevelled body overlapping itself, so the cut is made as for
    self-intersecting meshes (otherwise the pockets' caps are added, not
    cut)."""
    face = upward(graph, filled(graph, onto_drawing(graph, strands(graph, geometry, True, in_pocket(graph, first)))))
    cutter = graph.join(slab(graph, face, front - depth, front + depth), slab(graph, face, back - depth, back + depth))
    cut = graph.n("GeometryNodeMeshBoolean", Mesh_1=body, Mesh_2=cutter, Self_Intersection=True, Hole_Tolerant=True,
                  props={"operation": "DIFFERENCE", "solver": "EXACT"})["Mesh"]
    some = graph.bool_and(graph.compare(graph.domain_size(face)["Face Count"], 0, "GREATER_THAN", "INT"),
                          graph.compare(depth, 0.0, "GREATER_THAN"))
    return graph.switch(some, body, cut)


def banded(graph, body, heights):
    """``body`` (drawing space) with an edge loop wherever it crosses one
    of the drawing heights ``heights``, so a change of depth that starts
    there is followed exactly instead of being smoothed across the faces
    that span it: cut in two at each height, the cut faces dropped, the
    halves welded back."""
    for height in heights:
        bounds = graph.bound_box(body)
        low_x, low_y, low_z = graph.sep(bounds["Min"])
        high_x, high_y, high_z = graph.sep(bounds["Max"])
        above = graph.box(low_x - 1.0, height, low_z - 1.0, high_x + 1.0, high_y + 1.0, high_z + 1.0)
        below = graph.box(low_x - 1.0, low_y - 1.0, low_z - 1.0, high_x + 1.0, height, high_z + 1.0)
        halves = [graph.n("GeometryNodeMeshBoolean", Mesh_1=body, Mesh_2=cutter, Self_Intersection=True, Hole_Tolerant=True,
                          props={"operation": "DIFFERENCE", "solver": "EXACT"})["Mesh"] for cutter in (above, below)]
        _, face_y, _ = graph.sep(graph.position())
        cut = graph.bool_and(graph.compare(graph.abs(face_y - height), WELD, "LESS_THAN"),
                             graph.compare(graph.abs(graph.sep(graph.normal())[1]), 0.999, "GREATER_THAN"))
        rejoined = graph.merge(graph.join(*[graph.delete(half, cut, domain="FACE") for half in halves]), WELD)
        crossing = graph.bool_and(graph.compare(height, low_y, "GREATER_THAN"), graph.compare(height, high_y, "LESS_THAN"))
        body = graph.switch(crossing, body, rejoined)
    return body


@asset("WPN.Plate", "Solids")
def plate():
    """A part drawn as an outline: the object's strands are closed outlines
    in the sheet plane (the first an outer edge, the others holes and
    islands, filled even-odd) grown into a solid from ``Front`` to ``Back``
    with chamfered edges and its pockets sunk into both faces.  A ``Taper``
    below 1 narrows it towards the plane Y = 0 from its full depth at the
    height ``Taper Top`` (object space) to that share of it at ``Taper
    Bottom``, either way up -- a boot that slims to its sole, or the two
    halves of a groove running round a part."""
    graph = GN("WPN.Plate", plate.__doc__, modifier=True)
    geometry = graph.inp("Geometry", "GEOMETRY")
    front, back, chamfer, mirror = depth_inputs(graph)
    first, depth = pocket_inputs(graph, NO_POCKETS)
    taper = graph.inp("Taper", default=1.0, min=0.0, desc="share of the depth left at Taper Bottom")
    taper_top = graph.inp("Taper Top", default=0.0, subtype="DISTANCE")
    taper_bottom = graph.inp("Taper Bottom", default=-0.1, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("WPN.Housing"))
    outline = strands(graph, geometry, True, graph.bool_not(in_pocket(graph, first)))
    face = upward(graph, filled(graph, onto_drawing(graph, outline)))
    body = pocketed(graph, chamfered(graph, slab(graph, face, front, back), chamfer), geometry, first, depth, front, back)
    tapered = graph.compare(taper, 1.0, "NOT_EQUAL")
    body = graph.switch(tapered, body, banded(graph, body, (taper_top, taper_bottom)))
    solid = off_drawing(graph, body)
    x, y, z = graph.sep(graph.position())
    span = taper_top - taper_bottom
    span = graph.switch(graph.compare(graph.abs(span), 1e-9, "LESS_THAN"), span, 1e-9, "FLOAT")
    share = graph.clamp01((taper_top - z) / span)
    solid = graph.set_pos(solid, pos=graph.vec(x, y * (1.0 + (taper - 1.0) * share), z))
    graph.result(dressed(graph, solid, material, mirror))
    return graph


@asset("WPN.Ring", "Solids")
def ring():
    """A ring about the object's Y axis -- a disc for no inner radius, an arc
    of the ring from ``Start`` (anticlockwise on the sheet from its right)
    over ``Sweep`` -- from ``Front`` to ``Back``.  ``Rise`` lifts both faces
    towards the inner edge by that much: a spun plate, shallow cone on
    either side; ``Bulge`` lifts them by that much more halfway across, a
    parabola over the cone (sunk for a negative bulge: a dish), drawn in
    ``Rings`` bands.  The object's strands are pockets in its faces (sunk
    from the faces' height at the outer edge)."""
    graph = GN("WPN.Ring", ring.__doc__, modifier=True)
    geometry = graph.inp("Geometry", "GEOMETRY")
    inner = graph.inp("Inner Radius", default=0.0, min=0.0, subtype="DISTANCE")
    outer = graph.inp("Outer Radius", default=0.01, min=0.0, subtype="DISTANCE")
    start = graph.inp("Start", default=0.0, subtype="ANGLE")
    sweep = graph.inp("Sweep", default=math.tau, subtype="ANGLE")
    segments = graph.inp("Segments", "INT", default=96, min=3)
    rings = graph.inp("Rings", "INT", default=1, min=1)
    rise = graph.inp("Rise", default=0.0, subtype="DISTANCE", desc="how far the faces stand out at the inner edge")
    bulge = graph.inp("Bulge", default=0.0, subtype="DISTANCE", desc="how far the faces stand out over the cone halfway across")
    front, back, chamfer, mirror = depth_inputs(graph)
    first, depth = pocket_inputs(graph, 0)
    material = graph.inp("Material", "MATERIAL", default=M.get("WPN.Housing"))
    sheet = graph.grid(1.0, 1.0, segments + 1, rings + 1)
    u, v, _ = graph.sep(graph.position())
    angle = start + (u + 0.5) * sweep
    radius = inner + (v + 0.5) * (outer - inner)
    face = graph.set_pos(sheet, pos=graph.vec(graph.cos(angle) * radius, graph.sin(angle) * radius, 0.0))
    face = upward(graph, graph.merge(face, WELD))
    body = slab(graph, face, front, back)
    x, y, z = graph.sep(graph.position())
    towards = graph.clamp01((outer - graph.vec(x, y, 0.0).length()) / graph.max(outer - inner, 1e-9))
    lift = rise * towards + bulge * 4.0 * towards * (1.0 - towards)
    side = graph.switch(graph.compare(z, (front + back) * -0.5, "GREATER_THAN"), -1.0, 1.0, "FLOAT")
    body = graph.set_pos(body, offset=graph.vec(0.0, 0.0, side * lift))
    body = pocketed(graph, chamfered(graph, body, chamfer), geometry, first, depth, front, back)
    solid = off_drawing(graph, body)
    graph.result(dressed(graph, solid, material, mirror))
    return graph


@asset("WPN.Strokes", "Solids")
def strokes():
    """Lines painted along the object's strands (open polylines in the sheet
    plane; a strand that ends where it starts closes a loop): flat ribbons
    ``Width`` wide from ``Front`` to ``Back``, mitred at their corners --
    signwriting drawn stroke by stroke, as the sheet's lettering is."""
    graph = GN("WPN.Strokes", strokes.__doc__, modifier=True)
    geometry = graph.inp("Geometry", "GEOMETRY")
    width = graph.inp("Width", default=0.002, min=0.0, subtype="DISTANCE")
    front, back, _chamfer, mirror = depth_inputs(graph, -0.0001, 0.0, 0.0)
    material = graph.inp("Material", "MATERIAL", default=M.get("WPN.Paint"))
    lines = graph.n("GeometryNodeSetCurveNormal", Curve=strands(graph, geometry, False), Normal=(0.0, -1.0, 0.0))
    set_menu(graph._in_socket(lines.n, "Mode"), "Free")
    half = width * 0.5
    section = graph.quad_points(graph.vec(back * -1.0, half * -1.0, 0.0), graph.vec(front * -1.0, half * -1.0, 0.0),
                                graph.vec(front * -1.0, half, 0.0), graph.vec(back * -1.0, half, 0.0))
    ribbon = graph.n("GeometryNodeCurveToMesh", Curve=lines.o, Profile_Curve=section, Fill_Caps=True, Miter_Scale=True).o
    graph.result(graph.mat(mirrored(graph, ribbon, mirror), material))
    return graph


@asset("WPN.Lettering", "Solids")
def lettering():
    """A line of painted letters in the built-in font, its baseline running
    along +X from the object's origin, where the first letter's ink starts;
    a ``Width`` draws the line out (or in) to that length, as a sign
    painter fits lettering to its panel.  From ``Front`` to ``Back``."""
    graph = GN("WPN.Lettering", lettering.__doc__, modifier=True)
    graph.inp("Geometry", "GEOMETRY")
    text = graph.inp("Text", "STRING", default="")
    size = graph.inp("Size", default=0.005, min=0.0, subtype="DISTANCE")
    width = graph.inp("Width", default=0.0, min=0.0, subtype="DISTANCE", desc="length of the line; 0 keeps the font's")
    spacing = graph.inp("Character Spacing", default=1.0, min=0.0)
    front, back, chamfer, mirror = depth_inputs(graph, -0.0001, 0.0, 0.0)
    material = graph.inp("Material", "MATERIAL", default=M.get("WPN.Paint"))
    letters = graph.n("GeometryNodeStringToCurves", String=text, Size=size, Character_Spacing=spacing)
    face = upward(graph, filled(graph, graph.realize(letters["Curve Instances"])))
    bounds = graph.bound_box(face)
    left = graph.sep(bounds["Min"])[0]
    natural = graph.sep(bounds["Max"])[0] - left
    stretch = graph.switch(graph.compare(width, 0.0, "GREATER_THAN"), 1.0, width / graph.max(natural, 1e-6), "FLOAT")
    face = graph.transform(graph.move(face, x=left * -1.0), s=graph.vec(stretch, 1.0, 1.0))
    solid = off_drawing(graph, chamfered(graph, slab(graph, face, front, back), chamfer))
    graph.result(dressed(graph, solid, material, mirror))
    return graph
