"""
Core.project -- a built file made a project of its own: every file it reads from outside its folder copied into the
folder's ``Data`` and read from there by a relative path, the .blend saved in the folder.

``export(folder, name, sources)`` takes the open file as it stands: images, sounds, fonts, movie clips, volumes, cache files and
libraries read from a file, and every image and movie strip of every scene's sequencer (an image strip's frames as a
folder of their own).  A file already inside ``folder`` stays where it is; one outside it goes to ``Data/<kind>`` (two of
one name from different folders kept apart by a number).  What the file holds packed stays packed.  Opened from
anywhere the project reads only what lies beside it.
"""
from __future__ import annotations

import os
import shutil

import bpy

__all__ = ["export"]

DATA = "Data"
KINDS = (("images", "Textures"), ("sounds", "Audio"), ("fonts", "Fonts"), ("movieclips", "Video"), ("volumes", "Volumes"),
         ("cache_files", "Caches"), ("libraries", "Libraries"))


def _inside(path, folder):
    return os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(os.path.abspath(folder)) + os.sep)


def _placed(source, folder, kind, taken):
    """Where ``source`` lives in the project: itself when inside ``folder``, else a copy in ``Data/<kind>``."""
    if _inside(source, folder):
        return source
    if source in taken:
        return taken[source]
    target_dir = os.path.join(folder, DATA, kind)
    os.makedirs(target_dir, exist_ok=True)
    stem, extension = os.path.splitext(os.path.basename(source))
    target, number = os.path.join(target_dir, stem + extension), 1
    while target in taken.values() or (os.path.exists(target) and os.path.getsize(target) != os.path.getsize(source)):
        target, number = os.path.join(target_dir, f"{stem}.{number}{extension}"), number + 1
    if not os.path.exists(target) or os.path.getsize(target) != os.path.getsize(source):
        shutil.copy2(source, target)
    taken[source] = target
    return target


def _strips(folder, taken):
    """Every scene's image and movie strips read from the project: an image strip's frames copied as a folder."""
    count = 0
    for scene in bpy.data.scenes:
        if scene.sequence_editor is None:
            continue
        for strip in scene.sequence_editor.strips_all:
            if strip.type == "IMAGE":
                directory = os.path.abspath(bpy.path.abspath(strip.directory))
                if _inside(directory, folder):
                    continue
                target = os.path.join(folder, DATA, "Frames", strip.name)
                os.makedirs(target, exist_ok=True)
                for element in strip.elements:
                    source = os.path.join(directory, element.filename)
                    destination = os.path.join(target, element.filename)
                    if not os.path.exists(destination) or os.path.getsize(destination) != os.path.getsize(source):
                        shutil.copy2(source, destination)
                strip.directory = target + os.sep
                count += len(strip.elements)
            elif strip.type == "MOVIE":
                strip.filepath = _placed(os.path.abspath(bpy.path.abspath(strip.filepath)), folder, "Video", taken)
                count += 1
    return count


def export(folder, name, sources=()):
    """Save the open file as ``folder/<name>.blend`` reading every outside file from ``folder/Data``; returns the path.
    ``sources`` are the files it was built from (a cast's .blend): one of them at that path is never written over."""
    folder = os.path.abspath(folder)
    out = os.path.join(folder, f"{name}.blend")
    if any(os.path.exists(source) and os.path.exists(out) and os.path.samefile(source, out) for source in sources):
        raise FileExistsError(f"{out} is a file the project is built from: name the project otherwise")
    os.makedirs(folder, exist_ok=True)
    taken, moved = {}, 0
    for collection, kind in KINDS:
        for block in getattr(bpy.data, collection):
            if getattr(block, "packed_file", None) is not None or getattr(block, "library", None) is not None:
                continue
            path = getattr(block, "filepath", "")
            if not path or path.startswith("<"):
                continue
            source = os.path.abspath(bpy.path.abspath(path))
            if not os.path.exists(source):
                raise FileNotFoundError(f"{collection} '{block.name}' reads {source}, which is not there")
            block.filepath = _placed(source, folder, kind, taken)
            moved += 1
    frames = _strips(folder, taken)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True, relative_remap=True)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile(compress=True)
    print(f"[project] {out}: {moved} files and {frames} strip frames read from the project, {len(set(taken.values()))} copied "
          f"into {os.path.join(folder, DATA)}")
    return out
