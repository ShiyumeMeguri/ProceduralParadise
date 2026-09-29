"""
Choreography: keyframed performances written as data.

``pokes`` -- an object (a stick) pokes a target again and again::

    {"type": "pokes", "object": "Stick", "target": "Slime",
     "approach": 0.07, "withdraw": 0.16,
     "frames": {"thrust": 6, "retract": 10, "withdraw": 30},
     "pokes": [{"frame": 40, "azimuth": -55, "elevation": 50,
                "aim_height": 0.05, "depth": 0.012, "hold": 3}, ...]}

Each poke comes along the direction ``azimuth`` degrees round from the
target's front (its local -Y) and ``elevation`` degrees up, aimed at the
point ``aim_height`` above the target's origin.  The stick's tip (its origin,
the stick along its +Z) waits ``approach`` off the target's surface, thrusts
``depth`` into it in ``thrust`` frames, holds, retracts; after the last poke
it withdraws to ``withdraw`` off the surface.  The surface is the target's
shape: its first modifier alone, before any simulation.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from Core import anim as ANIM

__all__ = ["perform"]


def _direction(front, azimuth, elevation):
    right = Vector((-front.y, front.x, 0.0))
    horizontal = front * math.cos(math.radians(azimuth)) + right * math.sin(math.radians(azimuth))
    return (horizontal * math.cos(math.radians(elevation)) + Vector((0.0, 0.0, math.sin(math.radians(elevation))))).normalized()


def _shape_surface(target):
    """Ray caster against the target's shape (every modifier after the first
    muted while the rays are cast)."""
    muted = [modifier for modifier in list(target.modifiers)[1:] if modifier.show_viewport]
    for modifier in muted:
        modifier.show_viewport = False
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    inverse = target.matrix_world.inverted()

    def along(aim, direction):
        found, location, _normal, _index = target.ray_cast(inverse @ (aim + direction), (inverse.to_3x3() @ -direction).normalized(),
                                                           depsgraph=depsgraph)
        if not found:
            raise ValueError(f"a poke along {tuple(direction)} misses {target.name}")
        return target.matrix_world @ location

    def restore():
        for modifier in muted:
            modifier.show_viewport = True
        bpy.context.view_layer.update()
    return along, restore


def pokes(spec):
    stick = bpy.data.objects[spec["object"]]
    target = bpy.data.objects[spec["target"]]
    frames = spec["frames"]
    front = target.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))
    front = Vector((front.x, front.y, 0.0)).normalized()
    origin = target.matrix_world.translation
    along, restore = _shape_surface(target)
    stick.animation_data_clear()
    stick.rotation_mode = "QUATERNION"

    def key(frame, location, rotation):
        stick.location = location
        stick.rotation_quaternion = rotation
        stick.keyframe_insert("location", frame=frame)
        stick.keyframe_insert("rotation_quaternion", frame=frame)

    rotation = None
    for index, poke in enumerate(spec["pokes"]):
        direction = _direction(front, poke["azimuth"], poke["elevation"])
        previous = rotation
        rotation = direction.to_track_quat("Z", "Y")
        if previous is not None:
            rotation.make_compatible(previous)
        surface = along(origin + Vector((0.0, 0.0, poke["aim_height"])), direction)
        ready = surface + direction * spec["approach"]
        thrust = surface - direction * poke["depth"]
        if index == 0:
            key(1, ready, rotation)
        key(poke["frame"], ready, rotation)
        key(poke["frame"] + frames["thrust"], thrust, rotation)
        key(poke["frame"] + frames["thrust"] + poke["hold"], thrust, rotation)
        retracted = poke["frame"] + frames["thrust"] + poke["hold"] + frames["retract"]
        key(retracted, ready, rotation)
    key(retracted + frames["withdraw"], surface + direction * spec["withdraw"], rotation)
    restore()
    for curve in ANIM.fcurves_of(stick):
        for point in curve.keyframe_points:
            point.interpolation = "BEZIER"
            point.handle_left_type = "AUTO_CLAMPED"
            point.handle_right_type = "AUTO_CLAMPED"
        curve.update()


PERFORMANCES = {"pokes": pokes}


def perform(specs):
    for spec in specs:
        PERFORMANCES[spec["type"]](spec)
