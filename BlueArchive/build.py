"""
BlueArchive scene builder -- command line entry point.

Run with Blender (any 4.2+ build):

    blender -b -P BlueArchive/build.py -- Millennium/Rooms/ClubRoom --shot BG_Milleniumclub \
        --render out.png --samples 160 --save ClubRoom.blend

or with the ``bpy`` Python module:

    python BlueArchive/build.py Millennium/Rooms/ClubRoom --shot BG_Milleniumclub --render out.png

Arguments
---------
room                 room folder relative to BlueArchive/ (contains room.json)
--shot NAME          shot file in <room>/shots/NAME.json (camera solve, sky, sun, look)
--render PATH        render the shot camera to PATH (png)
--view NAME          render an alternate camera defined in the shot's "views"
--samples N          override Cycles samples
--scale S            resolution scale (e.g. 0.5 for previews)
--save PATH          save the built scene as .blend
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from Core import scene as SC, camera as CAM, render as RND  # noqa: E402


def parse(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    ap = argparse.ArgumentParser(description="Build a BlueArchive procedural scene")
    ap.add_argument("room")
    ap.add_argument("--shot", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--view", default=None)
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--save", default=None)
    ap.add_argument("--standalone", action="store_true")
    ap.add_argument("--no-city", action="store_true")
    ap.add_argument("--no-halo", action="store_true")
    ap.add_argument("--no-look", action="store_true")
    return ap.parse_args(argv)


def academy_of(room_rel):
    return room_rel.replace("\\", "/").split("/")[0]


def build(args):
    room_dir = os.path.join(HERE, args.room)
    academy = academy_of(args.room)
    mod = __import__(academy, fromlist=["rooms", "Kit"])
    __import__(f"{academy}.Kit")
    rooms = __import__(f"{academy}.rooms", fromlist=["build_room", "load_room"])
    from Kivotos import sky as KS

    sc = SC.reset_scene()
    room_def = rooms.load_room(room_dir)
    shot = {}
    if args.shot:
        with open(os.path.join(room_dir, "shots", f"{args.shot}.json"), encoding="utf-8") as f:
            shot = json.load(f)

    # ---- shot-level look parameters must be known before materials are built
    kit_mats = __import__(f"{academy}.Kit.materials", fromlist=["PARAMS"])
    kit_mats.PARAMS.clear()
    kit_mats.PARAMS.update(shot.get("materials", {}))

    # ---- exterior + room placement
    if args.standalone:
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
    exposure = r.get("exposure", 0.0)
    if not args.no_look and shot.get("look"):
        # exposure goes into the compositor *before* the grade, so the grade
        # sees exactly the values it was fitted on
        look = dict(shot["look"])
        look["exposure"] = look.get("exposure", 0.0) + exposure
        RND.color_management(r.get("view", "AgX"), r.get("look"), 0.0)
        RND.compositor(look)
        if look.get("lines"):
            cfg = dict(look["lines"])
            cfg.setdefault("collections", [f"ROOM_{room_def['id']}"])
            RND.lines(cfg)
    else:
        RND.color_management(r.get("view", "AgX"), r.get("look"), exposure)
    if args.scale or r.get("scale"):
        sc.render.resolution_percentage = int(round(100 * (args.scale or r.get("scale", 1.0))))
    if args.view:
        vcam = bpy.data.objects[f"VIEW_{args.view}"]
        sc.camera = vcam
        v = shot["views"][args.view]
        if "resolution" in v:
            sc.render.resolution_x, sc.render.resolution_y = v["resolution"]
    return dict(scene=sc, room=rb, camera=cam, room_matrix=M_room, shot=shot)


def main(argv=None):
    args = parse(argv or sys.argv)
    ctx = build(args)
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save), compress=True)
    if args.render:
        RND.render_still(os.path.abspath(args.render), use_compositor=not args.no_look)
    return ctx


if __name__ == "__main__":
    main()
