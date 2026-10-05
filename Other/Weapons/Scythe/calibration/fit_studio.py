"""
Fit the scythe's studio -- the soft boxes that light it as the design sheet
is drawn -- and the colour of each of its finishes.

The sheet's shading is light falling on the weapon from in front: its dark
housing brightens towards the middle of the head, the blackened flat of the
blade fades from the root to the tip, the polished grind flashes white
where it faces a bright box.  Gradients that change within a hand's width
across a flat plate need lights close to it, so the studio is a wall of
small soft boxes ``WALL["depth"]`` sheet units before the weapon, on a
``WALL["spacing"]`` grid, each aimed straight back at it, a row of boxes
above it (``TOP``) and a column behind its head (``REAR``) for the faces
the end view shows; only the wall boxes within reach of the weapon are
tried.  Every wall and top box has a twin mirrored behind the weapon at
the same power, so the weapon -- the same on both sides -- is lit the same
from behind, for every free camera.  The fit finds how bright each box is,
both as light on the surfaces (its diffuse factor) and as a card seen in
their reflections (its specular factor), how bright the world is, and the
colour of every finish.

Light adds up: the render under all boxes is the sum of the renders under
each one alone.  So every box is rendered twice at 1 W -- light only,
reflection only -- and the world once at strength 1, all linear, at
``SCALE`` of the sheet, through both cameras of the sheet (``SHOTS``: the
side view and the end view, the latter only over the strip of the sheet it
is drawn on); a flat render of the material colours tells the finishes
apart.  Over the weapon's pixels in both views (the blade's tip, drawn
over another figure, is left out) the render through the display's sRGB
encoding is fitted to the sheet: a finish's colour scales the light it
diffuses -- and, for a metal, the light it reflects -- channel by channel,
never above white; a glowing finish keeps its colour (its look is its
light), and so does a finish seen in fewer than FEWEST of the
pixels.  Powers and colours are found in turn, each a linear least squares
with the other held (weighted by the slope of the sRGB encoding at the
sheet's value, so the fit is in display terms), then polished together on
the true encoding.  Boxes the fit leaves dark are dropped; the rest go
into ``weapon.json`` as its lights, the world's strength as its studio and
the finishes' colours as its materials.  The basis is rendered with the
colours ``weapon.json`` already has, so a refit after changing the weapon
starts from the last one.

Two steps, because Blender's Python has no OpenCV::

    blender -b --factory-startup -P Other/Weapons/Scythe/calibration/fit_studio.py -- render <cache folder>
    python Other/Weapons/Scythe/calibration/fit_studio.py fit <cache folder>
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(FOLDER)))
WALL = {"columns": [300, 2800], "rows": [40, 2520], "spacing": 150.0, "depth": 320.0, "reach": 1.2}
TOP = {"columns": [300, 2800], "count": 5, "height": -500.0, "depths": [-900.0, -300.0]}
REAR = {"column": 150.0, "rows": [100, 2500], "count": 8, "target": 430.0}
SHOTS = {"Sheet": {"columns": [0, 2560]}, "End": {"columns": [50, 210]}}
SCALE = 0.5
SAMPLES = 32
EVERY = 8
FLOOR = 0.002
FEWEST = 30
DARKEST = 0.002
ROUNDS = 8
POLISH = 30
PARTS = ("diffuse", "specular")
CODES = 64.0


def panels(covered):
    """The candidate soft boxes -- name, centre and target (sheet units),
    size, whether it has a twin -- of which the wall's are those within
    reach of a sheet point of ``covered`` ([[u, v], ...])."""
    import numpy as np
    covered = np.asarray(covered, float)
    rig = []
    (u0, u1), (v0, v1), step = WALL["columns"], WALL["rows"], WALL["spacing"]
    reach = WALL["depth"] * WALL["reach"]
    for row, v in enumerate(np.arange(v0 + step * 0.5, v1, step)):
        for col, u in enumerate(np.arange(u0 + step * 0.5, u1, step)):
            if ((covered - (u, v)) ** 2).sum(axis=1).min() > reach * reach:
                continue
            rig.append({"name": f"Wall {row}.{col}", "at": [float(u), -WALL["depth"], float(v)], "target": [float(u), 0.0, float(v)],
                        "size": [step, step], "twin": True})
    (u0, u1), count = TOP["columns"], TOP["count"]
    width = (u1 - u0) / count
    for index, depth in enumerate(TOP["depths"]):
        for col in range(count):
            u = u0 + (col + 0.5) * width
            rig.append({"name": f"Top {index}.{col}", "at": [u, depth, TOP["height"]], "target": [u, depth * 0.3, 600.0],
                        "size": [width, abs(TOP["depths"][1] - TOP["depths"][0])], "twin": True})
    (v0, v1), count = REAR["rows"], REAR["count"]
    height = (v1 - v0) / count
    for row in range(count):
        v = v0 + (row + 0.5) * height
        rig.append({"name": f"Rear {row}", "at": [REAR["column"], 0.0, v], "target": [REAR["target"], 0.0, v],
                    "size": [height, height], "twin": False})
    return rig


def render_basis(cache):
    import bpy
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, "Other"))
    sys.path.insert(0, ROOT)
    import build
    build.main(["build.py", "Weapons/Scythe", "--no-save", "--no-look"])
    from Weapons import FINISHES
    from Weapons.scenes import Sheet
    from Core import jsonio
    sheet = Sheet(jsonio.load(os.path.join(FOLDER, "weapon.json"))["sheet"])
    scene = bpy.context.scene
    render = scene.render
    render.resolution_percentage = int(SCALE * 100)
    scene.eevee.taa_render_samples = SAMPLES
    render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    render.use_compositing = False
    render.use_crop_to_border = False
    settings = render.image_settings
    settings.file_format = "OPEN_EXR"
    settings.color_depth = "32"
    settings.color_mode = "RGBA"
    for obj in [o for o in scene.objects if o.type == "LIGHT"]:
        bpy.data.lights.remove(obj.data)
    emission = scene.world.node_tree.nodes["Emission"]
    cameras = {shot: bpy.data.objects[f"CAM_{shot}"] for shot in SHOTS}

    def shoot(name):
        for shot, spec in SHOTS.items():
            scene.camera = cameras[shot]
            render.use_border = True
            render.border_min_x, render.border_max_x = (column / render.resolution_x for column in spec["columns"])
            render.border_min_y, render.border_max_y = 0.0, 1.0
            os.makedirs(os.path.join(cache, shot), exist_ok=True)
            render.filepath = os.path.join(cache, shot, f"{name}.exr")
            bpy.ops.render.render(write_still=True)
        return os.path.join(cache, "Sheet", f"{name}.exr")

    emission.inputs["Strength"].default_value = 0.0
    image = bpy.data.images.load(shoot("self"))
    width, height = image.size
    pixels = np.empty(width * height * 4, np.float32)
    image.pixels.foreach_get(pixels)
    alpha = pixels.reshape(height, width, 4)[::-1, :, 3]
    rows, cols = np.nonzero(alpha[::4, ::4] > 0.5)
    covered = np.stack([cols * 4 / SCALE, rows * 4 / SCALE], axis=-1)
    emission.inputs["Strength"].default_value = 1.0
    shoot("world")
    emission.inputs["Strength"].default_value = 0.0
    rig = panels(covered)
    print(f"[fit_studio] {len(rig)} soft boxes")
    collection = bpy.data.collections.new("Basis")
    scene.collection.children.link(collection)
    boxes = []
    for panel in rig:
        data = bpy.data.lights.new(panel["name"], "AREA")
        data.energy = 1.0
        data.shape = "RECTANGLE"
        data.size, data.size_y = (value * sheet.scale for value in panel["size"])
        data.use_shadow_jitter = True
        pair = []
        for side in (1.0, -1.0) if panel["twin"] else (1.0,):
            u, y, v = panel["at"]
            tu, ty, tv = panel["target"]
            obj = bpy.data.objects.new(panel["name"], data)
            collection.objects.link(obj)
            obj.location = sheet.at([u, y * side, v])
            obj.rotation_euler = (sheet.at([tu, ty * side, tv]) - obj.location).to_track_quat("-Z", "Y").to_euler()
            obj.hide_render = True
            pair.append(obj)
        boxes.append(pair)
    for panel, pair in zip(rig, boxes):
        for obj in pair:
            obj.hide_render = False
        for part in PARTS:
            pair[0].data.diffuse_factor = 1.0 if part == "diffuse" else 0.0
            pair[0].data.specular_factor = 1.0 if part == "specular" else 0.0
            shoot(f"{panel['name']} {part}")
        for obj in pair:
            obj.hide_render = True
    finishes = sorted(m.name for m in bpy.data.materials if m.get("weapons_built") and m.name in FINISHES)
    rendered = {name: list(bpy.data.materials[name].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value)[:3]
                for name in finishes}
    for index, name in enumerate(finishes):
        bpy.data.materials[name].diffuse_color = ((index + 1) / CODES, 0.0, 0.0, 1.0)
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "MATERIAL"
    shading.show_object_outline = False
    shading.show_cavity = False
    scene.display.render_aa = "OFF"
    shoot("finish")
    with open(os.path.join(cache, "rig.json"), "w", encoding="utf-8") as handle:
        json.dump({"panels": rig, "finishes": finishes, "colours": rendered}, handle)


def samples(cache, names):
    """The pixels the fit runs over, from every shot: (sheet colour, own
    emission, finish index, basis values [pixel, channel, image])."""
    import cv2
    import numpy as np

    def exr(shot, name):
        image = cv2.imread(os.path.join(cache, shot, f"{name}.exr"), cv2.IMREAD_UNCHANGED)
        return image[..., :3][..., ::-1].astype(np.float64), image[..., 3].astype(np.float64)

    sheet = cv2.imread(os.path.join(FOLDER, "Reference", "Sheet.jpg")).astype(np.float64)[..., ::-1] / 255.0
    parts = []
    for shot, spec in SHOTS.items():
        own, coverage = exr(shot, "self")
        height, width = own.shape[:2]
        finish = np.rint(exr(shot, "finish")[0][..., 0] * CODES).astype(int) - 1
        kernel = np.ones((3, 3), np.uint8)
        steady = cv2.erode(finish.astype(np.float32), kernel) == cv2.dilate(finish.astype(np.float32), kernel)
        target = cv2.resize(cv2.GaussianBlur(sheet, (0, 0), 2.0), (width, height), interpolation=cv2.INTER_AREA)
        solid = (cv2.erode((coverage > 0.999).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & steady & (finish >= 0)
        inside = np.zeros_like(solid)
        inside[:, int(spec["columns"][0] * SCALE):int(spec["columns"][1] * SCALE)] = True
        rows, cols = np.nonzero(solid & inside)
        pick = np.arange(0, len(rows), EVERY)
        rows, cols = rows[pick], cols[pick]
        basis = np.stack([exr(shot, name)[0][rows, cols] for name in names], axis=-1)
        parts.append((target[rows, cols], own[rows, cols], finish[rows, cols], basis))
        print(f"{shot}: {len(rows)} pixels")
    return [np.concatenate(values, axis=0) for values in zip(*parts)]


def fit(cache):
    os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
    import numpy as np
    from scipy.optimize import least_squares, lsq_linear
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "Other"))
    from Core import jsonio
    from Weapons import FINISHES

    rig = json.load(open(os.path.join(cache, "rig.json"), encoding="utf-8"))
    boxes, finishes, rendered = rig["panels"], rig["finishes"], rig["colours"]
    names = ["world"] + [f"{box['name']} {part}" for box in boxes for part in PARTS]
    target, base, which, basis = samples(cache, names)
    count = len(finishes)
    metal = np.array([FINISHES[name].get("metallic", 0.0) > 0.5 for name in finishes])
    shiny = metal[which]
    reflection = np.array([name.endswith(" specular") for name in names])
    scaled = basis * (~reflection | shiny[:, None, None] * reflection)
    fixed = basis - scaled
    del basis
    colour = np.array([rendered[name] for name in finishes])
    lower = DARKEST / np.maximum(colour, 1e-4)
    upper = 1.0 / np.maximum(colour, 1e-4)
    held = np.array(["emission" in FINISHES[name] or (which == index).sum() < FEWEST for index, name in enumerate(finishes)])
    lower[held], upper[held] = 1.0, 1.0 + 1e-9

    def encode(linear):
        linear = np.clip(linear, 0.0, 1.0)
        return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)

    def slope(linear):
        inside = (linear > 0.0) & (linear < 1.0)
        return np.where(linear <= 0.0031308, 12.92, 1.055 / 2.4 * np.power(np.maximum(linear, 1e-9), 1 / 2.4 - 1.0)) * inside

    goal = np.where(target <= 0.04045, target / 12.92, np.power((target + 0.055) / 1.055, 2.4))
    weight = slope(np.clip(goal, 1e-4, 0.999))
    gains = np.clip(np.ones((count, 3)), lower, upper)
    powers = np.zeros(len(names))
    for _ in range(ROUNDS):
        gain = gains[which]
        system = (fixed + scaled * gain[..., None]) * weight[..., None]
        powers = lsq_linear(system.reshape(-1, len(names)), ((goal - base) * weight).ravel(), bounds=(0.0, np.inf), method="trf",
                            lsmr_tol="auto").x
        light, still = scaled @ powers, fixed @ powers
        for index in range(count):
            mine = which == index
            for channel in range(3):
                spread = (weight[mine, channel] ** 2 * light[mine, channel] ** 2).sum()
                if spread > 0.0:
                    best = (weight[mine, channel] ** 2 * light[mine, channel] * (goal[mine, channel] - base[mine, channel]
                                                                                - still[mine, channel])).sum() / spread
                    gains[index, channel] = np.clip(best, lower[index, channel], upper[index, channel])

    def split(x):
        return x[:len(names)], x[len(names):].reshape(count, 3)

    def residual(x):
        powers_, gains_ = split(x)
        return (encode(base + fixed @ powers_ + gains_[which] * (scaled @ powers_)) - target).ravel()

    def jacobian(x):
        powers_, gains_ = split(x)
        gain = gains_[which]
        light = scaled @ powers_
        steep = slope(base + fixed @ powers_ + gain * light)
        by_power = steep[..., None] * (fixed + scaled * gain[..., None])
        by_gain = np.zeros((len(which), 3, count * 3))
        for channel in range(3):
            by_gain[np.arange(len(which)), channel, which * 3 + channel] = steep[:, channel] * light[:, channel]
        return np.concatenate([by_power.reshape(len(which) * 3, -1), by_gain.reshape(len(which) * 3, -1)], axis=1)

    start = np.concatenate([powers, gains.ravel()])
    low = np.concatenate([np.zeros(len(names)), lower.ravel()])
    high = np.concatenate([np.full(len(names), np.inf), upper.ravel()])
    solved = least_squares(residual, np.clip(start, low, high), jac=jacobian, bounds=(low, high), method="trf", tr_solver="lsmr",
                           x_scale="jac", max_nfev=POLISH, verbose=1)
    powers, gains = split(solved.x)
    miss = np.abs(encode(base + fixed @ powers + gains[which] * (scaled @ powers)) - target).mean(axis=1)
    print(f"mean error {miss.mean() * 255:.1f} / 255 over {len(which)} pixels; world {powers[0]:.3f}")
    path = os.path.join(FOLDER, "weapon.json")
    data = jsonio.load(path)
    colours = {}
    for index, name in enumerate(finishes):
        mine = which == index
        fitted = [round(float(min(c * g, 1.0)), 4) for c, g in zip(colour[index], gains[index])]
        if not held[index]:
            colours[f"color:{FINISHES[name]['color']}"] = fitted
        print(f"  {name:16s} {fitted}   error {miss[mine].mean() * 255 if mine.any() else 0.0:5.1f} / 255 over {mine.sum()} pixels")
    lights = []
    strongest = powers[1:].max()
    for index, box in enumerate(boxes):
        diffuse, specular = powers[1 + 2 * index], powers[2 + 2 * index]
        power = max(diffuse, specular)
        if power > FLOOR * strongest:
            lights.append({"name": box["name"], "light": "AREA", "power": round(float(power), 5),
                           "diffuse": round(float(diffuse / power), 4), "specular": round(float(specular / power), 4),
                           "size": [round(v, 1) for v in box["size"]], "at": [round(v, 1) for v in box["at"]],
                           "target": [round(v, 1) for v in box["target"]], "twin": box["twin"]})
    data["lights"] = lights
    data["studio"] = {"strength": round(float(powers[0]), 4)}
    data["materials"] = colours
    jsonio.dump(data, path)
    print(f"{len(lights)} lights written to {path}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    {"render": render_basis, "fit": fit}[argv[0]](os.path.abspath(argv[1]))
