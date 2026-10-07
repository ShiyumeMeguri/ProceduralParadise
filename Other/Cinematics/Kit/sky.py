"""
Sky kit -- the world a set stands under, procedural (no images).

``sky_world(spec)`` builds the world shader from data::

    {"zenith": [r, g, b], "horizon": [r, g, b], "ground": [r, g, b],
     "strength": 1.0,             (how bright the whole sky is)
     "haze": 12.0,                (degrees over which the horizon colour gives way to the zenith's)
     "clouds": {"height": 1800.0,  (metres up to the cloud deck)
                "scale": 1400.0,   (metres across a cloud)
                "coverage": 0.5,   (share of the deck covered)
                "softness": 0.18,  (how soft a cloud's edge is)
                "lit": [r, g, b], "shade": [r, g, b],
                "fade": 4.0,       (degrees above the horizon below which the deck dissolves into the haze)
                "drift": [x, y]}}  (metres a second the deck moves)

The deck is a plane at ``height``: a ray climbing towards it meets the
cloud pattern where it crosses the plane, so clouds keep their place in
the sky whatever the camera does and shrink towards the horizon.  The
same sky lights the set; a set's sun is a lamp of its own.  The haze of
the air between the set's buildings is an object of the set
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
    clouds = spec.get("clouds")
    if clouds:
        lift = tree.math("MAXIMUM", height, 0.02)
        reach = clouds["height"] / lift
        drift = clouds.get("drift", (0.0, 0.0))
        seconds = tree.n("ShaderNodeValue")
        seconds.n.name = seconds.n.label = "Seconds"
        deck = tree.vec(direction.x * reach + seconds.o * drift[0], direction.y * reach + seconds.o * drift[1], 0.0)
        noise = tree.n("ShaderNodeTexNoise", Vector=deck, Scale=1.0 / clouds["scale"], Detail=8.0, Roughness=0.58,
                       Lacunarity=2.1, props={"noise_dimensions": "2D"})["Fac"]
        threshold = 1.0 - clouds["coverage"]
        density = tree.map_range(noise, threshold * 0.6 + 0.2 - clouds["softness"] * 0.5,
                                 threshold * 0.6 + 0.2 + clouds["softness"] * 0.5, 0.0, 1.0, interp="SMOOTHSTEP")
        body = tree.n("ShaderNodeTexNoise", Vector=deck, Scale=3.0 / clouds["scale"], Detail=4.0, Roughness=0.5,
                      props={"noise_dimensions": "2D"})["Fac"]
        tone = tree.mix(tree.clamp01(body * 1.6 - 0.3), _color(clouds["shade"]), _color(clouds["lit"]), "RGBA")
        fade = clouds.get("fade", 4.0) * 3.14159265 / 180.0
        visible = tree.clamp01(elevation / fade) * density
        sky = tree.mix(visible, sky, tone, "RGBA")
    below = tree.math("LESS_THAN", height, 0.0)
    sky = tree.mix(below, sky, _color(spec.get("ground", spec["horizon"])), "RGBA")
    light = tree.n("ShaderNodeBackground", Color=sky, Strength=spec.get("strength", 1.0))["Background"]
    tree.link(light, tree.n("ShaderNodeOutputWorld").n.inputs["Surface"])
    tree.layout()
    return world
