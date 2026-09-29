"""
Studio kit (``Props.Studio.*``): the tabletop every prop stands on, the
cyclorama behind it and the soft gradient world around them.

The table's top face is z = 0 (its edges are rounded by a Bevel modifier in
the scene data); the cyclorama is one sheet whose floor runs along -Y into a
quarter-circle bend and a wall at +Y.
"""
from __future__ import annotations

import math

import bpy

from Core import shaders as S
from Core.gn import GN, asset, set_mode
from Core.nodes import Tree
from . import materials as M

BEND_STEPS = 24


@asset("Props.Studio.Table", "Studio")
def table():
    """Tabletop slab, its top face at z = 0."""
    graph = GN("Props.Studio.Table", table.__doc__)
    width = graph.inp("Width", default=0.9, min=0.01, subtype="DISTANCE")
    depth = graph.inp("Depth", default=0.7, min=0.01, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.06, min=0.001, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("Props.Table"))
    slab = graph.move(graph.cube(graph.vec(width, depth, thickness)), z=thickness * -0.5)
    graph.result(graph.mat(slab, material))
    return graph


@asset("Props.Studio.Backdrop", "Studio")
def backdrop():
    """Photo cyclorama: the floor from y = -Depth runs into a quarter-circle
    bend of radius ``Bend Radius`` and a wall at y = Depth up to ``Height``."""
    graph = GN("Props.Studio.Backdrop", backdrop.__doc__)
    width = graph.inp("Width", default=3.0, min=0.01, subtype="DISTANCE")
    depth = graph.inp("Depth", default=1.2, min=0.01, subtype="DISTANCE")
    height = graph.inp("Height", default=1.6, min=0.01, subtype="DISTANCE")
    bend = graph.inp("Bend Radius", default=0.45, min=0.01, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("Props.Backdrop"))
    profile = [graph.vec(width * -0.5, depth * -1.0, 0.0)]
    for step in range(BEND_STEPS + 1):
        angle = step / BEND_STEPS * math.pi * 0.5
        profile.append(graph.vec(width * -0.5, depth - bend + bend * math.sin(angle), bend - bend * math.cos(angle)))
    profile.append(graph.vec(width * -0.5, depth, height))
    edges = graph.n("GeometryNodeCurveToMesh", Curve=graph.polyline(profile)).o
    sheet = graph.n("GeometryNodeExtrudeMesh")
    set_mode(sheet, "EDGES")
    graph.assign(graph._in_socket(sheet.n, "Mesh"), edges)
    graph.assign(graph._in_socket(sheet.n, "Offset"), (1.0, 0.0, 0.0))
    graph.assign(graph._in_socket(sheet.n, "Offset Scale"), width)
    graph.result(graph.mat(graph.smooth(sheet["Mesh"]), material))
    return graph


def world(spec):
    """Studio world from data: a vertical gradient from ``bottom`` through
    ``horizon`` to ``top`` (linear RGB), times ``strength``."""
    target = S.new_world(spec.get("name", "Studio"))
    tree = Tree.wrap(target.node_tree, clear=True)
    height = tree.n("ShaderNodeTexCoord")["Generated"].normalized().z
    upper = tree.mix(tree.clamp01(height * 1.6), tuple(spec["horizon"]), tuple(spec["top"]), "RGBA")
    lower = tree.mix(tree.clamp01(height * -3.0), tuple(spec["horizon"]), tuple(spec["bottom"]), "RGBA")
    shade = tree.mix(tree.math("GREATER_THAN", height, 0.0), lower, upper, "RGBA")
    light = tree.n("ShaderNodeEmission", Color=shade, Strength=spec.get("strength", 1.0))["Emission"]
    tree.link(light, tree.n("ShaderNodeOutputWorld").n.inputs["Surface"])
    tree.layout()
    bpy.context.scene.world = target
    return target
