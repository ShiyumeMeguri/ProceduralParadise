"""
Choreography -- a performance authored as key poses, played on a rig.

A performance file (``performances/<shot>.json``) is data::

    {"armature": "Avatar_LaPluma",
     "library": ["performances/LaPluma.poses.json"],  (files of poses the film's performances share)
     "poses": {"Ready": pose, ...},                 (poses of this performance alone)
     "keys": [{"frame": 96, "pose": "Ready", ...pose fields}, ...]}

A key's ``pose`` names a pose of the performance or of its ``library`` (a file
``{"poses": {...}}``: the character's vocabulary -- the way she floats, the way
she holds her scythe -- said once for every shot); a performance's own pose of
the same name is refused, two meanings of one name being one too many.

Every key is a whole pose: its ``pose``'s fields, then its own over them
(``points``, ``aims``, ``bones``, ``props``, ``grips`` and ``curl`` entry by
entry, the rest whole).  A pose::

    {"root":   {"at": [x, y, z], "turn": [x, y, z]},        (the rig in the set: metres, degrees)
     "points": {"pelvis": [x, y, z], "hand_r": [x, y, z], "foot_l": [x, y, z], ...},
     "aims":   {"chest": [x, y, z], "head": [x, y, z], "pelvis": [x, y, z]},
     "bones":  {"Head": [x, y, z], ...},                     (turns over the pose, degrees)
     "props":  {"ScytheRoot": {"hand": "Hand_R", "along": 0.8, "spin": 0, "twirl": 0, "flip": false,
                               "at": [x, y, z], "turn": [x, y, z]}},
     "grips":  {"Hand_L": {"prop": "ScytheRoot", "along": 0.45, "spin": 0, "flip": false}},
     "curl":   {"Hand_R": 1.0, ...},                         (fists: 0 open, 1 closed)
     "ease":   "BEZIER"}                                     (how it moves on to the next key)

A pose is found the way an animator finds one in Cascadeur: its ``points``
-- the auto-posing's control points (the RuriMotionFlow add-on, which must
be enabled: the pelvis, the neck, the hands and the feet, and as many of the
rest -- elbows, knees, where a hand or the head points -- as the pose cares
to pin) -- are put where it says and the add-on's auto-posing finds the
body that goes with them, its chest, head and pelvis facing the ``aims``.
Every point and direction is the character's own as it stands at rest --
facing +Y, its right +X, up +Z, the floor its feet stand on at Z = 0 -- and
the ``root`` places that in the set: a pose is found standing and is then
flown, flipped and turned however the root says -- ``at`` where the
character's pivot (the profile's ``pivot``: a point of her at rest, her
middle) is in the set, ``turn`` how she is turned about it, an XYZ Euler.  A
somersault turns about her middle, not about her feet: the root is an empty
of its own (``<rig> Pivot``) the rig hangs from.  The feet are always
pinned (to where they stand at rest unless the pose says).  ``bones`` turn
bones further once the body is found -- XYZ Eulers about the character's
axes where a bone stands -- the last touch of a head tilted, a wrist cocked.

A prop (a bone of the rig its weapon rides, the profile's ``props``) is held
in a ``hand``: its shaft runs through the palm along the knuckles,
``along`` metres up it from the prop's root, turned ``spin`` about it and
``twirl`` about the palm (a scythe spun between the fingers), its far end
past the thumb (or the little finger, ``flip``).  Posed ``at`` and
``turn`` (as its rest is turned), the prop is placed there and the hand
closes on it -- the hand's point and the point it aims are pinned where the
grip puts them and the hand turned to it; else the prop goes wherever the
hand is put.  A hand of ``grips`` closes on a prop held by another hand.  A
prop held by no hand stands at ``at``, turned ``turn``.

The rig is keyed on the keys alone, the curves between them Blender's own
(auto-clamped Bezier unless a key's ``ease`` says otherwise): the motion is
what a key frame animator would draw, every channel of it readable and
editable in the graph editor.  Bones turn in their own XYZ Euler; a prop
bone hangs on each hand that holds it by a Child Of constraint, keyed on
whichever holds it; a wrist's twist is shared out along its forearm's twist
bones (the profile's ``twists``); the root is keyed on the pivot.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from Core import jsonio

__all__ = ["perform"]

MERGED = ("points", "aims", "bones", "props", "grips", "curl")
HELD_PREFIX = "Held by "


def _vector(value):
    return Vector([float(component) for component in value])


def _turn(value):
    return Euler([math.radians(angle) for angle in value], "XYZ").to_quaternion()


def resolve(performance, folder=None):
    """The keys of ``performance``, each its pose with its own fields over it (its library read from ``folder``)."""
    poses = dict(performance.get("poses", {}))
    for library in performance.get("library", []):
        shared = jsonio.load(os.path.join(folder, library))["poses"]
        twice = sorted(set(shared) & set(poses))
        if twice:
            raise KeyError(f"{library}: poses {twice} are also the performance's own")
        poses.update(shared)
    resolved = []
    for key in performance["keys"]:
        base = poses[key["pose"]] if "pose" in key else {}
        pose = dict(base)
        for name, value in key.items():
            if name in MERGED:
                pose[name] = {**base.get(name, {}), **value}
            elif name != "pose":
                pose[name] = value
        resolved.append(pose)
    resolved.sort(key=lambda pose: pose["frame"])
    return resolved


class Grip:
    """How a hand closes on a prop's shaft (the profile's ``props``): the prop's frame relative to the hand's."""

    def __init__(self, rest, profile, prop_bone, hand):
        props = profile["props"]
        spec = next(spec for spec in props.values() if spec["bone"] == prop_bone)
        grip = next(entry for entry in spec["grips"].values() if entry["hand"] == hand)
        head = {name: rest[name].translation for name in grip["palm"] + grip["knuckles"] + [hand]}
        palm = sum((head[name] for name in grip["palm"]), Vector()) / len(grip["palm"])
        index, little = (head[name] for name in grip["knuckles"])
        self.across = (index - little).normalized()
        fingers = (head[grip["palm"][-1]] - head[hand]).normalized()
        self.inward = self.across.cross(fingers).normalized() * grip.get("side", 1.0)
        self.palm = palm + self.inward * spec["closure"]
        self.shaft = _vector(spec["shaft"][0])
        self.hand_rest = rest[hand]

    def in_hand(self, hold):
        """The prop's frame in the hand's when the hand holds it as ``hold`` says (``along``, ``spin``, ``flip``)."""
        up = -self.across if hold.get("flip", False) else self.across
        third = self.inward.cross(up)
        base = Matrix((self.inward, up, third)).transposed().to_quaternion()
        rotation = Quaternion(self.inward, math.radians(hold.get("twirl", 0.0))) @ Quaternion(up, math.radians(hold.get("spin", 0.0))) @ base
        origin = self.palm - rotation @ Vector((self.shaft.x, hold.get("along", 0.5), self.shaft.z))
        return self.hand_rest.inverted() @ Matrix.Translation(origin) @ rotation.to_matrix().to_4x4()


class Choreographer:
    """Finds the poses of a performance on ``rig`` (standing at the origin) through the auto-posing of RuriMotionFlow."""

    def __init__(self, rig, profile):
        from RuriMotionFlow.blender_host import headless
        self.rig = rig
        self.profile = profile
        self.rest = {bone.name: bone.matrix_local.copy() for bone in rig.data.bones}
        self.poser = headless.Poser(rig, profile["posing"]["profile"], False)
        self.poser.rest()
        self.rest_points = self.poser.points()
        self.grips = {}

    def grip(self, prop_bone, hand):
        if (prop_bone, hand) not in self.grips:
            self.grips[prop_bone, hand] = Grip(self.rest, self.profile, prop_bone, hand)
        return self.grips[prop_bone, hand]

    def _hand_targets(self, hand, matrix, targets):
        """Pin the hand ``hand`` to stand as ``matrix`` (armature space): its point, and the point it aims carried along."""
        spec = self.profile["hands"][hand]
        targets[spec["point"]] = matrix.translation.copy()
        aim = self.rest[hand].inverted() @ Vector(self.rest_points[spec["aim"]])
        targets[spec["aim"]] = matrix @ aim

    def _set_hands(self, hands):
        pose_bones = self.rig.pose.bones
        for hand, matrix in hands.items():
            pose_bones[hand].matrix = matrix
            bpy.context.view_layer.update()

    def _solve(self, pose, targets, label):
        errors = self.poser.solve(targets, pose.get("aims"), pose.get("passes", 1))
        missed = {name: round(error, 3) for name, error in errors.items() if error > self.profile["posing"]["tolerance"]}
        if missed:
            print(f"[choreography] {label}: points the body cannot reach (metres off): {missed}")

    def pose(self, pose):
        """Pose the rig as ``pose`` says; returns the props' holds {prop bone: (hand or None, local matrix)}."""
        rig = self.rig
        label = f"frame {pose['frame']}"
        for pose_bone in rig.pose.bones:
            pose_bone.matrix_basis.identity()
        self.poser.rest()
        targets = {name: _vector(point) for name, point in pose.get("points", {}).items()}
        props = pose.get("props", {})
        grips = pose.get("grips", {})
        placed = {}
        hands = {}
        for prop_bone, hold in props.items():
            if "at" not in hold:
                continue
            rotation = _turn(hold.get("turn", (0.0, 0.0, 0.0))) @ self.rest[prop_bone].to_quaternion()
            placed[prop_bone] = Matrix.Translation(_vector(hold["at"])) @ rotation.to_matrix().to_4x4()
            if hold.get("hand") is not None:
                hands[hold["hand"]] = placed[prop_bone] @ self.grip(prop_bone, hold["hand"]).in_hand(hold).inverted()
        for hand, grip in grips.items():
            if grip["prop"] in placed:
                hands[hand] = placed[grip["prop"]] @ self.grip(grip["prop"], hand).in_hand(grip).inverted()
        for hand, matrix in hands.items():
            self._hand_targets(hand, matrix, targets)
        self._solve(pose, targets, label)
        self._set_hands(hands)
        late = {hand: grip for hand, grip in grips.items() if grip["prop"] not in placed}
        if late:
            pose_bones = rig.pose.bones
            for prop_bone, hold in props.items():
                if prop_bone not in placed and hold.get("hand") is not None:
                    holder = hold["hand"]
                    hands[holder] = pose_bones[holder].matrix.copy()
                    placed[prop_bone] = hands[holder] @ self.grip(prop_bone, holder).in_hand(hold)
            for hand, grip in late.items():
                hands[hand] = placed[grip["prop"]] @ self.grip(grip["prop"], hand).in_hand(grip).inverted()
            for hand, matrix in hands.items():
                self._hand_targets(hand, matrix, targets)
            self.poser.rest()
            self._solve(pose, targets, label)
            self._set_hands(hands)
        pose_bones = rig.pose.bones
        for name, euler in pose.get("bones", {}).items():
            rest = self.rest[name].to_quaternion()
            turn = (rest.inverted() @ _turn(euler) @ rest).to_matrix().to_4x4()
            pose_bones[name].matrix_basis = pose_bones[name].matrix_basis @ turn
        for name, curl in pose.get("curl", {}).items():
            for finger, euler in self.profile["fists"][name].items():
                closed = Euler([math.radians(angle) for angle in euler], "XYZ").to_quaternion()
                pose_bones[finger].matrix_basis = Quaternion().slerp(closed, curl).to_matrix().to_4x4()
        bpy.context.view_layer.update()
        holds = {}
        for prop_bone, hold in props.items():
            hand = hold.get("hand")
            if hand is None:
                holds[prop_bone] = (None, self.rest[prop_bone].inverted() @ placed[prop_bone])
            else:
                in_hand = self.grip(prop_bone, hand).in_hand(hold)
                holds[prop_bone] = (hand, self.rest[prop_bone].inverted() @ in_hand)
        return holds


def _euler(previous, name, quaternion):
    """``quaternion`` as an XYZ Euler nearest the one keyed before it on ``name`` (no flips between keys)."""
    euler = quaternion.to_euler("XYZ", previous[name]) if name in previous else quaternion.to_euler("XYZ")
    previous[name] = euler
    return euler


def _twist(quaternion):
    """Angle of ``quaternion`` about the bone's own Y (its swing-twist split), within a half turn."""
    sign = -1.0 if quaternion.w < 0.0 else 1.0
    return 2.0 * math.atan2(sign * quaternion.y, sign * quaternion.w)


def perform(rig, folder, entry, frames, collection_objects, profile):
    """Key the performance file ``entry["performance"]`` on ``rig`` (see the module notes) and return its sources and the
    frames it covers -- from its first key to its last within the shot's ``frames``."""
    from Core.anim import fcurves_of
    path = os.path.join(folder, entry["performance"])
    performance = jsonio.load(path)
    keys = resolve(performance, folder)
    twists = profile["twists"]
    for obj in collection_objects:
        if any(obj.name.endswith(f".{prop}") for prop in profile["props"]):
            obj.location = (0.0, 0.0, 0.0)
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            obj.scale = (1.0, 1.0, 1.0)
    rig.location = (0.0, 0.0, 0.0)
    rig.rotation_mode = "XYZ"
    rig.rotation_euler = (0.0, 0.0, 0.0)
    rig.animation_data_clear()
    bpy.context.view_layer.update()
    choreographer = Choreographer(rig, profile)
    keyed = set(choreographer.poser.driven_names())
    for key in keys:
        keyed.update(key.get("bones", {}))
        keyed.update(hand for hand in key.get("grips", {}))
        for name in key.get("curl", {}):
            keyed.update(profile["fists"][name])
    twisted = {twist for spec in twists.values() for twist in spec["bones"]}
    keyed |= twisted
    found = []
    for key in keys:
        holds = choreographer.pose(key)
        basis = {name: rig.pose.bones[name].matrix_basis.copy() for name in keyed}
        found.append((key, basis, holds))
    for pose_bone in rig.pose.bones:
        pose_bone.matrix_basis.identity()
    hands = {}
    for key in keys:
        for prop_bone, hold in key.get("props", {}).items():
            if hold.get("hand") is not None and hold["hand"] not in hands.setdefault(prop_bone, []):
                hands[prop_bone].append(hold["hand"])
    constraints = {}
    for prop_bone, holders in hands.items():
        for hand in holders:
            constraint = rig.pose.bones[prop_bone].constraints.new("CHILD_OF")
            constraint.name = f"{HELD_PREFIX}{hand}"
            constraint.target = rig
            constraint.subtarget = hand
            constraint.inverse_matrix = Matrix.Identity(4)
            constraints[prop_bone, hand] = constraint
    moved = {name for _key, basis, _holds in found for name, matrix in basis.items() if matrix.translation.length > 1e-6}
    for name in keyed | set(hands):
        rig.pose.bones[name].rotation_mode = "XYZ"
    pivot = bpy.data.objects.new(f"{rig.name} Pivot", None)
    for collection in rig.users_collection:
        collection.objects.link(pivot)
    pivot.empty_display_type = "SPHERE"
    pivot.empty_display_size = 0.3
    pivot.rotation_mode = "XYZ"
    rig.parent = pivot
    rig.location = -_vector(profile["pivot"])
    previous = {}
    holders = {}
    for key, basis, holds in found:
        frame = key["frame"]
        root = key["root"]
        pivot.location = _vector(root["at"])
        pivot.rotation_euler = [math.radians(angle) for angle in root.get("turn", (0.0, 0.0, 0.0))]
        pivot.keyframe_insert("location", frame=frame)
        pivot.keyframe_insert("rotation_euler", frame=frame)
        for name in sorted(keyed - twisted):
            bone = rig.pose.bones[name]
            rotation = basis[name].to_quaternion()
            bone.rotation_euler = _euler(previous, name, rotation)
            bone.keyframe_insert("rotation_euler", frame=frame)
            if name in moved:
                bone.location = basis[name].translation
                bone.keyframe_insert("location", frame=frame)
        for name, spec in twists.items():
            if name not in basis:
                continue
            angle = _twist(basis[name].to_quaternion()) * spec["share"]
            for twist_name in spec["bones"]:
                twist = rig.pose.bones[twist_name]
                twist.rotation_euler = _euler(previous, twist_name, Quaternion((0.0, 1.0, 0.0), angle))
                twist.keyframe_insert("rotation_euler", frame=frame)
        for prop_bone, (hand, matrix) in holds.items():
            bone = rig.pose.bones[prop_bone]
            location, rotation, scale = matrix.decompose()
            bone.location = location
            bone.rotation_euler = _euler(previous, prop_bone, rotation)
            bone.scale = scale
            for channel in ("location", "rotation_euler", "scale"):
                bone.keyframe_insert(channel, frame=frame)
            for (owner, holder), constraint in constraints.items():
                if owner == prop_bone:
                    constraint.influence = 1.0 if holder == hand else 0.0
                    constraint.keyframe_insert("influence", frame=frame)
            holders.setdefault(prop_bone, []).append((frame, hand))
    eases = {key["frame"]: key.get("ease", "BEZIER") for key in keys}
    switches = {prop_bone: {frame for (frame, hand), (_next, after) in zip(track, track[1:]) if hand != after}
                for prop_bone, track in holders.items()}
    for curve in fcurves_of(rig) + fcurves_of(pivot):
        held = next((prop for prop in switches if curve.data_path.startswith(f'pose.bones["{prop}"]')), None)
        for point in curve.keyframe_points:
            frame = int(round(point.co.x))
            if "constraints[" in curve.data_path or (held is not None and frame in switches[held]):
                point.interpolation = "CONSTANT"
                continue
            point.interpolation = eases.get(frame, "BEZIER")
            point.handle_left_type = point.handle_right_type = "AUTO_CLAMPED"
        curve.update()
    first, last = frames
    inside = [key["frame"] for key in keys if first <= key["frame"] <= last]
    shown = (max(first, keys[0]["frame"]), min(last, keys[-1]["frame"])) if inside else (last + 1, last)
    return [path] + [os.path.join(folder, library) for library in performance.get("library", [])], shown
