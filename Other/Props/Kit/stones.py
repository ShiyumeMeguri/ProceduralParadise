"""
Stone kit: a rough rock and a carved stone basin.

A rock rests on z = 0 and may be cut flat at its top (a stone something
strikes); the basin stands on z = 0 around the origin, its floor slopes down
to a drain hole through the middle.
"""
from __future__ import annotations

from Core.gn import GN, asset
from . import materials as M


@asset("Props.Rock", "Stones")
def rock():
    """A rough rock: a sphere displaced by noise along its normals and
    scaled to ``Size``, flattened where it meets the ground (and, with
    ``Flat Top``, cut at z = Size z)."""
    graph = GN("Props.Rock", rock.__doc__)
    size = graph.inp("Size", "VECTOR", default=(0.08, 0.06, 0.05), subtype="XYZ")
    roughness = graph.inp("Roughness", default=0.22, min=0.0, max=0.9, desc="Relative depth of the bumps")
    detail = graph.inp("Scale", default=1.4, min=0.0, desc="Size of the bumps: noise frequency over the unit sphere")
    seed = graph.inp("Seed", "INT", default=0)
    flat_top = graph.inp("Flat Top", "BOOL", default=False)
    material = graph.inp("Material", "MATERIAL", default=M.get("Props.Stone"))
    sphere = graph.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=5)["Mesh"]
    bumps = graph.n("ShaderNodeTexNoise", Vector=graph.position(), W=seed, Scale=detail, Detail=4.0, Roughness=0.55,
                    props={"noise_dimensions": "4D"})["Fac"]
    lumpy = graph.set_pos(sphere, pos=graph.position() * (1.0 + (bumps - 0.5) * 2.0 * roughness))
    height = size.z
    scaled = graph.set_pos(lumpy, pos=graph.position() * size * 0.5 + graph.vec(0.0, 0.0, height * 0.5))
    top = graph.switch(flat_top, height * 4.0, height, "FLOAT")
    x, y, z = graph.sep(graph.position())
    cut = graph.set_pos(scaled, pos=graph.vec(x, y, graph.min(graph.max(z, 0.0), top)))
    graph.result(graph.mat(graph.smooth_by_angle(cut, 0.6), material))
    return graph


@asset("Props.Basin", "Stones")
def basin():
    """Carved stone basin: a rounded bowl whose floor slopes down to a drain
    hole through the middle."""
    graph = GN("Props.Basin", basin.__doc__)
    radius = graph.inp("Radius", default=0.09, min=0.01, subtype="DISTANCE")
    height = graph.inp("Height", default=0.05, min=0.005, subtype="DISTANCE")
    wall = graph.inp("Wall", default=0.014, min=0.002, subtype="DISTANCE")
    floor = graph.inp("Floor", default=0.014, min=0.002, subtype="DISTANCE")
    fall = graph.inp("Fall", default=0.004, min=0.0, desc="How much lower the floor is at the drain than at the wall")
    drain = graph.inp("Drain Radius", default=0.012, min=0.001, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("Props.Stone"))
    inner = radius - wall
    lip = wall * 0.3
    profile = [(drain, 0.0), (radius * 0.82, 0.0), (radius * 0.96, height * 0.18), (radius, height * 0.5),
               (radius * 0.985, height * 0.86), (radius - lip, height), (inner + lip, height), (inner, height - lip),
               (inner, floor + lip * 2.0), (inner - lip * 2.0, floor), (drain + lip, floor - fall), (drain, floor - fall - lip),
               (drain, 0.0)]
    graph.result(graph.mat(graph.smooth_by_angle(graph.lathe(profile, 64), 0.9), material))
    return graph
