"""
Core.film -- the build driver of a film: sets, a cast and the shots of a
reference video, rebuilt shot by shot.

A film item is a folder with ``film.json``, pure data::

    {"id": "LaPluma",
     "fps": 30, "resolution": [1920, 1080],
     "frames": [0, 724],                        (the reference video's frames the film covers)
     "reference": {"video": {"environment": "LAPLUMA_REFERENCE"},
                   "masks": [[x0, y0, x1, y1], ...]},   (pixels left out of every comparison)
     "cast": {"LaPluma": {...}},                (Core.cast entries)
     "sets": ["District", ...],                 (sets/<name>.json)
     "shots": ["Breakout", ...],                (shots/<name>.json, in the order they are cut)
     "holds": [208, ...],                       (frames that repeat the frame before them)
     "audio": {"environment": "LAPLUMA_MUSIC", "offset": 1.62}}   (optional: the soundtrack)

Frame numbers are the reference video's own, so a render of frame ``f`` is
compared with frame ``f`` of the reference.  Every shot covers ``frames``
[first, last] of the film; ``holds`` are the reference's repeated frames --
its cadence -- and are never rendered: the edit shows the frame before.

The family's interpreter (``<family>.scenes.build_film(folder, film,
args)``) builds the sets, the cast and one Blender scene per shot and
returns ``{"shots": {id: {"scene", "frames", "camera", "set", "cast", "performers", "overlays"}}}``
(the set's and the cast's collections, the rigs that perform in it, the scenes of the shot's overlays that its
picture carries -- the lowest layer first, each with a camera of its own); this module owns
everything around it: the command line, saving, rendering each shot's
frames into a folder of its own (a shot's frames survive interruption and
are kept apart by the inputs they were made with; rendering a shot anew
removes its frames made with other inputs, so one rendering of it is kept),
and two scenes that cut the shots in film order, each hold showing the frame before it:
``Film``, whose sequencer cuts the rendered frames into the video, and ``Preview``, the same
cut made of the shots' own scenes seen through their cameras -- the timeline of a saved film
plays the whole film from its first frame, every cut and hold where the video has them, with
what the cast does in the shots as it stands (:func:`preview_scene`).  The soundtrack is a sound
file of its owner's named by an environment variable (as the cast's files
are), never part of the project; the film's frame 0 plays it from
``offset`` seconds in.

Command line (after ``--``)::

    <family>/<item>              the film folder, relative to the world's folder
    --shots A,B                  build (and render) only these shots
    --render-shots               render the frames still missing of the shots
    --frames A-B                 only frames A..B of them
    --frame N --render PATH      a still of frame N
    --frame N --inspect PATH     frame N's cast seen through the shot's camera and from
                                 around it (right, back, left, above) without the set:
                                 a pose fitted from one view checked from the others
    --video                      cut the rendered frames into the video
    --scale S --samples N        preview size and quality
    --no-look                    leave every compositor look out
    --no-grade                   keep the looks but leave out their grades (the
                                 picture a grade is fitted on)
    --cast NAME=PATH             the .blend of a cast member (else its environment variable)
    --out PATH / --no-save       where the .blend goes / do not save it
    --project DIR                save it as a project of its own instead (Core.project): DIR/<film id>_Film.blend
                                 with its soundtrack in the cut and every file it reads from outside in DIR/Data,
                                 after what is rendered (the cut's frames are copied: with --render-shots)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import os
import shutil
import sys

import bpy

from . import jsonio

__all__ = ["is_film", "target", "parse", "film_frames", "run"]

FILM = "film.json"


def is_film(folder):
    return os.path.isfile(os.path.join(folder, FILM))


def target(argv, default):
    """The item folder named on the command line ``argv`` (the build
    script's own arguments), or ``default``."""
    for value in argv:
        if not value.startswith("-"):
            return value
        break
    return default


def _frame_range(text):
    first, _, last = text.partition("-")
    return int(first), int(last or first)


def parse(argv):
    parser = argparse.ArgumentParser(description="Build, render and cut a film")
    parser.add_argument("film")
    parser.add_argument("--shots", default=None)
    parser.add_argument("--render-shots", action="store_true")
    parser.add_argument("--frames", type=_frame_range, default=None)
    parser.add_argument("--frame", type=int, default=None)
    parser.add_argument("--render", default=None)
    parser.add_argument("--inspect", default=None)
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--scale", type=float, default=None)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--no-look", action="store_true")
    parser.add_argument("--no-grade", action="store_true")
    parser.add_argument("--cast", action="append", default=[])
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(argv)
    args.cast = dict(entry.split("=", 1) for entry in args.cast)
    args.shots = [name for name in args.shots.split(",") if name] if args.shots else None
    return args


def film_frames(film):
    first, last = film["frames"]
    return first, last


def _digest(paths, extra):
    digest = hashlib.sha256(f"{bpy.app.version_string} {bpy.app.build_hash.decode()}".encode())
    for text in extra:
        digest.update(text.encode())
    for path in sorted(paths):
        digest.update(os.path.basename(path).encode())
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()


def _code_files(root):
    return {os.path.abspath(module.__file__) for module in list(sys.modules.values())
            if getattr(module, "__file__", None) and os.path.abspath(module.__file__).startswith(root + os.sep)}


def shot_fingerprint(shot, root, script_path, args, cast_digests):
    """Identity of everything a shot's frames depend on: the Blender build,
    the options that change the picture, the project's code, the data files
    the shot was built from and the content of every cast member's file."""
    options = [f"scale={args.scale}", f"samples={args.samples}", f"look={not args.no_look}", f"grade={not args.no_grade}"]
    files = _code_files(root) | {os.path.abspath(script_path)} | set(shot["sources"])
    return _digest(files, options + sorted(cast_digests))[:16]


def _runs(frames, holds):
    """Contiguous runs of the frames to render (holds left out)."""
    runs = []
    for frame in frames:
        if frame in holds:
            continue
        if runs and runs[-1][1] == frame - 1:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame])
    return runs


def _shown(frame, holds):
    """The rendered frame the edit shows at ``frame``."""
    while frame in holds:
        frame -= 1
    return frame


def present(scene, frame=None):
    """Make ``scene`` the window's scene, then go to ``frame``: the render operator renders the
    scene it is given at the frame of the window's scene, whatever frame that one was put on."""
    bpy.context.window.scene = scene
    if frame is not None:
        scene.frame_set(frame)


def working_scene(preview):
    """The scene a saved film opens on: the ``Preview`` cut at its first frame, its timeline the whole film and the
    window's big area the sequencer's strips and preview -- Space plays the film as the video cuts it.  A shot to work on is
    a scene away in the scene list, in a workspace with a 3D viewport (the sequencer keeps showing the cut: it reads the
    workspace's sequencer scene, not the window's), and every 3D viewport is a material preview that lights by the scenes'
    own lamps and worlds.  (The ``Film`` scene only cuts rendered frames: opened on it the file shows nothing to work on.)"""
    present(preview, preview.frame_start)
    if bpy.app.background:
        _preview_layout(bpy.context.window, preview)


def _preview_layout(window, preview):
    """Put the window of a saved film so that it opens ready to play: the biggest 3D viewport of its screen the sequencer's
    strips and preview, every workspace's sequencer reading the ``preview`` cut, and every 3D viewport of the file a material
    preview of the scenes' own lamps and worlds (what the render lights with, not a studio light).  Only a saved file's
    layout is put so: a build run from the Blender UI leaves the user's own windows as they are."""
    viewports = [area for area in window.screen.areas if area.type == "VIEW_3D"]
    if viewports:
        cut = max(viewports, key=lambda area: area.width * area.height)
        cut.type = "SEQUENCE_EDITOR"
        cut.spaces.active.view_type = "SEQUENCER_PREVIEW"
    for workspace in bpy.data.workspaces:
        workspace.sequencer_scene = preview
        for each in workspace.screens:
            for area in each.areas:
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "MATERIAL"
                        space.shading.use_scene_lights = space.shading.use_scene_world = True
                        space.shading.use_scene_lights_render = space.shading.use_scene_world_render = True


def prune_renderings(folder):
    """Remove the shot's frames made with other inputs than ``folder``'s (its siblings)."""
    parent = os.path.dirname(folder)
    if not os.path.isdir(parent):
        return
    for name in os.listdir(parent):
        other = os.path.join(parent, name)
        if os.path.isdir(other) and os.path.normcase(other) != os.path.normcase(folder):
            shutil.rmtree(other)
            print(f"[film] removed the frames of other inputs {other}")


def _live_cloth(scene):
    """The call that writes the cloth's solved pose into the rigs of ``scene``, or None where no rig simulates live there:
    the RuriClothPhysics add-on solves a frame in the frame change and writes it at the start of the next, so a script
    that sets frames reads the pose of the frame it set only after this."""
    try:
        from RuriClothPhysics.blender_host import runtime, world
    except ImportError:
        return None
    if not world.live_bodies(scene):
        return None
    return lambda: runtime.flush_pose_writes(None)


def play_to(shot, frame):
    """Put the shot's scene on ``frame`` after playing it from its first frame, a frame at a time: live cloth is the state the
    frames before it left, and a script that jumps to a frame sees the cloth of no play."""
    scene = shot["scene"]
    present(scene)
    flush = _live_cloth(scene)
    if flush is None:
        scene.frame_set(frame)
        return
    for current in range(shot["frames"][0], frame + 1):
        scene.frame_set(current)
        flush()


def render_shot(shot, folder, holds, frames=None):
    """Render the frames of ``shot`` that are not on disk yet into
    ``folder`` (``<id>_####.png``), skipping holds.  Where the cast's cloth simulates live the shot is played
    from its first frame a frame at a time and each frame wanted is rendered as it is reached (the cloth is
    solved in the frame change of the scene the window shows, never in a render's own): the frames wanted are
    the same, and none is rendered with the cloth of another play."""
    from . import render as RND
    scene = shot["scene"]
    present(scene)
    first, last = shot["frames"]
    if frames is not None:
        first, last = max(first, frames[0]), min(last, frames[1])
    if first > last:
        return 0
    os.makedirs(folder, exist_ok=True)
    prefix = os.path.join(folder, f"{shot['id']}_")
    scene.render.filepath = prefix
    scene.render.use_overwrite = False
    scene.render.use_placeholder = False
    image = RND._output_kind("IMAGE", scene)
    image.file_format = "PNG"
    image.color_depth = "8"
    flush = _live_cloth(scene)
    live = flush is not None
    count = 0
    wanted = []
    for start, end in _runs(range(first, last + 1), holds):
        scene.frame_start, scene.frame_end = start, end
        missing = RND.unfinished_frames(scene)
        if not missing:
            continue
        if live:
            wanted += missing
            count += len(missing)
            continue
        scene.frame_start, scene.frame_end = missing[0], end
        bpy.ops.render.render(animation=True, scene=scene.name)
        count += len(missing)
    scene.frame_start, scene.frame_end = shot["frames"]
    if wanted:
        needed = set(wanted)
        for current in range(shot["frames"][0], max(wanted) + 1):
            scene.frame_set(current)
            flush()
            if current in needed:
                scene.render.filepath = os.path.join(folder, f"{shot['id']}_{current:04d}")
                bpy.ops.render.render(write_still=True, scene=scene.name)
        scene.render.filepath = prefix
    return count


INSPECTION_VIEWS = (("right", 90.0, 0.0), ("back", 180.0, 0.0), ("left", 270.0, 0.0), ("above", 0.0, 80.0))


def inspect_cast(shot, frame, path):
    """Render frame ``frame`` of ``shot`` through its camera, then from around the cast
    (the views orbit the cast's skeletons from the shot camera's side, framing their
    posed bones -- the bodies, not the reach of what they hold) with the set left out,
    each a PNG next to ``path`` (``<path>_<view>.png``).  Returns the files written."""
    import math

    from mathutils import Matrix, Vector

    from . import render as RND
    scene = shot["scene"]
    play_to(shot, frame)
    RND._output_kind("IMAGE", scene).file_format = "PNG"
    stem = os.path.splitext(os.path.abspath(path))[0]
    written = [f"{stem}_shot.png"]
    scene.render.filepath = written[0]
    bpy.ops.render.render(write_still=True, scene=scene.name)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    corners = [rig.evaluated_get(depsgraph).matrix_world @ end
               for rig in shot["cast"].all_objects if rig.type == "ARMATURE"
               for bone in rig.evaluated_get(depsgraph).pose.bones for end in (bone.head, bone.tail)]
    low = Vector([min(corner[axis] for corner in corners) for axis in range(3)])
    high = Vector([max(corner[axis] for corner in corners) for axis in range(3)])
    centre = (low + high) / 2.0
    radius = max((corner - centre).length for corner in corners) * 1.15
    shot_camera = shot["camera"]
    toward = centre - shot_camera.matrix_world.translation
    heading = math.atan2(toward.y, toward.x)
    data = bpy.data.cameras.new("Inspection")
    data.lens = 50.0
    data.clip_start, data.clip_end = 0.01, radius * 20.0
    viewer = bpy.data.objects.new("Inspection", data)
    scene.collection.objects.link(viewer)
    layer = scene.view_layers[0].layer_collection
    set_layer = next(child for child in layer.children if child.collection == shot["set"])
    excluded = set_layer.exclude
    set_layer.exclude = True
    narrow = min(scene.render.resolution_x, scene.render.resolution_y) / max(scene.render.resolution_x, scene.render.resolution_y)
    distance = radius / math.sin(math.atan(math.tan(data.angle / 2.0) * narrow))
    for name, azimuth, elevation in INSPECTION_VIEWS:
        angle = heading + math.pi + math.radians(azimuth)
        lift = math.radians(elevation)
        offset = Vector((math.cos(angle) * math.cos(lift), math.sin(angle) * math.cos(lift), math.sin(lift))) * distance
        viewer.location = centre + offset
        viewer.rotation_euler = (-offset).to_track_quat("-Z", "Y").to_euler()
        scene.camera = viewer
        written.append(f"{stem}_{name}.png")
        scene.render.filepath = written[-1]
        bpy.ops.render.render(write_still=True, scene=scene.name)
    scene.camera = shot_camera
    set_layer.exclude = excluded
    bpy.data.objects.remove(viewer)
    bpy.data.cameras.remove(data)
    return written


def soundtrack(film):
    """The film's soundtrack file (``film["audio"]``: an environment variable naming it), or None without one."""
    audio = film.get("audio")
    if not audio:
        return None
    path = os.environ.get(audio["environment"])
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"soundtrack: set the environment variable {audio['environment']} to the film's sound file")
    return os.path.abspath(path)


def _cut_scene(film, name):
    """Scene ``name`` made a cut of the film: its size, rate and frames, the Standard view (what a cut lays is
    display-referred already), the sequencer on and the compositor off, no strips yet.  Returns it and its strips."""
    first, last = film_frames(film)
    cut = bpy.data.scenes.get(name) or bpy.data.scenes.new(name)
    cut.render.resolution_x, cut.render.resolution_y = film["resolution"]
    cut.render.resolution_percentage = 100
    cut.render.fps, cut.render.fps_base = film["fps"], 1.0
    cut.frame_start, cut.frame_end = first, last
    cut.view_settings.view_transform = "Standard"
    cut.view_settings.look = "None"
    cut.display_settings.display_device = "sRGB"
    cut.render.use_sequencer = True
    cut.render.use_compositing = False
    sequences = cut.sequence_editor_create()
    for strip in list(sequences.strips):
        sequences.strips.remove(strip)
    return cut, sequences


def _cut_soundtrack(sequences, film, music, channel):
    """The soundtrack ``music`` on ``channel``: the film's first frame plays it from ``audio.offset`` seconds in."""
    first, last = film_frames(film)
    offset = int(round(film["audio"]["offset"] * film["fps"]))
    sound = sequences.strips.new_sound("Soundtrack", music, channel=channel, frame_start=first - offset)
    sound.left_handle = first
    sound.right_handle = last + 1


def _cut_video(cut, film, music):
    """``cut``'s output made the film's video: H.264 in an MP4, with the soundtrack's AAC when ``music`` is one."""
    from . import render as RND
    image = RND._output_kind("VIDEO", cut)
    image.file_format = "FFMPEG"
    ffmpeg = cut.render.ffmpeg
    ffmpeg.format = "MPEG4"
    ffmpeg.codec = "H264"
    for attribute, value in (("constant_rate_factor", "HIGH"), ("ffmpeg_preset", "GOOD"),
                             ("audio_codec", "AAC" if music is not None else "NONE"), ("audio_bitrate", 256), ("gopsize", film["fps"])):
        try:
            setattr(ffmpeg, attribute, value)
        except (AttributeError, TypeError):
            pass


def edit_scene(film, shots, folders, music=None, name="Film"):
    """The ``Film`` scene: a sequencer cut of every shot's frames in film
    order, each hold showing the frame before it, over the soundtrack
    ``music`` (the file :func:`soundtrack` names, for the video); rendering
    it writes the video."""
    holds = set(film.get("holds", ()))
    edit, sequences = _cut_scene(film, name)
    for shot_id, shot in shots.items():
        start, end = shot["frames"]
        prefix = os.path.join(folders[shot_id], f"{shot_id}_")
        files = [f"{os.path.basename(prefix)}{_shown(frame, holds):04d}.png" for frame in range(start, end + 1)]
        strip = sequences.strips.new_image(shot_id, os.path.join(folders[shot_id], files[0]), channel=1, frame_start=start)
        for file in files[1:]:
            strip.elements.append(file)
        strip.colorspace_settings.name = "sRGB"
    if music is not None:
        _cut_soundtrack(sequences, film, music, channel=2)
    _cut_video(edit, film, music)
    return edit


SCRATCH_CHANNEL = 127


def _scene_strips(sequences, name, scene, camera, channel, holds, over=False):
    """``scene`` seen through ``camera`` over its own frames on ``channel`` -- its frame f at the timeline's frame f, a hold
    frame showing the frame before it (:func:`_shown`): strips of the runs between the holds and a strip of each hold
    frame, none over another, so what a hold frame shows is the held frame alone, its transparency too.  ``over`` lays the
    picture over what is below it by its alpha: an overlay."""
    first, last = scene.frame_start, scene.frame_end

    def piece(label, start, end, shown):
        strip = sequences.strips.new_scene(label, scene, channel=SCRATCH_CHANNEL, frame_start=start - (shown - first))
        strip.left_handle, strip.right_handle = start, end + 1
        strip.channel = channel
        strip.scene_camera = camera
        strip.blend_type = "ALPHA_OVER" if over else "REPLACE"

    run = None
    for frame in range(first, last + 2):
        hold = frame <= last and frame in holds
        if run is not None and (hold or frame > last):
            piece(f"{name} {run}-{frame - 1}", run, frame - 1, run)
            run = None
        if hold:
            shown = _shown(frame, holds)
            if shown < first:
                raise ValueError(f"{name}: hold frame {frame} repeats frame {shown}, before the scene's first frame {first}")
            piece(f"{name} Hold {frame}", frame, frame, shown)
        elif run is None and frame <= last:
            run = frame


PREVIEW = "Preview"
PREVIEW_PERCENTAGE = 50


def preview_scene(film, shots, music=None, name=PREVIEW):
    """The ``Preview`` scene: the cut :func:`edit_scene` makes -- the shots in film order, each hold showing the frame
    before it, the same soundtrack -- with every picture the shot's own scene seen through its camera (a sequencer scene
    strip) instead of a rendered frame.  Its timeline plays the whole film from the first frame, every cut and hold where the
    video has them, and what is changed in a shot shows in it at once; a marker stands on the first frame of every shot.
    The overlays of a shot lie over its picture on the channels above the shots', layer by layer.

    What the render adds in the compositor -- the look and its grade, the underlays that only a depth test can place -- is
    not in it, and its picture is the material preview at ``PREVIEW_PERCENTAGE`` of the film's size (the sequencer's shading
    menu has the rendered picture of a strip: the scene as the render draws it, slowly)."""
    holds = set(film.get("holds", ()))
    preview, sequences = _cut_scene(film, name)
    preview.render.resolution_percentage = PREVIEW_PERCENTAGE
    preview.render.sequencer_gl_preview = "MATERIAL"
    for shot_id, shot in shots.items():
        _scene_strips(sequences, shot_id, shot["scene"], shot["camera"], 1, holds)
        preview.timeline_markers.new(shot_id, frame=shot["frames"][0])
    channel = 2
    for layer in range(max((len(shot.get("overlays", ())) for shot in shots.values()), default=0)):
        for shot_id, shot in shots.items():
            if layer < len(shot.get("overlays", ())):
                overlay = shot["overlays"][layer]
                _scene_strips(sequences, f"{shot_id} Overlays {layer}", overlay, overlay.camera, channel, holds, over=True)
        channel += 1
    if music is not None:
        _cut_soundtrack(sequences, film, music, channel)
    _cut_video(preview, film, music)
    preview.sync_mode = "AUDIO_SYNC" if music is not None else "FRAME_DROP"
    return preview


def run(here, root, script_path, argv=None):
    """Build the film named on the command line, save it, render what was
    asked for.  Returns the interpreter's production dict."""
    from . import cast as CAST, render as RND, scene as SC
    from .driver import script_args
    args = parse(script_args(sys.argv) if argv is None else argv)
    folder = os.path.join(here, args.film)
    film = jsonio.load(os.path.join(folder, FILM))
    package = args.film.replace("\\", "/").split("/")[0]
    interpreter = importlib.import_module(f"{package}.scenes")
    SC.reset_scene()
    production = interpreter.build_film(folder, film, args)
    shots = production["shots"]
    item = os.path.basename(args.film.rstrip("/\\"))
    build_dir = os.path.join(root, "Build", package, item)
    cast_digests = [CAST.blend_digest(path) for path in production.get("cast_files", ())]
    folders = {shot_id: os.path.join(build_dir, "frames", shot_id, shot_fingerprint(shot, root, script_path, args, cast_digests))
               for shot_id, shot in shots.items()}
    music = soundtrack(film) if args.video or args.project else None
    edit = edit_scene(film, shots, folders, music)
    preview = preview_scene(film, shots, music)
    video = os.path.join(build_dir, "video", f"{film['id']}.mp4")
    edit.render.filepath = video
    preview.render.filepath = f"//{film['id']}_Preview.mp4"
    out = os.path.abspath(args.out or os.path.join(build_dir, f"{item}.blend"))
    if not args.no_save and not args.project:
        working_scene(preview)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
        print(f"[film] saved {out}")
    holds = set(film.get("holds", ()))
    if args.render_shots:
        for shot_id, shot in shots.items():
            prune_renderings(folders[shot_id])
            count = render_shot(shot, folders[shot_id], holds, args.frames)
            print(f"[film] {shot_id}: rendered {count} frames into {folders[shot_id]}")
    if args.frame is not None and (args.render or args.inspect):
        shot = next((shot for shot in shots.values() if shot["frames"][0] <= args.frame <= shot["frames"][1]), None)
        if shot is None:
            raise ValueError(f"frame {args.frame} lies in none of the built shots {list(shots)}")
    if args.frame is not None and args.inspect:
        for written in inspect_cast(shot, args.frame, args.inspect):
            print(f"[film] inspection of frame {args.frame} -> {written}")
    if args.frame is not None and args.render:
        scene = shot["scene"]
        play_to(shot, args.frame)
        scene.render.filepath = os.path.abspath(args.render)
        RND._output_kind("IMAGE", scene).file_format = "PNG"
        bpy.ops.render.render(write_still=True, scene=scene.name)
        print(f"[film] frame {args.frame} of {shot['id']} -> {args.render}")
    if args.video:
        missing = [shot_id for shot_id, shot in shots.items()
                   for frame in range(shot["frames"][0], shot["frames"][1] + 1)
                   if frame not in holds and not os.path.isfile(os.path.join(folders[shot_id], f"{shot_id}_{frame:04d}.png"))]
        if missing:
            raise RuntimeError(f"cannot cut the video: frames missing in {sorted(set(missing))}")
        os.makedirs(os.path.dirname(video), exist_ok=True)
        present(edit)
        bpy.ops.render.render(animation=True, scene=edit.name)
        print(f"[film] video -> {video}")
    if args.project:
        from . import project
        working_scene(preview)
        project.export(args.project, f"{film['id']}_Film", production.get("cast_files", ()))
    return production
