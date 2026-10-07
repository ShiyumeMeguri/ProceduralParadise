"""
Cinematics builder -- a small interpreter of a film's data.

``build_film(folder, film, args)`` builds the sets the chosen shots stand
in, appends the cast into every set and makes one Blender scene per shot,
the set's and a performer of every character the shot casts of its own
(``Core.cast.instance_character``: shots never share a pose, a constraint
or a key); it knows no particular asset, set or film.  A set (``sets/<name>.json``)
is pure data::

    {"id": "District",
     "materials": {"CIN.Concrete.roughness": 0.8, "color:concrete": [r, g, b], ...},
     "sky": {...},                                 (Kit.sky.sky_world)
     "items": [item, ...],
     "lights": [lamp, ...],
     "views": {"name": {"location", "target", "lens"}, ...}}   (free cameras of the set scene)

An item is one object: ``name``, ``loc``, ``rot`` (degrees), ``scale`` and
either a ``frame`` (a frame building, see :mod:`frames`) or an ``asset``
with its ``inputs`` (one geometry-nodes modifier on an empty mesh).  An
item that is only there for a while -- what a breach throws into the air,
gone by the time another shot looks -- names its frames (``shown``:
[first, last]); outside them it is not rendered.
Inputs are data: degrees for angles, palette names for colours, library
names for materials.  A lamp is ``{"name", "light": "SUN" | "AREA" |
"POINT" | "SPOT", "power", "color", "angle" (a sun's disc, degrees),
"size", "loc", "direction" (towards the light)}``.

A shot (``shots/<id>.json``)::

    {"id": "Breakout", "set": "District", "frames": [68, 206],
     "camera": {"focal_px": 1315.0, "sensor": 36.0, "clip": [0.05, 8000.0],
                "keys": [{"frame": 68, "location": [x, y, z], "rotation": [w, x, y, z]}, ...]
                        or "calibration/<file>.json" (a file holding them),
                "place": "calibration/<shot>.place.json",        (optional)
                "dof": {"fstop": 2.0, "focus": {"cast": "LaPluma", "bone": "Head"}}},   (optional)
     "render": {"engine": "EEVEE", "samples": 64, "eevee": {...}, "view": "AgX", "look": null,
                "motion_blur": 0.5},
     "look": {...},                                 (Core.render.compositor)
     "cast": {"LaPluma": {"performance": "performances/Breakout.json"}},
     "items": [item, ...],                          (optional)
     "overlays": [{"name", "asset", "inputs", "shown": [first, last]}, ...],   (optional)
     "underlays": {"depth": 2.5, "items": [overlay, ...]}}                    (optional)

Camera keys are the solved camera of every frame in set metres: Blender's
convention, the camera looking along its local -Z with +Y up.  A camera
solved against nothing in the set -- the sky, which only shows it turning
-- is solved about the origin, and its ``place`` says where it stands in
the set: the ``location`` of the origin and the direction it looks
(``look``, or a ``target`` it looks at) with how far it turns about that
direction from upright (``roll``, degrees).  A performance fitted against
such a camera's picture moves with it (``"relative_to": "camera"``: her
root on every frame is in the frame's camera's frame).  A camera with
``dof`` focuses on a bone of the shot's performer of a cast member, the
lens open at ``fstop``.  The film's
``resolution`` and ``fps`` apply to every shot.

A shot's own ``items`` are set items only its camera sees -- a crow
passing its lens.  One with a ``camera_frame`` is placed in the frame of
the shot's camera on that frame (looking along its -Z, +Y up): where the
camera stood then, wherever the shot's camera is solved to stand.

An overlay is an asset the shot's camera carries in front of its lens --
a wipe, a title card -- drawn in the picture's own units: across from
-aspect to +aspect, up from -1 to +1 (``OVERLAY_DISTANCE`` in front of the
lens), each a hair nearer the lens than the one listed before it
(``OVERLAY_LAYER``), so later ones are drawn over earlier ones.  The
overlays are a scene of their own (``Shot.<id>.Overlays``): the shot's
camera moving the same way but in focus everywhere (a lens focused on her
would blur a card held at the lens), rendered on a transparent film and
laid over the shot's finished picture, the look and all
(``Core.render.compositor``).  Underlays are overlays standing ``depth``
metres from the lens -- a title behind her: their own scene again, laid
over the picture only where it shows something beyond that depth, so she
and what she holds hide them, and sharp wherever the lens is focused.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Matrix, Quaternion, Vector

from Core import cast as CAST, jsonio, scene as SC, values as V
from Core import render as RND
from Core.gn import get_asset
from . import CINEMATICS, PALETTE, frames as FR
from .Kit import materials as M, sky as SKY

__all__ = ["build_film", "load_scene", "build_scene"]

OVERLAY_DISTANCE = 0.1
OVERLAY_LAYER = 0.0004


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


def _show_between(obj, first, last):
    """Key ``obj`` (and what hangs under it) rendered on the frames ``first``..``last`` alone."""
    for part in [obj] + list(obj.children_recursive):
        for frame, hidden in ((first - 1, True), (first, False), (last, False), (last + 1, True)):
            part.hide_render = hidden
            part.keyframe_insert("hide_render", frame=frame)


def build_item(item, collection):
    obj = _build_item(item, collection)
    if "shown" in item:
        _show_between(obj, *item["shown"])
    return obj


def _build_item(item, collection):
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
    characters = {}
    cast_files = []
    for name, entry in _cast_entries(film, set_name).items():
        path = CAST.resolve_blend(entry, args.cast, name)
        prefix = f"{set_name}.{name}"
        rig, objects = CAST.append_character(path, entry["armature"], cast_collection, entry.get("hidden", ()), prefix=prefix)
        characters[name] = dict(rig=rig, objects=objects, prefix=prefix)
        cast_files.append(path)
        _rebuild_shading(entry)
    return dict(id=set_name, scene=scene, world=world, collection=collection, characters=characters,
                cast_files=cast_files, source=os.path.join(folder, "sets", f"{set_name}.json"))


def _camera_keys(folder, camera):
    keys = camera["keys"]
    if isinstance(keys, str):
        path = os.path.join(folder, keys)
        return jsonio.load(path)["keys"], [path]
    return keys, []


def _shot_place(folder, camera):
    """The matrix carrying a camera solved about the origin to where its ``place`` stands it (identity without one)."""
    if "place" not in camera:
        return Matrix.Identity(4), []
    path = os.path.join(folder, camera["place"])
    place = jsonio.load(path)
    location = _vector(place["location"])
    look = (_vector(place["target"]) - location) if "target" in place else _vector(place["look"])
    look.normalize()
    upright = Vector((0.0, 0.0, 1.0)) - look * look.z
    upright.normalize()
    backward = -look
    right = upright.cross(backward)
    rotation = Matrix((right, upright, backward)).transposed() @ Matrix.Rotation(math.radians(place.get("roll", 0.0)), 3, "Z")
    return Matrix.Translation(location) @ rotation.to_4x4(), [path]


def _key_matrix(location, rotation):
    return Matrix.Translation(_vector(location)) @ Quaternion(rotation).to_matrix().to_4x4()


def build_camera(name, folder, camera, film, collection):
    """The shot's camera, keyed every frame of its keys (placed by its ``place``); returns it, the
    files it was read from and its matrix in the set on every keyed frame."""
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
    place, place_sources = _shot_place(folder, camera)
    matrices = {}
    previous = {}
    for key in keys:
        matrix = place @ _key_matrix(key["location"], key["rotation"])
        matrices[key["frame"]] = matrix
        location, rotation, _scale = matrix.decompose()
        obj.location = location
        obj.rotation_quaternion = _continuous(previous, None, rotation)
        obj.keyframe_insert("location", frame=key["frame"])
        obj.keyframe_insert("rotation_quaternion", frame=key["frame"])
        if "focal_px" in key:
            data.lens = key["focal_px"] / width * data.sensor_width
            data.keyframe_insert("lens", frame=key["frame"])
    from Core.anim import fcurves_of
    for curve in fcurves_of(obj) + fcurves_of(data):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    return obj, sources + place_sources, matrices


def _camera_at(matrices, frame):
    """The shot camera's matrix on ``frame`` from its keyed ``matrices`` (frame -> matrix): as its keys play it, straight
    from key to key (location and quaternion component by component), held before the first and after the last."""
    if frame in matrices:
        return matrices[frame]
    frames = sorted(matrices)
    if frame < frames[0] or frame > frames[-1]:
        return matrices[frames[0] if frame < frames[0] else frames[-1]]
    after = next(key for key in frames if key > frame)
    before = max(key for key in frames if key < frame)
    share = (frame - before) / (after - before)
    (location_a, rotation_a, _), (location_b, rotation_b, _) = matrices[before].decompose(), matrices[after].decompose()
    if rotation_a.dot(rotation_b) < 0.0:
        rotation_b = -rotation_b
    rotation = Quaternion([a + (b - a) * share for a, b in zip(rotation_a, rotation_b)]).normalized()
    return Matrix.Translation(location_a.lerp(location_b, share)) @ rotation.to_matrix().to_4x4()


def _twist(quaternion, axis=Vector((0.0, 1.0, 0.0))):
    """Angle of ``quaternion`` about ``axis`` (its swing-twist split), within a half turn."""
    sign = -1.0 if quaternion.w < 0.0 else 1.0
    projection = sign * Vector((quaternion.x, quaternion.y, quaternion.z)).dot(axis)
    return 2.0 * math.atan2(projection, sign * quaternion.w)


def _continuous(previous, key, quaternion):
    """``quaternion`` on the same side as the one keyed before it (``q`` and ``-q`` are one
    rotation, but keys interpolated across a sign flip swing through every other one)."""
    quaternion = Quaternion(quaternion)
    if key in previous and previous[key].dot(quaternion) < 0.0:
        quaternion.negate()
    previous[key] = quaternion
    return quaternion


def perform(rig, folder, entry, frames, collection_objects, profile, cameras):
    """Key the performance file ``entry["performance"]`` on ``rig``: its
    placement and bone rotations every frame of it (her root in the frame's
    camera's frame when it is ``relative_to`` the camera: ``cameras``, the
    shot camera's matrix every frame), constant outside the
    shot's ``frames`` (motion blur never reads the next shot's pose), the
    cast hidden on the shot's frames the performance does not cover.  A
    wrist's twist is shared out along the forearm's twist bones (the cast
    profile's ``twists``: a share each), so the forearm turns with the hand.
    A held prop's bone (``held``: prop bone -> hand bone) hangs on the hand
    by a Child Of constraint and is keyed with its grip, the prop in the
    hand's frame and its scale: the bone's own pose is its rest inverted
    times the grip, so the constraint lands it exactly there."""
    path = os.path.join(folder, entry["performance"])
    performance = jsonio.load(path)
    relative = entry.get("relative_to")
    if relative not in (None, "camera"):
        raise ValueError(f"{path}: a performance is relative to the set or to the 'camera', not '{relative}'")
    twists = profile["twists"]
    rig.rotation_mode = "QUATERNION"
    first, last = frames
    keyed = [item for item in performance["frames"] if first <= item["frame"] <= last]
    previous = {}
    for held, hand in performance.get("held", {}).items():
        constraint = rig.pose.bones[held].constraints.new("CHILD_OF")
        constraint.name = f"Held by {hand}"
        constraint.target = rig
        constraint.subtarget = hand
        constraint.inverse_matrix = Matrix.Identity(4)
    for item in keyed:
        frame = item["frame"]
        root = _key_matrix(item["location"], item["rotation"])
        if relative == "camera":
            root = _camera_at(cameras, frame) @ root
        location, rotation, _scale = root.decompose()
        rig.location = location
        rig.rotation_quaternion = _continuous(previous, None, rotation)
        rig.keyframe_insert("location", frame=frame)
        rig.keyframe_insert("rotation_quaternion", frame=frame)
        for name, value in item["bones"].items():
            bone = rig.pose.bones[name]
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = _continuous(previous, name, value)
            bone.keyframe_insert("rotation_quaternion", frame=frame)
            if name in twists:
                angle = _twist(Quaternion(value)) * twists[name]["share"]
                for twist_name in twists[name]["bones"]:
                    twist = rig.pose.bones[twist_name]
                    twist.rotation_mode = "QUATERNION"
                    twist.rotation_quaternion = _continuous(previous, twist_name, Quaternion((0.0, 1.0, 0.0), angle))
                    twist.keyframe_insert("rotation_quaternion", frame=frame)
        for name, grip in item.get("grips", {}).items():
            bone = rig.pose.bones[name]
            matrix = (Matrix.Translation(_vector(grip["location"])) @ Quaternion(grip["rotation"]).to_matrix().to_4x4()
                      @ Matrix.Scale(grip["scale"], 4))
            location, rotation, scale = (rig.data.bones[name].matrix_local.inverted() @ matrix).decompose()
            bone.rotation_mode = "QUATERNION"
            bone.location = location
            bone.rotation_quaternion = _continuous(previous, name, rotation)
            bone.scale = scale
            bone.keyframe_insert("location", frame=frame)
            bone.keyframe_insert("rotation_quaternion", frame=frame)
            bone.keyframe_insert("scale", frame=frame)
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


def build_overlays(shot, camera, scene, items, kind):
    """A scene of the shot's overlays or underlays (``kind``, see the module notes), rendered through a copy of
    ``camera`` in focus everywhere and keyed by the same action, ``items`` carried in front of it in the
    picture's units.  None without items."""
    if not items:
        return None
    overlays = bpy.data.scenes.new(f"Shot.{shot['id']}.{kind}")
    for attribute in ("resolution_x", "resolution_y", "resolution_percentage", "fps", "fps_base"):
        setattr(overlays.render, attribute, getattr(scene.render, attribute))
    overlays.frame_start, overlays.frame_end = scene.frame_start, scene.frame_end
    overlays.render.engine = "BLENDER_EEVEE"
    overlays.eevee.taa_render_samples = 8
    overlays.render.film_transparent = True
    overlays.view_settings.view_transform = scene.view_settings.view_transform
    lens = camera.data.copy()
    lens.dof.use_dof = False
    viewer = bpy.data.objects.new(f"Shot.{shot['id']}.{kind} Camera", lens)
    overlays.collection.objects.link(viewer)
    viewer.rotation_mode = camera.rotation_mode
    viewer.animation_data_create()
    viewer.animation_data.action = camera.animation_data.action
    viewer.animation_data.action_slot = camera.animation_data.action_slot
    overlays.camera = viewer
    width, height = overlays.render.resolution_x, overlays.render.resolution_y
    half_height = OVERLAY_DISTANCE * lens.sensor_width / (2.0 * lens.lens) * height / width
    for layer, item in enumerate(items):
        name = f"Shot.{shot['id']}.{item['name']}"
        obj = _modified_object(name, bpy.data.meshes.new(name), item["asset"], item.get("inputs", {}), overlays.collection)
        obj.parent = viewer
        distance = OVERLAY_DISTANCE - layer * OVERLAY_LAYER
        obj.location = (0.0, 0.0, -distance)
        scale = half_height * distance / OVERLAY_DISTANCE
        obj.scale = (scale, scale, scale)
        if "shown" in item:
            _show_between(obj, *item["shown"])
    return overlays


def build_shot_items(shot, camera, scene):
    """The shot's own items (see the module notes), each named after the shot, in a collection of the shot."""
    collection = SC.collection(f"Shot.{shot['id']}.Items", parent=scene.collection)
    for item in shot.get("items", []):
        obj = build_item({**item, "name": f"Shot.{shot['id']}.{item['name']}"}, collection)
        if "camera_frame" in item:
            scene.frame_set(item["camera_frame"])
            obj.matrix_basis = camera.matrix_world @ obj.matrix_basis
    return collection


def build_shot(folder, film, shot, built_set, args):
    scene = bpy.data.scenes.new(f"Shot.{shot['id']}")
    _activate(scene)
    scene.collection.children.link(built_set["collection"])
    cast = SC.collection(f"Shot.{shot['id']}.Cast", parent=scene.collection)
    scene.world = built_set["world"]
    first, last = shot["frames"]
    scene.frame_start, scene.frame_end = first, last
    scene.render.fps, scene.render.fps_base = film["fps"], 1.0
    scene.render.resolution_x, scene.render.resolution_y = film["resolution"]
    scene.render.resolution_percentage = int(round(100 * (args.scale or 1.0)))
    cameras = SC.collection(f"Shot.{shot['id']}.Camera", parent=scene.collection)
    camera, sources, camera_matrices = build_camera(f"Shot.{shot['id']}.Camera", folder, shot["camera"], film, cameras)
    scene.camera = camera
    build_shot_items(shot, camera, scene)
    settings = shot["render"]
    engine = settings["engine"]
    RND.ENGINES[engine](samples=args.samples or settings.get("samples", 64), **settings.get(engine.lower(), {}))
    blur = settings.get("motion_blur")
    scene.render.use_motion_blur = bool(blur)
    if blur:
        scene.render.motion_blur_shutter = blur
    look = shot.get("look")
    overlays = build_overlays(shot, camera, scene, shot.get("overlays", []), "Overlays")
    underlay = None
    if shot.get("underlays"):
        underlay = (build_overlays(shot, camera, scene, shot["underlays"]["items"], "Underlays"), shot["underlays"]["depth"])
        scene.view_layers[0].use_pass_z = True
    if look and not args.no_look:
        RND.color_management(settings.get("view", "AgX"), settings.get("look"), 0.0)
        RND.compositor(look, overlay_scene=overlays, underlay=underlay)
    else:
        RND.color_management(settings.get("view", "AgX"), settings.get("look"), settings.get("exposure", 0.0))
        if overlays is not None or underlay is not None:
            RND.compositor({}, overlay_scene=overlays, underlay=underlay)
    performers = {}
    for name, entry in shot.get("cast", {}).items():
        character = built_set["characters"][name]
        rig, objects = CAST.instance_character(character["rig"], character["objects"], cast, f"{shot['id']}.{name}",
                                               character["prefix"])
        profile_path = os.path.join(folder, film["cast"][name]["rig"])
        sources += perform(rig, folder, entry, (first, last), objects, jsonio.load(profile_path), camera_matrices) + [profile_path]
        performers[name] = rig
    dof = shot["camera"].get("dof")
    if dof:
        camera.data.dof.use_dof = True
        camera.data.dof.aperture_fstop = dof["fstop"]
        camera.data.dof.focus_object = performers[dof["focus"]["cast"]]
        camera.data.dof.focus_subtarget = dof["focus"]["bone"]
    scene.frame_set(first)
    path = os.path.join(folder, "shots", f"{shot['id']}.json")
    return dict(id=shot["id"], scene=scene, frames=(first, last), camera=camera, set=built_set["collection"], cast=cast,
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
