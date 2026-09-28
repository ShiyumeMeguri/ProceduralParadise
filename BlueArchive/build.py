"""
BlueArchive scene builder.

With no arguments it builds the default scene -- the Millennium club room in
its campus, the ``BG_Milleniumclub`` shot camera and the ``Showcase`` camera
animation -- and saves it to the git-ignored ``Build/`` folder
(``Build/Millennium/ClubRoom/ClubRoom.blend``).

* Blender UI: Scripting workspace -> Text Editor -> Open
  ``BlueArchive/build.py`` -> Run Script.  The scene is built in place and
  saved; Ctrl+F12 renders the showcase frames (stop it any time, Ctrl+F12
  again carries on), and Ctrl+F12 in the ``<Animation> Video`` scene then
  assembles them into the MP4.
* Command line (any Blender 4.4+):

      blender -b -P BlueArchive/build.py
      blender -b -P BlueArchive/build.py -- --render-animation
      blender -b -P BlueArchive/build.py -- Millennium/Rooms/ClubRoom --render still.png

* ``bpy`` Python module:  ``python BlueArchive/build.py [room] [options]``

Animation frames are a PNG sequence in ``video/<Animation>/<inputs>/`` next
to the video, where ``<inputs>`` identifies everything they depend on: the
Blender build, the options that change the picture and every project module
and JSON file the build loaded.  Frames on disk are never rendered twice,
and frames of other inputs never mix into a sequence -- a changed scene
simply renders into a folder of its own.

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
--render-animation [PATH]  render the camera animation's missing frames and
                     assemble them into the MP4 at PATH
                     (default: <Build folder>/video/<Animation>.mp4)
--samples N          override Cycles samples
--scale S            resolution scale (e.g. 0.5 for previews)
--no-lines           skip the Freestyle ink lines (much faster animation renders)
--standalone         build the room without the campus (own curtain wall, sky only)
--no-city / --no-halo  skip parts of the exterior (faster previews)
--no-look            disable the compositor look
"""
from __future__ import annotations

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

import bpy  # noqa: E402,F401
from mathutils import Matrix  # noqa: E402


def parse(argv=None):
    """``argv=None``: this script's own command line; an explicit list is
    read like ``sys.argv`` of a plain Python run (program name first)."""
    from Core import driver
    parser = driver.base_parser("Build a BlueArchive procedural scene", "room", DEFAULT_ROOM)
    parser.add_argument("--no-lines", action="store_true")
    parser.add_argument("--standalone", action="store_true")
    parser.add_argument("--no-city", action="store_true")
    parser.add_argument("--no-halo", action="store_true")
    return driver.parse(parser, argv)


def academy_of(room_rel):
    return room_rel.replace("\\", "/").split("/")[0]


def build_dir(room_rel):
    """Git-ignored output folder of a room: Build/<Academy>/<Room>/."""
    parts = room_rel.replace("\\", "/").strip("/").split("/")
    return os.path.join(BUILD_DIR, parts[0], parts[-1])


def build(args):
    from Core import driver, jsonio, scene as SC
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
    shot = jsonio.load(os.path.join(room_dir, "shots", f"{shot_name}.json")) if shot_name else {}

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
        occluders = []
    else:
        campus_mod = __import__(f"{academy}.Campus.campus", fromlist=["build_campus", "room_matrix"])
        campus = campus_mod.load()
        towers = campus_mod.build_campus(campus, city=not args.no_city, halo=not args.no_halo,
                                         exterior=shot.get("exterior"))["towers"]
        M_room = campus_mod.room_matrix(campus, room_def["placement"])
        rb = rooms.build_room(room_dir, M_room, in_tower=True)
        occluders = [towers[room_def["placement"]["tower"]].name]

    # ---- sky + sun
    KS.build_world(shot.get("sky"))
    sun = shot.get("sun", {"azimuth": 245, "elevation": 38, "strength": 4.0})
    if sun:                                    # "sun": null for night shots
        KS.add_sun(sun["azimuth"], sun["elevation"], sun.get("strength", 4.0),
                   angle_deg=sun.get("angle", 1.5))

    # ---- cameras, render settings, look (ink lines trace the room itself)
    cam = driver.shot_cameras(shot, M_room)
    look = driver.render_setup(shot, args, {"collections": [f"ROOM_{room_def['id']}"],
                                            "occluders": occluders})

    # ---- camera animation (showcase video)
    anim_name = args.animation if args.animation is not None else defaults.get("animation")
    anim = None
    if anim_name and anim_name.lower() != "none":
        anim = driver.build_animation(room_dir, anim_name, shot, M_room, look)
    return dict(scene=sc, room=rb, camera=cam, room_matrix=M_room, shot=shot,
                animation=anim, room_def=room_def, shot_camera=cam, **look)


def main(argv=None):
    if __name__ == "__main__":
        from Core import driver as stale
        stale.fresh_modules(ROOT)
    from Core import driver
    args = parse(argv)
    ctx = build(args)
    out = os.path.abspath(args.out or os.path.join(build_dir(args.room), f"{os.path.basename(args.room.rstrip('/'))}.blend"))
    return driver.run(ctx, args, out, ROOT, os.path.join(HERE, "build.py"))


if __name__ == "__main__":
    main()
