"""
Leaf colours of the plants in the Nitia shot, fitted to the painting object
by object.

Every plant object -- a painted specimen, a planting prototype with all its
instances, a tree outside -- grows its leaves between two colours
(``Color A``, ``Color B``).  The colour a leaf is made of shows where the
sun falls on it: in shade the painter colours every leaf with the blue of
the shade, and that blue belongs to the skylight, not to the leaf.  So the
pixels of each plant in the shot (an object-ID render: every object an
emission of its own colour, glass that the ink pass sees through left
clear), less those the painting does not paint as foliage
(``planting_plan.foliage_mask``: not the floor, the haze or the glass behind
a rendered leaf), are split at their median luminance, and the median
linear colour of the painting's lighter half is compared with the
render's -- the render lit by the fitted lights and seen as the light fit
sees it, without the shot's look, whose grade is fitted last.  A plant is
fitted only where the painting shows sunlit leaves over it: at least
``MIN_PIXELS`` of its pixels painted yellow-green to green (the foliage
mask up to ``SUNLIT_HUE_MAX``), not only the teal shade or the cyan glass of
the stair, whose colours say nothing of the leaf.  Light is linear in albedo, so
both leaf colours are scaled channel by channel by that ratio --
``DAMPING`` of the way, by no more than ``STEP`` either way in one round --
and then brought back to their own luminance (``LUMINANCE``), never past
``ALBEDO_MAX``, and written into scene.json as the object's own colours.
Only the hue and the saturation are fitted: painted leaves never line up
with rendered ones leaf for leaf, so the painting inside a rendered plant's
outline mixes the plant with its neighbours, and its brightness regresses
towards the garden's mean -- fitted, it would flatten the garden's light
and shade -- while its hue still tells the plant's colour.  The brightness
of the leaves is the light's.  Plants without that much sunlit foliage keep
their colours.

Alternate with the light fit until neither moves, then fit the grade::

    blender -b -P Other/Greenhouse/GlassAtrium/calibration/fit_foliage.py -- work_dir [--samples 48] [--scale 0.25]
    python Other/Greenhouse/GlassAtrium/calibration/fit_foliage.py work_dir [--write]
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SCENE, "..", "..", ".."))
for path in (ROOT, os.path.join(ROOT, "Other"), HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import numpy as np  # noqa: E402

SCENE_JSON = os.path.join(SCENE, "scene.json")
REFERENCE = os.path.join(SCENE, "Reference", "Nitia_clean.webp")
COLOR_INPUTS = ("Color A", "Color B")
DAMPING = 0.8
STEP = 2.0
ALBEDO_MAX = 0.95
MIN_PIXELS = 150
SUNLIT_HUE_MAX = 75
ID_LEVELS = 7
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])


def id_color(index):
    """Emission colour of the ``index``-th object in the ID render: a point
    of a ``ID_LEVELS`` cubed lattice, never black (the empty background)."""
    step = index + 1
    return tuple((step // ID_LEVELS ** axis % ID_LEVELS) / (ID_LEVELS - 1) for axis in range(3))


def render(work, samples, scale):
    """The shot without its look, then the object-ID render: every object
    an emission of its ``id_color`` (glass that the ink pass sees through
    left clear), one sample, no pixel filter, so a pixel holds one object's
    colour exactly."""
    import bpy
    ns = {}
    exec(compile(open(os.path.join(ROOT, "Other", "build.py"), encoding="utf-8").read(), "build.py", "exec"), ns)
    context = ns["main"](["x", "--", "Greenhouse/GlassAtrium", "--no-save", "--no-look", "--samples", str(samples), "--scale", str(scale)])
    from Core import driver
    from Core.render import INK_SKIP
    driver.activate_still(context)
    scene = bpy.context.scene
    names = sorted(obj.name for obj in scene.objects if obj.type == "MESH")
    for index, name in enumerate(names):
        scene.objects[name]["id_color"] = (*id_color(index), 1.0)
    scene.render.filepath = os.path.join(work, "shot.png")
    bpy.ops.render.render(write_still=True)
    material = bpy.data.materials.new("__fit_foliage_id")
    tree = material.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    attribute = tree.nodes.new("ShaderNodeAttribute")
    attribute.attribute_type = "OBJECT"
    attribute.attribute_name = "id_color"
    emission = tree.nodes.new("ShaderNodeEmission")
    see_through = tree.nodes.new("ShaderNodeAttribute")
    see_through.attribute_type = "GEOMETRY"
    see_through.attribute_name = INK_SKIP
    clear = tree.nodes.new("ShaderNodeBsdfTransparent")
    mix = tree.nodes.new("ShaderNodeMixShader")
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(attribute.outputs["Color"], emission.inputs["Color"])
    tree.links.new(see_through.outputs["Fac"], mix.inputs[0])
    tree.links.new(emission.outputs["Emission"], mix.inputs[1])
    tree.links.new(clear.outputs["BSDF"], mix.inputs[2])
    tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
    for layer in scene.view_layers:
        layer.material_override = material
    for obj in scene.objects:
        if obj.type == "MESH" and obj.modifiers and obj.modifiers[0].type == "NODES" and obj.modifiers[0].node_group.name == "GH.Env.Haze":
            obj.hide_render = True
    scene.world = None
    scene.render.use_compositing = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.eevee.taa_render_samples = 1
    scene.render.filter_size = 0.0
    scene.render.filepath = os.path.join(work, "ids.png")
    bpy.ops.render.render(write_still=True)
    with open(os.path.join(work, "ids.json"), "w", encoding="utf-8") as handle:
        json.dump({name: id_color(index) for index, name in enumerate(names)}, handle)
    print("foliage renders ->", work)


def linear(bgr):
    c = bgr[..., ::-1].astype(np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def encoded(color):
    c = np.asarray(color, np.float64)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 1e-9), 1.0 / 2.4) - 0.055) * 255.0


def lighter_half(lin):
    """Median linear colour of the lighter half of the pixels ``lin``."""
    order = np.argsort(lin @ LUMINANCE)
    return np.median(lin[order[len(order) // 2:]], axis=0)


def plants(scene, presets):
    """{object name: item} for every item that grows leaves between two
    colours -- set in its inputs or given by its preset."""
    items = [item for group in scene["collections"].values() for item in group]
    items += [item for group in scene.get("library", {}).values() for item in group]
    return {item["name"]: item for item in items
            if all(key in item.get("inputs", {}) or key in presets.get(item.get("preset"), {}) for key in COLOR_INPUTS)}


def main(argv):
    try:
        import bpy  # noqa: F401
    except ImportError:
        bpy = None
    work = os.path.abspath(argv[0])
    if bpy is not None:
        os.makedirs(work, exist_ok=True)
        samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48
        scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.25
        render(work, samples, scale)
        return
    import cv2
    from Core.jsonio import dump
    from Greenhouse import PALETTE, PLANTS
    from planting_plan import foliage_mask
    shot = cv2.imread(os.path.join(work, "shot.png"))
    ids = cv2.imread(os.path.join(work, "ids.png"))[:, :, ::-1].astype(np.float64)
    colors = json.load(open(os.path.join(work, "ids.json"), encoding="utf-8"))
    height, width = shot.shape[:2]
    reference = cv2.imread(REFERENCE)
    painted_foliage = cv2.resize(foliage_mask(reference).astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0
    painted_sunlit = cv2.resize(foliage_mask(reference, SUNLIT_HUE_MAX).astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0
    painting = cv2.resize(reference, (width, height), interpolation=cv2.INTER_AREA)
    with open(SCENE_JSON, encoding="utf-8") as handle:
        scene = json.load(handle)
    growing = plants(scene, PLANTS)
    kernel = np.ones((3, 3), np.uint8)
    shot_linear, painting_linear = linear(shot), linear(painting)
    changed = 0
    for name, item in sorted(growing.items()):
        if name not in colors:
            continue
        plant = cv2.erode((np.abs(ids - encoded(colors[name])).sum(axis=2) < 6.0).astype(np.uint8), kernel) > 0
        if (plant & painted_sunlit).sum() < MIN_PIXELS:
            continue
        mask = plant & painted_foliage
        ratio = lighter_half(painting_linear[mask]) / np.maximum(lighter_half(shot_linear[mask]), 1e-4)
        factor = np.clip(ratio ** DAMPING, 1.0 / STEP, STEP)
        inputs = item.setdefault("inputs", {})
        preset = PLANTS.get(item.get("preset"), {})
        for key in COLOR_INPUTS:
            value = inputs.get(key, preset.get(key))
            current = np.array(PALETTE[value] if isinstance(value, str) else value[:3], np.float64)
            tinted = current * factor
            tinted *= (current @ LUMINANCE) / max(float(tinted @ LUMINANCE), 1e-6)
            inputs[key] = [round(float(channel), 3) for channel in np.minimum(tinted, ALBEDO_MAX)]
        changed += 1
        print("%-26s %6d px  factor %s  -> %s / %s" % (name, mask.sum(), np.round(factor, 2), inputs["Color A"], inputs["Color B"]))
    if "--write" in argv:
        dump(scene, SCENE_JSON)
        print("%d plants' colours written to %s" % (changed, SCENE_JSON))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
