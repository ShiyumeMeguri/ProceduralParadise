"""
Sky kit -- the world a set stands under, procedural (no images).

``sky_world(spec)`` builds the world shader from data::

    {"zenith": [r, g, b], "horizon": [r, g, b], "ground": [r, g, b],
     "strength": 1.0,             (how bright the whole sky is)
     "haze": 12.0,                (degrees over which the horizon colour gives way to the zenith's)
     "clouds": {...}}             (the cumulus: Kit.clouds, a deck of their own built with the sky)

The same sky lights the set; a set's sun is a lamp of its own.  The haze
of the air between the set's buildings is an object of the set
(``CIN.Env.Air``), thick low down and thinning upwards.
"""
from __future__ import annotations

import bpy

from Core import shaders as S
from Core.nodes import Tree

__all__ = ["sky_world"]


def _color(value):
    return tuple(float(component) for component in value) + (1.0,)


def sky_world(spec, name="Sky"):
    world = bpy.data.worlds.get(name) or bpy.data.worlds.new(name)
    bpy.context.scene.world = world
    tree = Tree.wrap(world.node_tree, clear=True)
    direction = tree.n("ShaderNodeTexCoord")["Generated"].normalized()
    height = direction.z
    elevation = tree.math("ARCSINE", tree.math("MAXIMUM", tree.math("MINIMUM", height, 1.0), -1.0))
    haze = spec.get("haze", 12.0) * 3.14159265 / 180.0
    upward = tree.clamp01(elevation / haze)
    upward = upward * upward * (3.0 - upward * 2.0)
    sky = tree.mix(upward, _color(spec["horizon"]), _color(spec["zenith"]), "RGBA")
    below = tree.math("LESS_THAN", height, 0.0)
    sky = tree.mix(below, sky, _color(spec.get("ground", spec["horizon"])), "RGBA")
    light = tree.n("ShaderNodeBackground", Color=sky, Strength=spec.get("strength", 1.0))["Background"]
    tree.link(light, tree.n("ShaderNodeOutputWorld").n.inputs["Surface"])
    tree.layout()
    return world
