"""
Core.anim -- keyframed camera moves that stay editable in Blender.

``camera_move`` builds a camera plus an aim target (Track To constraint) and
keys location / target / lens / shift -- and optionally any other animatable
value such as a compositor exposure -- at the given frames.  Between keys the
motion is a cubic Hermite spline (Catmull-Rom tangents over the key times,
zero tangents at the first/last key and at keys marked ``ease``).  It is
written as ordinary Bezier keyframes with explicit handles, so playback is
smooth and every key can still be tweaked in the Graph Editor.

Works with both action APIs: legacy ``action.fcurves`` (Blender 4.2/4.3) and
layered actions with channel bags (4.4+, the only one left in 5.x).
"""
from __future__ import annotations

import bpy
from mathutils import Vector

__all__ = ["fcurves_of", "camera_move", "hermite_handles"]


def fcurves_of(id_data):
    """All F-curves animating ``id_data`` (object, camera data, node tree...)."""
    ad = getattr(id_data, "animation_data", None)
    act = ad.action if ad else None
    if act is None:
        return []
    slot = getattr(ad, "action_slot", None)
    if slot is not None and hasattr(act, "layers"):
        for layer in act.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot) if hasattr(strip, "channelbag") else None
                if bag is not None:
                    return list(bag.fcurves)
    return list(getattr(act, "fcurves", []))


def _tangents(times, values, ease):
    n = len(times)
    m = [0.0] * n
    for i in range(1, n - 1):
        if not ease[i]:
            m[i] = (values[i + 1] - values[i - 1]) / float(times[i + 1] - times[i - 1])
    return m


def hermite_handles(fc, times, values, ease):
    """Give the keys of ``fc`` (one per entry of ``times``) Bezier handles that
    reproduce a C1 cubic Hermite spline through ``values``."""
    m = _tangents(times, values, ease)
    kps = sorted(fc.keyframe_points, key=lambda k: k.co[0])
    n = len(kps)
    for i, kp in enumerate(kps):
        kp.interpolation = "BEZIER"
        kp.handle_left_type = "FREE"
        kp.handle_right_type = "FREE"
        dl = (times[i] - times[i - 1]) / 3.0 if i > 0 else 1.0
        dr = (times[i + 1] - times[i]) / 3.0 if i < n - 1 else 1.0
        kp.handle_left = (times[i] - dl, values[i] - m[i] * dl)
        kp.handle_right = (times[i] + dr, values[i] + m[i] * dr)
    fc.update()


def _shape(id_data, data_path, frames, series, ease):
    """Apply Hermite handles to every F-curve of ``data_path`` on ``id_data``."""
    for fc in fcurves_of(id_data):
        if fc.data_path != data_path and not fc.data_path.endswith(data_path):
            continue
        idx = fc.array_index
        vals = [s[idx] if isinstance(s, (tuple, list, Vector)) else s for s in series]
        hermite_handles(fc, frames, vals, ease)


def camera_move(name, keys, parent_matrix=None, collection=None, sensor=36.0,
                extra=None):
    """Animated camera.

    ``keys``: list of dicts with ``frame``, ``location``, ``target`` (both in
    the parent frame), ``lens`` (mm, 36 mm sensor), optional ``shift``
    ([x, y]), ``ease`` (bool: stop smoothly on this key).
    ``extra``: optional list of ``(owner, attribute, values, id_data)`` for
    other animatable values keyed on the same frames -- ``owner`` holds the
    property (e.g. a compositor socket), ``id_data`` the data-block that owns
    the animation (e.g. the compositor node tree), ``values`` one per key.
    Returns the camera object; its aim target is ``<name>.Target``.
    """
    from mathutils import Matrix
    M = parent_matrix or Matrix.Identity(4)
    col = collection or bpy.context.scene.collection
    keys = sorted(keys, key=lambda k: k["frame"])
    frames = [float(k["frame"]) for k in keys]
    ease = [bool(k.get("ease", False)) for k in keys]

    data = bpy.data.cameras.new(name)
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = sensor
    data.clip_start, data.clip_end = 0.05, 20000.0
    cam = bpy.data.objects.new(name, data)
    col.objects.link(cam)
    tgt = bpy.data.objects.new(f"{name}.Target", None)
    tgt.empty_display_type = "SPHERE"
    tgt.empty_display_size = 0.15
    col.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    locs = [M @ Vector(k["location"]) for k in keys]
    tgts = [M @ Vector(k["target"]) for k in keys]
    lens = [float(k.get("lens", 28.0)) for k in keys]
    sx = [float(k.get("shift", (0.0, 0.0))[0]) for k in keys]
    sy = [float(k.get("shift", (0.0, 0.0))[1]) for k in keys]

    for f, p in zip(frames, locs):
        cam.location = p
        cam.keyframe_insert("location", frame=f)
    for f, p in zip(frames, tgts):
        tgt.location = p
        tgt.keyframe_insert("location", frame=f)
    for f, a, b, c in zip(frames, lens, sx, sy):
        data.lens, data.shift_x, data.shift_y = a, b, c
        for attr in ("lens", "shift_x", "shift_y"):
            data.keyframe_insert(attr, frame=f)
    _shape(cam, "location", frames, [tuple(p) for p in locs], ease)
    _shape(tgt, "location", frames, [tuple(p) for p in tgts], ease)
    _shape(data, "lens", frames, lens, ease)
    _shape(data, "shift_x", frames, sx, ease)
    _shape(data, "shift_y", frames, sy, ease)

    for owner, attr, series, id_data in (extra or []):
        for f, v in zip(frames, series):
            setattr(owner, attr, v)
            owner.keyframe_insert(attr, frame=f)
        _shape(id_data, attr, frames, series, ease)
    return cam
