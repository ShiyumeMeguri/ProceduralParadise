"""
Golden-angle point sets -- the 3D Fibonacci lattice -- as geometry-node fields.

Every organ that grows by phyllotaxis sits on the same lattice: the k-th of
n elements turns by the divergence angle from the one before (the golden
angle ``pi * (3 - sqrt(5))`` for Fibonacci spirals), and on a sphere its
height follows the equal-area rule ``z = 1 - t * (1 - cos(cap))`` with
``t = (k + 1/2) / n``, so the elements tile a spherical cap evenly while
their spiral parastichies come out in consecutive Fibonacci numbers.  On a
disc the radius grows as ``sqrt(t)`` (Vogel's sunflower model).

The point sets carry ``t`` as the named attribute ``fibonacci_t``: size,
tilt and colour of an organ are graded along the spiral from it.
"""
from __future__ import annotations

import math

__all__ = ["GOLDEN_ANGLE", "T_ATTRIBUTE", "spiral", "cap_polar", "direction", "cap_points", "disc_points",
           "read_t"]

GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))
T_ATTRIBUTE = "fibonacci_t"


def spiral(graph, count, divergence=GOLDEN_ANGLE):
    """Index fields of the lattice: ``(t, azimuth)`` with t = (index + 1/2) /
    count and azimuth = index * divergence."""
    index = graph.index()
    return (index + 0.5) / count, index * divergence


def cap_polar(graph, t, cap_angle, start_angle=0.0):
    """Polar angle of the equal-area lattice at parameter ``t`` on the band
    between the polar angles ``start_angle`` and ``cap_angle`` (a cap when
    the band starts at the pole)."""
    top = graph.cos(start_angle)
    return graph.math("ARCCOSINE", top - t * (top - graph.cos(cap_angle)))


def direction(graph, polar, azimuth):
    """Unit vector at the given polar angle (from +Z) and azimuth."""
    ring = graph.sin(polar)
    return graph.vec(ring * graph.cos(azimuth), ring * graph.sin(azimuth), graph.cos(polar))


def cap_points(graph, count, cap_angle, radius=1.0, divergence=GOLDEN_ANGLE, start_angle=0.0):
    """``count`` points on the spherical cap of half-angle ``cap_angle``
    about +Z (or on the band from ``start_angle`` to ``cap_angle``), radius
    ``radius``, in spiral order."""
    t, azimuth = spiral(graph, count, divergence)
    position = direction(graph, cap_polar(graph, t, cap_angle, start_angle), azimuth)
    if not (isinstance(radius, float) and radius == 1.0):
        position = position * radius
    return graph.store(graph.points(count, position), T_ATTRIBUTE, t)


def disc_points(graph, count, radius, divergence=GOLDEN_ANGLE, dome=0.0):
    """Vogel's sunflower: ``count`` points on a disc of ``radius`` in the XY
    plane, optionally lifted into a dome of height ``dome`` at the centre."""
    t, azimuth = spiral(graph, count, divergence)
    distance = graph.math("SQRT", t) * radius
    height = (1.0 - t) * dome
    position = graph.vec(distance * graph.cos(azimuth), distance * graph.sin(azimuth), height)
    return graph.store(graph.points(count, position), T_ATTRIBUTE, t)


def read_t(graph):
    return graph.named(T_ATTRIBUTE)
