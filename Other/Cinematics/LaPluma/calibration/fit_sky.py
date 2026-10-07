"""
A shot's sky fitted to its reference: the colours of its world and the look of its clouds.

    blender -b --factory-startup -P fit_sky.py -- <frames dir> <shot> [<masks dir> ...] --frames 214,230,262
            [--scale 0.25] [--samples 16] [--rounds 3] [--exclude x0,y0,x1,y1 ...] [--spread 3] [--write]

The shot's sky alone -- its world, its cloud deck, the set's air and sun, through the shot's camera (focused as the
film focuses it: on its performer's bone, the performer posed but not drawn), render settings and look, the
buildings left out -- is rendered at ``scale`` on the ``frames`` and compared with the reference by eye
(:mod:`picture_fit`) on the blocks that show sky (:mod:`sky_reads`, blocks of 1 / ``scale`` pixels, the buildings'
blocks too left out, and the picture's ``exclude`` boxes: what the sky alone cannot draw, the dust a breach throws).
The parameters (:data:`PARAMETERS`: the zenith's and the horizon's colours, the sky's
strength; the clouds' shade below and on top, their whiteness -- no less than half the palette's: a cloud is white
--, density, softness, threshold, gathering, height, thinning with height, billows, erosion and how much they throw
forwards) are turned one after another (:func:`picture_fit.descend`).  With
``write`` the best are written into the shot's sky.
"""
import argparse
import copy
import json
import os
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import picture_fit  # noqa: E402
import sky_reads  # noqa: E402
from Core import render as RND  # noqa: E402
from Cinematics import scenes as SCN  # noqa: E402
from Cinematics.Kit import clouds as CL  # noqa: E402

PARAMETERS = [(("zenith", 0), 0.02, 0.0), (("zenith", 1), 0.03, 0.0), (("zenith", 2), 0.05, 0.0), (("horizon", 0), 0.08, 0.0),
              (("horizon", 1), 0.08, 0.0), (("horizon", 2), 0.08, 0.0), (("strength", None), 0.15, 0.0),
              (("clouds.shade_low", None), 0.1, 0.0), (("clouds.shade_high", None), 0.1, 0.0), (("clouds.whiteness", None), 0.15, 0.5),
              (("clouds.density", None), 0.01, 0.002), (("clouds.soft", None), 0.03, 0.01), (("clouds.threshold", None), 0.03, 0.0),
              (("clouds.gather", None), 0.15, 0.0), (("clouds.height", None), 80.0, 60.0), (("clouds.climb", None), 0.05, 0.0),
              (("clouds.billow", None), 30.0, 10.0), (("clouds.erode", None), 0.1, 0.0), (("clouds.forward", None), 0.1, 0.0)]


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir")
    parser.add_argument("shot")
    parser.add_argument("masks", nargs="*")
    parser.add_argument("--frames", required=True)
    parser.add_argument("--scale", type=float, default=0.25)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--spread", type=float, default=3.0)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def _read(sky, key):
    name, index = key
    if name.startswith("clouds."):
        field = name.split(".", 1)[1]
        clouds = {**CL.CLOUDS, **sky["clouds"]}
        if field == "height":
            return sky["clouds"]["scale"][2] * 2.0
        if field == "whiteness":
            return clouds["color"][0] / CL.CLOUDS["color"][0]
        return clouds[field]
    return sky[name][index] if index is not None else sky[name]


def _changed(sky, key, value):
    sky = copy.deepcopy(sky)
    name, index = key
    if name.startswith("clouds."):
        field = name.split(".", 1)[1]
        clouds = sky["clouds"]
        if field == "height":
            floor = clouds["loc"][2] - clouds["scale"][2]
            clouds["loc"] = [clouds["loc"][0], clouds["loc"][1], floor + value / 2.0]
            clouds["scale"] = [clouds["scale"][0], clouds["scale"][1], value / 2.0]
        elif field == "whiteness":
            clouds["color"] = [channel * value for channel in CL.CLOUDS["color"]]
        else:
            clouds[field] = value
    elif index is not None:
        sky[name] = list(sky[name])
        sky[name][index] = value
    else:
        sky[name] = value
    return sky


class Fit:
    def __init__(self, args):
        self.reads = sky_reads.ShotSky(args.shot, int(round(1.0 / args.scale)))
        shot, spec = self.reads.shot, self.reads.spec
        scene = bpy.context.scene
        for obj in self.reads.set_collection.all_objects:
            obj.hide_render = obj not in self.reads.air
        lights = sky_reads.SC.collection("Fit Lights", parent=scene.collection)
        for lamp in spec.get("lights", []):
            SCN.build_lamp(lamp, lights)
        self.sun = next((lamp for lamp in spec.get("lights", []) if lamp["light"] == "SUN"), None)
        settings = shot["render"]
        RND.ENGINES[settings["engine"]](samples=args.samples, **settings.get(settings["engine"].lower(), {}))
        scene.render.resolution_x, scene.render.resolution_y = self.reads.width, self.reads.height
        scene.render.resolution_percentage = int(round(100 * args.scale))
        scene.camera = self.reads.camera
        dof = shot["camera"].get("dof")
        if dof:
            lens = self.reads.camera.data.dof
            lens.use_dof = True
            lens.aperture_fstop = dof["fstop"]
            lens.focus_object = self.reads.performer(dof["focus"]["cast"])
            lens.focus_subtarget = dof["focus"]["bone"]
        RND.color_management(settings.get("view", "AgX"), settings.get("look"), 0.0)
        RND.compositor(shot.get("look", {}))
        self.folder = tempfile.mkdtemp(prefix="fit_sky_")
        self.frames = [int(value) for value in args.frames.split(",")]
        pictures, weights = {}, {}
        for frame in self.frames:
            boxes = [[int(value) for value in box.split(",")] for box in args.exclude]
            pictures[frame], blocked = self.reads.read(args.frames_dir, args.masks, frame, boxes)
            origin, rays = self.reads.rays(frame)
            blocked |= self.reads.hidden_by_set(origin, rays, ~blocked, 8000.0)
            weights[frame] = (~blocked).astype(float)
            print(f"[fit sky] {args.shot} {frame}: {int(weights[frame].sum())} sky blocks of {blocked.size}", flush=True)
        self.measure = picture_fit.Measure(pictures, weights, spread=args.spread)
        self.built = None

    def _apply(self, sky):
        if self.built is not None:
            world, collection = self.built
            for obj in list(collection.objects):
                bpy.data.objects.remove(obj)
            bpy.data.collections.remove(collection)
        world, collection, _files = SCN.build_sky(sky_reads.FILM, sky, self.sun, "Fit", bpy.context.scene.collection)
        bpy.context.scene.world = world
        self.built = (world, collection)

    def score(self, sky):
        self._apply(sky)
        scene = bpy.context.scene
        parts = []
        for frame in self.frames:
            scene.frame_set(frame)
            scene.render.filepath = os.path.join(self.folder, f"f{frame}.png")
            bpy.ops.render.render(write_still=True)
            parts.append(self.measure.distance(frame, sky_reads.image(scene.render.filepath)))
        return sum(parts) / len(parts), parts


def main():
    args = _arguments()
    fit = Fit(args)
    sky = copy.deepcopy(fit.reads.sky)
    sky["clouds"] = {"color": CL.CLOUDS["color"], **sky["clouds"]}
    sky, best = picture_fit.descend(sky, PARAMETERS, fit.score, args.rounds, _read, _changed,
                                    lambda line: print(f"[fit sky] {line}", flush=True))
    print(f"[fit sky] best {best:.3f}: {json.dumps({key: sky[key] for key in ('zenith', 'horizon', 'strength', 'clouds') if key in sky})}",
          flush=True)
    if args.write:
        path = os.path.join(sky_reads.FILM, "shots", f"{args.shot}.json")
        data = json.load(open(path, encoding="utf-8"))
        set_sky = fit.reads.spec["sky"]
        changes = {key: sky[key] for key in ("zenith", "horizon", "strength") if sky.get(key) != set_sky.get(key)}
        clouds = {key: value for key, value in sky["clouds"].items() if set_sky.get("clouds", {}).get(key) != value}
        data["sky"] = {**data.get("sky", {}), **changes, "clouds": clouds}
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print(f"[fit sky] written into {path}", flush=True)


if __name__ == "__main__":
    main()
