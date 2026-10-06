"""
Fit the cast's rig to the reference, frame by frame (PyTorch).

    python fit_pose.py <rig.npz> <keypoints.npz> <camera.json> <first> <last> <out performance.json>
                       [--masks DIR] [--start pose.json] [--iterations N]

The rig (``export_rig.py``) is posed with Blender's own forward kinematics:
a bone's pose is its parent's pose times its rest offset times its local
rotation, the second and third finger segments add the first segment's
curl (the rig's Copy Rotation constraints).  Every frame of the shot is
fitted at once: the whole-body keypoints of the reference (``keypoints.py``)
pull the rig's joints onto them through the shot's solved camera, a
silhouette (``--masks``) keeps the rig inside the character's outline, and
smoothness ties neighbouring frames together.  The fit runs coarse to fine
-- placement, then body and limbs, then hands.

An ``--anchor frame:axis:value`` pins the root's set coordinate on a frame
where the reference shows where she is (breaking through a window) and the
picture alone cannot tell how far away she is.

The performance written is the rig object's placement (set metres) and
every fitted bone's local rotation for every frame; the film's interpreter
keys them on the cast.
"""
import argparse
import json
import math
import os

import cv2
import numpy as np
import torch

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
parser.add_argument("--width", type=int, default=1920)
parser.add_argument("--height", type=int, default=1080)
args = parser.parse_args()
device = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(0)

rig = np.load(args.rig)
names = [str(name) for name in rig["names"]]
index = {name: k for k, name in enumerate(names)}
parents = rig["parents"]
rest = torch.tensor(rig["rest"], dtype=torch.float32, device=device)
lengths = torch.tensor(rig["lengths"], dtype=torch.float32, device=device)

BODY = ["Pelvis", "Spine", "Spine1", "Spine2", "Neck", "Head", "Clavicle_L", "Clavicle_R", "UpperArm_L", "UpperArm_R",
        "Forearm_L", "Forearm_R", "Hand_L", "Hand_R", "Thigh_L", "Thigh_R", "Calf_L", "Calf_R", "Foot_L", "Foot_R",
        "Toe0_L", "Toe0_R"]
FINGERS = [f"Finger{digit}_{side}" for side in "LR" for digit in range(5)]
CURLED = {f"Finger{digit}{segment}_{side}": f"Finger{digit}{'' if segment == 1 else 1}_{side}"
          for side in "LR" for digit in range(5) for segment in (1, 2)}
FITTED = BODY + FINGERS


def bone_point(name, along=0.0, offset=(0.0, 0.0, 0.0)):
    return (index[name], along, offset)


SIDES = {"L": "left", "R": "right"}
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

camera_data = json.load(open(args.camera, encoding="utf-8"))
keys = {key["frame"]: key for key in camera_data["keys"]}
focal = float(camera_data["focal_px"])


def quaternion_matrix(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


camera_rotation = torch.tensor(np.array([quaternion_matrix(keys[f]["rotation"]) for f in frames]), dtype=torch.float32, device=device)
camera_location = torch.tensor(np.array([keys[f]["location"] for f in frames]), dtype=torch.float32, device=device)


def project(points):
    """points (F, N, 3) world -> pixels (F, N, 2), depth (F, N)."""
    local = torch.einsum("fij,fnj->fni", camera_rotation.transpose(1, 2), points - camera_location[:, None, :])
    depth = -local[..., 2]
    safe = depth.clamp(min=0.05)
    u = args.width / 2 + focal * local[..., 0] / safe
    v = args.height / 2 - focal * local[..., 1] / safe
    return torch.stack([u, v], -1), depth


def axis_angle_matrix(vector):
    angle = vector.norm(dim=-1, keepdim=True).clamp(min=1e-8)
    axis = vector / angle
    x, y, z = axis.unbind(-1)
    zero = torch.zeros_like(x)
    K = torch.stack([zero, -z, y, z, zero, -x, -y, x, zero], -1).reshape(*vector.shape[:-1], 3, 3)
    eye = torch.eye(3, device=vector.device).expand(K.shape)
    sin = torch.sin(angle)[..., None]
    cos = torch.cos(angle)[..., None]
    return eye + sin * K + (1 - cos) * (K @ K)


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


offsets = {}
for b, parent in enumerate(parents):
    offsets[b] = rest[b] if parent < 0 else torch.linalg.inv(rest[parent]) @ rest[b]
order = []
seen = set()
for b in range(len(names)):
    chain = []
    k = b
    while k >= 0 and k not in seen:
        chain.append(k)
        k = parents[k]
    for k in reversed(chain):
        seen.add(k)
        order.append(k)

needed = set()
for bone, _, _ in KEYPOINTS.values():
    k = bone
    while k >= 0:
        needed.add(k)
        k = parents[k]
mesh_names = [str(name) for name in rig["meshes"]]
kept = np.array([mesh_names[source] not in set(args.exclude) for source in rig["sources"]])
samples = torch.tensor(rig["positions"][kept], dtype=torch.float32, device=device)
sample_bones = torch.tensor(rig["bones"][kept], dtype=torch.long, device=device)
sample_weights = torch.tensor(rig["weights"][kept], dtype=torch.float32, device=device)
for b in rig["bones"][kept].ravel():
    k = int(b)
    while k >= 0:
        needed.add(k)
        k = parents[k]
order = [b for b in order if b in needed]

fitted_index = {name: k for k, name in enumerate(FITTED)}
rotations = torch.zeros(count, len(FITTED), 3, device=device)
root_rotation = torch.zeros(count, 3, device=device)
root_location = torch.zeros(count, 3, device=device)

if args.start and os.path.exists(args.start):
    start = json.load(open(args.start, encoding="utf-8"))
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
    torso = [5, 6, 11, 12]
    for k in range(count):
        points_2d = observed[k].cpu().numpy()
        shoulders = (points_2d[5] + points_2d[6]) / 2
        hips = (points_2d[11] + points_2d[12]) / 2
        width = np.linalg.norm(points_2d[5] - points_2d[6]) + np.linalg.norm(points_2d[11] - points_2d[12])
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
        from scipy.spatial.transform import Rotation as _Rotation
        root_rotation.data[k] = torch.tensor(_Rotation.from_matrix(world_from_body).as_rotvec(), dtype=torch.float32, device=device)
        ray = np.array([(centre_pixel[0] - args.width / 2) / focal, -(centre_pixel[1] - args.height / 2) / focal, -1.0])
        torso_centre = camera_location[k].cpu().numpy() + rotation_camera @ ray * depth
        root_location.data[k] = torch.tensor(torso_centre - body_up * 1.12, dtype=torch.float32, device=device)

rotations.requires_grad_(True)
root_rotation.requires_grad_(True)
root_location.requires_grad_(True)


def pose(rotations, root_rotation, root_location):
    """World matrices (F, B, 4, 4) of the needed bones."""
    F = rotations.shape[0]
    world = {}
    object_matrix = torch.eye(4, device=device).repeat(F, 1, 1)
    object_matrix[:, :3, :3] = axis_angle_matrix(root_rotation)
    object_matrix[:, :3, 3] = root_location
    first_segments = {}
    for b in order:
        name = names[b]
        local = torch.eye(4, device=device).repeat(F, 1, 1)
        if name in fitted_index:
            vector = rotations[:, fitted_index[name]]
            if name in FINGERS:
                local[:, :3, :3] = euler_xyz(vector)
                first_segments[name] = vector[:, 0]
            else:
                local[:, :3, :3] = axis_angle_matrix(vector)
        elif name in CURLED:
            source = CURLED[name]
            while source in CURLED:
                source = CURLED[source]
            if source in first_segments:
                local[:, :3, :3] = rotation_x(first_segments[source])
        parent = parents[b]
        base = object_matrix @ offsets[b] if parent < 0 else world[parent] @ offsets[b]
        world[b] = base @ local
    return world


def keypoint_positions(world):
    result = []
    for key in sorted(KEYPOINTS):
        bone, along, offset = KEYPOINTS[key]
        point = torch.tensor([offset[0], float(lengths[bone]) * along + offset[1], offset[2], 1.0], device=device)
        result.append((world[bone] @ point)[:, :3])
    return torch.stack(result, 1)


keypoint_ids = torch.tensor(sorted(KEYPOINTS), device=device)
MIRRORED = {}
for left, right in ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 20), (18, 21), (19, 22)):
    MIRRORED[left], MIRRORED[right] = right, left
for offset in range(21):
    MIRRORED[91 + offset], MIRRORED[112 + offset] = 112 + offset, 91 + offset
mirrored_ids = torch.tensor([MIRRORED.get(key, key) for key in sorted(KEYPOINTS)], device=device)
inverse_rest = torch.linalg.inv(rest)


def skinned(world):
    matrices = torch.stack([world[b] if b in world else torch.eye(4, device=device).repeat(count, 1, 1) for b in range(len(names))], 1)
    skinning = matrices @ inverse_rest[None]
    homogeneous = torch.cat([samples, torch.ones(len(samples), 1, device=device)], 1)
    total = torch.zeros(matrices.shape[0], len(samples), 3, device=device)
    for slot in range(4):
        transform = skinning[:, sample_bones[:, slot]]
        moved = torch.einsum("fnij,nj->fni", transform, homogeneous)[..., :3]
        total = total + moved * sample_weights[None, :, slot, None]
    return total


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


body_keys = [k for k in range(23)]
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
        sample_pixels, _ = project(skinned(world))
        outside = sample_map(mask_distance, sample_pixels)
        terms["silhouette"] = 2.0 * robust(outside, 15.0).mean()
    return terms


stages = [(0, int(args.iterations * 0.25), [root_rotation, root_location], 0.03),
          (1, int(args.iterations * 0.45), [rotations, root_rotation, root_location], 0.02),
          (2, int(args.iterations * 0.30), [rotations, root_rotation, root_location], 0.01)]
for stage, steps, parameters, rate in stages:
    optimizer = torch.optim.Adam(parameters, lr=rate)
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


def quaternion_from_matrix(matrix):
    m = matrix
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        return [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        return [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    if m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        return [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    return [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]


result = {"armature": "Avatar_LaPluma", "frames": []}
with torch.no_grad():
    object_rotation = axis_angle_matrix(root_rotation).cpu().numpy()
    for k, frame in enumerate(frames):
        bones = {}
        vectors = {}
        for name in FITTED:
            vector = rotations[k, fitted_index[name]]
            matrix = (euler_xyz(vector) if name in FINGERS else axis_angle_matrix(vector)).cpu().numpy()
            bones[name] = [round(float(v), 6) for v in quaternion_from_matrix(matrix)]
            vectors[name] = [round(float(v), 6) for v in vector.cpu().numpy()]
        result["frames"].append({"frame": frame,
                                 "location": [round(float(v), 5) for v in root_location[k].cpu().numpy()],
                                 "rotation": [round(float(v), 6) for v in quaternion_from_matrix(object_rotation[k])],
                                 "rotation_vector": [round(float(v), 6) for v in root_rotation[k].cpu().numpy()],
                                 "bones": bones, "bones_vector": vectors})
json.dump(result, open(args.out, "w", encoding="utf-8"), indent=1)
print("wrote", args.out)
