"""
A shot's set lit and coloured as its reference shows it: its lamps, the parameters and colours of its materials, its
sky.

    blender -b --factory-startup -P fit_set.py -- <frames dir> <shot> <spec.json> [<masks dir> ...] [--write]

The shot's set as the shot renders it -- its items (what is there for a while too, while it is), lamps and sky,
through the shot's camera (focused as the film focuses it, on its performer's bone, the performer posed but not
drawn), render settings and look -- is rendered at the spec's ``scale`` on its ``frames`` and compared with the
reference on the blocks the masks leave (the cast and what it holds) by eye (:mod:`picture_fit`, leaving out the
worst ``trim`` of the blocks: the shot's titles and cards, drawn over the picture, are not the set's).  The spec names
what is turned and by how much a step::

    {"frames": [700], "scale": 0.25, "trim": 0.15, "rounds": 4,
     "parameters": [{"light": "Window Light", "power": 600.0}, {"light": "Window Light", "color": 0.05},
                    {"material": "CIN.HallGlow.strength", "step": 2.0}, {"material": "color:hall_wall", "step": 0.05},
                    {"sky": "zenith", "step": 0.05}, ...]}

a colour turned channel by channel; a material parameter the set does not give starts from the entry's ``start``
(the library's own value), a colour from the palette's.  With ``write`` the best lamps and materials (and sky, if
fitted) are written into the set.
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
from Cinematics.Kit import materials as M  # noqa: E402


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir")
    parser.add_argument("shot")
    parser.add_argument("spec")
    parser.add_argument("masks", nargs="*")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def _parameters(spec, state):
    """The turned values as (key, step, lowest): a key is (part, name, field, channel)."""
    keys = []
    for entry in spec["parameters"]:
        if "light" in entry:
            lamp = next(lamp for lamp in state["lights"] if lamp["name"] == entry["light"])
            if "power" in entry:
                keys.append((("lights", entry["light"], "power", None), entry["power"], 0.0))
            if "color" in entry:
                keys += [(("lights", entry["light"], "color", channel), entry["color"], 0.0) for channel in range(len(lamp["color"]))]
        elif "material" in entry:
            value = state["materials"][entry["material"]]
            channels = range(len(value)) if isinstance(value, list) else [None]
            keys += [(("materials", entry["material"], None, channel), entry["step"], 0.0) for channel in channels]
        elif "sky" in entry:
            value = state["sky"][entry["sky"]]
            channels = range(len(value)) if isinstance(value, list) else [None]
            keys += [(("sky", entry["sky"], None, channel), entry["step"], 0.0) for channel in channels]
    return keys


def _read(state, key):
    part, name, field, channel = key
    if part == "lights":
        value = next(lamp for lamp in state["lights"] if lamp["name"] == name)[field]
    else:
        value = state[part][name]
    return value[channel] if channel is not None else value


def _changed(state, key, value):
    state = copy.deepcopy(state)
    part, name, field, channel = key
    holder, slot = (next(lamp for lamp in state["lights"] if lamp["name"] == name), field) if part == "lights" else (state[part], name)
    if channel is None:
        holder[slot] = value
    else:
        holder[slot] = list(holder[slot])
        holder[slot][channel] = value
    return state


class Fit:
    def __init__(self, args, spec):
        self.reads = sky_reads.ShotSky(args.shot, int(round(1.0 / spec.get("scale", 0.25))), whole=True)
        shot, set_spec = self.reads.shot, self.reads.spec
        scene = bpy.context.scene
        lights = sky_reads.SC.collection("Fit Lights", parent=scene.collection)
        self.lamps = {lamp["name"]: SCN.build_lamp(lamp, lights) for lamp in set_spec.get("lights", [])}
        self.sun = next((lamp for lamp in set_spec.get("lights", []) if lamp["light"] == "SUN"), None)
        settings = shot["render"]
        RND.ENGINES[settings["engine"]](samples=spec.get("samples", 16), **settings.get(settings["engine"].lower(), {}))
        scene.render.resolution_x, scene.render.resolution_y = self.reads.width, self.reads.height
        scene.render.resolution_percentage = int(round(100 * spec.get("scale", 0.25)))
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
        self.folder = tempfile.mkdtemp(prefix="fit_set_")
        self.frames = spec["frames"]
        pictures, weights = {}, {}
        for frame in self.frames:
            pictures[frame], blocked = self.reads.read(args.frames_dir, args.masks, frame)
            weights[frame] = (~blocked).astype(float)
        self.measure = picture_fit.Measure(pictures, weights, spec.get("trim", 0.0))
        self.sky = None

    def _apply(self, state):
        for lamp in state["lights"]:
            data = self.lamps[lamp["name"]].data
            data.energy = lamp["power"]
            data.color = lamp["color"]
        SCN.set_materials({"materials": state["materials"]})
        for name, builder in M.LIBRARY.builders.items():
            material = bpy.data.materials.get(name)
            if material is not None and material.get(M.LIBRARY.tag):
                builder()
        if self.sky is not None:
            world, collection = self.sky
            if collection is not None:
                for obj in list(collection.objects):
                    bpy.data.objects.remove(obj)
                bpy.data.collections.remove(collection)
        world, collection, _files = SCN.build_sky(sky_reads.FILM, state["sky"], self.sun, "Fit", bpy.context.scene.collection)
        bpy.context.scene.world = world
        self.sky = (world, collection)

    def score(self, state):
        self._apply(state)
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
    spec = json.load(open(args.spec, encoding="utf-8"))
    if any("sky" in entry for entry in spec["parameters"]):
        shot = json.load(open(os.path.join(sky_reads.FILM, "shots", f"{args.shot}.json"), encoding="utf-8"))
        if "sky" in shot:
            raise ValueError(f"{args.shot} changes its set's sky: fit that with fit_sky.py, not into the set")
    fit = Fit(args, spec)
    set_spec = fit.reads.spec
    state = {"lights": copy.deepcopy(set_spec.get("lights", [])), "materials": copy.deepcopy(set_spec.get("materials", {})),
             "sky": copy.deepcopy(fit.reads.sky)}
    for entry in spec["parameters"]:
        key = entry.get("material")
        if key is not None and key not in state["materials"]:
            if key.startswith("color:"):
                state["materials"][key] = list(M.PALETTE[key[len("color:"):]])
            elif "start" in entry:
                state["materials"][key] = entry["start"]
            else:
                raise KeyError(f"{key}: neither the set nor the spec gives a value to start the fit from")
    state, best = picture_fit.descend(state, _parameters(spec, state), fit.score, spec.get("rounds", 4), _read, _changed,
                                      lambda line: print(f"[fit set] {line}", flush=True))
    print(f"[fit set] best {best:.3f}: {json.dumps(state)}", flush=True)
    if args.write:
        path = os.path.join(sky_reads.FILM, "sets", f"{fit.reads.shot['set']}.json")
        data = json.load(open(path, encoding="utf-8"))
        data["lights"] = state["lights"]
        data["materials"] = state["materials"]
        if any("sky" in entry for entry in spec["parameters"]):
            data["sky"] = state["sky"]
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print(f"[fit set] written into {path}", flush=True)


if __name__ == "__main__":
    main()
