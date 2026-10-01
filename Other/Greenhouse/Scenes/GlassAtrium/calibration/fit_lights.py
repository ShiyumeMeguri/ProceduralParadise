"""
Light balancing as an inverse problem.

Light transport is linear in the light sources, so the atrium is rendered
once per group of sources, every other source dark: the daylight (the sun
lamps and the sky, the world -- skylight is sunlight scattered by the air,
so the two keep the balance the scene gives them: ``sky`` strengths at
``sun_ratio`` of the sun's power), every other lamp, and every glowing
material (the city smog glows with the skylight it scatters in; dark, it
still absorbs).  Any balance is then sum_g w_g * I_g with one strength per
group.  The colours are the
scene's -- the sun's, the hazy dome's, the smog's pink: free, they would
tint every surface and every reflection to imitate the painting's colours
instead of leaving them to the materials; and a sky free of the sun is
fitted as bright as the painting's pale shadows ask, which no sky is: every
pane would mirror it as a milky veil.
The strengths are fitted so that this sum, after the Standard view
transform (sRGB encoding, clipping at white), reproduces the painting with
the figure removed.  Leaves, flags and shadows cannot line up with the
painted ones stroke for stroke, and where they do not, a pixelwise error
is least for flat light -- so the fit also matches the spread of CIELAB
colours (``QUANTILES``) in each horizontal band (``BANDS``): the band's
darks, mid-tones and highlights and their hues, next to the error on
blurred display values that keeps the layout of light and dark.  Powell's
method from several starts (every strength 1, and each group in turn
brighter) finds the lowest of the objective's valleys.

Two steps, because Blender's Python has no SciPy::

    blender -b -P Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_lights.py -- groups.npz [--samples 64] [--scale 0.25]
    python Other/Greenhouse/Scenes/GlassAtrium/calibration/fit_lights.py groups.npz [--apply]

``--apply`` multiplies the scene's strengths by the result: the daylight's
(the sun lamps' power, and the sky's strengths set to ``sun_ratio`` of
it), another lamp's power, an emissive material's brightness parameter
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
DAYLIGHT = "daylight"
EMISSIVE = {"GH.Smog": "smog_brightness"}
BLUR = 1.0 / 60.0
BANDS = (0.0, 0.2, 0.4, 0.7, 1.0)
QUANTILES = np.linspace(5.0, 95.0, 10)
LAB_RANGE = np.array([100.0, 60.0, 60.0])


def glows(material):
    """The Emission nodes of ``material`` with the colours they glow."""
    return [(node, tuple(node.inputs["Color"].default_value)) for node in material.node_tree.nodes if node.type == "EMISSION"]


def render_groups(out, samples, scale):
    """Renders the shot once per group -- the daylight, each other lamp,
    each glowing material -- with every other source dark: lamps hidden,
    the sky a black world, the other glows black (their media still
    absorb)."""
    import bpy
    import tempfile
    ns = {}
    exec(compile(open(os.path.join(ROOT, "Other", "build.py"), encoding="utf-8").read(), "build.py", "exec"), ns)
    context = ns["main"](["x", "--", "Greenhouse/Scenes/GlassAtrium", "--no-save", "--no-look", "--samples", str(samples)])
    from Core import driver
    driver.activate_still(context)
    scene = bpy.context.scene
    scene.render.resolution_percentage = int(round(scale * 100))
    scene.render.use_compositing = False
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    sky = scene.world
    dark = bpy.data.worlds.new("__dark")
    lamps = [obj for obj in scene.objects if obj.type == "LIGHT"]
    groups = {DAYLIGHT: {"kind": "daylight"}}
    groups.update({lamp.name: {"kind": "lamp"} for lamp in lamps if lamp.data.type != "SUN"})
    emissive = {name: glows(bpy.data.materials[name]) for name in EMISSIVE if name in bpy.data.materials}
    groups.update({name: {"kind": "emissive", "material": name} for name in emissive})
    folder = tempfile.mkdtemp(prefix="gh_lightgroups_")
    images = {}
    for name, info in groups.items():
        scene.world = sky if info["kind"] == "daylight" else dark
        for lamp in lamps:
            lamp.hide_render = not (lamp.name == name or (info["kind"] == "daylight" and lamp.data.type == "SUN"))
        for material, nodes in emissive.items():
            for node, colour in nodes:
                node.inputs["Color"].default_value = colour if material == name else (0.0, 0.0, 0.0, 1.0)
        scene.render.filepath = os.path.join(folder, name + ".exr")
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(scene.render.filepath, check_existing=False)
        width, height = image.size
        pixels = np.empty(width * height * 4, np.float32)
        image.pixels.foreach_get(pixels)
        bpy.data.images.remove(image)
        images[name] = pixels.reshape(height, width, 4)[::-1, :, :3]
    np.savez_compressed(out, groups=json.dumps(groups), **{f"image:{name}": image for name, image in images.items()})
    print("groups ->", out, sorted(images))


def srgb(linear):
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(np.maximum(linear, 1e-8), 1.0 / 2.4) - 0.055)


def band_quantiles(display):
    """CIELAB ``QUANTILES`` of every horizontal band of a display image."""
    import cv2
    lab = cv2.cvtColor(display.astype(np.float32), cv2.COLOR_RGB2Lab)
    height = display.shape[0]
    return np.stack([np.percentile(lab[int(top * height):int(bottom * height)].reshape(-1, 3), QUANTILES, axis=0)
                     for top, bottom in zip(BANDS[:-1], BANDS[1:])])


class Target:
    """The painting as the fits compare a display image of ``size`` with
    it: ``terms`` gives the error on display values blurred by ``BLUR`` of
    the width, and the distance of the band quantiles."""

    def __init__(self, reference, size):
        import cv2
        self.display = cv2.resize(reference.astype(np.float32), size, interpolation=cv2.INTER_AREA)
        self.sigma = size[0] * BLUR
        self.blurred = cv2.GaussianBlur(self.display, (0, 0), self.sigma)
        self.bands = band_quantiles(self.display)

    def terms(self, image):
        import cv2
        layout = float(np.mean(np.abs(cv2.GaussianBlur(image, (0, 0), self.sigma) - self.blurred)))
        bands = float(np.mean(np.abs(band_quantiles(image) - self.bands) / LAB_RANGE))
        return layout, bands


def fit(images, reference, prior=0.002, iterations=3000, lift=2.0):
    """{group: strength} minimising the band-quantile distance plus the
    error on blurred display values (:class:`Target`)."""
    import cv2
    from scipy.optimize import minimize

    names = sorted(images)
    height, width = reference.shape[:2]
    size = (width // 2, height // 2)
    stack = np.stack([cv2.resize(images[name].astype(np.float32), size, interpolation=cv2.INTER_AREA) for name in names], 0)
    target = Target(reference, size)

    def display(log_weights):
        light = np.maximum(np.einsum("ghwc,g->hwc", stack, np.exp(log_weights)), 0.0)
        return np.minimum(srgb(light), 1.0).astype(np.float32)

    def terms(log_weights):
        return target.terms(display(log_weights))

    def objective(log_weights):
        return sum(terms(log_weights)) + prior * float(np.mean(log_weights ** 2))

    starts = [np.zeros(len(names))] + [np.eye(len(names))[index] * lift for index in range(len(names))]
    runs = [minimize(objective, start, method="Powell", bounds=[(-6.0, 5.0)] * len(names),
                     options={"maxiter": iterations, "xtol": 1e-3, "ftol": 1e-6}) for start in starts]
    best = min(runs, key=lambda run: run.fun)
    for label, point in (("before", starts[0]), ("after", best.x)):
        print("%s: layout %.4f, bands %.4f" % ((label,) + terms(point)))
    return {name: float(np.exp(best.x[index])) for index, name in enumerate(names)}


def apply(groups, weights):
    from Core.jsonio import dump
    with open(SCENE_JSON, encoding="utf-8") as handle:
        scene = json.load(handle)
    materials = scene.setdefault("materials", {})
    for name, info in groups.items():
        strength = weights[name]
        if info["kind"] == "daylight":
            suns = [item for item in scene["lights"] if item["light"] == "SUN"]
            for sun in suns:
                sun["power"] = round(sun["power"] * strength, 4)
            sky = scene["sky"]
            sky["light_strength"] = round(sky["sun_ratio"] * max(sun["power"] for sun in suns), 4)
        elif info["kind"] == "lamp":
            lamp = next(item for item in scene["lights"] if item["name"] == name)
            lamp["power"] = round(lamp["power"] * strength, 4)
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
