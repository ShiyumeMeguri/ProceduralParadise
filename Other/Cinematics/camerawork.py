"""
Camerawork -- a shot's camera as a camera operator moves it, from key positions.

A shot's ``camera`` is data::

    {"lens": 35.0, "sensor": 36.0, "clip": [0.05, 8000.0],
     "dof": {"fstop": 2.8, "focus": {"cast": "LaPluma", "bone": "Head"}},
     "follow": {"cast": "LaPluma", "bone": "Pelvis"},          (optional)
     "keys": [{"frame": 68, "at": [x, y, z], "aim": [x, y, z], "roll": 0.0, "lens": 35.0,
               "carry": 1.0, "track": 1.0, "ease": "BEZIER"}, ...],
     "shake": [{"frames": [first, last], "amount": 1.5, "scale": 3.0}, ...]}   (optional)

The camera stands ``at`` and looks at ``aim`` (set metres), turned ``roll``
degrees about its line of sight, through a lens of ``lens`` millimetres on a
``sensor`` as wide.  A camera that ``follow``s a bone of a performer rides
with it: its ``at`` is where it stands from the bone -- the share ``carry`` of
the bone's travel carried along (1 without it) -- and its ``aim`` where it
looks from it, ``track`` of it followed: a camera flying beside her, or one
that stands still and pans after her.  Each key holds its values until the
next one takes over along Blender's own curves (auto-clamped Bezier, or as the
key's ``ease`` says), every one of them a channel of the rig the graph editor
shows: the camera's mount (where it stands, looking at its aim by a Track To),
the aim, and the camera under the mount (its roll, its lens).  A ``shake``
jolts the camera over its frames -- turns of up to ``amount`` degrees that
change over ``scale`` frames, as a handheld camera takes an impact.
"""
from __future__ import annotations

import math

import bpy

__all__ = ["build_camera", "follow"]


def _keyed(target, path, value, frame, index=-1):
    setattr(target, path, value)
    target.keyframe_insert(path, frame=frame, index=index)


def _empty(name, collection):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj.empty_display_size = 0.2
    return obj


def build_camera(name, camera, film, collection):
    """The shot's camera rig (see the module notes) in ``collection``, keyed; returns the camera object.  A camera that
    follows a performer is tied to it by :func:`follow` once the performer is built."""
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = camera.get("sensor", 36.0)
    data.clip_start, data.clip_end = camera.get("clip", (0.05, 8000.0))
    mount = _empty(f"{name} Mount", collection)
    aim = _empty(f"{name} Aim", collection)
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.parent = mount
    obj.rotation_mode = "XYZ"
    look = mount.constraints.new("TRACK_TO")
    look.name = "Look"
    look.target = aim
    look.track_axis = "TRACK_NEGATIVE_Z"
    look.up_axis = "UP_Y"
    keys = sorted(camera["keys"], key=lambda key: key["frame"])
    for key in keys:
        frame = key["frame"]
        _keyed(mount, "location", key["at"], frame)
        _keyed(aim, "location", key["aim"], frame)
        _keyed(obj, "rotation_euler", (0.0, 0.0, math.radians(key.get("roll", 0.0))), frame)
        _keyed(data, "lens", key.get("lens", camera["lens"]), frame)
    from Core.anim import fcurves_of
    eases = {key["frame"]: key.get("ease", "BEZIER") for key in keys}
    for holder in (mount, aim, obj, data):
        for curve in fcurves_of(holder):
            for point in curve.keyframe_points:
                point.interpolation = eases.get(int(round(point.co.x)), "BEZIER")
                point.handle_left_type = point.handle_right_type = "AUTO_CLAMPED"
            curve.update()
    for jolt in camera.get("shake", []):
        first, last = jolt["frames"]
        for axis in range(3):
            curve = next(curve for curve in fcurves_of(obj) if curve.data_path == "rotation_euler" and curve.array_index == axis)
            noise = curve.modifiers.new("NOISE")
            noise.strength = math.radians(jolt["amount"]) * (2.0 if axis < 2 else 1.0)
            noise.scale = jolt.get("scale", 3.0)
            noise.phase = 17.0 * axis + first
            noise.use_restricted_range = True
            noise.frame_start, noise.frame_end = first, last
            noise.blend_in = noise.blend_out = min(4.0, (last - first) / 3.0)
    return obj


def follow(camera_object, camera, performers):
    """Tie a camera that ``follow``s a performer (see the module notes) to its bone: the mount carries ``carry`` of its
    travel, the aim ``track`` of it, as keyed."""
    spec = camera.get("follow")
    if not spec:
        return
    rig = performers[spec["cast"]]
    mount = camera_object.parent
    aim = mount.constraints["Look"].target
    for holder, share in ((mount, "carry"), (aim, "track")):
        tie = holder.constraints.new("COPY_LOCATION")
        tie.name = "Follow"
        tie.target = rig
        tie.subtarget = spec["bone"]
        tie.use_offset = True
        holder.constraints.move(len(holder.constraints) - 1, 0)
        for key in camera["keys"]:
            tie.influence = key.get(share, 1.0)
            tie.keyframe_insert("influence", frame=key["frame"])
    from Core.anim import fcurves_of
    for holder in (mount, aim):
        for curve in fcurves_of(holder):
            if "constraints[" in curve.data_path:
                for point in curve.keyframe_points:
                    point.handle_left_type = point.handle_right_type = "AUTO_CLAMPED"
                curve.update()
