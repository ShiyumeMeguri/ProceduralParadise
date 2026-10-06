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
     "holds": [208, ...]}                       (frames that repeat the frame before them)

Frame numbers are the reference video's own, so a render of frame ``f`` is
compared with frame ``f`` of the reference.  Every shot covers ``frames``
[first, last] of the film; ``holds`` are the reference's repeated frames --
its cadence -- and are never rendered: the edit shows the frame before.

The family's interpreter (``<family>.scenes.build_film(folder, film,
args)``) builds the sets, the cast and one Blender scene per shot and
returns ``{"shots": {id: {"scene", "frames"}}}``; this module owns
everything around it: the command line, saving, rendering each shot's
frames into a folder of its own (a shot's frames survive interruption and
are kept apart by the inputs they were made with), and the ``Film`` scene
whose sequencer cuts the shots into the video.

Command line (after ``--``)::

    <family>/<item>              the film folder, relative to the world's folder
    --shots A,B                  build (and render) only these shots
    --render-shots               render the frames still missing of the shots
    --frames A-B                 only frames A..B of them
    --frame N --render PATH      a still of frame N
    --video                      cut the rendered frames into the video
    --scale S --samples N        preview size and quality
    --no-look                    leave every compositor look out
    --cast NAME=PATH             the .blend of a cast member (else its environment variable)
    --out PATH / --no-save       where the .blend goes / do not save it
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import os
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
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--scale", type=float, default=None)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--no-look", action="store_true")
    parser.add_argument("--cast", action="append", default=[])
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-save", action="store_true")
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
    options = [f"scale={args.scale}", f"samples={args.samples}", f"look={not args.no_look}"]
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


def render_shot(shot, folder, holds, frames=None):
    """Render the frames of ``shot`` that are not on disk yet into
    ``folder`` (``<id>_####.png``), skipping holds."""
    from . import render as RND
    scene = shot["scene"]
    first, last = shot["frames"]
    if frames is not None:
        first, last = max(first, frames[0]), min(last, frames[1])
    if first > last:
        return 0
    os.makedirs(folder, exist_ok=True)
    scene.render.filepath = os.path.join(folder, f"{shot['id']}_")
    scene.render.use_overwrite = False
    scene.render.use_placeholder = False
    image = RND._output_kind("IMAGE", scene)
    image.file_format = "PNG"
    image.color_depth = "8"
    count = 0
    for start, end in _runs(range(first, last + 1), holds):
        scene.frame_start, scene.frame_end = start, end
        missing = RND.unfinished_frames(scene)
        if not missing:
            continue
        scene.frame_start, scene.frame_end = missing[0], end
        bpy.ops.render.render(animation=True, scene=scene.name)
        count += len(missing)
    scene.frame_start, scene.frame_end = shot["frames"]
    return count


def edit_scene(film, shots, folders, name="Film"):
    """The ``Film`` scene: a sequencer cut of every shot's frames in film
    order, each hold showing the frame before it; rendering it writes the
    video."""
    from . import render as RND
    holds = set(film.get("holds", ()))
    first, last = film_frames(film)
    edit = bpy.data.scenes.get(name) or bpy.data.scenes.new(name)
    edit.render.resolution_x, edit.render.resolution_y = film["resolution"]
    edit.render.resolution_percentage = 100
    edit.render.fps, edit.render.fps_base = film["fps"], 1.0
    edit.frame_start, edit.frame_end = first, last
    edit.view_settings.view_transform = "Standard"
    edit.view_settings.look = "None"
    edit.display_settings.display_device = "sRGB"
    sequences = edit.sequence_editor_create()
    for strip in list(sequences.strips):
        sequences.strips.remove(strip)
    for shot_id, shot in shots.items():
        start, end = shot["frames"]
        prefix = os.path.join(folders[shot_id], f"{shot_id}_")
        files = [f"{os.path.basename(prefix)}{_shown(frame, holds):04d}.png" for frame in range(start, end + 1)]
        strip = sequences.strips.new_image(shot_id, os.path.join(folders[shot_id], files[0]), channel=1, frame_start=start)
        for file in files[1:]:
            strip.elements.append(file)
        strip.colorspace_settings.name = "sRGB"
    edit.render.use_sequencer = True
    edit.render.use_compositing = False
    image = RND._output_kind("VIDEO", edit)
    image.file_format = "FFMPEG"
    ffmpeg = edit.render.ffmpeg
    ffmpeg.format = "MPEG4"
    ffmpeg.codec = "H264"
    for attribute, value in (("constant_rate_factor", "HIGH"), ("ffmpeg_preset", "GOOD"), ("audio_codec", "NONE"),
                             ("gopsize", film["fps"])):
        try:
            setattr(ffmpeg, attribute, value)
        except (AttributeError, TypeError):
            pass
    return edit


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
    edit = edit_scene(film, shots, folders)
    video = os.path.join(build_dir, "video", f"{film['id']}.mp4")
    edit.render.filepath = video
    out = os.path.abspath(args.out or os.path.join(build_dir, f"{item}.blend"))
    if not args.no_save:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
        print(f"[film] saved {out}")
    holds = set(film.get("holds", ()))
    if args.render_shots:
        for shot_id, shot in shots.items():
            count = render_shot(shot, folders[shot_id], holds, args.frames)
            print(f"[film] {shot_id}: rendered {count} frames into {folders[shot_id]}")
    if args.frame is not None and args.render:
        shot = next((shot for shot in shots.values() if shot["frames"][0] <= args.frame <= shot["frames"][1]), None)
        if shot is None:
            raise ValueError(f"frame {args.frame} lies in none of the built shots {list(shots)}")
        scene = shot["scene"]
        scene.frame_set(args.frame)
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
        bpy.ops.render.render(animation=True, scene=edit.name)
        print(f"[film] video -> {video}")
    return production
