"""
BlueArchive scene builder.

With no arguments it builds the default scene -- the Millennium club room in
its campus, the ``BG_Milleniumclub`` shot camera and the ``Showcase`` camera
animation -- and saves it to the git-ignored ``Build/`` folder
(``Build/Millennium/ClubRoom/ClubRoom.blend``).

* Blender UI: Scripting workspace -> Text Editor -> Open
  ``BlueArchive/build.py`` -> Run Script.  The scene is built in place and
  saved; press Ctrl+F12 to render the showcase video.
* Command line (any Blender 4.2+):

      blender -b -P BlueArchive/build.py
      blender -b -P BlueArchive/build.py -- --render-animation
      blender -b -P BlueArchive/build.py -- Millennium/Rooms/ClubRoom --render still.png

* ``bpy`` Python module:  ``python BlueArchive/build.py [room] [options]``

Arguments (all optional)
------------------------
room                 room folder relative to BlueArchive/ (default Millennium/Rooms/ClubRoom)
--shot NAME          shot in <room>/shots/ (default: room.json "defaults")
--animation NAME     camera animation in <room>/animations/ (default: room.json
                     "defaults"; "none" to skip)
--out PATH           .blend to write (default Build/<Academy>/<Room>/<Room>.blend)
--no-save            do not write the .blend
--render PATH        render the shot camera (the painting's framing) to PATH (png)
--view NAME          render an alternate camera from the shot's "views" instead
--render-animation [PATH]  render the camera animation to PATH
                     (default: <Build folder>/video/<Animation>.mp4)
--samples N          override Cycles samples
--scale S            resolution scale (e.g. 0.5 for previews)
--no-lines           skip the Freestyle ink lines (much faster animation renders)
--standalone         build the room without the campus (own curtain wall, sky only)
--no-city / --no-halo  skip parts of the exterior (faster previews)
--no-look            disable the compositor look
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys


def _locate_here():
    """Folder of this script, however it is run: ``blender -P`` / ``python``
    (real ``__file__``) or Blender's Text Editor (``__file__`` is then a
    pseudo path inside the .blend, but the text data-block knows the file)."""
    f = globals().get("__file__")
    if f and os.path.isfile(f):
        return os.path.dirname(os.path.abspath(f))
    try:
        import bpy
        space = getattr(bpy.context, "space_data", None)
        texts = [getattr(space, "text", None)] + list(bpy.data.texts)
        for t in texts:
            if t is not None and t.filepath:
                p = os.path.abspath(bpy.path.abspath(t.filepath))
                if os.path.basename(p) == "build.py" and os.path.isfile(p):
                    return os.path.dirname(p)
    except ImportError:
        pass
    d = os.getcwd()
    while True:
        for cand in (d, os.path.join(d, "BlueArchive")):
            if os.path.isfile(os.path.join(cand, "build.py")) and \
                    os.path.isdir(os.path.join(cand, "Kivotos")):
                return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    raise RuntimeError("Cannot find BlueArchive/build.py: open the file itself in Blender's "
                       "Text Editor (Text > Open) or run  blender -P BlueArchive/build.py")


HERE = _locate_here()
ROOT = os.path.dirname(HERE)
BUILD_DIR = os.path.join(ROOT, "Build")          # git-ignored output folder
DEFAULT_ROOM = "Millennium/Rooms/ClubRoom"
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402


def _fresh_modules():
    """A Blender session keeps imported modules between script runs; drop this
    project's modules so every run builds with the code that is on disk."""
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        if name != "__main__" and f and os.path.abspath(f).startswith(ROOT + os.sep):
            del sys.modules[name]


def _script_args(argv):
    """Arguments meant for this script: everything after ``--``; for a plain
    ``python build.py ...`` run everything after the script; none when run
    from the Blender UI (Blender's own argv is not ours)."""
    if "--" in argv:
        return argv[argv.index("--") + 1:]
    if argv and os.path.basename(argv[0]) == "build.py":
        return argv[1:]
    return []


def parse(argv=None):
    """``argv=None``: this script's own command line; an explicit list is
    read like ``sys.argv`` of a plain Python run (program name first)."""
    if argv is None:
        argv = _script_args(sys.argv)
    elif "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    ap = argparse.ArgumentParser(description="Build a BlueArchive procedural scene")
    ap.add_argument("room", nargs="?", default=DEFAULT_ROOM)
    ap.add_argument("--shot", default=None)
    ap.add_argument("--animation", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--render", default=None)
    ap.add_argument("--view", default=None)
    ap.add_argument("--render-animation", nargs="?", const="", default=None)
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--no-lines", action="store_true")
    ap.add_argument("--standalone", action="store_true")
    ap.add_argument("--no-city", action="store_true")
    ap.add_argument("--no-halo", action="store_true")
    ap.add_argument("--no-look", action="store_true")
    return ap.parse_args(argv)


def academy_of(room_rel):
    return room_rel.replace("\\", "/").split("/")[0]


def build_dir(room_rel):
    """Git-ignored output folder of a room: Build/<Academy>/<Room>/."""
    parts = room_rel.replace("\\", "/").strip("/").split("/")
    return os.path.join(BUILD_DIR, parts[0], parts[-1])


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build(args):
    from Core import scene as SC, camera as CAM, render as RND
    room_dir = os.path.join(HERE, args.room)
    academy = academy_of(args.room)
    __import__(academy, fromlist=["rooms", "Kit"])
    __import__(f"{academy}.Kit")
    rooms = __import__(f"{academy}.rooms", fromlist=["build_room", "load_room"])
    from Kivotos import sky as KS

    sc = SC.reset_scene()
    room_def = rooms.load_room(room_dir)
    defaults = room_def.get("defaults", {})
    shot_name = args.shot or defaults.get("shot")
    shot = _load_json(os.path.join(room_dir, "shots", f"{shot_name}.json")) if shot_name else {}

    # ---- shot-level look parameters must be known before materials are built
    kit_mats = __import__(f"{academy}.Kit.materials", fromlist=["PARAMS"])
    kit_mats.PARAMS.clear()
    kit_mats.PARAMS.update(shot.get("materials", {}))

    # ---- exterior + room placement (academies without a campus model, or
    # rooms without a placement, are built standalone)
    has_campus = os.path.isdir(os.path.join(HERE, academy, "Campus"))
    if args.standalone or not has_campus or "placement" not in room_def:
        M_room = Matrix.Identity(4)
        rb = rooms.build_room(room_dir, M_room, in_tower=False)
    else:
        campus_mod = __import__(f"{academy}.Campus.campus", fromlist=["build_campus", "room_matrix"])
        campus = campus_mod.load()
        campus_mod.build_campus(campus, city=not args.no_city, halo=not args.no_halo,
                                exterior=shot.get("exterior"))
        M_room = campus_mod.room_matrix(campus, room_def["placement"])
        rb = rooms.build_room(room_dir, M_room, in_tower=True)

    # ---- sky + sun
    KS.build_world(shot.get("sky"))
    sun = shot.get("sun", {"azimuth": 245, "elevation": 38, "strength": 4.0})
    if sun:                                    # "sun": null for night shots
        KS.add_sun(sun["azimuth"], sun["elevation"], sun.get("strength", 4.0),
                   angle_deg=sun.get("angle", 1.5))

    # ---- cameras
    cam = None
    if shot.get("camera"):
        cam = CAM.camera_from_solve(f"CAM_{shot['id']}", shot["camera"], parent_matrix=M_room)
    for name, v in (shot.get("views") or {}).items():
        loc = M_room @ Vector(v["location"])
        tgt = M_room @ Vector(v["target"])
        CAM.look_camera(f"VIEW_{name}", loc, tgt, lens=v.get("lens", 24.0))

    # ---- render settings
    r = shot.get("render", {})
    RND.setup_cycles(samples=args.samples or r.get("samples", 128))
    view = shot["views"][args.view] if args.view else None
    # a view may carry its own camera exposure (e.g. exterior views)
    exposure = (view or {}).get("exposure", r.get("exposure", 0.0))
    comp = None
    look_exposure = 0.0
    if not args.no_look and shot.get("look"):
        # exposure goes into the compositor *before* the grade, so the grade
        # sees exactly the values it was fitted on
        look = dict(shot["look"])
        look_exposure = look.get("exposure", 0.0)
        look["exposure"] = look_exposure + exposure
        RND.color_management(r.get("view", "AgX"), r.get("look"), 0.0)
        comp = RND.compositor(look)
        if look.get("lines") and not args.no_lines:
            cfg = dict(look["lines"])
            cfg.setdefault("collections", [f"ROOM_{room_def['id']}"])
            RND.lines(cfg)
    else:
        RND.color_management(r.get("view", "AgX"), r.get("look"), exposure)
    if args.scale or r.get("scale"):
        sc.render.resolution_percentage = int(round(100 * (args.scale or r.get("scale", 1.0))))
    if view is not None:
        sc.camera = bpy.data.objects[f"VIEW_{args.view}"]
        if "resolution" in view:
            sc.render.resolution_x, sc.render.resolution_y = view["resolution"]

    # ---- camera animation (showcase video)
    anim_name = args.animation if args.animation is not None else defaults.get("animation")
    anim = None
    if anim_name and anim_name.lower() != "none":
        anim = build_animation(room_dir, anim_name, shot, M_room, comp,
                               look_exposure, r.get("exposure", 0.0))
    return dict(scene=sc, room=rb, camera=cam, room_matrix=M_room, shot=shot,
                animation=anim, room_def=room_def, shot_camera=cam, compositor=comp,
                look_exposure=look_exposure, exposure=exposure)


def build_animation(room_dir, name, shot, M_room, comp, look_exposure=0.0, exposure=0.0):
    """Animated camera from <room>/animations/<name>.json.  Keys are in the
    room frame; ``"camera": "shot"`` starts from the painting's framing.  A
    key's ``exposure`` (stops, default: the shot's) is keyed on the
    compositor exposure, ahead of the grade."""
    from Core import anim as ANIM, camera as CAM
    spec = _load_json(os.path.join(room_dir, "animations", f"{name}.json"))
    keys = []
    for k in spec["keys"]:
        k = dict(k)
        if k.get("camera") == "shot" and shot.get("camera"):
            c = shot["camera"]
            intr = CAM.solve_intrinsics(c)
            yaw = c.get("yaw_deg", 0.0)
            fwd = (-math.sin(math.radians(yaw)), math.cos(math.radians(yaw)), 0.0)
            loc = c["location"]
            k.setdefault("location", loc)
            k.setdefault("target", [loc[i] + 10.0 * fwd[i] for i in range(3)])
            k.setdefault("lens", intr["lens"])
            k.setdefault("shift", [intr["shift_x"], intr["shift_y"]])
        keys.append(k)
    extra = []
    if comp is not None:            # always keyed, so the video never inherits a view's exposure
        node = comp.ng.nodes.get("Exposure")
        if node is not None:
            sock = node.inputs[1]
            vals = [look_exposure + k.get("exposure", exposure) for k in keys]
            extra.append((sock, "default_value", vals, comp.ng))
    cam = ANIM.camera_move(f"CAM_{spec['id']}", keys, parent_matrix=M_room, extra=extra)
    return dict(camera=cam, spec=spec, frame_start=int(min(k["frame"] for k in keys)),
                frame_end=int(max(k["frame"] for k in keys)))


def activate_animation(ctx, samples=None):
    """Make the animation the scene's render: camera, frame range, fps,
    resolution, samples and the video output next to the saved .blend."""
    from Core import render as RND
    sc = ctx["scene"]
    a = ctx["animation"]
    spec = a["spec"]
    sc.camera = a["camera"]
    sc.frame_start, sc.frame_end = a["frame_start"], a["frame_end"]
    sc.frame_set(a["frame_start"])
    W, H = spec.get("resolution", (1920, 1080))
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.cycles.samples = samples or spec.get("samples", sc.cycles.samples)
    RND.video_output(f"//video/{spec['id']}_", fps=spec.get("fps", 30))


def activate_still(ctx, view_name=None):
    """Still render of the painting's framing (shot camera, shot resolution)
    or of a shot view; the camera animation's exposure keys are dropped so
    the still uses its own exposure."""
    sc = ctx["scene"]
    shot = ctx["shot"]
    if view_name:
        v = shot["views"][view_name]
        sc.camera = bpy.data.objects[f"VIEW_{view_name}"]
        sc.render.resolution_x, sc.render.resolution_y = v.get("resolution", (1280, 720))
    elif ctx["shot_camera"] is not None:
        sc.camera = ctx["shot_camera"]
        sc.render.resolution_x, sc.render.resolution_y = shot["camera"]["resolution"]
    comp = ctx.get("compositor")
    if comp is not None:
        comp.ng.animation_data_clear()
        node = comp.ng.nodes.get("Exposure")
        if node is not None:
            node.inputs[1].default_value = ctx["look_exposure"] + ctx["exposure"]


def _viewport_through_camera():
    """In the UI, look through the scene camera in every 3D viewport."""
    wm = bpy.context.window_manager
    for win in (wm.windows if wm else ()):
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.region_3d.view_perspective = "CAMERA"


def main(argv=None):
    if __name__ == "__main__":
        _fresh_modules()
    from Core import render as RND
    args = parse(argv)
    ctx = build(args)
    sc = ctx["scene"]
    out = args.out or os.path.join(build_dir(args.room), f"{os.path.basename(args.room.rstrip('/'))}.blend")
    if ctx["animation"] is not None:
        activate_animation(ctx, args.samples)
    backend = RND.use_gpu_if_available()
    print(f"[build] Cycles device: {backend or 'CPU'}")
    if not args.no_save:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out), compress=True)
        print(f"[build] saved {os.path.abspath(out)}")
    if args.render_animation is not None and ctx["animation"] is not None:
        spec = ctx["animation"]["spec"]
        path = args.render_animation or os.path.join(build_dir(args.room), "video", f"{spec['id']}_")
        activate_animation(ctx, args.samples)
        RND.video_output(os.path.abspath(path), fps=spec.get("fps", 30))
        bpy.ops.render.render(animation=True)
        print(f"[build] rendered animation -> {os.path.abspath(path)}")
    if args.render:
        activate_still(ctx, args.view)
        RND.render_still(os.path.abspath(args.render), use_compositor=not args.no_look)
    if not bpy.app.background:
        _viewport_through_camera()
    return ctx


if __name__ == "__main__":
    main()
