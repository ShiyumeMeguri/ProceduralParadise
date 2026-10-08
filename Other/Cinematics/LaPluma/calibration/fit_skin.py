"""
How strongly a shot's lamp lights her, from her skin in the reference (run in the Blender that built the shot alone,
after ``Other/build.py``):

    SKIN_FRAMES=<frames dir> [SKIN_OUT=<folder>] [SKIN_WRITE=1] blender -b -P Other/build.py -P <this file> -- \\
        Cinematics/LaPluma --shots <Shot> --scale 0.5 --samples 16 --no-save

The shot's spec (``calibration/<Shot>.skin_fit.json``)::

    {"lamp": "Sun", "frames": [430, 450, 470, 500], "points": [["Nose01Joint_M"]], "radius": 0.01, "rounds": 7}

names the set's lamp to turn, the frames where the reference shows her skin lit as the shot lights it, and on her the
places to read it: each the middle of its bones' heads, read over a disc ``radius`` metres across as the shot's camera
sees it there.  The shot is rendered as the film renders it (its look and all) with the lamp at one power after
another, and the linear brightness of the discs compared with the reference's: the power is bisected (on its log)
until the median over frames and places of the render's over the reference's is one -- or, where even the lamp
at its strongest leaves her duller than the reference (her toon skin stops brightening once lit), to the least power
that brings her within :data:`PLATEAU` of as bright as it can (what is left is not the lamp's).  The film's skin is shaded by
the character's own materials, which no set fit sees (her colours are masked out of every fit): under the district's
sun at the sky's power her face clipped white where the reference's is a lit, soft skin.  With ``SKIN_WRITE`` the
power is written as the shot's light (its ``lights``); its sky, lit by that lamp, must be fitted again after.  With
``SKIN_OUT`` the renders at that power and the places read (``places.json``: frame, centre and radius in the film's
pixels) are kept there.
"""
import json
import math
import os
import tempfile

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FILM = os.path.join(HERE, "..")
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])
LOW, HIGH = 1.0 / 16.0, 2.0
PLATEAU = 0.005


def image(path):
    """``path`` as an array of rows from the top, RGB 0..255."""
    picture = bpy.data.images.load(path, check_existing=False)
    width, height = picture.size
    pixels = np.empty(width * height * 4, np.float32)
    picture.pixels.foreach_get(pixels)
    bpy.data.images.remove(picture)
    return pixels.reshape(height, width, 4)[::-1, :, :3] * 255.0


def linear(display):
    value = display / 255.0
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4) @ LUMINANCE


def disc_mean(picture, centre, radius):
    """The mean linear brightness of ``picture`` (rows x columns x RGB, display 0..255) over a disc, or None off it."""
    height, width = picture.shape[:2]
    x, y = centre
    if not (radius < x < width - radius and radius < y < height - radius):
        return None
    rows, columns = np.ogrid[:height, :width]
    inside = (columns - x) ** 2 + (rows - y) ** 2 <= radius ** 2
    return float(linear(picture[inside].astype(np.float64)).mean())


def main():
    scenes = [scene for scene in bpy.data.scenes if scene.name.startswith("Shot.") and "." not in scene.name[len("Shot."):]]
    if len(scenes) != 1:
        raise SystemExit(f"[skin] build the shot alone (--shots): built {[scene.name for scene in scenes]}")
    scene = scenes[0]
    shot_id = scene.name[len("Shot."):]
    spec = json.load(open(os.path.join(HERE, f"{shot_id}.skin_fit.json"), encoding="utf-8"))
    frames_dir = os.environ["SKIN_FRAMES"]
    rig = next(obj for obj in scene.collection.children[f"Shot.{shot_id}.Cast"].all_objects if obj.type == "ARMATURE")
    lamp = bpy.data.objects[spec["lamp"]]
    lamp.data.animation_data_clear()
    start = lamp.data.energy
    camera = scene.camera
    scale = scene.render.resolution_percentage / 100.0
    places = []
    for frame in spec["frames"]:
        bpy.context.window.scene = scene
        scene.frame_set(frame)
        inverse = np.linalg.inv(np.array(camera.matrix_world))
        focal = camera.data.lens / camera.data.sensor_width * scene.render.resolution_x
        reference = image(os.path.join(frames_dir, "f%04d.png" % frame))
        for bones in spec["points"]:
            world = np.mean([np.array(rig.matrix_world) @ np.array([*rig.pose.bones[name].head, 1.0]) for name in bones], axis=0)
            local = inverse @ world
            depth = -local[2]
            centre = (scene.render.resolution_x / 2 + focal * local[0] / depth, scene.render.resolution_y / 2 - focal * local[1] / depth)
            radius = focal * spec["radius"] / depth
            seen = disc_mean(reference, centre, radius)
            if seen is not None:
                places.append((frame, centre, radius, seen))
    if not places:
        raise SystemExit("[skin] no place to read is in the picture on the spec's frames")
    folder = os.environ.get("SKIN_OUT") or tempfile.mkdtemp(prefix="fit_skin_")
    os.makedirs(folder, exist_ok=True)

    def ratio(power):
        lamp.data.energy = power
        ratios, renders = [], {}
        for frame in sorted({place[0] for place in places}):
            bpy.context.window.scene = scene
            scene.frame_set(frame)
            scene.render.filepath = os.path.join(folder, f"f{frame}.png")
            bpy.ops.render.render(write_still=True, scene=scene.name)
            renders[frame] = image(scene.render.filepath)
        for frame, centre, radius, seen in places:
            ours = disc_mean(renders[frame], (centre[0] * scale, centre[1] * scale), max(radius * scale, 1.5))
            if ours is not None:
                ratios.append(ours / max(seen, 1e-4))
        value = float(np.median(ratios))
        print(f"[skin] {shot_id} {spec['lamp']} {power:.4f}: her skin {value:.3f} of the reference's ({len(ratios)} places)", flush=True)
        return value

    low, high = math.log(start * LOW), math.log(start * HIGH)
    if ratio(math.exp(low)) > 1.0:
        raise SystemExit(f"[skin] even at {math.exp(low):.4f} her skin is brighter than the reference's: the lamp is not what lights it")
    brightest = ratio(math.exp(high))
    goal = 1.0 if brightest > 1.0 else brightest - PLATEAU
    if brightest <= 1.0:
        print(f"[skin] at its strongest the lamp leaves her skin {brightest:.3f} of the reference's: the least power within "
              f"{PLATEAU} of that", flush=True)
    for _round in range(spec.get("rounds", 7)):
        middle = 0.5 * (low + high)
        if ratio(math.exp(middle)) > goal:
            high = middle
        else:
            low = middle
    power = round(math.exp(0.5 * (low + high)), 4)
    value = ratio(power)
    print(f"[skin] best {shot_id} {spec['lamp']} power {power} (was {start}): her skin {value:.3f} of the reference's", flush=True)
    with open(os.path.join(folder, "places.json"), "w", encoding="utf-8") as handle:
        json.dump([{"frame": frame, "centre": list(centre), "radius": radius} for frame, centre, radius, _seen in places], handle)
    if os.environ.get("SKIN_WRITE"):
        path = os.path.join(FILM, "shots", f"{shot_id}.json")
        shot = json.load(open(path, encoding="utf-8"))
        shot.setdefault("lights", {}).setdefault(spec["lamp"], {})["power"] = power
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(shot, indent=1, ensure_ascii=False) + "\n")
        print(f"[skin] written into {path}", flush=True)


main()
