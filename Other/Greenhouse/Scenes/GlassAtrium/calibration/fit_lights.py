"""
Light balancing as an inverse problem, per colour channel.

Light transport is linear in the light sources, so the atrium is rendered
once with every source in its own Cycles light group: each lamp, the sky
(the world) and every emissive object (the city smog glows with the skylight
it scatters in).  Any balance is then sum_g w_g * I_g with a weight per
group *and channel*, so one solve finds both how bright and what colour
every source is.  The weights are fitted so that this sum, after the
Standard view transform (sRGB encoding, clipping at white), reproduces the
painting with the figure removed: a robust (Charbonnier) error on
downsampled, blurred display values, optimised over log-weights with
L-BFGS, a weak prior keeping every weight near 1.

Two steps, because Blender's Python has no SciPy::

    blender -b -P Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_lights.py -- groups.npz [--samples 64] [--scale 0.25]
    python Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_lights.py groups.npz [--apply]

``--apply`` writes the result into scene.json: a lamp's power and colour,
the sky's strength and tint (``color:`` overrides of the sky palette
entries), an emissive object's colour (``color:<its colour key>``,
``EMISSIVE_COLORS``).  Render ungraded; refit the grade afterwards.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SCENE, "..", "..", "..", ".."))
for path in (ROOT, os.path.join(ROOT, "Other")):
    if path not in sys.path:
        sys.path.insert(0, path)

import numpy as np  # noqa: E402

SCENE_JSON = os.path.join(SCENE, "scene.json")
REFERENCE = os.path.join(SCENE, "Reference", "Nitia_clean.webp")
SKY = "sky"
SKY_COLORS = ("sky_zenith", "sky_horizon", "haze")
EMISSIVE_COLORS = {"GH.HazeFar": "smog"}


def emissive_material(obj):
    """Name of the library material with emission an object renders with."""
    evaluated = obj.evaluated_get(__import__("bpy").context.evaluated_depsgraph_get())
    for slot in evaluated.material_slots:
        if slot.material is not None and slot.material.name in EMISSIVE_COLORS:
            return slot.material.name
    return None


def render_groups(out, samples, scale):
    import bpy
    import tempfile
    ns = {}
    exec(compile(open(os.path.join(ROOT, "Other", "build.py"), encoding="utf-8").read(), "build.py", "exec"), ns)
    context = ns["main"](["x", "--", "Greenhouse/Scenes/GlassAtrium", "--no-save", "--no-look", "--samples", str(samples)])
    from Core import driver
    driver.activate_still(context)
    scene = bpy.context.scene
    scene.render.resolution_percentage = int(round(scale * 100))
    layer = scene.view_layers[0]
    groups = {}
    for obj in scene.objects:
        if obj.type == "LIGHT":
            groups[obj.name] = {"kind": "lamp"}
            obj.lightgroup = obj.name
        elif obj.type == "MESH" and emissive_material(obj):
            groups[obj.name] = {"kind": "emissive", "material": emissive_material(obj)}
            obj.lightgroup = obj.name
    scene.world.lightgroup = SKY
    groups[SKY] = {"kind": "sky"}
    for name in groups:
        layer.lightgroups.add(name=name)
    folder = tempfile.mkdtemp(prefix="gh_lightgroups_")
    tree = bpy.data.node_groups.new("LightGroups", "CompositorNodeTree")
    scene.compositing_node_group = tree
    layers = tree.nodes.new("CompositorNodeRLayers")
    output = tree.nodes.new("CompositorNodeOutputFile")
    output.directory = folder
    output.file_name = ""
    output.format.media_type = "IMAGE"
    output.format.file_format = "OPEN_EXR"
    output.format.color_depth = "32"
    for name in groups:
        output.file_output_items.new("RGBA", name)
        source = next(socket for socket in layers.outputs if socket.name.endswith(name) and socket.enabled)
        tree.links.new(source, output.inputs[name])
    scene.render.use_compositing = True
    scene.render.filepath = os.path.join(folder, "combined.png")
    bpy.ops.render.render(write_still=True)
    images = {}
    for file in os.listdir(folder):
        for name in groups:
            if file.startswith(name) and file.endswith(".exr"):
                image = bpy.data.images.load(os.path.join(folder, file), check_existing=False)
                width, height = image.size
                pixels = np.empty(width * height * 4, np.float32)
                image.pixels.foreach_get(pixels)
                bpy.data.images.remove(image)
                images[name] = pixels.reshape(height, width, 4)[::-1, :, :3]
    np.savez_compressed(out, groups=json.dumps(groups), **{f"image:{name}": image for name, image in images.items()})
    print("groups ->", out, sorted(images))


def srgb(linear):
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(np.maximum(linear, 1e-8), 1.0 / 2.4) - 0.055)


def fit(images, reference, size=(217, 300), blur=1.5, prior=0.002, iterations=400):
    """{group: RGB weights} minimising the display-space error."""
    import cv2
    from scipy.optimize import minimize

    def prepare(image):
        return cv2.GaussianBlur(cv2.resize(image.astype(np.float32), size, interpolation=cv2.INTER_AREA), (0, 0), blur)

    names = sorted(images)
    stack = np.stack([prepare(images[name]) for name in names], 0)
    target = prepare(reference)

    def objective(log_weights):
        weights = np.exp(log_weights).reshape(len(names), 3)
        light = np.maximum(np.einsum("ghwc,gc->hwc", stack, weights), 0.0)
        display = np.minimum(srgb(light), 1.0)
        residual = display - target
        charbonnier = np.sqrt(residual * residual + 1e-4)
        slope = np.where(light <= 0.0031308, 12.92, 1.055 / 2.4 * np.power(np.maximum(light, 1e-8), 1.0 / 2.4 - 1.0))
        slope = np.where(display >= 1.0, 0.0, slope)
        pixel_gradient = residual / charbonnier * slope / residual.size
        gradient = np.einsum("ghwc,hwc->gc", stack, pixel_gradient) * weights
        gradient = gradient.ravel() + 2.0 * prior * log_weights / log_weights.size
        return charbonnier.mean() + prior * np.mean(log_weights ** 2), gradient

    result = minimize(objective, np.zeros(len(names) * 3), jac=True, method="L-BFGS-B",
                      bounds=[(-6.0, 4.0)] * (len(names) * 3), options={"maxiter": iterations})
    weights = np.exp(result.x).reshape(len(names), 3)
    print("display error: before %.4f after %.4f" % (objective(np.zeros(len(names) * 3))[0], result.fun))
    return {name: weights[index].tolist() for index, name in enumerate(names)}


def split(weights):
    """(strength, tint): the mean of the RGB weights and the colour they
    leave once it is divided out."""
    strength = float(np.mean(weights))
    return strength, [float(value / strength) for value in weights]


def apply(groups, weights):
    from Core.jsonio import dump
    from Greenhouse import PALETTE
    with open(SCENE_JSON, encoding="utf-8") as handle:
        scene = json.load(handle)
    materials = scene.setdefault("materials", {})

    def tinted(key, tint):
        base = materials.get(f"color:{key}", PALETTE[key])
        materials[f"color:{key}"] = [round(min(channel * factor, 1.0), 4) for channel, factor in zip(base, tint)]

    for name, info in groups.items():
        strength, tint = split(weights[name])
        if info["kind"] == "lamp":
            lamp = next(item for item in scene["lights"] if item["name"] == name)
            lamp["power"] = round(lamp["power"] * strength, 4)
            color = lamp.get("color", [1.0, 1.0, 1.0])
            peak = max(channel * factor for channel, factor in zip(color, tint))
            lamp["color"] = [round(channel * factor / peak, 4) for channel, factor in zip(color, tint)]
            lamp["power"] = round(lamp["power"] * peak, 4)
        elif info["kind"] == "sky":
            scene["sky"]["camera_strength"] = round(scene["sky"]["camera_strength"] * strength, 4)
            scene["sky"]["light_strength"] = round(scene["sky"]["light_strength"] * strength, 4)
            for key in SKY_COLORS:
                tinted(key, tint)
        else:
            key = EMISSIVE_COLORS[info["material"]]
            materials["far_haze_brightness"] = round(materials.get("far_haze_brightness", 1.0) * strength, 4)
            tinted(key, tint)
    dump(scene, SCENE_JSON)
    print("applied to", SCENE_JSON)


def main(argv):
    try:
        import bpy  # noqa: F401
    except ImportError:
        bpy = None
    if bpy is not None:
        samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
        scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.25
        render_groups(os.path.abspath(argv[0]), samples, scale)
        return
    import cv2
    data = np.load(argv[0])
    groups = json.loads(str(data["groups"]))
    images = {name: data[f"image:{name}"] for name in groups}
    height, width = next(iter(images.values())).shape[:2]
    reference = cv2.imread(REFERENCE)[:, :, ::-1].astype(np.float32) / 255.0
    reference = cv2.resize(reference, (width, height), interpolation=cv2.INTER_AREA)
    weights = fit(images, reference)
    print(json.dumps({name: [round(value, 3) for value in rgb] for name, rgb in weights.items()}, indent=1))
    if "--apply" in argv:
        apply(groups, weights)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
