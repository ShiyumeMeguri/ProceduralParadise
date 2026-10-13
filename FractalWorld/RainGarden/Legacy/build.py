import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

from rain_garden.library import build_library
from rain_garden.scene_builder import SceneBuilder


def log(message):
    print(f"[rain-garden] {message}", flush=True)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", required=True)
    parser.add_argument("--palette", required=True)
    parser.add_argument("--layout", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--preset", default="blockout")
    parser.add_argument("--render")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def enable_gpu():
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.refresh_devices()
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
    log("gpu devices: " + ", ".join(f"{device.name}({device.type})={device.use}" for device in preferences.devices))


def main():
    arguments = parse_arguments()
    started = time.time()
    palette = json.loads(Path(arguments.palette).read_text(encoding="utf-8"))
    layout = json.loads(Path(arguments.layout).read_text(encoding="utf-8"))
    registry = build_library(arguments.library, palette, log)
    log(f"library built in {time.time() - started:.1f}s")

    bpy.ops.wm.read_homefile(use_empty=True)
    scene_path = Path(arguments.scene)
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    builder = SceneBuilder(layout, arguments.library, registry, log)
    builder.build(arguments.preset)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path), relative_remap=True)
    log(f"scene saved in {time.time() - started:.1f}s -> {scene_path}")

    if arguments.render:
        if bpy.context.scene.render.engine == "CYCLES":
            enable_gpu()
        bpy.context.scene.render.filepath = arguments.render
        render_started = time.time()
        bpy.ops.render.render(write_still=True)
        log(f"rendered in {time.time() - render_started:.1f}s -> {arguments.render}")


main()
