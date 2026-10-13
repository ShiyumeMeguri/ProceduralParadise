"""
Construction helpers the Rain Garden kit shares on top of :class:`Core.gn.GN`
(only what ``GN`` itself does not offer):

* :func:`box`           box of a size (vector) about a centre;
* :func:`box_between`   box spanning two corner vectors (sockets or tuples);
* :func:`count_for`     how many items of a spacing fit along a length;
* :func:`euler`         rotation from an Euler vector;
* :func:`held_normal`   a curve whose normal is held to a fixed direction;
* :func:`framed_sweep`  a profile swept along such a curve (arches in a
                        vertical plane, bands that must stay level);
* :func:`fill_at_height` a closed curve filled at its own height (Fill Curve
                        works in the XY plane and drops it), faces up;
* :func:`hanging_ribbon` a vertical strip between two heights under a curve;
* :func:`measured`      a refractive body carrying its ``thickness``;
* :func:`flip`          a mesh with its faces turned over;
* :func:`unit_lathe`    a surface of revolution from a profile in units of
                        its radius and height, scaled to both.
"""
from __future__ import annotations

from Core.gn import get_asset, set_mode

TAU = 6.283185307179586


def euler(graph, vector):
    return graph.n("FunctionNodeEulerToRotation", vector).o


def box(graph, size, centre):
    return graph.transform(graph.cube(size), t=centre)


def box_between(graph, low, high):
    size = graph.vmath("SUBTRACT", high, low)
    centre = graph.vmath("SCALE", graph.vmath("ADD", low, high), scale=0.5)
    return box(graph, size, centre)


def count_for(graph, length, spacing):
    return graph.to_int(graph.math("DIVIDE", length, spacing)) + 1


def held_normal(graph, curve, up=(0.0, 0.0, 1.0)):
    """``curve`` with its normal held to the direction ``up``."""
    framed = graph.n("GeometryNodeSetCurveNormal", curve)
    set_mode(framed, "FREE")
    graph.assign(framed.n.inputs["Normal"], up)
    return framed.o


def framed_sweep(graph, curve, profile, up=(0.0, 0.0, 1.0), caps=True):
    """``profile`` swept along ``curve`` with the curve normal held to
    ``up``: the profile's X runs along ``up``, its Y along tangent x up."""
    return graph.sweep(held_normal(graph, curve, up), profile, caps)


def fill_at_height(graph, curve, mode="NGONS"):
    filled = graph.fill(curve, mode)
    upward = graph.n("GeometryNodeFlipFaces", filled, Selection=graph.compare(graph.normal().z, 0.0, "LESS_THAN")).o
    return graph.move(upward, z=graph.bound_box(curve)["Min"].z)


def hanging_ribbon(graph, curve, bottom, top):
    """Vertical strip from ``bottom`` to ``top`` (heights above the curve)."""
    edges = graph.sweep(graph.move(curve, z=bottom), None, False)
    return graph.n("GeometryNodeExtrudeMesh", props={"mode": "EDGES"}, Mesh=edges, Offset=graph.vec(0.0, 0.0, top - bottom)).o


def measured(graph, mesh, longest):
    """``mesh`` (closed, normals out) carrying the ``thickness`` a refractive
    body's material reads (``Shading.Thickness``), at most ``longest``."""
    return graph.group(get_asset("Shading.Thickness"), Mesh=mesh, Max_Thickness=longest).o


def flip(graph, mesh):
    return graph.n("GeometryNodeFlipFaces", mesh).o


def unit_lathe(graph, profile, radius, height, segments=48):
    """:meth:`GN.lathe` of ``profile`` [(r, z), ...] (from the axis at the
    bottom, out, up) given in units of ``radius`` and ``height``."""
    return graph.transform(graph.lathe(profile, segments), s=graph.vec(radius, radius, height))
