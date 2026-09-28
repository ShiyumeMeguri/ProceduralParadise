"""
Self-similar geometry as an iterated function system unrolled into levels.

A druse of crystals whose feet sprout smaller druses, a botryoidal mineral
of spheres budding spheres, a hydrangea head of flowers made of flowers --
each is the attractor of a set of similarity maps applied to a seed shape.
Geometry nodes have no recursion, so the attractor is built level by level:
``level 0 = seed`` and ``level k = seed + children(level k-1)``, where
``children`` instances its argument on a fixed set of child frames
(position, rotation, scale).  Instances of instances keep every level's
memory proportional to the seed, not to the number of copies.
"""
from __future__ import annotations

__all__ = ["levels", "pick_level"]


def levels(graph, seed, children, depth):
    """``[level 0, ..., level depth]`` of the system (see module doc)."""
    stages = [seed]
    for _ in range(depth):
        stages.append(graph.join(seed, children(stages[-1])))
    return stages


def pick_level(graph, stages, index):
    """The level selected by the (integer socket or constant) ``index``."""
    if isinstance(index, int):
        return stages[index]
    return graph.index_switch(index, stages, "GEOMETRY")
