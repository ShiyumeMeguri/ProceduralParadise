"""
Environment kit -- geometry-node groups (``CF.Env.*``): the world outside
the glass.

The conservatory stands on a stone terrace in a still sea under the stars;
crystal spires -- the kit's own self-similar druses at the scale of towers
-- rise from the water all around, scattered on an equal-area golden-angle
annulus.

Local frames: centred on the origin, the sea surface at z = 0.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset
from Fractals import phyllotaxis as PHY
from ..values import apply
from . import materials as M

TAU = math.tau


@asset("CF.Env.Spires", "Environment")
def spires():
    """Crystal spires on a Vogel annulus between ``Inner Radius`` and
    ``Outer Radius`` (equal area per spire), each a druse ``Height Min`` ..
    ``Height Max`` tall, leaning a little."""
    graph = GN("CF.Env.Spires", spires.__doc__)
    count = graph.inp("Count", "INT", default=40, min=0, max=2000)
    inner = graph.inp("Inner Radius", default=70.0, subtype="DISTANCE")
    outer = graph.inp("Outer Radius", default=420.0, subtype="DISTANCE")
    low = graph.inp("Height Min", default=25.0, subtype="DISTANCE")
    high = graph.inp("Height Max", default=110.0, subtype="DISTANCE")
    lean = graph.inp("Lean", default=math.radians(12.0), subtype="ANGLE")
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.CrystalFar"))

    variants = [apply(graph, graph.group(get_asset("CF.Crystal.Druse")),
                      {"Count": 4, "Spread": 14.0, "Length": 1.0, "Thickness": 0.06, "Levels": 1, "Children": 4,
                       "Child Scale": 0.35, "Falloff": 0.35, "Seed": seed * 4 + variant, "Material": material}).o
                for variant in range(4)]
    choices = graph.n("GeometryNodeGeometryToInstance", Geometry=variants).o
    t, azimuth = PHY.spiral(graph, count)
    reach = graph.math("SQRT", inner * inner + t * (outer * outer - inner * inner))
    azimuth = azimuth + seed * 0.61
    sites = graph.points(count, graph.vec(reach * graph.cos(azimuth), reach * graph.sin(azimuth), -2.0))
    tilt = graph.vec(graph.random(-1.0, 1.0, seed) * lean, graph.random(-1.0, 1.0, seed + 1) * lean,
                     graph.random(0.0, TAU, seed + 2))
    height = low + graph.math("POWER", graph.random(0.0, 1.0, seed + 3), 1.5) * (high - low)
    graph.result(graph.iop(sites, choices, rot=tilt, scale=height, pick=True,
                           index=graph.random(0, 3, seed + 4, dtype="INT")))
    return graph


@asset("CF.Env.Sea", "Environment")
def sea():
    """The still sea: one plane of ``Size`` at z = 0 (its surface is in the
    material)."""
    graph = GN("CF.Env.Sea", sea.__doc__)
    size = graph.inp("Size", default=6000.0, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Sea"))
    graph.result(graph.mat(graph.grid(size, size, 2, 2), material))
    return graph


@asset("CF.Env.Haze", "Environment")
def haze():
    """Box of luminous air (volume only) of ``Size``, standing on z = 0."""
    graph = GN("CF.Env.Haze", haze.__doc__)
    size = graph.inp("Size", "VECTOR", default=(60.0, 60.0, 22.0))
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Haze"))
    _, _, height = graph.sep(size)
    graph.result(graph.mat(graph.move(graph.cube(size), z=height * 0.5), material))
    return graph


@asset("CF.Env.Terrace", "Environment")
def terrace():
    """Stone terrace the conservatory stands on: a polygonal platform with
    its top at z = 0 and a flight of steps all round down to the sea."""
    graph = GN("CF.Env.Terrace", terrace.__doc__)
    radius = graph.inp("Radius", default=34.0, subtype="DISTANCE")
    sides = graph.inp("Sides", "INT", default=16, min=3, max=128)
    height = graph.inp("Height", default=1.8, subtype="DISTANCE")
    steps = graph.inp("Steps", "INT", default=6, min=0, max=40)
    tread = graph.inp("Tread", default=0.45, subtype="DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Stone"))

    rise = height / graph.max(steps + 1.0, 1.0)
    level = graph.index()
    flights = graph.points(steps + 1, graph.vec(0.0, 0.0, level * rise * -1.0))
    slab = graph.n("GeometryNodeMeshCylinder", props={"fill_type": "NGON"}, Vertices=sides, Radius=1.0, Depth=1.0).o
    slab = graph.move(slab, z=-0.5)
    platform = graph.iop(flights, slab, scale=graph.vec(radius + level * tread, radius + level * tread, rise))
    graph.result(graph.mat(graph.realize(platform), material))
    return graph
