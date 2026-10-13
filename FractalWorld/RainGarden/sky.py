"""
Rain Garden sky -- the daylight dome over the glass vault, and its sun.

``scene.json`` ``"sun"`` gives the sun's ``elevation`` and ``azimuth``
(degrees; azimuth clockwise from +Y), ``power`` (W/m^2), ``angle`` (its
angular diameter, degrees) and ``color``; the sun lamp and the glow of the
sky around it are both placed from that one direction.

``"sky"`` shades the dome: a gradient from ``horizon_color`` to
``zenith_color``, a tight ``sun_glow`` and a wide ``sun_halo`` around the
sun, soft clouds above the horizon (``cloud_*``) and a hazy
``ground_color`` below it.  The camera sees the sky at ``camera_strength``
while light, reflections and refraction see ``strength``: the bright, cool
fill of the reference without a blown-out sky in the roof glazing.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from Core import shaders as S
from Core.nodes import Tree

__all__ = ["sun_direction", "build_sun", "build_world"]


def sun_direction(sun):
    elevation = math.radians(sun["elevation"])
    azimuth = math.radians(sun["azimuth"])
    return Vector((math.sin(azimuth) * math.cos(elevation), math.cos(azimuth) * math.cos(elevation), math.sin(elevation)))


def build_sun(sun, collection, name="Sun"):
    """Sun lamp shining from :func:`sun_direction` (its local +Z points at
    the sun)."""
    data = bpy.data.lights.new(name, "SUN")
    data.energy = sun["power"]
    data.angle = math.radians(sun.get("angle", 1.0))
    data.color = sun.get("color", (1.0, 1.0, 1.0))
    lamp = bpy.data.objects.new(name, data)
    lamp.rotation_euler = sun_direction(sun).to_track_quat("Z", "Y").to_euler()
    collection.objects.link(lamp)
    return lamp


def _rgba(value):
    return (*value[:3], 1.0)


def build_world(sky, sun, name="Rain Garden Sky"):
    world = S.new_world(name)
    t = Tree.wrap(world.node_tree, clear=True)
    direction = t.vmath("NORMALIZE", t.n("ShaderNodeTexCoord")["Generated"])
    x, y, height = t.sep(direction)
    gradient = t.map_range(height, sky["horizon_height"], sky["zenith_height"], 0.0, 1.0, interp="SMOOTHSTEP")
    color = t.mix(gradient, _rgba(sky["horizon_color"]), _rgba(sky["zenith_color"]), data_type="RGBA")
    toward = t.max(t.vmath("DOT_PRODUCT", direction, tuple(sun_direction(sun))), 0.0)
    glow = t.math("POWER", toward, sky["sun_glow_power"]) * sky["sun_glow_strength"]
    halo = t.math("POWER", toward, sky["sun_halo_power"]) * sky["sun_halo_strength"]
    color = t.mix(t.clamp01(glow + halo), color, _rgba(sky["sun_glow_color"]), data_type="RGBA")
    lift = height + 0.12
    dome = t.vec(x / lift, y / lift, 0.0)
    clouds = S.noise(t, dome, sky["cloud_scale"], 6.0, 0.55)["Fac"]
    cover = t.map_range(clouds, sky["cloud_threshold"], sky["cloud_threshold"] + sky["cloud_softness"], 0.0, sky["cloud_opacity"])
    cover = cover * t.map_range(height, 0.02, 0.25, 0.0, 1.0)
    color = t.mix(cover, color, _rgba(sky.get("cloud_color", (1.0, 1.0, 1.0))), data_type="RGBA")
    below = t.map_range(height, 0.0, -0.08, 0.0, 1.0)
    color = t.mix(below, color, _rgba(sky["ground_color"]), data_type="RGBA")
    camera = t.n("ShaderNodeLightPath")["Is Camera Ray"]
    strength = t.mix(camera, sky["strength"], sky["camera_strength"])
    background = t.n("ShaderNodeBackground", Color=color, Strength=strength)["Background"]
    output = t.n("ShaderNodeOutputWorld")
    t.link(background, output.n.inputs["Surface"])
    t.layout()
    return world
