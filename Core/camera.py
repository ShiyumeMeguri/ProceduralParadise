"""
Core.camera -- cameras from photogrammetric solves + projection utilities.

A *solve* describes a pinhole camera the way it was measured from a reference
image (all in pixels of the reference resolution)::

    {
      "resolution":   [1280, 900],
      "focal_px":     1137.1,
      "principal_px": [733.9, 492.56],   # optical centre (lens shift)
      "location":     [x, y, z],         # in the parent (room) frame, metres
      "yaw_deg":      21.41,             # rotation about +Z; 0 looks along +Y
      "pitch_deg":    0.0,               # + looks up
      "roll_deg":     0.0
    }

Blender cameras express the principal point through ``shift_x/shift_y`` in
units of the larger sensor dimension; this module converts exactly, so a
render at the solve resolution lands on the reference pixel grid.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Euler, Matrix, Vector

__all__ = ["camera_from_solve", "look_camera", "project_points", "solve_intrinsics"]


def solve_intrinsics(solve):
    W, H = solve["resolution"]
    f_px = solve["focal_px"]
    cx, cy = solve.get("principal_px", (W / 2, H / 2))
    sensor = 36.0
    lens = f_px / W * sensor
    m = max(W, H)
    shift_x = (W / 2 - cx) / m
    shift_y = (cy - H / 2) / m
    return dict(lens=lens, sensor=sensor, shift_x=shift_x, shift_y=shift_y, W=W, H=H)


def _cam_rotation(yaw, pitch, roll):
    # Blender camera looks down its local -Z with +Y up.  Rx(90) makes it look
    # along world +Y; then pitch (about local X), roll (about view axis), yaw (Z).
    R = (Matrix.Rotation(math.radians(yaw), 4, "Z")
         @ Matrix.Rotation(math.radians(pitch), 4, "X")
         @ Matrix.Rotation(math.radians(90.0), 4, "X")
         @ Matrix.Rotation(math.radians(-roll), 4, "Z"))
    return R


def camera_from_solve(name, solve, parent_matrix=None, collection=None, set_active=True,
                      clip=(0.05, 20000.0)):
    intr = solve_intrinsics(solve)
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = intr["sensor"]
    cam.lens = intr["lens"]
    cam.shift_x = intr["shift_x"]
    cam.shift_y = intr["shift_y"]
    cam.clip_start, cam.clip_end = clip
    ob = bpy.data.objects.new(name, cam)
    (collection or bpy.context.scene.collection).objects.link(ob)
    local = (Matrix.Translation(Vector(solve["location"]))
             @ _cam_rotation(solve.get("yaw_deg", 0.0), solve.get("pitch_deg", 0.0),
                             solve.get("roll_deg", 0.0)))
    ob.matrix_world = (parent_matrix or Matrix.Identity(4)) @ local
    if set_active:
        sc = bpy.context.scene
        sc.camera = ob
        sc.render.resolution_x = intr["W"]
        sc.render.resolution_y = intr["H"]
        sc.render.resolution_percentage = 100
        sc.render.pixel_aspect_x = sc.render.pixel_aspect_y = 1.0
    return ob


def look_camera(name, location, target, lens=28.0, collection=None, shift=(0.0, 0.0),
                set_active=False):
    """Free camera looking at ``target`` (for alternate views / validation)."""
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = 36.0
    cam.shift_x, cam.shift_y = shift
    cam.clip_start, cam.clip_end = 0.05, 20000.0
    ob = bpy.data.objects.new(name, cam)
    (collection or bpy.context.scene.collection).objects.link(ob)
    ob.location = Vector(location)
    d = Vector(target) - Vector(location)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if set_active:
        bpy.context.scene.camera = ob
    return ob


def project_points(cam_obj, points_world, scene=None):
    """Project world points to pixel coordinates (x right, y down) of the
    scene's render resolution.  Returns list of (u, v, depth)."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = scene or bpy.context.scene
    W = sc.render.resolution_x * sc.render.resolution_percentage / 100.0
    H = sc.render.resolution_y * sc.render.resolution_percentage / 100.0
    out = []
    for p in points_world:
        v = world_to_camera_view(sc, cam_obj, Vector(p))
        out.append((v.x * W, (1.0 - v.y) * H, v.z))
    return out
