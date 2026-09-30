"""
Light balancing as an inverse problem.

Light transport is linear in the light sources, so the atrium is rendered
once with every source in its own Cycles light group: each lamp, the sky
(the world) and every emissive object (the city smog glows with the skylight
it scatters in).  Any balance is then sum_g w_g * I_g with one strength per
group.  The colours are the scene's -- the sun's, the hazy dome's, the
smog's pink: free, they would tint every surface and every reflection to
imitate the painting's colours instead of leaving them to the materials.
The strengths are fitted so that this sum, after the Standard view
transform (sRGB encoding, clipping at white), reproduces the painting with
the figure removed: a robust (Charbonnier) error on downsampled, blurred
display values, optimised over log-strengths with L-BFGS, a weak prior
keeping every strength near 1.

Two steps, because Blender's Python has no SciPy::

    blender -b -P Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_lights.py -- groups.npz [--samples 64] [--scale 0.25]
    python Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_lights.py groups.npz [--apply]

``--apply`` multiplies the scene's strengths by the result: a lamp's power,
the sky's strength, an emissive material's brightness parameter
(``EMISSIVE``).  Render ungraded; refit the grade afterwards.
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
EMISSIVE = {"GH.Smog": "smog_brightness"}


def emissive_material(obj):
    """Name of the library material with emission an object renders with."""
    evaluated = obj.evaluated_get(__import__("bpy").context.evaluated_depsgraph_get())
    for slot in evaluated.material_slots:
        if slot.material is not None and slot.material.name in EMISSIVE:
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


def fit(images, reference, size=(217, 300), blur=1.5, prior=0.002, iterations=400, grid=(3, 4), contrast=0.5):
    """{group: strength} minimising the display-space error.

    A pixelwise error alone favours flat light -- where leaves and shadows
    do not line up leaf for leaf, averaging them scores best -- so a second,
    derivative-free stage adds ``contrast`` times the mismatch of each
    ``grid`` region's 5th, 50th and 95th luminance percentile: the light
    must also give every region the painting's darks and highlights."""
    import cv2
    from scipy.optimize import minimize

    def prepare(image):
        return cv2.GaussianBlur(cv2.resize(image.astype(np.float32), size, interpolation=cv2.INTER_AREA), (0, 0), blur)

    names = sorted(images)
    stack = np.stack([prepare(images[name]) for name in names], 0)
    target = prepare(reference)

    def objective(log_weights):
        weights = np.exp(log_weights)
        light = np.maximum(np.einsum("ghwc,g->hwc", stack, weights), 0.0)
        display = np.minimum(srgb(light), 1.0)
        residual = display - target
        charbonnier = np.sqrt(residual * residual + 1e-4)
        slope = np.where(light <= 0.0031308, 12.92, 1.055 / 2.4 * np.power(np.maximum(light, 1e-8), 1.0 / 2.4 - 1.0))
        slope = np.where(display >= 1.0, 0.0, slope)
        pixel_gradient = residual / charbonnier * slope / residual.size
        gradient = np.einsum("ghwc,hwc->g", stack, pixel_gradient) * weights + 2.0 * prior * log_weights / log_weights.size
        return charbonnier.mean() + prior * np.mean(log_weights ** 2), gradient

    start = np.zeros(len(names))
    bounds = [(-6.0, 4.0)] * len(names)
    result = minimize(objective, start, jac=True, method="L-BFGS-B", bounds=bounds, options={"maxiter": iterations})
    print("display error: before %.4f after %.4f" % (objective(start)[0], result.fun))

    sharp = np.stack([cv2.resize(images[name].astype(np.float32), size, interpolation=cv2.INTER_AREA) for name in names], 0)
    sharp_target = cv2.resize(reference.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    luma = np.array([0.2126, 0.7152, 0.0722])
    rows, cols = grid
    height, width = sharp_target.shape[:2]
    cells = [(slice(r * height // rows, (r + 1) * height // rows), slice(c * width // cols, (c + 1) * width // cols)) for r in range(rows) for c in range(cols)]
    quantiles = [5, 50, 95]
    target_levels = np.array([np.percentile(sharp_target[cell] @ luma, quantiles) for cell in cells])

    def levels(log_weights):
        display = np.minimum(srgb(np.maximum(np.einsum("ghwc,g->hwc", sharp, np.exp(log_weights)), 0.0)), 1.0) @ luma
        return np.array([np.percentile(display[cell], quantiles) for cell in cells])

    def combined(log_weights):
        return objective(log_weights)[0] + contrast * np.mean(np.abs(levels(log_weights) - target_levels))

    second = minimize(combined, result.x, method="Powell", bounds=bounds, options={"maxiter": 4000, "xtol": 1e-3, "ftol": 1e-5})
    best = second.x if second.fun < combined(result.x) else result.x
    print("with contrast: %.4f (display %.4f, levels %.4f)"
          % (combined(best), objective(best)[0], np.mean(np.abs(levels(best) - target_levels))))
    return {name: float(np.exp(best[index])) for index, name in enumerate(names)}


def apply(groups, weights):
    from Core.jsonio import dump
    with open(SCENE_JSON, encoding="utf-8") as handle:
        scene = json.load(handle)
    materials = scene.setdefault("materials", {})
    for name, info in groups.items():
        strength = weights[name]
        if info["kind"] == "lamp":
            lamp = next(item for item in scene["lights"] if item["name"] == name)
            lamp["power"] = round(lamp["power"] * strength, 4)
        elif info["kind"] == "sky":
            scene["sky"]["camera_strength"] = round(scene["sky"]["camera_strength"] * strength, 4)
            scene["sky"]["light_strength"] = round(scene["sky"]["light_strength"] * strength, 4)
        else:
            key = EMISSIVE[info["material"]]
            materials[key] = round(materials.get(key, 1.0) * strength, 4)
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
    print(json.dumps({name: round(value, 4) for name, value in weights.items()}))
    if "--apply" in argv:
        apply(groups, weights)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
