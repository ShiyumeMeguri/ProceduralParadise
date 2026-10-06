"""
Cinematics builder -- a small interpreter of a film's data.

``build_film(folder, film, args)`` builds the sets the chosen shots stand
in, appends the cast into every set and makes one Blender scene per shot;
it knows no particular asset, set or film.  A set (``sets/<name>.json``)
is pure data::

    {"id": "District",
     "materials": {"CIN.Concrete.roughness": 0.8, "color:concrete": [r, g, b], ...},
     "sky": {...},                                 (Kit.sky.sky_world)
     "items": [item, ...],
     "lights": [lamp, ...],
     "views": {"name": {"location", "target", "lens"}, ...}}   (free cameras of the set scene)

An item is one object: ``name``, ``loc``, ``rot`` (degrees), ``scale`` and
either a ``frame`` (a frame building, see :mod:`frames`) or an ``asset``
with its ``inputs`` (one geometry-nodes modifier on an empty mesh).
Inputs are data: degrees for angles, palette names for colours, library
names for materials.  A lamp is ``{"name", "light": "SUN" | "AREA" |
"POINT" | "SPOT", "power", "color", "angle" (a sun's disc, degrees),
"size", "loc", "direction" (towards the light)}``.

A shot (``shots/<id>.json``)::

    {"id": "Breakout", "set": "District", "frames": [68, 206],
     "camera": {"focal_px": 1315.0, "sensor": 36.0, "clip": [0.05, 8000.0],
                "keys": [{"frame": 68, "location": [x, y, z], "rotation": [w, x, y, z]}, ...]
                        or "calibration/<file>.json" (a file holding them)},
     "render": {"engine": "EEVEE", "samples": 64, "eevee": {...}, "view": "AgX", "look": null,
                "motion_blur": 0.5},
     "look": {...},                                 (Core.render.compositor)
     "cast": {"LaPluma": {"performance": "performances/Breakout.json"}}}

Camera keys are the solved camera of every frame in set metres: Blender's
convention, the camera looking along its local -Z with +Y up.  The film's
``resolution`` and ``fps`` apply to every shot.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Quaternion, Vector

from Core import cast as CAST, jsonio, scene as SC, values as V
from Core import render as RND
from Core.gn import get_asset
from . import CINEMATICS, PALETTE, frames as FR
from .Kit import materials as M, sky as SKY

__all__ = ["build_film", "load_scene", "build_scene"]


def load_scene(folder):
    return jsonio.load(os.path.join(folder, "film.json"))


def build_scene(folder):
    raise RuntimeError("a film is built by Core.film (build_film), not as a single scene")


def _vector(value, default=(0.0, 0.0, 0.0)):
    return Vector([float(component) for component in (value if value is not None else default)])


def _activate(scene):
    bpy.context.window.scene = scene


def _converted(group, values):
    sockets = {entry.name: entry for entry in group.interface.items_tree
               if getattr(entry, "in_out", None) == "INPUT" and entry.item_type == "SOCKET"}
    result = {}
    for name, value in values.items():
        if name not in sockets:
            raise KeyError(f"{group.name}: no input '{name}'. Inputs: {list(sockets)}")
        socket = sockets[name]
        if socket.socket_type == "NodeSocketMaterial":
            result[name] = M.get(value)
        else:
            result[name] = V.socket_value(socket, value, PALETTE)
    return result


def _place(obj, item):
    obj.location = _vector(item.get("loc"))
    obj.rotation_euler = [math.radians(angle) for angle in item.get("rot", (0.0, 0.0, 0.0))]
    scale = item.get("scale", 1.0)
    obj.scale = (scale, scale, scale) if isinstance(scale, (int, float)) else tuple(scale)


def _modified_object(name, mesh, asset_name, inputs, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    group = get_asset(asset_name)
    modifier = obj.modifiers.new(asset_name.split(".")[-1], "NODES")
    modifier.node_group = group
    SC.set_gn_inputs(modifier, _converted(group, inputs))
    return obj


def build_frame(item, collection):
    """A frame building: its members, glazing and floors as three objects
    under one empty (the item's placement)."""
    name = item["name"]
    frame = item["frame"]
    members, glazing, floors = FR.frame_meshes(name, frame, CINEMATICS["modules"])
    root = bpy.data.objects.new(name, None)
    collection.objects.link(root)
    _place(root, item)
    parts = [_modified_object(f"{name}.Members", members, "CIN.Structure.Members", frame.get("members", {}), collection),
             _modified_object(f"{name}.Glazing", glazing, "CIN.Structure.Panes", frame.get("glazing", {}), collection),
             _modified_object(f"{name}.Floors", floors, "CIN.Structure.Slabs",
                              {"Thickness": frame.get("slab", 0.3), **frame.get("floors", {})}, collection)]
    for part in parts:
        part.parent = root
    return root


def build_item(item, collection):
    if "frame" in item:
        return build_frame(item, collection)
    obj = _modified_object(item["name"], bpy.data.meshes.new(item["name"]), item["asset"], item.get("inputs", {}), collection)
    _place(obj, item)
    return obj


def build_lamp(item, collection):
    data = bpy.data.lights.new(item["name"], item["light"])
    data.energy = item["power"]
    data.color = tuple(PALETTE[item["color"]]) if isinstance(item.get("color"), str) else tuple(item.get("color", (1.0, 1.0, 1.0)))
    if item["light"] == "SUN":
        data.angle = math.radians(item.get("angle", 1.0))
    if item["light"] == "AREA":
        data.shape = item.get("shape", "RECTANGLE")
        data.size, data.size_y = item["size"]
    obj = bpy.data.objects.new(item["name"], data)
    collection.objects.link(obj)
    obj.location = _vector(item.get("loc"))
    if "direction" in item:
        obj.rotation_euler = (-_vector(item["direction"])).to_track_quat("-Z", "Y").to_euler()
    return obj


def _cast_entries(film, set_name):
    return {name: entry for name, entry in film.get("cast", {}).items() if set_name in entry.get("sets", [set_name])}


def _rebuild_shading(entry):
    """Run the host add-on that owns the character's shading: its shading
    groups are runtime data rebuilt from the material records, so an
    appended character has none until the add-on has run (it would render
    black).  ``shading`` names the add-on's module and the call that brings
    appended materials up to date."""
    shading = entry.get("shading")
    if not shading:
        return
    import importlib
    module = importlib.import_module(shading["module"])
    bpy.context.view_layer.update()
    getattr(module, shading["call"])()
    error = getattr(module, shading.get("error", ""), "") if shading.get("error") else ""
    if error:
        raise RuntimeError(f"{shading['module']}: {error}")


def build_set(folder, set_name, film, args):
    spec = jsonio.load(os.path.join(folder, "sets", f"{set_name}.json"))
    scene = bpy.data.scenes.new(set_name)
    _activate(scene)
    scene.render.resolution_x, scene.render.resolution_y = film["resolution"]
    scene.render.fps = film["fps"]
    M.PARAMS.clear()
    M.PARAMS.update(spec.get("materials", {}))
    world = SKY.sky_world(spec["sky"], f"{set_name}.Sky")
    collection = SC.collection(set_name, parent=scene.collection)
    for item in spec.get("items", []):
        build_item(item, collection)
    lights = SC.collection(f"{set_name}.Lights", parent=collection)
    for lamp in spec.get("lights", []):
        build_lamp(lamp, lights)
    for name, view in spec.get("views", {}).items():
        from Core import camera as CAM
        camera = CAM.look_camera(f"{set_name}.View.{name}", _vector(view["location"]), _vector(view["target"]),
                                 lens=view.get("lens", 24.0), collection=scene.collection, clip=view.get("clip", 0.05))
        camera.data.clip_end = view.get("far", 20000.0)
    cast_collection = SC.collection(f"{set_name}.Cast", parent=scene.collection)
    rigs = {}
    cast_files = []
    for name, entry in _cast_entries(film, set_name).items():
        path = CAST.resolve_blend(entry, args.cast, name)
        rig, _objects = CAST.append_character(path, entry["armature"], cast_collection, entry.get("hidden", ()),
                                              prefix=f"{set_name}.{name}")
        rigs[name] = rig
        cast_files.append(path)
        _rebuild_shading(entry)
    return dict(id=set_name, scene=scene, world=world, collection=collection, cast=cast_collection, rigs=rigs,
                cast_files=cast_files, source=os.path.join(folder, "sets", f"{set_name}.json"))


def _camera_keys(folder, camera):
    keys = camera["keys"]
    if isinstance(keys, str):
        path = os.path.join(folder, keys)
        return jsonio.load(path)["keys"], [path]
    return keys, []


def build_camera(name, folder, camera, film, collection):
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = camera.get("sensor", 36.0)
    width = film["resolution"][0]
    data.lens = camera["focal_px"] / width * data.sensor_width
    data.clip_start, data.clip_end = camera.get("clip", (0.05, 8000.0))
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.rotation_mode = "QUATERNION"
    keys, sources = _camera_keys(folder, camera)
    for key in keys:
        obj.location = _vector(key["location"])
        obj.rotation_quaternion = Quaternion(key["rotation"])
        obj.keyframe_insert("location", frame=key["frame"])
        obj.keyframe_insert("rotation_quaternion", frame=key["frame"])
        if "focal_px" in key:
            data.lens = key["focal_px"] / width * data.sensor_width
            data.keyframe_insert("lens", frame=key["frame"])
    from Core.anim import fcurves_of
    for curve in fcurves_of(obj) + fcurves_of(data):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    return obj, sources


TWISTS = {"Hand_L": ("ForeTwist_L", "ForeTwist1_L"), "Hand_R": ("ForeTwist_R", "ForeTwist1_R")}


def _twist(quaternion, axis=Vector((0.0, 1.0, 0.0))):
    """Angle of ``quaternion`` about ``axis`` (its swing-twist split)."""
    projection = Vector((quaternion.x, quaternion.y, quaternion.z)).dot(axis)
    return 2.0 * math.atan2(projection, quaternion.w)


def perform(rig, folder, entry, frames, collection_objects):
    """Key the performance file ``entry["performance"]`` on ``rig``: its
    placement and bone rotations every frame of it, constant outside the
    shot's ``frames`` (motion blur never reads the next shot's pose), the
    cast hidden on the shot's frames the performance does not cover.  A
    wrist's twist is shared out along the forearm's twist bones (a third
    each, as the rig expects of them), so the forearm turns with the hand."""
    path = os.path.join(folder, entry["performance"])
    performance = jsonio.load(path)
    rig.rotation_mode = "QUATERNION"
    first, last = frames
    keyed = [item for item in performance["frames"] if first <= item["frame"] <= last]
    for item in keyed:
        frame = item["frame"]
        rig.location = _vector(item["location"])
        rig.rotation_quaternion = Quaternion(item["rotation"])
        rig.keyframe_insert("location", frame=frame)
        rig.keyframe_insert("rotation_quaternion", frame=frame)
        for name, value in item["bones"].items():
            bone = rig.pose.bones[name]
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = Quaternion(value)
            bone.keyframe_insert("rotation_quaternion", frame=frame)
            if name in TWISTS:
                angle = _twist(Quaternion(value)) / 3.0
                for twist_name in TWISTS[name]:
                    twist = rig.pose.bones[twist_name]
                    twist.rotation_mode = "QUATERNION"
                    twist.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), angle)
                    twist.keyframe_insert("rotation_quaternion", frame=frame)
    shown = (keyed[0]["frame"], keyed[-1]["frame"]) if keyed else (last + 1, last)
    switches = [(first, shown[0] > first), (shown[0], False), (shown[1] + 1, True)]
    for obj in collection_objects:
        if obj.hide_viewport:
            continue
        for frame, hidden in switches:
            if first <= frame <= last:
                obj.hide_render = hidden
                obj.keyframe_insert("hide_render", frame=frame)
    return [path]


def build_shot(folder, film, shot, built_set, args):
    scene = bpy.data.scenes.new(f"Shot.{shot['id']}")
    _activate(scene)
    scene.collection.children.link(built_set["collection"])
    scene.collection.children.link(built_set["cast"])
    scene.world = built_set["world"]
    first, last = shot["frames"]
    scene.frame_start, scene.frame_end = first, last
    scene.render.fps, scene.render.fps_base = film["fps"], 1.0
    scene.render.resolution_x, scene.render.resolution_y = film["resolution"]
    scene.render.resolution_percentage = int(round(100 * (args.scale or 1.0)))
    cameras = SC.collection(f"Shot.{shot['id']}.Camera", parent=scene.collection)
    camera, sources = build_camera(f"Shot.{shot['id']}.Camera", folder, shot["camera"], film, cameras)
    scene.camera = camera
    settings = shot["render"]
    engine = settings["engine"]
    RND.ENGINES[engine](samples=args.samples or settings.get("samples", 64), **settings.get(engine.lower(), {}))
    blur = settings.get("motion_blur")
    scene.render.use_motion_blur = bool(blur)
    if blur:
        scene.render.motion_blur_shutter = blur
    look = shot.get("look")
    if look and not args.no_look:
        RND.color_management(settings.get("view", "AgX"), settings.get("look"), 0.0)
        RND.compositor(look)
    else:
        RND.color_management(settings.get("view", "AgX"), settings.get("look"), settings.get("exposure", 0.0))
    for name, entry in shot.get("cast", {}).items():
        sources += perform(built_set["rigs"][name], folder, entry, (first, last), list(built_set["cast"].all_objects))
    scene.frame_set(first)
    path = os.path.join(folder, "shots", f"{shot['id']}.json")
    return dict(id=shot["id"], scene=scene, frames=(first, last), camera=camera,
                sources=[path, built_set["source"], os.path.join(folder, "film.json")] + sources)


def build_film(folder, film, args):
    names = args.shots or film["shots"]
    unknown = sorted(set(names) - set(film["shots"]))
    if unknown:
        raise KeyError(f"no shots {unknown} in {film['id']} (shots: {film['shots']})")
    shots = {name: jsonio.load(os.path.join(folder, "shots", f"{name}.json")) for name in film["shots"] if name in names}
    sets = {}
    for shot in shots.values():
        if shot["set"] not in sets:
            sets[shot["set"]] = build_set(folder, shot["set"], film, args)
    built = {shot_id: build_shot(folder, film, shot, sets[shot["set"]], args) for shot_id, shot in shots.items()}
    first = next(iter(built.values()))["scene"]
    _activate(first)
    for scene in list(bpy.data.scenes):
        if scene.name == "Scene" and not scene.objects:
            bpy.data.scenes.remove(scene)
    return {"shots": built, "cast_files": sorted({path for built_set in sets.values() for path in built_set["cast_files"]})}
