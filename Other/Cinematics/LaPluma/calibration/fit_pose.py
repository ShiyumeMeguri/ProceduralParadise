"""
Fit the cast's rig to the reference, frame by frame (PyTorch).

    python fit_pose.py <rig.npz> <profile.json> <keypoints.npz> <camera.json> <first> <last> <out performance.json>
                       [--masks DIR] [--occluders DIR] [--parts DIR] [--start performance.json] [--iterations N]
                       [--anchor F:AXIS:V ...] [--prop MESH --grip NAME] [--held-weight W] [--drift-weight W]
                       [--steady-weight W] [--still FIRST:LAST ...] [--regrip FRAME ...]

The rig (``export_rig.py``) is posed with Blender's own forward kinematics
(``skeleton.py``).  What the rig is -- which bones are fitted and how far
each may turn, which keypoint sits on which bone, which finger segments
copy their first segment's curl, which keypoints mirror which and which
mirror together -- is the cast's profile (``cast/<name>.json``), data.  A
detector seeing her from behind reads her left and right the wrong way
round, sometimes for her legs and not her arms: each swap group (head,
arms, legs) is read as detected or swapped, whichever fits it.  Every fitted joint is three
Euler angles in its bone's rest frame, each held within the joint's range
(a knee and an elbow bend one way about one axis, a hip or a shoulder
turns within a body's reach): a pose that only fits the picture from the
camera, folding a knee sideways or backwards, cannot be reached.

Every frame of the shot is fitted at once: the whole-body keypoints of the
reference (``keypoints.py``) pull the rig onto them through the shot's
solved camera, a silhouette (``--masks``, and ``--occluders``: what may hide
her, her scythe) keeps the rig inside the character's outline, and
smoothness ties neighbouring frames together: the joints' turns change
smoothly, and what is drawn -- her keypoints and the points of a prop she
holds -- does not shake: its acceleration in the world, as many pixels as
that shakes it on the picture at its depth, costs ``--steady-weight`` a
point and a frame (none unless the shot asks: where the camera flies with her,
her motion in the world is the flight, and holding it steady pulled her off
her keypoints) (the joints' smoothness alone weighs a wrist's turn as a
toe's, and a scythe held a metre from the hand shook).  It moves the arm
and the grip's drift, never the grip: a prop the hand turns about its
length shakes least, and the grip would turn the shaft onto that axis.
It is weighed in the last stage, once the pose is found: a start's shake
outweighs every other term and turns the arm wherever it shakes least.
Over the frames a ``--still first:last`` names -- the reference holding
her still -- what is drawn does not move either: its speed is weighed as
its acceleration is (a fit that is only kept from shaking wanders after
the keypoints' slow drift).  A keypoint the detector puts
outside that outline (grown by ``KEYPOINT_MARGIN`` pixels) is its mistake --
seen from behind it finds a face in her coat -- and is not used; nor is one
within ``--edge-margin`` pixels of the frame's edge: what lies beyond the
frame the detector still places, on its edge (her ankles below a shot cut at
her knees), and a leg pulled up to it kneels.

The reference is an AI film: its character's proportions are not the
model's, so only the torso's keypoints (those without a parent in the
profile's ``segments``) are pulled onto their places.  A limb is fitted by
its segments' angles: each segment (a keypoint from its parent keypoint)
turns as the picture turns it, and is shortened only as far as the picture
shortens it beyond ``PROPORTION_TOLERANCE`` -- matching the places of a
limb the model draws shorter would reach it towards the camera.  How far a
keypoint still pulls (its robust scale) starts wide and narrows stage by
stage (``REACH``): a pose that starts far from its keypoints is first drawn
near them, then fitted closely, a detector's stray keypoint let go again.
Frames whose keypoints were set by hand (the keypoints file's ``annotated``)
are read left and right as given, and a keypoint set by hand (its ``by_hand``)
is the picture's truth: neither the outline (under a coat the mask leaves
out) nor the frame's edge drops it, and its misfit grows without bound
(:func:`firm`) where a detection's levels off -- a grip or a silhouette
cannot pull her away from it.  Without a ``--start`` she starts on each
frame where her torso's keypoints are seen standing on them, turned the way
they face; a frame where they are not seen starts between the nearest two
that are.

Keypoints and an outline place her limbs on the picture but not which is
nearer: a leg folded towards the camera and the same leg folded away look
alike.  The profile's ``parts`` (a part is the surface skinned below its
bones: a leg below its thigh) are masked in the shot (``--parts``: a
``roto.py`` folder, a mask per part, each told from the other by what only
it wears).  A part fills its own mask, and where a part's mask shows it and
not another part, that other part, if it falls there, lies behind it:
seen, a part is in front.
The fit runs coarse to fine -- placement (where the torso is seen, and the hand on what
it holds), then body and limbs, then hands.
An ``--anchor frame:axis:value`` pins the root's set coordinate on a frame
where the reference shows where she is (breaking through a window).

With ``--prop`` the prop she holds (the profile's ``props``, in the grip
the shot names: ``--grip``, one of its ``grips``, right or left) is held as a
hand holds it: hung on the hand by one grip for the whole shot -- the prop
turned so in the hand's frame, the hand on one point of its shaft -- with a
small drift of that turn, slow from frame to frame (``--drift-weight``: what
the drift and its changes cost), and the arm turns it as the picture turns
the prop -- a shot whose hand takes the prop again (``--regrip``: the
frames it does) holds it by a grip of its own over each span between -- :
the prop's turn against its silhouette's (``fit_prop.py``: the
``--start`` performance's ``placements``, one picture for any size; robust
-- a placement flipped end for end is let go, ``--held-weight``), the palm
on the grip's point of the picture's shaft (``--grip-weight``).  How large
the prop is drawn in the film -- how far, then, it is -- is fitted as one
scale for the shot; that scale is only how the picture is matched: the prop
is as large as its maker made it (the cast's character sheet).  The grip
starts as the hand holds the placed prop on most frames (the turn closest to
all the frames' turns), on the point of the picture's shaft the palm lies
nearest on the middle frame of the shot.  Fitted freely frame by frame -- the
silhouette's turn, the shaft's point nearest the palm -- the prop shimmered
in her hand: in the hall's still picture its outline moved 8 px a frame
where the reference's moves under one.  The grips written (the prop in the
hand's frame, frame by frame: the grip and its drift) hang it on the hand at
that size.

The card is shared (``gpu_budget.py``): the terms each frame answers for
alone are added up a batch of frames at a time, as many as the claim
holds, and only the terms that tie frames together see the whole shot.

The performance written is the rig object's placement (set metres) and
every fitted bone's local rotation for every frame, with the rest of every
bone it keys or holds a prop with (``rests``: a rig re-rolled since is
keyed the same pose); the film's interpreter keys them on the cast.
"""
import argparse
import json
import os

import cv2
import numpy as np
import torch
from scipy.spatial.transform import Rotation as ScipyRotation
from scipy.spatial.transform import Slerp

from gpu_budget import chunk, claim
from prop import Prop
from silhouette import Silhouette
from skeleton import Camera, Skeleton, axis_angle_matrices, quaternion_from_matrix, rests

parser = argparse.ArgumentParser()
parser.add_argument("rig")
parser.add_argument("profile")
parser.add_argument("keypoints")
parser.add_argument("camera")
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("out")
parser.add_argument("--masks", default=None)
parser.add_argument("--occluders", default=None, help="masks of what may hide her (her scythe)")
parser.add_argument("--parts", default=None, help="a roto.py folder: a mask folder per profile part")
parser.add_argument("--cover-weight", type=float, default=1.0, help="a part filling its mask")
parser.add_argument("--silhouette-weight", type=float, default=2.0, help="her surface staying inside her outline (and out of the picture where it shows none of her)")
parser.add_argument("--order-weight", type=float, default=20.0, help="a part seen in front of another")
parser.add_argument("--part-samples", type=int, default=700, help="surface samples per part for coverage and order")
parser.add_argument("--start", default=None)
parser.add_argument("--iterations", type=int, default=1500)
parser.add_argument("--exclude", nargs="*", default=["Scythe"])
parser.add_argument("--anchor", nargs="*", default=[], help="frame:axis:value -- the root's set coordinate on that frame")
parser.add_argument("--prop", default=None, help="the mesh of a prop she holds")
parser.add_argument("--grip", default=None, help="which of the prop's grips (the profile's props.<prop>.grips) holds it")
parser.add_argument("--grip-weight", type=float, default=40.0)
parser.add_argument("--held-weight", type=float, default=1.0, help="the held prop's turn against its silhouette's")
parser.add_argument("--drift-weight", type=float, default=10.0, help="the grip's drift from frame to frame and in all")
parser.add_argument("--steady-weight", type=float, default=0.0, help="what is drawn shaking: a point's acceleration (px at its depth) squared")
parser.add_argument("--still", nargs="*", default=[], help="first:last -- frames the reference holds her still on: what is drawn does not move")
parser.add_argument("--regrip", nargs="*", type=int, default=[], help="frames the hand takes the prop again: a grip for every span")
parser.add_argument("--hand-weight", type=float, default=0.4, help="the hand keypoints' weight against the body's")
parser.add_argument("--edge-margin", type=float, default=24.0, help="keypoints this near the frame's edge are not used (px)")
parser.add_argument("--width", type=int, default=1920)
parser.add_argument("--height", type=int, default=1080)
args = parser.parse_args()
device = "cuda"
budget = claim()
torch.manual_seed(0)

skeleton = Skeleton(args.rig, device)
profile = json.load(open(args.profile, encoding="utf-8"))
names = skeleton.names
index = skeleton.index
lengths = skeleton.lengths

FITTED = list(profile["joints"])
fitted_index = {name: k for k, name in enumerate(FITTED)}
limits = torch.deg2rad(torch.tensor([[profile["joints"][name][axis] for axis in "xyz"] for name in FITTED],
                                    dtype=torch.float32, device=device))
low, high = limits[..., 0], limits[..., 1]
free = (high - low) > 1e-6
CURLED = profile["curls"]
KEYPOINTS = {int(key): (index[spec["bone"]], float(spec.get("along", 0.0)), tuple(spec.get("offset", (0.0, 0.0, 0.0))))
             for key, spec in profile["keypoints"].items()}
MIRRORED = {}
for left, right in profile["mirror"]:
    MIRRORED[left], MIRRORED[right] = right, left
TORSO = set(profile["torso"])
BODY_KEYS = profile["body"]
SWAP_GROUPS = list(profile["swap_groups"])
GROUP_OF = {key: g for g, name in enumerate(SWAP_GROUPS) for first, last in profile["swap_groups"][name]["keys"] for key in range(first, last + 1)}
SEGMENT_OF = {int(child): int(parent) for child, parent in profile["segments"].items()}
PROPORTION_TOLERANCE = float(np.log(1.3))
HELD_REACH = 0.3
DRIFT_STEADY = 100.0
STEADY_PROP_POINTS = 32
REACH = (4.0, 2.0, 1.0)
LEFT_KEYS = {left for left, _ in profile["mirror"]}
RIGHT_KEYS = {right for _, right in profile["mirror"]}

data = np.load(args.keypoints)
frame_list = [int(f) for f in data["frames"]]
selected = [k for k, f in enumerate(frame_list) if args.first <= f <= args.last]
frames = [frame_list[k] for k in selected]
observed = torch.tensor(data["points"][selected], dtype=torch.float32, device=device)
scores = torch.tensor(data["scores"][selected], dtype=torch.float32, device=device)
by_hand = torch.tensor(data["by_hand"][selected] if "annotated" in data else np.zeros(data["scores"][selected].shape, bool), device=device)
count = len(frames)
KEYPOINT_MARGIN = 40
if args.masks:
    outside = np.zeros(tuple(scores.shape), bool)
    pixels = data["points"][selected]
    for slot, frame in enumerate(frames):
        outline = None
        for directory in [args.masks] + ([args.occluders] if args.occluders else []):
            path = os.path.join(directory, "m%04d.png" % frame)
            if os.path.exists(path):
                layer = cv2.imread(path, cv2.IMREAD_GRAYSCALE) > 127
                outline = layer if outline is None else outline | layer
        if outline is None:
            continue
        grown = cv2.dilate(outline.astype(np.uint8), np.ones((2 * KEYPOINT_MARGIN + 1, 2 * KEYPOINT_MARGIN + 1), np.uint8)) > 0
        u = np.clip(np.round(pixels[slot, :, 0]).astype(int), 0, grown.shape[1] - 1)
        v = np.clip(np.round(pixels[slot, :, 1]).astype(int), 0, grown.shape[0] - 1)
        outside[slot] = ~grown[v, u]
    outside &= ~by_hand.cpu().numpy()
    dropped = outside & (data["scores"][selected] > 1.5)
    scores = torch.where(torch.tensor(outside, device=device), torch.zeros_like(scores), scores)
    worst = sorted(((int(dropped[slot].sum()), frame) for slot, frame in enumerate(frames)), reverse=True)[:8]
    print("keypoints outside her outline, not used:", int(dropped.sum()), "of", int((data["scores"][selected] > 1.5).sum()),
          "-- most on", [(frame, n) for n, frame in worst if n], flush=True)
edge = ((observed[..., 0] < args.edge_margin) | (observed[..., 0] > args.width - args.edge_margin)
        | (observed[..., 1] < args.edge_margin) | (observed[..., 1] > args.height - args.edge_margin)) & ~by_hand
print("keypoints on the frame's edge, not used:", int((edge & (scores > 1.5)).sum()), flush=True)
scores = torch.where(edge, torch.zeros_like(scores), scores)

camera = Camera(args.camera, frames, args.width, args.height, device)
focal = camera.focal
camera_rotation = camera.rotation
camera_location = camera.location
project = camera.project


def euler_xyz(vector):
    """Blender XYZ Euler: R = Rz @ Ry @ Rx."""
    x, y, z = vector.unbind(-1)
    cx, sx, cy, sy, cz, sz = torch.cos(x), torch.sin(x), torch.cos(y), torch.sin(y), torch.cos(z), torch.sin(z)
    one, zero = torch.ones_like(x), torch.zeros_like(x)
    Rx = torch.stack([one, zero, zero, zero, cx, -sx, zero, sx, cx], -1).reshape(*x.shape, 3, 3)
    Ry = torch.stack([cy, zero, sy, zero, one, zero, -sy, zero, cy], -1).reshape(*x.shape, 3, 3)
    Rz = torch.stack([cz, -sz, zero, sz, cz, zero, zero, zero, one], -1).reshape(*x.shape, 3, 3)
    return Rz @ Ry @ Rx


def rotation_x(angle):
    cos, sin = torch.cos(angle), torch.sin(angle)
    one, zero = torch.ones_like(angle), torch.zeros_like(angle)
    return torch.stack([one, zero, zero, zero, cos, -sin, zero, sin, cos], -1).reshape(*angle.shape, 3, 3)


def angles_of(parameters):
    """Joint angles (F, J, 3) within their ranges: a free axis is its range squashed onto the parameter."""
    return torch.where(free, low + (high - low) * torch.sigmoid(parameters), low)


def parameters_of(angles):
    share = ((angles - low) / (high - low).clamp(min=1e-6)).clamp(0.02, 0.98)
    return torch.log(share / (1.0 - share))


kept_meshes = [name for name in skeleton.meshes if name not in set(args.exclude)]
samples, sample_bones, sample_weights = skeleton.samples(kept_meshes)
prop = Prop(skeleton, args.prop) if args.prop else None
prop_profile = profile["props"][args.prop] if prop is not None else None
if prop is not None and args.grip not in prop_profile["grips"]:
    raise SystemExit(f"--prop {args.prop} needs --grip, one of {sorted(prop_profile['grips'])}")
grip = prop_profile["grips"][args.grip] if prop is not None else None
hand_bone = index[grip["hand"]] if prop is not None else None
palm_bones = [index[name] for name in grip["palm"]] if prop is not None else []
order = skeleton.ancestry([bone for bone, _, _ in KEYPOINTS.values()] + [int(b) for b in sample_bones.unique()]
                         + palm_bones + ([hand_bone] if hand_bone is not None else []))

start = json.load(open(args.start, encoding="utf-8")) if args.start and os.path.exists(args.start) else None
angles = torch.zeros(count, len(FITTED), 3, device=device)
root_rotation = torch.zeros(count, 3, device=device)
root_location = torch.zeros(count, 3, device=device)
if start is not None:
    by_frame = {key["frame"]: key for key in start["frames"]}
    for k, frame in enumerate(frames):
        if frame in by_frame:
            entry = by_frame[frame]
            root_location[k] = torch.tensor(entry["location"])
            root_rotation[k] = torch.tensor(entry["rotation_vector"])
            for name, value in entry["bones"].items():
                if name in fitted_index:
                    w, x, y, z = value
                    angles[k, fitted_index[name]] = torch.tensor(ScipyRotation.from_quat([x, y, z, w]).as_euler("xyz"), dtype=torch.float32)
else:
    torso_keys = [5, 6, 11, 12]
    seen = [k for k in range(count) if bool((scores[k, torso_keys] > 1.5).all())]
    if not seen:
        raise SystemExit("her torso's keypoints are seen on no frame: give a --start")
    for k in seen:
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
        root_rotation[k] = torch.tensor(ScipyRotation.from_matrix(world_from_body).as_rotvec(), dtype=torch.float32, device=device)
        ray = np.array([(centre_pixel[0] - args.width / 2) / focal, -(centre_pixel[1] - args.height / 2) / focal, -1.0])
        torso_centre = camera_location[k].cpu().numpy() + rotation_camera @ ray * depth
        root_location[k] = torch.tensor(torso_centre - body_up * 1.12, dtype=torch.float32, device=device)
    known = ScipyRotation.from_rotvec(root_rotation[seen].cpu().numpy())
    between = Slerp(seen, known) if len(seen) > 1 else None
    for k in range(count):
        if k in seen:
            continue
        if between is not None and seen[0] < k < seen[-1]:
            root_rotation[k] = torch.tensor(between([k]).as_rotvec()[0], dtype=torch.float32, device=device)
            after = next(j for j in seen if j > k)
            before = max(j for j in seen if j < k)
            share = (k - before) / (after - before)
            root_location[k] = root_location[before] * (1.0 - share) + root_location[after] * share
        else:
            nearest = seen[0] if k < seen[0] else seen[-1]
            root_rotation[k] = root_rotation[nearest]
            root_location[k] = root_location[nearest]
joint_parameters = parameters_of(angles).requires_grad_(True)
root_rotation.requires_grad_(True)
root_location.requires_grad_(True)


def object_matrices(root_rotation, root_location):
    matrix = torch.eye(4, device=device).repeat(root_location.shape[0], 1, 1)
    matrix[:, :3, :3] = axis_angle_matrices(root_rotation)
    matrix[:, :3, 3] = root_location
    return matrix


def pose(joint_angles, root_rotation, root_location):
    """World matrices (F, 4, 4) of the needed bones."""
    F = joint_angles.shape[0]
    object_matrix = object_matrices(root_rotation, root_location)

    def local(b):
        name = names[b]
        if name in fitted_index:
            matrix = torch.eye(4, device=device).repeat(F, 1, 1)
            matrix[:, :3, :3] = euler_xyz(joint_angles[:, fitted_index[name]])
            return matrix
        if name in CURLED:
            matrix = torch.eye(4, device=device).repeat(F, 1, 1)
            matrix[:, :3, :3] = rotation_x(joint_angles[:, fitted_index[CURLED[name]], 0])
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


keypoint_ids = torch.tensor(sorted(KEYPOINTS), device=device)
column_of = {key: k for k, key in enumerate(sorted(KEYPOINTS))}
segment_columns = torch.tensor([column_of[key] for key in sorted(KEYPOINTS) if key in SEGMENT_OF], device=device)
parent_columns = torch.tensor([column_of[SEGMENT_OF[key]] for key in sorted(KEYPOINTS) if key in SEGMENT_OF], device=device)
is_segment = torch.zeros(len(KEYPOINTS), dtype=torch.bool, device=device).index_fill_(0, segment_columns, True)
keypoint_groups = torch.tensor([GROUP_OF[key] for key in sorted(KEYPOINTS)], device=device)
mirrored_ids = torch.tensor([MIRRORED.get(key, key) for key in sorted(KEYPOINTS)], device=device)
weights = torch.tensor([args.hand_weight if key >= BODY_KEYS else 1.0 for key in sorted(KEYPOINTS)], device=device)
stage_active = [torch.tensor([1.0 if key in TORSO else 0.0 for key in sorted(KEYPOINTS)], device=device),
                torch.tensor([1.0 if key < BODY_KEYS else 0.0 for key in sorted(KEYPOINTS)], device=device),
                weights]

silhouette = Silhouette(args.masks, args.occluders, frames, args.width, args.height, device, targets=8) if args.masks else None
part_names = [name for name in profile.get("parts", {}) if args.parts and os.path.isdir(os.path.join(args.parts, name))]
dominant = sample_bones.gather(1, sample_weights.argmax(1, keepdim=True))[:, 0]
part_generator = torch.Generator().manual_seed(0)
part_samples, part_silhouettes = {}, {}
for name in part_names:
    below = torch.tensor(sorted(skeleton.descendants(index[bone] for bone in profile["parts"][name])), device=device)
    members = torch.nonzero(torch.isin(dominant, below))[:, 0]
    part_samples[name] = members[torch.randperm(len(members), generator=part_generator)[:args.part_samples].to(device)]
    part_silhouettes[name] = Silhouette(os.path.join(args.parts, name), None, frames, args.width, args.height, device, targets=300)
    print(f"part {name}: {len(members)} samples, masked on {int(part_silhouettes[name].present.sum())} of {count} frames", flush=True)

reading = torch.full((count, len(SWAP_GROUPS)), -1, dtype=torch.long, device=device)
everything = torch.arange(count, device=device)
for g, name in enumerate(SWAP_GROUPS):
    sides = profile["swap_groups"][name].get("parts")
    if not sides or not all(side in part_silhouettes for side in sides):
        continue
    group_keys = [key for key in sorted(KEYPOINTS) if GROUP_OF[key] == g and (key in LEFT_KEYS or key in RIGHT_KEYS)]
    points = observed[:, group_keys]
    sure = (scores[:, group_keys] > 3.0).float()
    handed = torch.tensor([1.0 if key in LEFT_KEYS else -1.0 for key in group_keys], device=device)
    on_left = (part_silhouettes[sides[0]].inside(points, everything) > 0.5).float()
    on_right = (part_silhouettes[sides[1]].inside(points, everything) > 0.5).float()
    vote = ((on_left - on_right) * handed * sure).sum(1)
    reading[:, g] = torch.where(vote >= 2, 0, torch.where(vote <= -2, 1, -1))
    print(f"{name}: read as detected on {int((reading[:, g] == 0).sum())} frames, swapped on "
          f"{[frames[k] for k in range(count) if int(reading[k, g]) == 1]}, left to the fit on {int((reading[:, g] == -1).sum())}", flush=True)
annotated = [k for k, frame in enumerate(frames) if frame in {int(value) for value in data.get("annotated", ())}]
reading[annotated] = 0
if annotated:
    print("frames annotated by hand, read as given:", [frames[k] for k in annotated], flush=True)


def project_frames(points, slots):
    """points (B, N, 3) world on the frames ``slots`` -> pixels (B, N, 2), depth (B, N)."""
    local = torch.einsum("fji,fnj->fni", camera_rotation[slots], points - camera_location[slots][:, None, :])
    depth = -local[..., 2]
    safe = depth.clamp(min=0.05)
    u = args.width / 2 + focal * local[..., 0] / safe
    v = args.height / 2 - focal * local[..., 1] / safe
    return torch.stack([u, v], -1), depth


frames_at_once = chunk(budget, bytes_each=len(samples) * 4 * 16 * 4 * 8 + 4 * 1024 ** 2 + len(part_names) ** 2 * args.part_samples ** 2 * 4 * 6,
                       resident=(silhouette.outside_maps.numel() * 8 if silhouette is not None else 0)
                       + sum(part.outside_maps.numel() * 8 for part in part_silhouettes.values()), most=count)
print(f"[gpu] {frames_at_once} frames at a time", flush=True)


def robust(residual, scale):
    return robust_squared(residual ** 2, scale)


def robust_squared(squared, scale):
    """``robust`` of a residual given as its square (smooth where the residual itself is not)."""
    ratio = squared / scale ** 2
    return ratio / (ratio + 1.0)


def firm(residual, scale):
    return firm_squared(residual ** 2, scale)


def firm_squared(squared, scale):
    """A misfit like :func:`robust_squared` near zero that keeps growing (as the residual over ``scale``) far off: what a
    keypoint set by hand costs."""
    return torch.sqrt(1.0 + squared / scale ** 2) - 1.0


if prop is not None:
    if start is None or prop.name not in start.get("film_scales", {}):
        raise SystemExit(f"--prop needs a --start performance with {prop.name}'s placements (fit_prop.py)")
    placements = prop.read_placements([by_frame[frame] for frame in frames])
    log_film_scale = torch.tensor([float(np.log(start["film_scales"][prop.name]))], device=device, requires_grad=True)
    shaft = torch.tensor(prop_profile["shaft"], dtype=torch.float32, device=device)
    span_of = torch.tensor([sum(frame >= regrip for regrip in args.regrip) for frame in frames], device=device)
    turns, shares = [], []
    with torch.no_grad():
        start_world = pose(angles_of(joint_parameters), root_rotation, root_location)
        for span in range(len(args.regrip) + 1):
            members = torch.nonzero(span_of == span)[:, 0]
            if len(members) == 0:
                raise SystemExit(f"--regrip {args.regrip}: span {span} holds none of the shot's frames")
            relative = start_world[hand_bone][members, :3, :3].transpose(1, 2) @ placements[members, :3, :3]
            cosines = (((relative[:, None] * relative[None]).sum((-2, -1)) - 1.0) / 2.0).clamp(-1.0, 1.0)
            spread = (torch.acos(cosines) ** 2 / (torch.acos(cosines) ** 2 + HELD_REACH ** 2)).sum(1)
            turns.append(ScipyRotation.from_matrix(relative[int(spread.argmin())].cpu().numpy()).as_rotvec())
            middle = int(members[len(members) // 2])
            ends = placements[middle, :3, :3] @ shaft.T + placements[middle, :3, 3:4]
            ends = camera_location[middle][:, None] + torch.exp(log_film_scale) * (ends - camera_location[middle][:, None])
            axis = ends[:, 1] - ends[:, 0]
            palm = sum(start_world[bone][middle, :3, 3] for bone in palm_bones) / len(palm_bones)
            shares.append(float((((palm - ends[:, 0]) * axis).sum() / (axis * axis).sum()).clamp(0.05, 0.95)))
            print(f"held: span {span} grip starts from frame {frames[int(members[int(spread.argmin())])]}'s, on {shares[-1]:.2f} "
                  f"of the shaft", flush=True)
    grip_turn = torch.tensor(np.array(turns), dtype=torch.float32, device=device, requires_grad=True)
    grip_drift = torch.zeros(count, 3, device=device, requires_grad=True)
    grip_along = torch.tensor([float(np.log(share / (1.0 - share))) for share in shares], device=device, requires_grad=True)
    steady_samples = prop.subset(STEADY_PROP_POINTS, torch.Generator().manual_seed(0))


def placed_prop(slots):
    """The prop where its silhouette puts it on the frames ``slots``, as large as the film's: grown about the camera."""
    scale = torch.exp(log_film_scale)
    matrix = placements[slots].clone()
    matrix[:, :3, :3] = placements[slots][:, :3, :3] * scale
    matrix[:, :3, 3] = camera_location[slots] + scale * (placements[slots][:, :3, 3] - camera_location[slots])
    return matrix


def palm_of(world):
    return sum(world[bone][:, :3, 3] for bone in palm_bones) / len(palm_bones)


def gripped_share(slots):
    """Where along the shaft the hand holds it on the frames ``slots`` (0 its first end, 1 its second)."""
    return torch.sigmoid(grip_along)[span_of[slots]]


def grip_distance(world, slots):
    """How far the palm is from the grip's point of the picture's shaft on the frames ``slots``."""
    held = placed_prop(slots)
    ends = torch.einsum("fij,nj->fni", held[:, :3, :3], shaft) + held[:, None, :3, 3]
    return (palm_of(world) - (ends[:, 0] + gripped_share(slots)[:, None] * (ends[:, 1] - ends[:, 0]))).norm(dim=-1)


def held_turn(world, slots, grip=None):
    """The held prop's turn on the frames ``slots``: the holding hand's, turned by the grip (``grip``, the fitted one
    unless given) and its drift there."""
    grip = grip_turn if grip is None else grip
    return world[hand_bone][:, :3, :3] @ axis_angle_matrices(grip[span_of[slots]]) @ axis_angle_matrices(grip_drift[slots])


def held_misfit(world, slots):
    """How far (radians) the held prop is turned from its silhouette's turn on the frames ``slots``."""
    cosine = (((held_turn(world, slots) * placements[slots][:, :3, :3]).sum((-2, -1)) - 1.0) / 2.0).clamp(-1.0 + 1e-6, 1.0 - 1e-6)
    return torch.acos(cosine)


def held_at_model_size(world, slots, fixed_grip=False):
    """The prop as large as its maker made it on the frames ``slots``, in her hand: turned by the grip and its drift
    from the hand, the grip's point of its shaft in the palm (the grip taken as it stands, not fitted through this,
    with ``fixed_grip``)."""
    rotation = held_turn(world, slots, grip_turn.detach() if fixed_grip else None)
    share = gripped_share(slots).detach() if fixed_grip else gripped_share(slots)
    local = shaft[0] + share[:, None] * (shaft[1] - shaft[0])
    matrix = torch.eye(4, device=device).repeat(len(slots), 1, 1)
    matrix[:, :3, :3] = rotation
    matrix[:, :3, 3] = palm_of(world) - torch.einsum("bij,bj->bi", rotation, local)
    return matrix


def drawn_points(world, slots):
    """What is drawn on the frames ``slots`` (B, N, 3): her keypoints and, held, points over the prop."""
    points = keypoint_positions(world)
    if prop is None:
        return points
    held = held_at_model_size(world, slots, fixed_grip=True)
    return torch.cat([points, Prop.place(held[:, :3, :3], held[:, :3, 3], steady_samples)], 1)


def shake(world):
    """How far (px at their depth) what is drawn accelerates from frame to frame, the shot's inner frames (F - 2, N), and
    how far it moves from each frame to the next (F - 1, N)."""
    points = drawn_points(world, everything)
    _, depth = project_frames(points, everything)
    scale = focal / depth.detach().clamp(min=0.3)
    accel = points[2:] - 2 * points[1:-1] + points[:-2]
    speed = points[1:] - points[:-1]
    return torch.sqrt((accel ** 2).sum(-1) + 1e-12) * scale[1:-1], torch.sqrt((speed ** 2).sum(-1) + 1e-12) * scale[:-1]


still_steps = torch.zeros(max(count - 1, 0), dtype=torch.bool, device=device)
for span in args.still:
    first_text, last_text = span.split(":")
    still_steps |= torch.tensor([int(first_text) <= frames[k] and frames[k + 1] <= int(last_text) for k in range(count - 1)],
                                dtype=torch.bool, device=device)


def misordered(pixels, depth, slots):
    """How far each part, where another part's mask shows that other part and not it, lies
    in front of that other part's surface there (m, summed over its samples)."""
    total = 0.0
    seen = {name: {other: part_silhouettes[other].inside(pixels[name], slots) for other in part_names} for name in part_names}
    for name in part_names:
        for other in part_names:
            if other == name:
                continue
            hidden = (seen[name][other] > 0.5).float() * (seen[name][name] < 0.5).float()
            near = torch.exp(-torch.cdist(pixels[name], pixels[other]) ** 2 / (2.0 * 6.0 ** 2))
            weight = near.sum(-1)
            surface = (near * depth[other][:, None, :]).sum(-1) / weight.clamp(min=1e-6)
            ahead = torch.relu(surface + 0.06 - depth[name]) * (weight > 0.5).float() * hidden
            total = total + torch.sqrt(ahead ** 2 + 0.01 ** 2).sub(0.01).sum()
    return total


def grouped(per_key):
    """Per-keypoint values (B, K) summed over the profile's swap groups (B, G)."""
    return torch.zeros(per_key.shape[0], len(SWAP_GROUPS), device=device).index_add_(1, keypoint_groups, per_key)


def segment_misfit(pixels, target):
    """Per segment (B, S): how far the rig's segment turns from the picture's (the squared chord between their
    directions, the turn's square for small turns), how much more than the proportions differ it is shortened or
    lengthened against it (log of the lengths' ratio beyond the tolerance), and the picture's segment's length (0
    where it has none: a keypoint not found sits at the origin)."""
    rig = pixels[:, segment_columns] - pixels[:, parent_columns]
    seen = target[:, segment_columns] - target[:, parent_columns]
    usable = seen.norm(dim=-1) > 1.0
    seen = torch.where(usable[..., None], seen, torch.ones_like(seen))
    seen_length = seen.norm(dim=-1)
    rig_length = torch.sqrt((rig ** 2).sum(-1) + 1e-6)
    chord = ((rig / rig_length[..., None] - seen / seen_length[..., None]) ** 2).sum(-1)
    ratio = torch.log(rig_length.clamp(min=1.0)) - torch.log(seen_length.clamp(min=1.0))
    return chord, torch.relu(ratio.abs() - PROPORTION_TOLERANCE), seen_length * usable


def keypoint_misfit(pixels, ids, slots, reach=1.0):
    """Per keypoint (B, K), read against the detector's keypoints ``ids`` (as detected or mirrored): a torso
    keypoint's distance from its place, a limb keypoint's segment's turn and shortening, each robust (its
    scale ``reach`` times its own; firm where set by hand) and weighted by how sure the detector is of what it needs."""
    target = observed[slots][:, ids]
    confidence = ((scores[slots][:, ids] - 1.5) / 3.0).clamp(0.0, 1.0)
    hand = by_hand[slots][:, ids]
    distance = (pixels - target).norm(dim=-1)
    placed = torch.where(hand, firm(distance, 25.0 * reach), robust(distance, 25.0 * reach)) * confidence
    chord, shortening, length = segment_misfit(pixels, target)
    sure = torch.minimum(confidence[:, segment_columns], confidence[:, parent_columns]) * (length / 30.0).clamp(0.0, 1.0)
    hand_segment = hand[:, segment_columns] & hand[:, parent_columns]
    turned = torch.where(hand_segment, firm_squared(chord, 0.25 * reach) + firm(shortening, 0.2 * reach),
                         robust_squared(chord, 0.25 * reach) + robust(shortening, 0.2 * reach))
    angled = torch.zeros_like(placed).index_copy(1, segment_columns, turned * sure)
    return torch.where(is_segment[None], angled, placed)


def frame_terms(stage, slots):
    """The terms each frame answers for alone, on the frames ``slots``: parts of the shot's sums."""
    joint_angles = angles_of(joint_parameters[slots])
    world = pose(joint_angles, root_rotation[slots], root_location[slots])
    pixels, depth = project_frames(keypoint_positions(world), slots)
    active = stage_active[stage]
    direct = grouped(keypoint_misfit(pixels, keypoint_ids, slots, REACH[stage]) * active)
    swapped = grouped(keypoint_misfit(pixels, mirrored_ids, slots, REACH[stage]) * active)
    read = reading[slots]
    chosen = torch.where(read == 0, direct, torch.where(read == 1, swapped, torch.minimum(direct, swapped)))
    terms = {"keypoints": chosen.sum() / count, "behind": torch.relu(0.3 - depth).sum()}
    if (silhouette is not None or part_names) and stage >= 1:
        sample_pixels, sample_depth = project_frames(skeleton.skin(world, samples, sample_bones, sample_weights, len(slots)), slots)
    if silhouette is not None and stage >= 1:
        terms["silhouette"] = args.silhouette_weight * (silhouette.precision(sample_pixels, slots) * silhouette.present[slots]).sum() / count
    if part_names and stage >= 1:
        pixels = {name: sample_pixels[:, part_samples[name]] for name in part_names}
        depth = {name: sample_depth[:, part_samples[name]] for name in part_names}
        terms["cover"] = args.cover_weight * sum((part_silhouettes[name].coverage(pixels[name], slots) * part_silhouettes[name].present[slots]).sum()
                                                 for name in part_names) / count
        terms["order"] = args.order_weight * misordered(pixels, depth, slots) / (count * args.part_samples)
    if prop is not None:
        terms["grip"] = args.grip_weight * torch.sqrt(grip_distance(world, slots) ** 2 + 0.01 ** 2).sum() / count
    if prop is not None and stage >= 1:
        terms["held"] = args.held_weight * robust(held_misfit(world, slots), HELD_REACH).sum() / count
    return terms


def shot_terms(stage):
    """The terms that tie the frames together."""
    joint_angles = angles_of(joint_parameters)
    terms = {}
    accel = joint_angles[2:] - 2 * joint_angles[1:-1] + joint_angles[:-2]
    terms["smooth"] = 30.0 * (accel ** 2).sum() / count
    root_accel = root_location[2:] - 2 * root_location[1:-1] + root_location[:-2]
    root_spin = root_rotation[2:] - 2 * root_rotation[1:-1] + root_rotation[:-2]
    terms["root_smooth"] = 300.0 * ((root_accel ** 2).sum() + (root_spin ** 2).sum()) / count
    for anchor in args.anchor:
        frame_text, axis_name, value_text = anchor.split(":")
        if int(frame_text) in frames:
            k = frames.index(int(frame_text))
            terms[f"anchor {anchor}"] = 50.0 * (root_location[k, "XYZ".index(axis_name)] - float(value_text)) ** 2
    terms["prior"] = 0.005 * (joint_angles ** 2).sum() / count
    if args.steady_weight > 0.0 and count > 2 and stage == len(REACH) - 1:
        accel, speed = shake(pose(joint_angles, root_rotation, root_location))
        terms["steady"] = args.steady_weight * (accel ** 2).sum() / count
        if bool(still_steps.any()):
            terms["still"] = args.steady_weight * (speed[still_steps] ** 2).sum() / count
    if prop is not None:
        drift_change = grip_drift[2:] - 2 * grip_drift[1:-1] + grip_drift[:-2]
        terms["drift"] = args.drift_weight * ((grip_drift ** 2).sum() + DRIFT_STEADY * (drift_change ** 2).sum()) / count
    return terms


chunks = [torch.arange(start, min(count, start + frames_at_once), device=device) for start in range(0, count, frames_at_once)]


stages = [(0, int(args.iterations * 0.25), [root_rotation, root_location], 0.03),
          (1, int(args.iterations * 0.45), [joint_parameters, root_rotation, root_location], 0.02),
          (2, int(args.iterations * 0.30), [joint_parameters, root_rotation, root_location], 0.01)]
for stage, steps, parameters, rate in stages:
    groups = [{"params": parameters, "lr": rate}]
    if prop is not None and stage >= 1:
        groups.append({"params": [log_film_scale], "lr": 0.003})
        groups.append({"params": [grip_turn, grip_drift, grip_along], "lr": 0.01})
    optimizer = torch.optim.Adam(groups)
    for step in range(steps):
        optimizer.zero_grad()
        values = {}
        for slots in chunks:
            terms = frame_terms(stage, slots)
            sum(terms.values()).backward()
            for key, value in terms.items():
                values[key] = values.get(key, 0.0) + float(value)
        terms = shot_terms(stage)
        sum(terms.values()).backward()
        values.update({key: float(value) for key, value in terms.items()})
        optimizer.step()
        if step % 200 == 0 or step == steps - 1:
            print(f"stage {stage} step {step:4d} " + " ".join(f"{k} {v:.3f}" for k, v in values.items()), flush=True)

with torch.no_grad():
    joint_angles = angles_of(joint_parameters)
    world = pose(joint_angles, root_rotation, root_location)
    pixels, _ = project(keypoint_positions(world))
    everything = torch.arange(count, device=device)
    better = grouped(keypoint_misfit(pixels, mirrored_ids, everything)) < grouped(keypoint_misfit(pixels, keypoint_ids, everything))
    use_mirror = torch.where(reading == -1, better, reading == 1)[:, keypoint_groups]
    for g, name in enumerate(SWAP_GROUPS):
        print(f"frames whose {name} are fitted with left and right swapped:",
              [frames[k] for k in range(count) if bool(use_mirror[k, (keypoint_groups == g).nonzero()[0, 0]])])
    ids = torch.where(use_mirror, mirrored_ids[None], keypoint_ids[None])
    target = torch.gather(observed, 1, ids[..., None].expand(-1, -1, 2))
    confidence = torch.gather(scores, 1, ids)
    error = (pixels - target).norm(dim=-1)
    good = confidence > 3.0
    body = keypoint_ids < BODY_KEYS
    torso = body & ~is_segment
    per_frame = [float(error[k][good[k] & torso].median()) if (good[k] & torso).any() else float("nan") for k in range(count)]
    print("median torso keypoint error (px, confident):", float(error[:, torso][good[:, torso]].median()))
    print("frames whose confident torso keypoints miss by over 20 px (median):",
          [(frames[k], round(value)) for k, value in enumerate(per_frame) if value > 20.0])
    chord, shortening, length = segment_misfit(pixels, target)
    limb = body[segment_columns]
    sure = (good[:, segment_columns] & good[:, parent_columns] & (length > 30.0))
    turned = torch.rad2deg(2.0 * torch.asin((chord.sqrt() / 2.0).clamp(max=1.0)))
    print("median limb segment turn (deg, confident body):", float(turned[:, limb][sure[:, limb]].median()) if sure[:, limb].any() else None,
          " hands:", float(turned[:, ~limb][sure[:, ~limb]].median()) if sure[:, ~limb].any() else None)
    per_frame = [float(turned[k][sure[k] & limb].median()) if (sure[k] & limb).any() else float("nan") for k in range(count)]
    print("frames whose confident limb segments turn by over 15 deg (median):",
          [(frames[k], round(value)) for k, value in enumerate(per_frame) if value > 15.0])
    at_limit = ((joint_angles - low).abs() < 0.01) | ((high - joint_angles).abs() < 0.01)
    held_at_limit = {}
    for j, name in enumerate(FITTED):
        if free[j].any():
            share = float(at_limit[:, j][:, free[j]].float().mean())
            if share > 0.2:
                held_at_limit[name] = round(share, 2)
    print("joints held at a limit (share of frames):", held_at_limit)
    if count > 2:
        shaken, moved = shake(world)
        keys = len(KEYPOINTS)
        if bool(still_steps.any()):
            print(f"moving while still (px/frame at depth): keypoints median {float(moved[still_steps][:, :keys].median()):.2f}"
                  + (f"; prop median {float(moved[still_steps][:, keys:].median()):.2f} 90% "
                     f"{float(moved[still_steps][:, keys:].quantile(0.9)):.2f}" if prop is not None else ""))
        print(f"shake (px/frame^2 at depth): keypoints median {float(shaken[:, :keys].median()):.2f} "
              f"90% {float(shaken[:, :keys].quantile(0.9)):.2f}" + (f"; prop median {float(shaken[:, keys:].median()):.2f} "
              f"90% {float(shaken[:, keys:].quantile(0.9)):.2f}" if prop is not None else ""))
    if part_names:
        sample_pixels, sample_depth = project(skeleton.skin(world, samples, sample_bones, sample_weights, count))
        for name in part_names:
            gaps = part_silhouettes[name].gaps(sample_pixels[:, part_samples[name]], everything).median(1).values
            shown = part_silhouettes[name].present.bool()
            print(f"part {name}: median gap of its mask to it (px), every 5th masked frame:",
                  " ".join(f"{frames[k]}:{float(gaps[k]):.0f}" for k in range(0, count, 5) if shown[k]))
        ahead = []
        for k in range(count):
            slots = everything[k:k + 1]
            amount = float(misordered({name: sample_pixels[k:k + 1, part_samples[name]] for name in part_names},
                                 {name: sample_depth[k:k + 1, part_samples[name]] for name in part_names}, slots))
            if amount > 0.5:
                ahead.append((frames[k], round(amount, 1)))
        print("frames where a part lies in front of the part its mask shows (summed m):", ahead)
    if prop is not None:
        distance = grip_distance(world, torch.arange(count, device=device))
        print("film scale", round(float(torch.exp(log_film_scale)), 4))
        print("palm to shaft (cm):", " ".join(f"{frames[k]}:{float(distance[k]) * 100:.0f}" for k in range(0, count, 5)))
        misfit = torch.rad2deg(held_misfit(world, torch.arange(count, device=device)))
        drift = torch.rad2deg(grip_drift.norm(dim=-1))
        print(f"held on {[round(float(share), 2) for share in torch.sigmoid(grip_along)]} of the shaft; turned from its silhouette (deg) median {float(misfit.median()):.1f} "
              f"90% {float(misfit.quantile(0.9)):.1f}; drift (deg) median {float(drift.median()):.1f} most {float(drift.max()):.1f}")
        print("turned from its silhouette (deg):", " ".join(f"{frames[k]}:{float(misfit[k]):.0f}" for k in range(0, count, 5)))

result = {"armature": profile["armature"], "frames": []}
with torch.no_grad():
    object_rotation = axis_angle_matrices(root_rotation).cpu().numpy()
    rotation_matrices = euler_xyz(joint_angles).cpu().numpy()
    for k, frame in enumerate(frames):
        bones = {name: [round(float(v), 6) for v in quaternion_from_matrix(rotation_matrices[k, j])] for j, name in enumerate(FITTED)}
        result["frames"].append({"frame": frame,
                                 "location": [round(float(v), 5) for v in root_location[k].cpu().numpy()],
                                 "rotation": [round(float(v), 6) for v in quaternion_from_matrix(object_rotation[k])],
                                 "rotation_vector": [round(float(v), 6) for v in root_rotation[k].cpu().numpy()],
                                 "bones": bones})
    result["rests"] = rests(skeleton, FITTED)
    if prop is not None:
        prop.write_grips(result["frames"], torch.linalg.inv(world[hand_bone]) @ held_at_model_size(world, torch.arange(count, device=device)))
        result["held"] = {prop.name: grip["hand"]}
        result["rests"].update(rests(skeleton, [grip["hand"]]))
json.dump(result, open(args.out, "w", encoding="utf-8"), indent=1)
print("wrote", args.out)
