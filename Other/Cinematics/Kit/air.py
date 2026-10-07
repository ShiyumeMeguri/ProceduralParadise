"""
Air kit (``CIN.Env.Air``): the haze between a set's buildings.

``CIN.Env.Air``: the box between the corners ``Min`` and ``Max`` filled with ``CIN.Air`` --
haze thick near the ground and thinning upwards (to 1/e every ``CIN.Air.height`` metres), so
the far towers of a street fade into it while the sky overhead stays clear.
"""
from __future__ import annotations

from Core.gn import GN, asset
from . import materials as M


@asset("CIN.Env.Air", "Air")
def air():
    """The haze of a set: a box between ``Min`` and ``Max`` filled with ``Material``."""
    graph = GN("CIN.Env.Air", air.__doc__)
    low = graph.inp("Min", "VECTOR", default=(-2000.0, -2000.0, 0.0), subtype="TRANSLATION")
    high = graph.inp("Max", "VECTOR", default=(2000.0, 2000.0, 400.0), subtype="TRANSLATION")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Air"))
    graph.result(graph.mat(graph.transform(graph.cube((1.0, 1.0, 1.0)), t=(low + high) * 0.5, s=high - low), material))
    return graph
