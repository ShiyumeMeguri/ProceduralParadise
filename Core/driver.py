"""
Core.driver -- the build driver every world's ``build.py`` shares.

A world's build script knows how to assemble its own scenes (academies and
rooms, realms and scenes ...).  Everything around that lives here once:
reading the command line, the shot's cameras, render settings and
compositor look, the showcase camera animation, the fingerprint that keeps
animation frames of different inputs apart, and the save / render / video
flow of :func:`run`.

A build script calls, in order::

    args = driver.parse(parser, argv)          # parser from base_parser()
    ... reset the scene, build the world ...
    shot_camera = driver.shot_cameras(shot, matrix)
    look = driver.render_setup(shot, args)
    animation = driver.build_animation(folder, name, shot, matrix, look)
    driver.run(context, args, out, root, script_path)

``context`` is a dict with at least ``scene``, ``shot``, ``shot_camera``,
``animation`` (or None) and the keys returned by :func:`render_setup`.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import sys

import bpy
from mathutils import Vector

__all__ = ["fresh_modules", "script_args", "base_parser", "parse", "fingerprint", "shot_cameras",
           "render_setup", "build_animation", "build_scene_folder", "activate_animation", "activate_still",
           "viewport_through_camera", "run"]

OUTPUT_OPTIONS = {"out", "no_save", "render", "view", "render_animation"}


def fresh_modules(root):
    """A Blender session keeps imported modules between script runs; drop the
    project's modules so every run builds with the code that is on disk."""
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None) or ""
        if name != "__main__" and path and os.path.abspath(path).startswith(root + os.sep):
            del sys.modules[name]


def script_args(argv, script_name="build.py"):
    """Arguments meant for the build script: everything after ``--``; for a
    plain ``python build.py ...`` run everything after the script; none when
    run from the Blender UI (Blender's own argv is not ours)."""
    if "--" in argv:
        return argv[argv.index("--") + 1:]
    if argv and os.path.basename(argv[0]) == script_name:
        return argv[1:]
    return []


def base_parser(description, target, default_target):
    """Argument parser with the options every world shares; ``target`` names
    the positional scene argument (e.g. ``room``)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(target, nargs="?", default=default_target)
    parser.add_argument("--shot", default=None)
    parser.add_argument("--animation", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--render", default=None)
    parser.add_argument("--view", default=None)
    parser.add_argument("--render-animation", nargs="?", const="", default=None)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--scale", type=float, default=None)
    parser.add_argument("--no-look", action="store_true")
    return parser


def parse(parser, argv=None, script_name="build.py"):
    """``argv=None``: the script's own command line; an explicit list is read
    like ``sys.argv`` of a plain Python run (program name first)."""
    if argv is None:
        argv = script_args(sys.argv, script_name)
    elif "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def fingerprint(args, root, script_path):
    """Identity of everything an animation's frames depend on: the Blender
    build, every option that changes the picture, and the content of each
    project module and JSON file the build loaded."""
    from . import jsonio
    digest = hashlib.sha256(f"{bpy.app.version_string} {bpy.app.build_hash.decode()}".encode())
    for key, value in sorted(vars(args).items()):
        if key not in OUTPUT_OPTIONS:
            digest.update(f"|{key}={value!r}".encode())
    modules = {os.path.abspath(module.__file__) for module in list(sys.modules.values())
               if getattr(module, "__file__", None) and os.path.abspath(module.__file__).startswith(root + os.sep)}
    modules.add(os.path.abspath(script_path))
    for path in sorted(modules | jsonio.LOADED):
        digest.update(os.path.relpath(path, root).encode())
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()


def shot_cameras(shot, matrix):
    """The shot camera ``CAM_<id>`` (from the shot's photogrammetric solve,
    if any) and one free camera ``VIEW_<name>`` per entry of ``views``, all
    placed in the frame ``matrix``.  Returns the shot camera or None."""
    from . import camera as CAM
    camera = None
    if shot.get("camera"):
        camera = CAM.camera_from_solve(f"CAM_{shot['id']}", shot["camera"], parent_matrix=matrix)
    for name, view in (shot.get("views") or {}).items():
        location = matrix @ Vector(view["location"])
        target = matrix @ Vector(view["target"])
        CAM.look_camera(f"VIEW_{name}", location, target, lens=view.get("lens", 24.0))
    return camera


def render_setup(shot, args, lines_defaults=None):
    """Render engine (the shot's ``render.engine``: CYCLES or EEVEE, with its
    settings under ``render.cycles`` / ``render.eevee``), colour management
    and the compositor look of a shot.

    The look's exposure goes into the compositor *before* the grade, so the
    grade sees exactly the values it was fitted on; a view may carry its own
    camera exposure.  ``lines_defaults`` completes a look's ``lines`` entry
    (collections, occluders) for worlds that draw Freestyle ink lines.
    Returns ``dict(engine, compositor, look_exposure, exposure)``."""
    from . import render as RND
    sc = bpy.context.scene
    settings = shot["render"]
    engine = settings["engine"]
    RND.ENGINES[engine](samples=args.samples or settings.get("samples", 128),
                        **settings.get(engine.lower(), {}))
    view = shot["views"][args.view] if args.view else None
    exposure = (view or {}).get("exposure", settings.get("exposure", 0.0))
    compositor = None
    look_exposure = 0.0
    if not args.no_look and shot.get("look"):
        look = dict(shot["look"])
        look_exposure = look.get("exposure", 0.0)
        look["exposure"] = look_exposure + exposure
        RND.color_management(settings.get("view", "AgX"), settings.get("look"), 0.0)
        lines_layer = None
        ink_layer = None
        if not getattr(args, "no_lines", False):
            if look.get("lines"):
                lines_layer = RND.lines({**(lines_defaults or {}), **look["lines"]})
            ink_layer = RND.ink(look.get("ink"))
        compositor = RND.compositor(look, lines_layer, ink_layer)
    else:
        RND.color_management(settings.get("view", "AgX"), settings.get("look"), exposure)
    if args.scale or settings.get("scale"):
        sc.render.resolution_percentage = int(round(100 * (args.scale or settings.get("scale", 1.0))))
    if view is not None:
        sc.camera = bpy.data.objects[f"VIEW_{args.view}"]
        if "resolution" in view:
            sc.render.resolution_x, sc.render.resolution_y = view["resolution"]
    return dict(engine=engine, compositor=compositor, look_exposure=look_exposure, exposure=exposure)


def build_animation(folder, name, shot, matrix, look):
    """Animated camera from ``<folder>/animations/<name>.json``.  Keys are in
    the frame ``matrix``; ``"camera": "shot"`` starts from the shot camera's
    framing.  A key's ``exposure`` (stops, default: the shot's) is keyed on
    the compositor exposure, ahead of the grade."""
    from . import anim as ANIM, camera as CAM, jsonio
    spec = jsonio.load(os.path.join(folder, "animations", f"{name}.json"))
    exposure = shot.get("render", {}).get("exposure", 0.0)
    keys = []
    for key in spec["keys"]:
        key = dict(key)
        if key.get("camera") == "shot" and shot.get("camera"):
            solve = shot["camera"]
            intrinsics = CAM.solve_intrinsics(solve)
            yaw = solve.get("yaw_deg", 0.0)
            forward = (-math.sin(math.radians(yaw)), math.cos(math.radians(yaw)), 0.0)
            location = solve["location"]
            key.setdefault("location", location)
            key.setdefault("target", [location[i] + 10.0 * forward[i] for i in range(3)])
            key.setdefault("lens", intrinsics["lens"])
            key.setdefault("shift", [intrinsics["shift_x"], intrinsics["shift_y"]])
        keys.append(key)
    extra = []
    compositor = look["compositor"]
    if compositor is not None:
        node = compositor.ng.nodes.get("Exposure")
        if node is not None:
            socket = node.inputs[1]
            values = [look["look_exposure"] + key.get("exposure", exposure) for key in keys]
            extra.append((socket, "default_value", values, compositor.ng))
    camera = ANIM.camera_move(f"CAM_{spec['id']}", keys, parent_matrix=matrix, extra=extra)
    return dict(camera=camera, spec=spec, frame_start=int(min(key["frame"] for key in keys)),
                frame_end=int(max(key["frame"] for key in keys)))


def build_scene_folder(here, args):
    """Build the scene folder ``args.scene`` (relative to ``here``, e.g.
    ``CrystalFantasy/Scenes/Conservatory``) of a world whose first folder is a
    package with a ``Kit`` (registering its assets and its material library
    ``Kit.materials``) and a ``scenes`` interpreter (``load_scene``,
    ``build_scene``).  The scene's ``materials`` fill the library's look
    parameters before anything is built; every shot in ``shots/`` gets its
    camera, the active one (``--shot`` or the scene's ``defaults``) with its
    views, render setup and look; the camera flight (``--animation`` or the
    defaults) is added when there is one.  Returns the context for
    :func:`run`."""
    from mathutils import Matrix
    from . import camera as CAM, jsonio, scene as SC
    scene_dir = os.path.join(here, args.scene)
    package = args.scene.replace("\\", "/").split("/")[0]
    __import__(f"{package}.Kit")
    scenes = __import__(f"{package}.scenes", fromlist=["build_scene", "load_scene"])
    materials = __import__(f"{package}.Kit.materials", fromlist=["PARAMS"])

    sc = SC.reset_scene()
    definition = scenes.load_scene(scene_dir)
    defaults = definition.get("defaults", {})
    materials.PARAMS.clear()
    materials.PARAMS.update(definition.get("materials", {}))
    built = scenes.build_scene(scene_dir)

    shots_dir = os.path.join(scene_dir, "shots")
    active = args.shot or defaults.get("shot")
    identity = Matrix.Identity(4)
    for name in sorted(os.path.splitext(file)[0] for file in os.listdir(shots_dir) if file.endswith(".json")):
        if name != active:
            other = jsonio.load(os.path.join(shots_dir, f"{name}.json"))
            CAM.camera_from_solve(f"CAM_{other['id']}", other["camera"], set_active=False)
    shot = dict(jsonio.load(os.path.join(shots_dir, f"{active}.json")))
    shot["views"] = {**definition.get("views", {}), **shot.get("views", {})}
    camera = shot_cameras(shot, identity)
    look = render_setup(shot, args)

    animation_name = args.animation if args.animation is not None else defaults.get("animation")
    animation = None
    if animation_name and animation_name.lower() != "none":
        animation = build_animation(scene_dir, animation_name, shot, identity, look)
    return dict(scene=sc, built=built, camera=camera, shot=shot, animation=animation, shot_camera=camera, **look)


def activate_animation(context, samples, video, inputs):
    """Make the animation the scene's render: camera, frame range, fps,
    resolution, samples, the PNG frames in ``<video minus extension>/<inputs>/``
    and the ``<Animation> Video`` scene that assembles them into ``video``."""
    from . import render as RND
    sc = context["scene"]
    animation = context["animation"]
    spec = animation["spec"]
    sc.camera = animation["camera"]
    sc.frame_start, sc.frame_end = animation["frame_start"], animation["frame_end"]
    sc.frame_set(animation["frame_start"])
    width, height = spec.get("resolution", (1920, 1080))
    sc.render.resolution_x, sc.render.resolution_y = width, height
    if samples or "samples" in spec:
        RND.set_samples(context["engine"], samples or spec["samples"], sc)
    stem = os.path.splitext(video)[0]
    RND.frame_output(f"{stem}/{inputs}/{bpy.path.basename(stem)}_", fps=spec.get("fps", 30))
    context["video_scene"] = RND.video_scene(video, f"{spec['id']} Video", sc)


def activate_still(context, view_name=None):
    """Still render of the shot camera (at the shot resolution) or of a shot
    view; the camera animation's exposure keys are dropped so the still uses
    its own exposure."""
    sc = context["scene"]
    shot = context["shot"]
    if view_name:
        view = shot["views"][view_name]
        sc.camera = bpy.data.objects[f"VIEW_{view_name}"]
        sc.render.resolution_x, sc.render.resolution_y = view.get("resolution", (1280, 720))
    elif context["shot_camera"] is not None:
        sc.camera = context["shot_camera"]
        sc.render.resolution_x, sc.render.resolution_y = shot["camera"]["resolution"]
    compositor = context.get("compositor")
    if compositor is not None:
        compositor.ng.animation_data_clear()
        node = compositor.ng.nodes.get("Exposure")
        if node is not None:
            node.inputs[1].default_value = context["look_exposure"] + context["exposure"]


def viewport_through_camera():
    """In the UI, look through the scene camera in every 3D viewport."""
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else ()):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.region_3d.view_perspective = "CAMERA"


def run(context, args, out, root, script_path):
    """Everything after the build: the animation's frame folder and video
    scene, GPU selection, saving ``out``, rendering missing animation frames
    and the video, and the still of ``--render``."""
    from . import render as RND
    sc = context["scene"]
    animation = context["animation"]
    if animation is not None:
        video_id = animation["spec"]["id"]
        video = os.path.abspath(args.render_animation) if args.render_animation else \
            os.path.join(os.path.dirname(out), "video", f"{video_id}.mp4")
        in_blend = video if args.render_animation or args.no_save else f"//video/{video_id}.mp4"
        activate_animation(context, args.samples, in_blend, fingerprint(args, root, script_path)[:16])
    if context["engine"] == "CYCLES":
        backend = RND.use_gpu_if_available()
        print(f"[build] Cycles device: {backend or 'CPU'}")
    if not args.no_save:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
        print(f"[build] saved {out}")
    if animation is not None and (not args.no_save or args.render_animation is not None):
        missing = RND.unfinished_frames(sc)
        total = sc.frame_end - sc.frame_start + 1
        frames_dir = os.path.dirname(RND.frame_paths(sc)[sc.frame_start])
        print(f"[build] animation frames rendered: {total - len(missing)}/{total} in {frames_dir}")
        if args.render_animation is not None:
            if missing:
                bpy.ops.render.render(animation=True)
                missing = RND.unfinished_frames(sc)
                if missing:
                    raise RuntimeError(f"{len(missing)} frames were not rendered, first {missing[0]}")
            bpy.ops.render.render(animation=True, scene=context["video_scene"].name)
            print(f"[build] video -> {video}")
    if args.render:
        activate_still(context, args.view)
        RND.render_still(os.path.abspath(args.render), use_compositor=not args.no_look)
    if not bpy.app.background:
        viewport_through_camera()
    return context
