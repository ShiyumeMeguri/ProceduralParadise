"""
Core.physics.ground -- the analytic ground plane taken from an object.
"""
from __future__ import annotations

from ..gn import GN, asset


@asset("Physics.Ground", "Physics")
def ground():
    """Height of the top of an object's world-space bounding box, the infinite
    ground plane of the simulations (a table top, a floor).  ``Has Ground`` is
    false when no object is set or it has no mesh."""
    g = GN("Physics.Ground", ground.__doc__)
    target = g.inp("Object", "OBJECT")
    g.out("Height", "FLOAT")
    g.out("Has Ground", "BOOL")
    info = g.object_info(target)
    world = g.transform_by(info["Geometry"], info["Transform"])
    g.result(g.bound_box(world)["Max"].z, g.compare(g.domain_size(world, "MESH")["Point Count"], 0, "GREATER_THAN"))
    return g
