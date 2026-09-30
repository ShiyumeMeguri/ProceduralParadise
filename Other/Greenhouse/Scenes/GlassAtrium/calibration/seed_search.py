"""
Seeds of the random garden, chosen against the painting.

Where the planting scatters its plants and how each specimen spreads its
leaves is random -- one garden among equally good ones -- so the seeds are
chosen as the painting's: object by object, a listed object's ``Seed`` is
tried at ``--tries`` other values, the painting's camera view rendered for
each, and the seed that brings the render closest to the painting kept.
Closeness is the reported measure: the error of colours blurred by
``BLUR`` of the image width, plus ``PIXEL_WEIGHT`` of the error pixel by
pixel.  Choosing among whole renders by the measure itself (and not, say,
region by region) keeps the choice honest: seed noise can only make a
whole garden better or worse, never be picked piecewise.

One Blender session sets the seeds in place and renders again, so a try
costs one small render::

    blender -b -P Other/Greenhouse/Scenes/GlassAtrium/calibration/seed_search.py -- "Shrubs Painted,Areca Palm" [--tries 6] [--rounds 1] [--samples 32] [--scale 0.25]

writes the chosen seeds into scene.json.  Run it last: lighting and
material fits change what the best garden is.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SCENE, "..", "..", "..", ".."))
for path in (ROOT, os.path.join(ROOT, "Other")):
    if path not in sys.path:
        sys.path.insert(0, path)

import numpy as np  # noqa: E402

SCENE_JSON = os.path.join(SCENE, "scene.json")
REFERENCE = os.path.join(SCENE, "Reference", "Nitia_clean.webp")
BLUR = 1.0 / 60.0
PIXEL_WEIGHT = 0.25
STRIDE = 97


def display(path, size=None):
    """RGB display values (0..1) of an image file, box-filtered to ``size``."""
    import bpy
    image = bpy.data.images.load(path, check_existing=False)
    if size is not None and tuple(image.size) != size:
        image.scale(*size)
    width, height = image.size
    pixels = np.empty(width * height * 4, np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape(height, width, 4)[::-1, :, :3]


def gaussian(image, sigma):
    """``image`` blurred by a Gaussian of ``sigma`` pixels (periodic edges
    padded away by mirroring)."""
    pad = int(np.ceil(3 * sigma))
    padded = np.pad(image, ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    height, width = padded.shape[:2]
    fy = np.fft.fftfreq(height)[:, None]
    fx = np.fft.fftfreq(width)[None, :]
    kernel = np.exp(-2.0 * (np.pi * sigma) ** 2 * (fx * fx + fy * fy))
    blurred = np.real(np.fft.ifft2(np.fft.fft2(padded, axes=(0, 1)) * kernel[:, :, None], axes=(0, 1)))
    return blurred[pad:-pad, pad:-pad]


def main(argv):
    import bpy
    from Core import driver, jsonio, scene as SC
    names = [name.strip() for name in argv[0].split(",") if name.strip()]
    tries = int(argv[argv.index("--tries") + 1]) if "--tries" in argv else 6
    rounds = int(argv[argv.index("--rounds") + 1]) if "--rounds" in argv else 1
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
    scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.25
    ns = {}
    exec(compile(open(os.path.join(ROOT, "Other", "build.py"), encoding="utf-8").read(), "build.py", "exec"), ns)
    context = ns["main"](["x", "--", "Greenhouse/Scenes/GlassAtrium", "--no-save", "--samples", str(samples)])
    driver.activate_still(context)
    scene = bpy.context.scene
    scene.render.resolution_percentage = int(round(scale * 100))
    frame = tempfile.mkdtemp(prefix="gh_seeds_")
    scene.render.filepath = os.path.join(frame, "try.png")
    size = (scene.render.resolution_x * scene.render.resolution_percentage // 100,
            scene.render.resolution_y * scene.render.resolution_percentage // 100)
    target = display(REFERENCE, size)
    sigma = size[0] * BLUR
    target_blurred = gaussian(target, sigma)

    def measure():
        bpy.ops.render.render(write_still=True)
        image = display(scene.render.filepath)
        blurred = float(np.mean(np.abs(gaussian(image, sigma) - target_blurred)))
        pixel = float(np.mean(np.abs(image - target)))
        return blurred + PIXEL_WEIGHT * pixel, blurred, pixel

    def modifier(name):
        return next(m for m in bpy.data.objects[name].modifiers if m.type == "NODES")

    best = measure()
    print("start: blurred %.4f, pixel %.4f" % best[1:], flush=True)
    chosen = {}
    for _ in range(rounds):
        for name in names:
            mod = modifier(name)
            start = SC.get_gn_input(mod, "Seed")
            keep = start
            for step in range(1, tries + 1):
                SC.set_gn_inputs(mod, {"Seed": start + step * STRIDE})
                bpy.data.objects[name].update_tag()
                result = measure()
                if result[0] < best[0]:
                    best, keep = result, start + step * STRIDE
            SC.set_gn_inputs(mod, {"Seed": keep})
            bpy.data.objects[name].update_tag()
            chosen[name] = keep
            print("%-26s seed %d -> %d   blurred %.4f, pixel %.4f" % ((name, start, keep) + best[1:]), flush=True)
    with open(SCENE_JSON, encoding="utf-8") as handle:
        data = json.load(handle)
    for group in data["collections"].values():
        for item in group:
            if item["name"] in chosen:
                item.setdefault("inputs", {})["Seed"] = chosen[item["name"]]
    jsonio.dump(data, SCENE_JSON)
    print("seeds written to", SCENE_JSON)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
