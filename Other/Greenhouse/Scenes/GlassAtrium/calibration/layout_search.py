"""
The free parts of the garden's layout, chosen against the painting.

Where the planting scatters its plants and how each specimen spreads its
leaves is random -- one garden among equally good ones; where a painted
specimen stands and how large it grows is known only to the width of its
painted mass, which way it faces not at all, and where the sun stands only
to the few degrees its painted shafts and shadows give.  So these are
chosen as the painting's: object by object, one field is tried at a few
other values, the painting's camera view rendered for each, and the value
that brings the render closest to the painting kept.  The fields
(``FIELDS``):

* ``seed`` -- the object's ``Seed`` input, tried at ``--tries`` other values;
* ``move`` -- its position, shifted by ``--step`` metres (default 0.2)
  along +X, -X, +Y and -Y;
* ``turn`` -- its heading, turned by ``--tries`` multiples of ``--step``
  degrees (default 45);
* ``size`` -- its scale, larger and smaller by the fraction ``--step``
  (default 0.1);
* ``aim`` -- a lamp's direction, its azimuth and its elevation turned by
  ``--step`` degrees (default 2) either way;
* ``input`` -- the geometry-nodes input named by ``--input`` (a leaflet's
  width, a frond count), larger and smaller by the fraction ``--step``
  (default 0.2): what the painting shows of a plant's make only to within
  the width of a painted stroke.

Closeness is the reported measure: the error of colours blurred by
``BLUR`` of the image width, plus ``PIXEL_WEIGHT`` of the error pixel by
pixel.  Choosing among whole renders by the measure itself (and not, say,
region by region) keeps the choice honest: seed noise can only make a
whole garden better or worse, never be picked piecewise.

One Blender session changes the objects in place and renders again, so a
try costs one small render::

    blender -b -P Other/Greenhouse/Scenes/GlassAtrium/calibration/layout_search.py -- "Ground Painted,Areca Palm" [--field seed|move|turn|size|aim|input] [--input NAME] [--tries 6] [--step S] [--rounds 1] [--samples 32] [--scale 0.25]

writes the chosen values into scene.json.  Run it last: lighting and
material fits change what the best garden is.
"""
from __future__ import annotations

import json
import math
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
    """``image`` blurred by a Gaussian of ``sigma`` pixels, its edges padded
    by mirroring."""
    pad = int(np.ceil(3 * sigma))
    padded = np.pad(image, ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    height, width = padded.shape[:2]
    fy = np.fft.fftfreq(height)[:, None]
    fx = np.fft.fftfreq(width)[None, :]
    kernel = np.exp(-2.0 * (np.pi * sigma) ** 2 * (fx * fx + fy * fy))
    blurred = np.real(np.fft.ifft2(np.fft.fft2(padded, axes=(0, 1)) * kernel[:, :, None], axes=(0, 1)))
    return blurred[pad:-pad, pad:-pad]


class Seed:
    """The object's geometry-nodes ``Seed``."""

    def __init__(self, option):
        self.tries = option("--tries", 6, int)

    @staticmethod
    def modifier(obj):
        return next(m for m in obj.modifiers if m.type == "NODES")

    def get(self, obj):
        from Core import scene as SC
        return SC.get_gn_input(self.modifier(obj), "Seed")

    def set(self, obj, value):
        from Core import scene as SC
        SC.set_gn_inputs(self.modifier(obj), {"Seed": value})

    def candidates(self, value):
        return [value + index * STRIDE for index in range(1, self.tries + 1)]

    def store(self, item, value):
        item.setdefault("inputs", {})["Seed"] = value

    def show(self, value):
        return "%d" % value


class Move:
    """The object's position on the floor."""

    def __init__(self, option):
        self.distance = option("--step", 0.2, float)

    def get(self, obj):
        return (obj.location.x, obj.location.y)

    def set(self, obj, value):
        obj.location.x, obj.location.y = value

    def candidates(self, value):
        x, y = value
        return [(x + dx, y + dy) for dx, dy in ((self.distance, 0.0), (-self.distance, 0.0), (0.0, self.distance), (0.0, -self.distance))]

    def store(self, item, value):
        item["loc"] = [round(value[0], 3), round(value[1], 3)] + list(item.get("loc", [0.0, 0.0, 0.0]))[2:]

    def show(self, value):
        return "(%.3f, %.3f)" % value


class Turn:
    """The object's heading, degrees about Z."""

    def __init__(self, option):
        self.tries, self.angle = option("--tries", 6, int), option("--step", 45.0, float)

    def get(self, obj):
        return math.degrees(obj.rotation_euler.z)

    def set(self, obj, value):
        obj.rotation_euler.z = math.radians(value)

    def candidates(self, value):
        return [(value + index * self.angle) % 360.0 for index in range(1, self.tries + 1)]

    def store(self, item, value):
        rotation = list(item.get("rot", [0.0, 0.0, 0.0]))
        rotation[2] = round(value, 1)
        item["rot"] = rotation

    def show(self, value):
        return "%g" % value


class Size:
    """The object's uniform scale."""

    def __init__(self, option):
        self.fraction = option("--step", 0.1, float)

    def get(self, obj):
        return obj.scale.x

    def set(self, obj, value):
        obj.scale = (value, value, value)

    def candidates(self, value):
        return [value * (1.0 + self.fraction), value * (1.0 - self.fraction)]

    def store(self, item, value):
        item["scale"] = round(value, 3)

    def show(self, value):
        return "%.3f" % value


class Aim:
    """A lamp's direction (towards the light) as azimuth and elevation,
    degrees."""

    def __init__(self, option):
        self.angle = option("--step", 2.0, float)

    def get(self, obj):
        from mathutils import Vector
        x, y, z = obj.rotation_euler.to_matrix() @ Vector((0.0, 0.0, 1.0))
        return (math.degrees(math.atan2(y, x)), math.degrees(math.asin(max(-1.0, min(1.0, z)))))

    @staticmethod
    def vector(value):
        azimuth, elevation = (math.radians(angle) for angle in value)
        return (math.cos(elevation) * math.cos(azimuth), math.cos(elevation) * math.sin(azimuth), math.sin(elevation))

    def set(self, obj, value):
        from mathutils import Vector
        obj.rotation_euler = (-Vector(self.vector(value))).to_track_quat("-Z", "Y").to_euler()

    def candidates(self, value):
        azimuth, elevation = value
        return [(azimuth + self.angle, elevation), (azimuth - self.angle, elevation), (azimuth, elevation + self.angle), (azimuth, elevation - self.angle)]

    def store(self, item, value):
        item["direction"] = [round(component, 4) for component in self.vector(value)]

    def show(self, value):
        return "(azimuth %.1f, elevation %.1f)" % value


class Input:
    """A numeric geometry-nodes input of the object (``--input``), larger
    and smaller by the fraction ``--step``; whole numbers stay whole."""

    def __init__(self, option):
        self.name, self.fraction = option("--input", None, str), option("--step", 0.2, float)

    def get(self, obj):
        from Core import scene as SC
        return SC.get_gn_input(Seed.modifier(obj), self.name)

    def set(self, obj, value):
        from Core import scene as SC
        SC.set_gn_inputs(Seed.modifier(obj), {self.name: value})

    def candidates(self, value):
        if isinstance(value, int):
            return sorted({max(value + delta, 1) for delta in (-max(round(value * self.fraction), 1), max(round(value * self.fraction), 1))} - {value})
        return [value * (1.0 + self.fraction), value * (1.0 - self.fraction)]

    def store(self, item, value):
        item.setdefault("inputs", {})[self.name] = value if isinstance(value, int) else round(value, 4)

    def show(self, value):
        return "%s %s" % (self.name, value if isinstance(value, int) else "%.4f" % value)


FIELDS = {"seed": Seed, "move": Move, "turn": Turn, "size": Size, "aim": Aim, "input": Input}


def main(argv):
    import bpy
    from Core import driver, jsonio

    def option(name, default, kind):
        return kind(argv[argv.index(name) + 1]) if name in argv else default

    names = [name.strip() for name in argv[0].split(",") if name.strip()]
    kind = option("--field", "seed", str)
    field = FIELDS[kind](option)
    rounds = option("--rounds", 1, int)
    samples = option("--samples", 32, int)
    scale = option("--scale", 0.25, float)
    ns = {}
    exec(compile(open(os.path.join(ROOT, "Other", "build.py"), encoding="utf-8").read(), "build.py", "exec"), ns)
    context = ns["main"](["x", "--", "Greenhouse/Scenes/GlassAtrium", "--no-save", "--samples", str(samples)])
    driver.activate_still(context)
    scene = bpy.context.scene
    scene.render.resolution_percentage = int(round(scale * 100))
    frame = tempfile.mkdtemp(prefix="gh_layout_")
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

    best = measure()
    print("start: blurred %.4f, pixel %.4f" % best[1:], flush=True)
    chosen = {}
    for _ in range(rounds):
        for name in names:
            obj = bpy.data.objects[name]
            start = field.get(obj)
            keep = start
            for value in field.candidates(start):
                field.set(obj, value)
                result = measure()
                if result[0] < best[0]:
                    best, keep = result, value
            field.set(obj, keep)
            if keep != start:
                chosen[name] = keep
            print("%-26s %s %s -> %s   blurred %.4f, pixel %.4f" % ((name, kind, field.show(start), field.show(keep)) + best[1:]), flush=True)
    with open(SCENE_JSON, encoding="utf-8") as handle:
        data = json.load(handle)
    items = [item for group in data["collections"].values() for item in group] + data.get("lights", [])
    for item in items:
        if item["name"] in chosen:
            field.store(item, chosen[item["name"]])
    jsonio.dump(data, SCENE_JSON)
    print("%d %s choices written to %s" % (len(chosen), kind, SCENE_JSON))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
