"""
A fitted performance (``calibration/<shot>.fit.json``, calibration/fit_pose.py's) read as key poses: the draft of a
choreography (Other.Cinematics.choreography) the hand then puts right.

    blender -b -P Other/Cinematics/LaPluma/calibration/extract_choreography.py -- <shot> <out.json> [step]

The fit turned every bone by itself frame by frame; read through forward kinematics on the rig as it stands (its rests
carried as the fit's own ``rests`` say), each key frame -- every ``step`` frames and the last -- gives what a choreography
asks for: the root (her pelvis, and her body's own frame -- right from hip to hip, up from pelvis to neck -- as an XYZ
Euler continuous from key to key; in the frame the fit's root is in -- the shot's camera's for a performance ``relative_to``
it, the set's otherwise), her neck, hands and feet in that frame, the way her chest, head and pelvis face, and the scythe where
the fit put it with the hold (``along``, ``spin``, ``flip``) that brings the holding hand closest to how the fit turned it.
The knees and elbows are left to the auto-posing, and so is everything the fit read wrongly: the draft is read, not
believed -- a frame the fit read facing the wrong way, a foot no leg reaches, are put right by hand.  What the hand found
by reading the draft is data, ``calibration/<shot>.extract.json``::

    {"mirror": [[first, last], ...], "notes": [...]}

the frames the fit read facing the wrong way: their joints are read mirrored in the depth of the camera's picture about
the pelvis with left and right swapped -- the body turned the way the picture equally allows -- and their scythe is held
as the nearest frame read the right way holds it (the fit placed it for the body it misread).
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
FILM = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(FILM, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "Other"))
from Core import cast as CAST, jsonio, scene as SC  # noqa: E402
from Cinematics import choreography as CH, scenes as SCN  # noqa: E402

POINTS = {"neck": "Neck", "hand_l": "Hand_L", "hand_r": "Hand_R", "foot_l": "Foot_L", "foot_r": "Foot_R"}
SWAP = {"hand_l": "hand_r", "hand_r": "hand_l", "foot_l": "foot_r", "foot_r": "foot_l", "hip_l": "hip_r", "hip_r": "hip_l"}
DEPTH = Matrix.Diagonal((1.0, 1.0, -1.0, 1.0))
FACING = {"chest": "Spine2", "head": "Head", "pelvis": "Pelvis"}
SPINS = range(0, 360, 15)


def rounded(values, digits=3):
    return [round(float(value), digits) for value in values]


def facing(matrix, rest, mirrored):
    """The way a bone posed as ``matrix`` faces (its rest's forward carried), mirrored in depth when its frame is."""
    forward = matrix.to_quaternion() @ rest.to_quaternion().inverted() @ Vector((0.0, 1.0, 0.0))
    return Vector((forward.x, forward.y, -forward.z)) if mirrored else forward


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    shot_id, out = argv[0], os.path.abspath(argv[1])
    step = int(argv[2]) if len(argv) > 2 else 4
    film = jsonio.load(os.path.join(FILM, "film.json"))
    shot = jsonio.load(os.path.join(FILM, "shots", f"{shot_id}.json"))
    cast_name, entry = next(iter(shot["cast"].items()))
    cast = film["cast"][cast_name]
    profile = jsonio.load(os.path.join(FILM, cast["rig"]))
    fit = jsonio.load(os.path.join(FILM, "calibration", f"{shot_id}.fit.json"))
    SC.reset_scene()
    collection = SC.collection("Extract", parent=bpy.context.scene.collection)
    corrections_path = os.path.join(HERE, f"{shot_id}.extract.json")
    mirror = jsonio.load(corrections_path).get("mirror", []) if os.path.isfile(corrections_path) else []
    relative = entry.get("relative_to") == "camera"
    rig, _objects = CAST.link_character(CAST.resolve_blend(cast, {}, cast_name), cast["armature"], collection, cast.get("hidden", ()), prefix="Extract")
    camera, _sources, _matrices = SCN.build_camera("Extract Camera", FILM, shot["camera"], film, collection)
    rest = {bone.name: bone.matrix_local.copy() for bone in rig.data.bones}
    parent = {bone.name: bone.parent.name if bone.parent else None for bone in rig.data.bones}
    turns = {name: Quaternion(value).inverted() @ rest[name].to_quaternion() for name, value in fit["rests"].items()}
    held = fit.get("held", {})
    prop_bone, holding = next(iter(held.items())) if held else (None, None)
    pivot = Vector(profile["pivot"])
    grip = CH.Grip(rest, profile, prop_bone, holding) if prop_bone else None
    first, last = shot["frames"]
    frames = [item for item in fit["frames"] if first <= item["frame"] <= last]
    chosen = frames[::step]
    if chosen[-1] is not frames[-1]:
        chosen.append(frames[-1])
    keys = []
    previous_turn = None
    previous_prop = None
    for item in chosen:
        local = {name: turns[name].inverted() @ Quaternion(value) @ turns[name] for name, value in item["bones"].items()}
        posed = {}

        def pose(name):
            if name not in posed:
                own = local.get(name, Quaternion()).to_matrix().to_4x4()
                above = parent[name]
                posed[name] = rest[name] @ own if above is None else pose(above) @ rest[above].inverted() @ rest[name] @ own
            return posed[name]
        root = Matrix.Translation(Vector(item["location"])) @ Quaternion(item["rotation"]).to_matrix().to_4x4()
        world = root
        bpy.context.scene.frame_set(item["frame"])
        to_view = Matrix.Identity(4) if relative else camera.matrix_world.inverted()
        head = {name: (to_view @ world @ pose(bone)).translation for name, bone in {**POINTS, "pelvis": "Pelvis", "hip_l": "Thigh_L", "hip_r": "Thigh_R"}.items()}
        mirrored = any(low <= item["frame"] <= high for low, high in mirror)
        reflect = Matrix.Translation(head["pelvis"]) @ DEPTH @ Matrix.Translation(-head["pelvis"])
        if mirrored:
            head = {SWAP.get(name, name): reflect @ point for name, point in head.items()}
        from_view = to_view.inverted()
        right = (head["hip_r"] - head["hip_l"]).normalized()
        up = head["neck"] - head["pelvis"]
        up = (up - right * up.dot(right)).normalized()
        body = Matrix((right, up.cross(right), up)).transposed()
        inverse = body.transposed()
        root_turn = (from_view.to_quaternion() @ body.to_quaternion()).to_matrix()
        turn = root_turn.to_euler("XYZ", previous_turn) if previous_turn is not None else root_turn.to_euler("XYZ")
        previous_turn = turn
        key = {"frame": item["frame"],
               "root": {"at": rounded(from_view @ head["pelvis"]), "turn": rounded([math.degrees(angle) for angle in turn], 2)},
               "points": {"pelvis": rounded(pivot), **{name: rounded(pivot + inverse @ (head[name] - head["pelvis"])) for name in POINTS}},
               "aims": {name: rounded(inverse @ facing(to_view @ world @ pose(bone), rest[bone], mirrored)) for name, bone in FACING.items()},
               "curl": {"Hand_R": 1.0 if holding == "Hand_R" else 0.4, "Hand_L": 1.0 if holding == "Hand_L" else 0.4}}
        if prop_bone and prop_bone in item.get("grips", {}) and not mirrored:
            hold = item["grips"][prop_bone]
            in_hand = (turns[holding].inverted().to_matrix().to_4x4() @ Matrix.Translation(Vector(hold["location"]))
                       @ Quaternion(hold["rotation"]).to_matrix().to_4x4())
            prop_world = to_view @ world @ pose(holding) @ in_hand
            to_character = Matrix.Translation(pivot) @ inverse.to_4x4() @ Matrix.Translation(-head["pelvis"])
            prop = to_character @ prop_world
            prop_turn = (prop.to_quaternion() @ rest[prop_bone].to_quaternion().inverted())
            prop_euler = prop_turn.to_euler("XYZ", previous_prop) if previous_prop is not None else prop_turn.to_euler("XYZ")
            previous_prop = prop_euler
            hand = to_character @ to_view @ world @ pose(holding)
            shaft = prop.to_quaternion() @ Vector((0.0, 1.0, 0.0))
            along = max(0.05, min(1.1, (hand.translation - prop.translation).dot(shaft)))
            best = None
            for flip in (False, True):
                for spin in SPINS:
                    candidate = {"along": along, "spin": spin, "flip": flip}
                    predicted = (prop @ grip.in_hand(candidate).inverted()).to_quaternion()
                    miss = predicted.rotation_difference(hand.to_quaternion()).angle
                    if best is None or miss < best[0]:
                        best = (miss, candidate)
            key["props"] = {prop_bone: {"hand": holding, "along": round(along, 3), "spin": best[1]["spin"], "flip": best[1]["flip"],
                                        "at": rounded(prop.translation), "turn": rounded([math.degrees(angle) for angle in prop_euler], 2)}}
        keys.append(key)
    held_keys = [key for key in keys if "props" in key]
    for key in keys:
        if "props" not in key and held_keys:
            nearest = min(held_keys, key=lambda other: abs(other["frame"] - key["frame"]))
            hold = nearest["props"][prop_bone]
            key["props"] = {prop_bone: {name: hold[name] for name in ("hand", "along", "spin", "flip")}}
    performance = {"armature": fit["armature"],
                   "notes": [f"Drafted from the fit by calibration/extract_choreography.py (every {step} frames), then put right by hand."],
                   "keys": keys}
    jsonio.dump(performance, out)
    print(f"[extract] {shot_id}: {len(keys)} keys -> {out}")


main()
