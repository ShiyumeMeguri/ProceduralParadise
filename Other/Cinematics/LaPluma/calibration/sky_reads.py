"""
What of the reference shows sky, frame by frame, as a shot's camera sees it (run inside Blender: ``cloud_map.py``,
``fit_sky.py``).

The picture is read in blocks of ``block`` pixels.  A block shows sky unless something stands in front of it: the
set's standing buildings the shot shows (the block's ray from the camera meets them before ``distance``), the cast
and what it holds (``<masks dir>/<object>/m####.png``, white = the object, grown by ``margin`` blocks), a crow or a
beam (a pixel darker than ``darkest``), the watermark (the film's ``reference.masks``).
"""
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

from Core import cast as CAST, jsonio, scene as SC  # noqa: E402
from Cinematics import scenes as SCN  # noqa: E402

FILM = os.path.join(HERE, "..")
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])


def image(path):
    """``path`` as an array of rows from the top, RGB 0..255."""
    picture = bpy.data.images.load(path, check_existing=False)
    width, height = picture.size
    pixels = np.empty(width * height * 4, np.float32)
    picture.pixels.foreach_get(pixels)
    bpy.data.images.remove(picture)
    return pixels.reshape(height, width, 4)[::-1, :, :3] * 255.0


def blocks(values, block, reduce):
    height, width = values.shape[:2]
    trimmed = values[:height - height % block, :width - width % block]
    shaped = trimmed.reshape(height // block, block, width // block, block, *values.shape[2:])
    return reduce(reduce(shaped, axis=3), axis=1)


def grown(mask, margin):
    result = mask.copy()
    for _ in range(margin):
        step = result.copy()
        step[1:] |= result[:-1]
        step[:-1] |= result[1:]
        step[:, 1:] |= result[:, :-1]
        step[:, :-1] |= result[:, 1:]
        result = step
    return result


def _volume_only(material):
    outputs = [node for node in material.node_tree.nodes if node.type == "OUTPUT_MATERIAL"] if material and material.node_tree else []
    return bool(outputs) and all(not node.inputs["Surface"].is_linked and node.inputs["Volume"].is_linked for node in outputs)


class ShotSky:
    """A shot's camera and the set it sees -- what stands of it, or all of it as the shot renders it (``whole``: what
    is there for a while, while it is, the shot's hidden items left out over its frames) -- ready to tell the
    reference's sky blocks."""

    def __init__(self, shot_name, block=4, darkest=55.0, margin=2, whole=False):
        self.film = jsonio.load(os.path.join(FILM, "film.json"))
        self.shot = jsonio.load(os.path.join(FILM, "shots", f"{shot_name}.json"))
        self.spec = jsonio.load(os.path.join(FILM, "sets", f"{self.shot['set']}.json"))
        self.sky = SCN.shot_sky(self.spec["sky"], self.shot.get("sky", {}))
        self.block, self.darkest, self.margin = block, darkest, margin
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj)
        SCN.set_materials(self.spec)
        self.set_collection = SC.collection("Sky Reads Set", parent=bpy.context.scene.collection)
        hidden = self.shot.get("hidden", ())
        sun = next((lamp for lamp in self.spec.get("lights", []) if lamp["light"] == "SUN"), None)
        for item in self.spec.get("items", []):
            if whole or ("shown" not in item and item["name"] not in hidden):
                SCN.build_item(item, self.set_collection, sun)
        if whole:
            SCN.hide_set_items(self.shot, self.set_collection)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        self.air = []
        for obj in self.set_collection.all_objects:
            if obj.type == "MESH":
                materials = [material for material in obj.evaluated_get(depsgraph).data.materials if material is not None]
                if materials and all(_volume_only(material) for material in materials):
                    obj.hide_viewport = True
                    self.air.append(obj)
        cameras = SC.collection("Sky Reads Camera", parent=bpy.context.scene.collection)
        self.camera, _sources, self.matrices = SCN.build_camera("Sky Reads Camera", FILM, self.shot["camera"], self.film, cameras)
        self.width, self.height = self.film["resolution"]

    def performer(self, name):
        """The shot's performer ``name`` as the film plays it -- its rig posed frame by frame, nothing of it drawn --
        what the camera's depth of field focuses on (the character's .blend as the film finds it)."""
        entry = self.film["cast"][name]
        collection = SC.collection("Sky Reads Cast", parent=bpy.context.scene.collection)
        rig, objects = CAST.append_character(CAST.resolve_blend(entry, {}, name), entry["armature"], collection,
                                             entry.get("hidden", ()), prefix=f"Sky Reads.{name}")
        profile = jsonio.load(os.path.join(FILM, entry["rig"]))
        SCN.perform(rig, FILM, self.shot["cast"][name], tuple(self.shot["frames"]), objects, profile, self.matrices)
        for obj in objects:
            if obj != rig:
                bpy.data.objects.remove(obj)
        return rig

    def rays(self, frame):
        """The camera's place and the ray of every block's middle on ``frame``."""
        bpy.context.scene.frame_set(frame)
        matrix = np.array(self.camera.matrix_world)
        focal = self.camera.data.lens / self.camera.data.sensor_width * self.width
        rows, columns = self.height // self.block, self.width // self.block
        across = ((np.arange(columns) + 0.5) * self.block - self.width / 2.0) / focal
        up = -((np.arange(rows) + 0.5) * self.block - self.height / 2.0) / focal
        local = np.stack(np.broadcast_arrays(across[None, :], up[:, None], -np.ones((rows, columns))), axis=-1)
        return matrix[:3, 3], local @ matrix[:3, :3].T

    def ray(self, frame, x, y):
        """The camera's place and the unit ray through the picture's pixel (``x``, ``y``) on ``frame``."""
        bpy.context.scene.frame_set(frame)
        matrix = np.array(self.camera.matrix_world)
        focal = self.camera.data.lens / self.camera.data.sensor_width * self.width
        local = np.array([(x - self.width / 2.0) / focal, -(y - self.height / 2.0) / focal, -1.0])
        direction = matrix[:3, :3] @ local
        return matrix[:3, 3], direction / np.linalg.norm(direction), focal

    def hidden_by_set(self, origin, rays, candidates, distance):
        """Which of the ``candidates`` rays meet the standing set within ``distance``."""
        scene = bpy.context.scene
        depsgraph = bpy.context.evaluated_depsgraph_get()
        hidden = np.zeros(candidates.shape, bool)
        start = tuple(float(value) for value in origin)
        reach = np.broadcast_to(distance, candidates.shape)
        for row, column in zip(*np.nonzero(candidates)):
            direction = tuple(float(value) for value in rays[row, column])
            hidden[row, column] = scene.ray_cast(depsgraph, start, direction, distance=float(reach[row, column]))[0]
        return hidden

    def read(self, frames_dir, mask_dirs, frame, boxes=()):
        """The reference ``frame`` in blocks (mean RGB 0..255) and which blocks show something other than the set's sky,
        the set's buildings left to :meth:`hidden_by_set` -- and, left out besides, the picture's ``boxes`` [x0, y0, x1, y1]
        (what a fit cannot draw: the dust of a breach that is not the sky's)."""
        picture = image(os.path.join(frames_dir, f"f{frame:04d}.png"))
        luminance = picture @ LUMINANCE
        hidden = np.zeros(luminance.shape, bool)
        for x0, y0, x1, y1 in list(self.film.get("reference", {}).get("masks", [])) + list(boxes):
            hidden[y0:y1, x0:x1] = True
        hidden |= luminance < self.darkest
        blocked = blocks(hidden, self.block, np.max)
        for folder in mask_dirs:
            for name in sorted(os.listdir(folder)):
                mask_path = os.path.join(folder, name, f"m{frame:04d}.png")
                if os.path.isfile(mask_path):
                    blocked |= grown(blocks(image(mask_path)[:, :, 0] > 127.0, self.block, np.max), self.margin)
        return blocks(picture, self.block, np.mean), blocked
