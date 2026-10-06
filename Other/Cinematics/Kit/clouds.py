"""
Clouds kit (``CIN.Clouds.*``): cumulus as solid shapes in the sky, built by geometry nodes.

``CIN.Clouds.Cumulus``: one cloud.  ``Blobs`` spheres heaped in the half-ellipsoid ``Size``
(half its length, half its width, its height) over a flat base -- a wide skirt low down,
towers rising narrower and rounder -- are fused into one surface: a volume of the spheres
meshed at ``Voxel``, its creases relaxed (``Relax`` passes of averaging every vertex with its
neighbours) so the heap reads as one body, then billowed: pushed out along the normals by
two octaves of noise, ``Billow`` metres deep at the scale of a tenth of the cloud.  The base
is cut flat where the cloud condenses.  Its shading is ``CIN.Cloud``.

``CIN.Clouds.Field``: ``Count`` cumulus over the rectangle ``Origin`` +- ``Extent`` (its Z
the height of the bases), each a turned, scaled copy of one of ``SHAPES`` clouds -- sizes
about ``Size`` -- drifting along ``Drift`` metres a second from the frame ``Start``.  A
cloud is a kilometre away and seen from the side; variety is in the heaps, not the copies.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, set_mode
from . import materials as M

SHAPES = 6
SEEDS = {"blob x": 1.0, "blob y": 2.0, "blob z": 3.0, "blob r": 4.0, "place x": 5.0, "place y": 6.0, "turn": 7.0,
         "size": 8.0, "shape": 9.0, "squash": 10.0}


@asset("CIN.Clouds.Cumulus", "Clouds")
def cumulus():
    """One cumulus heaped from ``Blobs`` spheres over a flat base (see the module notes)."""
    graph = GN("CIN.Clouds.Cumulus", cumulus.__doc__)
    size = graph.inp("Size", "VECTOR", default=(400.0, 250.0, 260.0), subtype="TRANSLATION")
    blobs = graph.inp("Blobs", "INT", default=40, min=1)
    seed = graph.inp("Seed", "INT", default=0)
    voxel = graph.inp("Voxel", default=12.0, min=0.5, subtype="DISTANCE")
    billow = graph.inp("Billow", default=24.0, min=0.0, subtype="DISTANCE")
    relax = graph.inp("Relax", "INT", default=12, min=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Cloud"))

    def draw(key, low=0.0, high=1.0):
        return graph.random(low, high, seed * 53 + int(SEEDS[key]), ID=graph.index())

    points = graph.new_points(blobs)
    rise = draw("blob z") ** 1.4
    reach = 1.0 - rise * 0.6
    place = graph.vec(draw("blob x", -1.0, 1.0) * reach, draw("blob y", -1.0, 1.0) * reach, rise * 0.8) * size
    points = graph.set_pos(points, pos=place)
    radius = graph.min(size.x, size.y) * (0.3 - rise * 0.1) * draw("blob r", 0.55, 1.0)
    points = graph.n("GeometryNodeSetPointRadius", Points=points, Radius=radius).o
    to_volume = graph.n("GeometryNodePointsToVolume", Points=points, Density=1.0, Radius=radius)
    set_mode(to_volume, "Size", ("resolution_mode",), ("Resolution Mode",))
    graph.assign(graph._in_socket(to_volume.n, "Voxel Size"), voxel)
    to_mesh = graph.n("GeometryNodeVolumeToMesh", Volume=to_volume.o, Threshold=0.1)
    set_mode(to_mesh, "Size", ("resolution_mode",), ("Resolution Mode",))
    graph.assign(graph._in_socket(to_mesh.n, "Voxel Size"), voxel)
    surface = to_mesh.o
    relaxed = graph.n("GeometryNodeBlurAttribute", Value=graph.position(), Iterations=relax, Weight=1.0, props={"data_type": "FLOAT_VECTOR"}).o
    surface = graph.set_pos(surface, pos=relaxed)
    scale = graph.max(graph.min(size.x, size.y) * 0.1, 1.0)
    large = graph.n("ShaderNodeTexNoise", Vector=graph.position(), Scale=1.0 / scale, Detail=2.0, Roughness=0.5,
                    props={"noise_dimensions": "3D"})["Fac"]
    small = graph.n("ShaderNodeTexNoise", Vector=graph.position(), Scale=3.0 / scale, Detail=3.0, Roughness=0.55,
                    props={"noise_dimensions": "3D"})["Fac"]
    upward = graph.max(graph.normal().z, 0.0)
    surface = graph.set_pos(surface, offset=graph.normal() * (((large - 0.45) + (small - 0.45) * 0.35) * billow * (0.5 + upward)))
    surface = graph.set_pos(surface, pos=graph.vec(graph.position().x, graph.position().y, graph.max(graph.position().z, size.z * 0.02)))
    graph.result(graph.mat(graph.smooth(surface), material))
    return graph


@asset("CIN.Clouds.Field", "Clouds")
def field():
    """``Count`` cumulus over a rectangle of sky (see the module notes)."""
    graph = GN("CIN.Clouds.Field", field.__doc__)
    count = graph.inp("Count", "INT", default=12, min=0)
    seed = graph.inp("Seed", "INT", default=0)
    origin = graph.inp("Origin", "VECTOR", default=(0.0, 3000.0, 900.0), subtype="TRANSLATION")
    extent = graph.inp("Extent", "VECTOR", default=(4000.0, 2000.0, 0.0), subtype="TRANSLATION")
    size = graph.inp("Size", "VECTOR", default=(450.0, 300.0, 300.0), subtype="TRANSLATION")
    size_spread = graph.inp("Size Spread", default=0.35, min=0.0, max=1.0)
    voxel = graph.inp("Voxel", default=14.0, min=0.5, subtype="DISTANCE")
    billow = graph.inp("Billow", default=16.0, min=0.0, subtype="DISTANCE")
    drift = graph.inp("Drift", "VECTOR", default=(3.0, 1.0, 0.0), desc="m/s")
    start = graph.inp("Start", default=0.0)
    fps = graph.inp("FPS", default=30.0, min=1.0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Cloud"))
    time = (graph.scene_frame() - start) * (1.0 / fps)

    def draw(key, low=0.0, high=1.0):
        return graph.random(low, high, seed * 71 + int(SEEDS[key]), ID=graph.index())

    shapes = [graph.group(get_asset("CIN.Clouds.Cumulus"), Size=size, Blobs=60 + k * 10, Seed=seed * 11 + k, Voxel=voxel,
                          Billow=billow, Material=material).o for k in range(SHAPES)]
    library = graph.n("GeometryNodeGeometryToInstance", Geometry=list(reversed(shapes))).o
    points = graph.new_points(count)
    place = origin + graph.vec(draw("place x", -1.0, 1.0), draw("place y", -1.0, 1.0), 0.0) * extent + drift * time
    points = graph.set_pos(points, pos=place)
    scale = 1.0 + draw("size", -1.0, 1.0) * size_spread
    squash = draw("squash", 0.75, 1.15)
    shape = graph.to_int(draw("shape") * SHAPES, "FLOOR")
    rotation = graph.vec(0.0, 0.0, draw("turn") * (2.0 * math.pi))
    graph.result(graph.iop(points, library, rot=rotation, scale=graph.vec(scale, scale, scale * squash), pick=True, index=shape))
    return graph
