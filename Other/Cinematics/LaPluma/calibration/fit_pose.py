"""
Fit the cast's rig to the reference, frame by frame (PyTorch).

    python fit_pose.py <rig.npz> <keypoints.npz> <camera.json> <first> <last> <out performance.json>
                       [--masks DIR] [--start pose.json] [--iterations N]

The rig (``export_rig.py``) is posed with Blender's own forward kinematics
(``skeleton.py``); the second and third finger segments add the first
segment's curl (the rig's Copy Rotation constraints).  Every frame of the
shot is fitted at once: the whole-body keypoints of the reference
(``keypoints.py``) pull the rig's joints onto them through the shot's solved
camera, a silhouette (``--masks``) keeps the rig inside the character's
outline, and smoothness ties neighbouring frames together.  The fit runs
coarse to fine -- placement, then body and limbs, then hands.

An ``--anchor frame:axis:value`` pins the root's set coordinate on a frame
where the reference shows where she is (breaking through a window) and the
picture alone cannot tell how far away she is.

With ``--prop`` the prop she holds (``prop.py``) is fitted with her, in
her hand: its bone is the hand bone's (the ``--start`` performance's
``held``) times a grip, one grip for the shot that may drift a little from
frame to frame (``--grip-drift`` holds it).  The prop is turned as the
picture turns it (``aims``, from ``fit_prop.py``; ``--aim-weight``), and
the wrist and arm follow it.  Its silhouette (``--prop-weight``) is matched
by the prop grown about the hand by the shot's ``film_scale``
(``prop.py``): where the film's prop is not the model's size, the angle is
what is kept, and the silhouette may be left out.  Its silhouette
(``--prop-masks``, hidden only behind her; its parts' own silhouettes with
``--prop-part``, ``prop.parts``) then poses her arm as much as her
keypoints do -- the prop's outline is sharper than her hand's.  The grips
start from the ``--start`` performance's (``fit_prop.py`` places the prop
on its silhouette and writes them); the shared grip is the one of them
that fits the most frames, and the drift is let go of slowly, so the arm
comes to the prop.

The performance written is the rig object's placement (set metres) and
every fitted bone's local rotation for every frame; the film's interpreter
keys them on the cast.
"""
import argparse
import json
import os

import cv2
import numpy as np
import torch
from scipy.spatial.transform import Rotation as ScipyRotation

from prop import Prop, fitted, parts
from skeleton import Camera, Skeleton, axis_angle_matrices, quaternion_from_matrix

parser = argparse.ArgumentParser()
parser.add_argument("rig")
parser.add_argument("keypoints")
parser.add_argument("camera")
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("out")
parser.add_argument("--masks", default=None)
parser.add_argument("--start", default=None)
parser.add_argument("--iterations", type=int, default=1500)
parser.add_argument("--exclude", nargs="*", default=["Scythe"])
parser.add_argument("--anchor", nargs="*", default=[], help="frame:axis:value -- the root's set coordinate on that frame")
parser.add_argument("--prop", default=None, help="the mesh of a prop she holds, fitted with her")
parser.add_argument("--prop-masks", default=None)
parser.add_argument("--prop-part", action="append", default=[], help="DIR=MATERIAL,MATERIAL -- a part of the prop and its masks")
parser.add_argument("--prop-rest-precision", type=float, default=1.0)
parser.add_argument("--prop-weight", type=float, default=1.0)
parser.add_argument("--prop-smooth", type=float, default=5.0)
parser.add_argument("--grip-drift", type=float, default=1.0, help="how firmly each frame's grip keeps to the shared one")
parser.add_argument("--aim-weight", type=float, default=20.0, help="how firmly the prop is turned as the picture turns it")
parser.add_argument("--width", type=int, default=1920)
parser.add_argument("--height", type=int, default=1080)
args = parser.parse_args()
device = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(0)

skeleton = Skeleton(args.rig, device)
names = skeleton.names
index = skeleton.index
lengths = skeleton.lengths

BODY = ["Pelvis", "Spine", "Spine1", "Spine2", "Neck", "Head", "Clavicle_L", "Clavicle_R", "UpperArm_L", "UpperArm_R",
        "Forearm_L", "Forearm_R", "Hand_L", "Hand_R", "Thigh_L", "Thigh_R", "Calf_L", "Calf_R", "Foot_L", "Foot_R",
        "Toe0_L", "Toe0_R"]
FINGERS = [f"Finger{digit}_{side}" for side in "LR" for digit in range(5)]
CURLED = {f"Finger{digit}{segment}_{side}": f"Finger{digit}{'' if segment == 1 else 1}_{side}"
          for side in "LR" for digit in range(5) for segment in (1, 2)}
FITTED = BODY + FINGERS


def bone_point(name, along=0.0, offset=(0.0, 0.0, 0.0)):
    return (index[name], along, offset)


KEYPOINTS = {
    0: bone_point("Nose01Joint_M"), 1: bone_point("FaceIrisJoint_L"), 2: bone_point("FaceIrisJoint_R"),
    3: bone_point("Ear_01_Jnt_L"), 4: bone_point("Ear_01_Jnt_R"),
    5: bone_point("UpperArm_L"), 6: bone_point("UpperArm_R"), 7: bone_point("Forearm_L"), 8: bone_point("Forearm_R"),
    9: bone_point("Hand_L"), 10: bone_point("Hand_R"), 11: bone_point("Thigh_L"), 12: bone_point("Thigh_R"),
    13: bone_point("Calf_L"), 14: bone_point("Calf_R"), 15: bone_point("Foot_L"), 16: bone_point("Foot_R"),
    17: bone_point("Toe0_L", 1.0), 18: bone_point("Toe0_L", 0.7, (0.03, 0.0, 0.0)), 19: bone_point("Foot_L", 0.0, (0.0, -0.09, -0.06)),
    20: bone_point("Toe0_R", 1.0), 21: bone_point("Toe0_R", 0.7, (-0.03, 0.0, 0.0)), 22: bone_point("Foot_R", 0.0, (0.0, -0.09, -0.06)),
}
for side, base in (("L", 91), ("R", 112)):
    KEYPOINTS[base] = bone_point(f"Hand_{side}")
    for digit, first in ((0, 1), (1, 5), (2, 9), (3, 13), (4, 17)):
        KEYPOINTS[base + first] = bone_point(f"Finger{digit}_{side}")
        KEYPOINTS[base + first + 1] = bone_point(f"Finger{digit}1_{side}")
        KEYPOINTS[base + first + 2] = bone_point(f"Finger{digit}2_{side}")
        KEYPOINTS[base + first + 3] = bone_point(f"Finger{digit}2_{side}", 1.0)

data = np.load(args.keypoints)
frame_list = [int(f) for f in data["frames"]]
selected = [k for k, f in enumerate(frame_list) if args.first <= f <= args.last]
frames = [frame_list[k] for k in selected]
observed = torch.tensor(data["points"][selected], dtype=torch.float32, device=device)
scores = torch.tensor(data["scores"][selected], dtype=torch.float32, device=device)
count = len(frames)

camera = Camera(args.camera, frames, args.width, args.height, device)
focal = camera.focal
camera_rotation = camera.rotation
camera_location = camera.location
project = camera.project


def rotation_vector(matrix):
    return ScipyRotation.from_matrix(matrix).as_rotvec()


def rotation_x(angle):
    cos, sin = torch.cos(angle), torch.sin(angle)
    one, zero = torch.ones_like(angle), torch.zeros_like(angle)
    return torch.stack([one, zero, zero, zero, cos, -sin, zero, sin, cos], -1).reshape(*angle.shape, 3, 3)


def euler_xyz(vector):
    """Blender XYZ Euler: R = Rz @ Ry @ Rx."""
    x, y, z = vector.unbind(-1)
    cx, sx, cy, sy, cz, sz = torch.cos(x), torch.sin(x), torch.cos(y), torch.sin(y), torch.cos(z), torch.sin(z)
    one, zero = torch.ones_like(x), torch.zeros_like(x)
    Rx = torch.stack([one, zero, zero, zero, cx, -sx, zero, sx, cx], -1).reshape(*x.shape, 3, 3)
    Ry = torch.stack([cy, zero, sy, zero, one, zero, -sy, zero, cy], -1).reshape(*x.shape, 3, 3)
    Rz = torch.stack([cz, -sz, zero, sz, cz, zero, zero, zero, one], -1).reshape(*x.shape, 3, 3)
    return Rz @ Ry @ Rx


kept_meshes = [name for name in skeleton.meshes if name not in set(args.exclude)]
samples, sample_bones, sample_weights = skeleton.samples(kept_meshes)
prop = Prop(skeleton, args.prop) if args.prop else None
start = json.load(open(args.start, encoding="utf-8")) if args.start and os.path.exists(args.start) else None
if prop is not None and not (start and prop.name in start.get("held", {})):
    raise SystemExit(f"--prop needs a --start performance holding {prop.name} (fit_prop.py)")
held_hand = index[start["held"][prop.name]] if prop is not None else None
order = skeleton.ancestry([bone for bone, _, _ in KEYPOINTS.values()] + [int(b) for b in sample_bones.unique()]
                         + ([held_hand] if held_hand is not None else []))

fitted_index = {name: k for k, name in enumerate(FITTED)}
rotations = torch.zeros(count, len(FITTED), 3, device=device)
root_rotation = torch.zeros(count, 3, device=device)
root_location = torch.zeros(count, 3, device=device)

if start is not None:
    by_frame = {key["frame"]: key for key in start["frames"]}
    for k, frame in enumerate(frames):
        if frame in by_frame:
            entry = by_frame[frame]
            root_location[k] = torch.tensor(entry["location"])
            root_rotation[k] = torch.tensor(entry["rotation_vector"])
            for name, value in entry["bones_vector"].items():
                if name in fitted_index:
                    rotations[k, fitted_index[name]] = torch.tensor(value)
else:
    from scipy.spatial.transform import Rotation as _Rotation
    for k in range(count):
        points_2d = observed[k].cpu().numpy()
        shoulders = (points_2d[5] + points_2d[6]) / 2
        hips = (points_2d[11] + points_2d[12]) / 2
        length = np.linalg.norm(shoulders - hips)
        depth = float(focal * 0.42 / max(length, 15.0))
        centre_pixel = (shoulders + hips) / 2
        rotation_camera = camera_rotation[k].cpu().numpy()
        right_camera, up_camera, back_camera = rotation_camera[:, 0], rotation_camera[:, 1], rotation_camera[:, 2]
        upward_2d = (shoulders - hips) / max(length, 1e-6)
        body_up = right_camera * upward_2d[0] - up_camera * upward_2d[1]
        body_up /= np.linalg.norm(body_up)
        across = points_2d[5] - points_2d[6]
        facing_camera = (across[0] * upward_2d[1] - across[1] * upward_2d[0]) < 0
        forward = back_camera if facing_camera else -back_camera
        forward = forward - body_up * float(forward @ body_up)
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, body_up)
        world_from_body = np.stack([right, forward, body_up], 1)
        root_rotation.data[k] = torch.tensor(_Rotation.from_matrix(world_from_body).as_rotvec(), dtype=torch.float32, device=device)
        ray = np.array([(centre_pixel[0] - args.width / 2) / focal, -(centre_pixel[1] - args.height / 2) / focal, -1.0])
        torso_centre = camera_location[k].cpu().numpy() + rotation_camera @ ray * depth
        root_location.data[k] = torch.tensor(torso_centre - body_up * 1.12, dtype=torch.float32, device=device)

rotations.requires_grad_(True)
root_rotation.requires_grad_(True)
root_location.requires_grad_(True)


def object_matrices(root_rotation, root_location):
    matrix = torch.eye(4, device=device).repeat(root_location.shape[0], 1, 1)
    matrix[:, :3, :3] = axis_angle_matrices(root_rotation)
    matrix[:, :3, 3] = root_location
    return matrix


def pose(rotations, root_rotation, root_location):
    """World matrices (F, B, 4, 4) of the needed bones."""
    F = rotations.shape[0]
    object_matrix = object_matrices(root_rotation, root_location)
    first_segments = {}

    def local(b):
        name = names[b]
        if name in fitted_index:
            vector = rotations[:, fitted_index[name]]
            matrix = torch.eye(4, device=device).repeat(F, 1, 1)
            if name in FINGERS:
                matrix[:, :3, :3] = euler_xyz(vector)
                first_segments[name] = vector[:, 0]
            else:
                matrix[:, :3, :3] = axis_angle_matrices(vector)
            return matrix
        if name in CURLED:
            source = CURLED[name]
            while source in CURLED:
                source = CURLED[source]
            if source in first_segments:
                matrix = torch.eye(4, device=device).repeat(F, 1, 1)
                matrix[:, :3, :3] = rotation_x(first_segments[source])
                return matrix
        return None

    return skeleton.pose(object_matrix, local, order)


def keypoint_positions(world):
    result = []
    for key in sorted(KEYPOINTS):
        bone, along, offset = KEYPOINTS[key]
        point = torch.tensor([offset[0], float(lengths[bone]) * along + offset[1], offset[2], 1.0], device=device)
        result.append((world[bone] @ point)[:, :3])
    return torch.stack(result, 1)


def camera_projection(points, slots):
    local = torch.einsum("bji,bnj->bni", camera_rotation[slots], points - camera_location[slots][:, None, :])
    safe = (-local[..., 2]).clamp(min=0.05)
    return torch.stack([args.width / 2 + focal * local[..., 0] / safe, args.height / 2 - focal * local[..., 1] / safe], -1)


if prop is not None:
    prop_generator = torch.Generator().manual_seed(0)
    prop_track = prop.subset(16, prop_generator)
    prop_parts = parts(prop, args.prop_part, args.prop_masks, args.masks, frames, args.width, args.height, device, prop_generator,
                       args.prop_rest_precision)
    prop_present = torch.stack([part.silhouette.present for part in prop_parts]).max(0).values
    frame_slots = torch.arange(count, device=device)
    start_grips = prop.read_grips([by_frame[frame] for frame in frames])
    if start_grips is None:
        raise SystemExit(f"--start has no grip of {prop.name} on every frame (fit_prop.py)")
    with torch.no_grad():
        start_hand = pose(rotations, root_rotation, root_location)[held_hand]
        costs = []
        for candidate in start_grips:
            placed = start_hand @ candidate
            precision, coverage = fitted(prop_parts, camera_projection, placed[:, :3, :3], placed[:, :3, 3], frame_slots, True)
            costs.append(float(((precision + coverage) * prop_present).sum()))
        shared = int(np.argmin(costs))
    print("shared grip starts from frame", frames[shared], flush=True)
    aims = prop.read_aims([by_frame[frame] for frame in frames])
    shared_grip = start_grips[shared]
    drift_start = torch.linalg.inv(shared_grip)[None] @ start_grips
    log_film_scale = torch.tensor([float(np.log(start["film_scales"][prop.name]))], device=device, requires_grad=args.prop_weight > 0.0)
    grip_turn = torch.zeros(3, device=device, requires_grad=True)
    grip_shift = torch.zeros(3, device=device, requires_grad=True)
    drift_turn = torch.tensor(np.array([rotation_vector(m) for m in drift_start[:, :3, :3].cpu().numpy()]), dtype=torch.float32,
                              device=device).requires_grad_(True)
    drift_shift = drift_start[:, :3, 3].clone().requires_grad_(True)


def grips():
    """Each frame's grip: the shared grip times that frame's drift."""
    shared_matrix = torch.eye(4, device=device)
    shared_matrix[:3, :3] = shared_grip[:3, :3] @ axis_angle_matrices(grip_turn)
    shared_matrix[:3, 3] = shared_grip[:3, 3] + grip_shift
    drift = torch.eye(4, device=device).repeat(count, 1, 1)
    drift[:, :3, :3] = axis_angle_matrices(drift_turn)
    drift[:, :3, 3] = drift_shift
    return shared_matrix[None] @ drift


def film_grown(hand_matrix):
    """The hand's matrix with the film's size of the prop folded in: the prop grown about the hand."""
    grown = torch.eye(4, device=device) * torch.exp(log_film_scale)
    grown[3, 3] = 1.0
    return hand_matrix @ grown


keypoint_ids = torch.tensor(sorted(KEYPOINTS), device=device)
MIRRORED = {}
for left, right in ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 20), (18, 21), (19, 22)):
    MIRRORED[left], MIRRORED[right] = right, left
for offset in range(21):
    MIRRORED[91 + offset], MIRRORED[112 + offset] = 112 + offset, 91 + offset
mirrored_ids = torch.tensor([MIRRORED.get(key, key) for key in sorted(KEYPOINTS)], device=device)

mask_distance = None
if args.masks:
    maps = []
    for frame in frames:
        path = os.path.join(args.masks, "m%04d.png" % frame)
        mask = cv2.imread(path, cv2.IMREAD_GRAYSCALE) if os.path.exists(path) else None
        if mask is None:
            maps.append(np.zeros((args.height, args.width), np.float32))
            continue
        outside = cv2.distanceTransform((mask < 128).astype(np.uint8), cv2.DIST_L2, 3)
        maps.append(outside.astype(np.float32))
    mask_distance = torch.tensor(np.array(maps), device=device)


def sample_map(maps, pixels):
    F, H, W = maps.shape
    grid = torch.stack([pixels[..., 0] / (W - 1) * 2 - 1, pixels[..., 1] / (H - 1) * 2 - 1], -1)
    return torch.nn.functional.grid_sample(maps[:, None], grid[:, :, None, :], align_corners=True)[:, 0, :, 0]


def robust(residual, scale):
    squared = (residual / scale) ** 2
    return squared / (squared + 1.0)


hand_keys = list(range(91, 133))
weight_map = torch.ones(133, device=device)
weight_map[hand_keys] = 0.4


def loss_terms(stage):
    world = pose(rotations, root_rotation, root_location)
    joints = keypoint_positions(world)
    pixels, depth = project(joints)
    target = observed[:, keypoint_ids]
    confidence = ((scores[:, keypoint_ids] - 1.5) / 3.0).clamp(0.0, 1.0)
    active = torch.zeros(len(keypoint_ids), device=device)
    for slot, key in enumerate(sorted(KEYPOINTS)):
        if stage == 0 and key in (5, 6, 11, 12, 0, 1, 2):
            active[slot] = 1.0
        elif stage == 1 and key < 23:
            active[slot] = 1.0
        elif stage == 2:
            active[slot] = float(weight_map[key])
    error = (pixels - target).norm(dim=-1)
    mirrored_error = (pixels - observed[:, mirrored_ids]).norm(dim=-1)
    mirrored_confidence = ((scores[:, mirrored_ids] - 1.5) / 3.0).clamp(0.0, 1.0)
    direct = (robust(error, 25.0) * confidence * active).sum(1)
    swapped = (robust(mirrored_error, 25.0) * mirrored_confidence * active).sum(1)
    data_term = torch.minimum(direct, swapped).sum() / count
    terms = {"keypoints": data_term}
    accel = rotations[2:] - 2 * rotations[1:-1] + rotations[:-2]
    terms["smooth"] = 30.0 * (accel ** 2).sum() / count
    root_accel = root_location[2:] - 2 * root_location[1:-1] + root_location[:-2]
    root_spin = root_rotation[2:] - 2 * root_rotation[1:-1] + root_rotation[:-2]
    terms["root_smooth"] = 300.0 * ((root_accel ** 2).sum() + (root_spin ** 2).sum()) / count
    root_velocity = root_location[1:] - root_location[:-1]
    terms["root_speed"] = 15.0 * (root_velocity ** 2).sum() / count
    for anchor in args.anchor:
        frame_text, axis_name, value_text = anchor.split(":")
        if int(frame_text) in frames:
            k = frames.index(int(frame_text))
            terms[f"anchor {anchor}"] = 50.0 * (root_location[k, "XYZ".index(axis_name)] - float(value_text)) ** 2
    terms["prior"] = 0.005 * (rotations ** 2).sum() / count
    terms["behind"] = torch.relu(0.3 - depth).sum()
    if mask_distance is not None and stage >= 1:
        sample_pixels, _ = project(skeleton.skin(world, samples, sample_bones, sample_weights, count))
        outside = sample_map(mask_distance, sample_pixels)
        terms["silhouette"] = 2.0 * robust(outside, 15.0).mean()
    if prop is not None:
        placed = film_grown(world[held_hand]) @ grips()
        rotation, translation = placed[:, :3, :3], placed[:, :3, 3]
        if args.prop_weight > 0.0:
            precision, coverage = fitted(prop_parts, camera_projection, rotation, translation, frame_slots)
            terms["prop"] = args.prop_weight * ((precision + coverage) * prop_present).sum() / prop_present.sum().clamp(min=1.0)
        if aims is not None:
            held_rotation = (world[held_hand] @ grips())[:, :3, :3]
            terms["aim"] = args.aim_weight * ((held_rotation - aims) ** 2).sum((1, 2)).mean()
        held = world[held_hand] @ grips()
        tracked = Prop.place(held[:, :3, :3], held[:, :3, 3], prop_track)
        acceleration = tracked[2:] - 2 * tracked[1:-1] + tracked[:-2]
        terms["prop_smooth"] = args.prop_smooth * (acceleration ** 2).sum(-1).mean()
        drift = (drift_turn ** 2).sum(-1) / 0.1 ** 2 + (drift_shift ** 2).sum(-1) / 0.03 ** 2
        terms["drift"] = args.grip_drift * DRIFT_SCHEDULE[stage] * drift.mean()
    return terms


DRIFT_SCHEDULE = (0.01, 0.1, 1.0)


stages = [(0, int(args.iterations * 0.25), [root_rotation, root_location], 0.03),
          (1, int(args.iterations * 0.45), [rotations, root_rotation, root_location], 0.02),
          (2, int(args.iterations * 0.30), [rotations, root_rotation, root_location], 0.01)]
for stage, steps, parameters, rate in stages:
    groups = [{"params": parameters, "lr": rate}]
    if prop is not None:
        groups.append({"params": [grip_turn, grip_shift, drift_turn, drift_shift], "lr": 0.01})
        if log_film_scale.requires_grad:
            groups.append({"params": [log_film_scale], "lr": 0.003})
    optimizer = torch.optim.Adam(groups)
    for step in range(steps):
        optimizer.zero_grad()
        terms = loss_terms(stage)
        total = sum(terms.values())
        total.backward()
        optimizer.step()
        if step % 200 == 0 or step == steps - 1:
            print(f"stage {stage} step {step:4d} " + " ".join(f"{k} {float(v):.3f}" for k, v in terms.items()), flush=True)

with torch.no_grad():
    world = pose(rotations, root_rotation, root_location)
    pixels, _ = project(keypoint_positions(world))
    target = observed[:, keypoint_ids]
    confidence = scores[:, keypoint_ids]
    direct = (pixels - target).norm(dim=-1)
    mirrored = (pixels - observed[:, mirrored_ids]).norm(dim=-1)
    use_mirror = (mirrored.median(1).values < direct.median(1).values)[:, None]
    error = torch.where(use_mirror, mirrored, direct)
    print("frames fitted with left and right swapped:", [frames[k] for k in range(count) if bool(use_mirror[k, 0])])
    good = confidence > 3.0
    print("median keypoint error (px, confident body):", float(error[:, :23][good[:, :23]].median()),
          " hands:", float(error[:, 23:][good[:, 23:]].median()) if good[:, 23:].any() else None)
    if prop is not None:
        placed = film_grown(world[held_hand]) @ grips()
        rotation, translation = placed[:, :3, :3], placed[:, :3, 3]
        print("film scale", float(torch.exp(log_film_scale)))
        for part_index, part in enumerate(prop_parts):
            inner = camera_projection(Prop.place(rotation, translation, part.points), frame_slots)
            cover = camera_projection(Prop.place(rotation, translation, part.cover_points), frame_slots)
            outside = part.silhouette.outside(inner, frame_slots)
            gaps = part.silhouette.gaps(cover, frame_slots)
            print(f"prop part {part_index}: frame, share outside its silhouette, median gap (px):",
                  " ".join(f"{frame}:{float((outside[k] > 6.0).float().mean()):.2f}/{float(gaps[k].median()):.1f}" for k, frame in enumerate(frames)))
        if aims is not None:
            held_rotation = (world[held_hand] @ grips())[:, :3, :3]
            turn = torch.acos(((torch.einsum("fij,fij->f", held_rotation, aims) - 1.0) / 2.0).clamp(-1.0, 1.0)) * 57.2958
            print("prop turned off the picture's angle (degrees):", " ".join(f"{frames[k]}:{float(turn[k]):.0f}" for k in range(0, count, 5)))
        print("grip drift (degrees / cm):", " ".join(f"{frames[k]}:{float(drift_turn[k].norm()) * 57.3:.0f}/{float(drift_shift[k].norm()) * 100:.0f}"
                                                    for k in range(0, count, 5)))

result = {"armature": "Avatar_LaPluma", "frames": []}
with torch.no_grad():
    object_rotation = axis_angle_matrices(root_rotation).cpu().numpy()
    for k, frame in enumerate(frames):
        bones = {}
        vectors = {}
        for name in FITTED:
            vector = rotations[k, fitted_index[name]]
            matrix = (euler_xyz(vector) if name in FINGERS else axis_angle_matrices(vector)).cpu().numpy()
            bones[name] = [round(float(v), 6) for v in quaternion_from_matrix(matrix)]
            vectors[name] = [round(float(v), 6) for v in vector.cpu().numpy()]
        result["frames"].append({"frame": frame,
                                 "location": [round(float(v), 5) for v in root_location[k].cpu().numpy()],
                                 "rotation": [round(float(v), 6) for v in quaternion_from_matrix(object_rotation[k])],
                                 "rotation_vector": [round(float(v), 6) for v in root_rotation[k].cpu().numpy()],
                                 "bones": bones, "bones_vector": vectors})
if prop is not None:
    with torch.no_grad():
        prop.write_grips(result["frames"], grips())
        result["held"] = {prop.name: names[held_hand]}
        result["film_scales"] = {prop.name: round(float(torch.exp(log_film_scale)), 4)}
json.dump(result, open(args.out, "w", encoding="utf-8"), indent=1)
print("wrote", args.out)
