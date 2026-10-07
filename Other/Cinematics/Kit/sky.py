"""
Sky kit -- the world a set stands under, procedural (no images).

``sky_world(spec)`` builds the world shader from data::

    {"zenith": [r, g, b], "horizon": [r, g, b], "ground": [r, g, b],
     "strength": 1.0,             (how bright the whole sky is)
     "haze": 12.0,                (degrees over which the horizon colour gives way to the zenith's)
     "ambient": [r, g, b],        (the light it sheds on the set from above the horizon)
     "clouds": {...}}             (the cumulus: Kit.clouds, a deck of their own built with the sky)

The camera sees the sky's gradient; the set is lit by its ``ambient`` above the horizon and its ground below -- the sky
as the set sees it, clouds and all, for the cumulus are a volume that lights only itself (``fit_sky.py`` measures it:
the mean of what the sky shows).  A sky without an ambient (no clouds) lights the set as it looks.  A set's sun is a
lamp of its own.  The haze
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
    ground = _color(spec.get("ground", spec["horizon"]))
    strength = spec.get("strength", 1.0)
    seen = tree.n("ShaderNodeBackground", Color=tree.mix(below, sky, ground, "RGBA"), Strength=strength)["Background"]
    light = seen
    if "ambient" in spec:
        shed = tree.mix(below, _color(spec["ambient"]), _color([channel * strength for channel in ground[:3]]), "RGBA")
        lighting = tree.n("ShaderNodeBackground", Color=shed, Strength=1.0)["Background"]
        light = tree.n("ShaderNodeMixShader", tree.n("ShaderNodeLightPath")["Is Camera Ray"], lighting, seen)["Shader"]
    tree.link(light, tree.n("ShaderNodeOutputWorld").n.inputs["Surface"])
    tree.layout()
    return world
