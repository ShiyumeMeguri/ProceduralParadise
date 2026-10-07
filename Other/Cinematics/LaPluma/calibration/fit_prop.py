"""
Place a prop of the cast (her scythe) on its silhouette, frame by frame (PyTorch) --
the starting grips for fitting her and the prop together.

    python fit_prop.py <rig.npz> <profile.json> <camera.json> <performance.json> <prop mesh> <masks dir> <first> <last>
                       --grip NAME [--occluders DIR] [--part NAME=DIR ...] [--out performance.json]

The prop (``prop.py``), as large as its maker made it, is placed on every
frame so that, seen through the shot's solved camera, it fills its
silhouette (``roto.py``) and stays inside it -- or inside the character's
silhouette (``--occluders``), where she hides it.  A ``--part`` (the prop's
points of the materials the cast profile names for it: the blade, the
hub) fills its own silhouette (``NAME=DIR``) and
the rest of the prop the rest, so the blade cannot lie where the shaft is.
The search runs per frame over many orientations, each at the distance the
silhouette's size implies, keeps the best few -- each also rolled a quarter, a
half and three quarters of a turn about its shaft, which the silhouette cannot
tell apart where the blade is out of the picture -- refines them, and takes the
path through them that turns least from frame to frame; a frame whose own
fit strays, or where the prop is not seen (no mask), is placed between its neighbours, and the whole shot is refined
together with smoothness.

The picture places the prop up to how far it is: twice as large twice as
far looks the same.  Each frame's placement at the model's size is
written into the performance (``placements``), and a first guess of how
large the film's prop is (``film_scales``): the median, over the frames, of
the size at which the shaft (the cast profile's ``props``) lies as far from
the camera as the wrist of the performance's hand where the wrist crosses
it in the picture -- the hand of the grip the shot holds it in (``--grip``:
one of the prop's ``grips``, right or left).  ``fit_pose.py --prop`` then fits her to it: the prop
stays where the picture has it, her hand closes on it, and its size is
fitted with her.  The card is shared (``gpu_budget.py``): orientations,
candidates and frames are worked through in batches the claim holds.
"""
import argparse
import json
import math
import os

import numpy as np
import torch

from gpu_budget import chunk, claim
from prop import Prop, fitted, parts
from silhouette import Silhouette
from skeleton import Camera, Skeleton, axis_angle_matrices, quaternion_from_matrix, quaternion_matrices

parser = argparse.ArgumentParser()
parser.add_argument("rig")
parser.add_argument("profile")
parser.add_argument("camera")
parser.add_argument("performance")
parser.add_argument("prop")
parser.add_argument("masks")
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("--grip", required=True, help="which of the prop's grips (the profile's props.<prop>.grips) holds it in this shot")
parser.add_argument("--occluders", default=None)
parser.add_argument("--part", action="append", default=[], help="NAME=DIR -- a part of the prop (the profile's parts) and its masks")
parser.add_argument("--smooth-weight", type=float, default=5.0)
parser.add_argument("--orientations", type=int, default=3000)
parser.add_argument("--keep", type=int, default=10)
parser.add_argument("--iterations", type=int, default=800)
parser.add_argument("--out", default=None)
parser.add_argument("--width", type=int, default=1920)
parser.add_argument("--height", type=int, default=1080)
args = parser.parse_args()
device = "cuda"
budget = claim()
generator = torch.Generator().manual_seed(0)
width, height = args.width, args.height

skeleton = Skeleton(args.rig, device)
profile = json.load(open(args.profile, encoding="utf-8"))
prop_profile = profile["props"][args.prop]
performance = json.load(open(args.performance, encoding="utf-8"))
items = {item["frame"]: item for item in performance["frames"]}
frames = [frame for frame in range(args.first, args.last + 1) if frame in items]
count = len(frames)
camera = Camera(args.camera, frames, width, height, device)
prop = Prop(skeleton, args.prop)
track_points = prop.subset(16, generator)
silhouette = Silhouette(args.masks, args.occluders, frames, width, height, device)
present = silhouette.present
part_directories = dict(spec.split("=", 1) for spec in args.part)
prop_parts = parts(prop, prop_profile, part_directories, args.masks, args.occluders, frames, width, height, device, generator)
search_points = torch.cat([part.search_points for part in prop_parts])

frame_items = [items[frame] for frame in frames]
object_matrix = torch.eye(4, device=device).repeat(count, 1, 1)
object_matrix[:, :3, :3] = quaternion_matrices(torch.tensor([item["rotation"] for item in frame_items], dtype=torch.float64)).float().to(device)
object_matrix[:, :3, 3] = torch.tensor([item["location"] for item in frame_items], dtype=torch.float32, device=device)
keyed = {}
for name in frame_items[0]["bones"]:
    matrix = torch.eye(4, device=device).repeat(count, 1, 1)
    matrix[:, :3, :3] = quaternion_matrices(torch.tensor([item["bones"][name] for item in frame_items], dtype=torch.float64)).float().to(device)
    keyed[skeleton.index[name]] = matrix
hand = skeleton.index[prop_profile["grips"][args.grip]["hand"]]
body = skeleton.pose(object_matrix, lambda b: keyed.get(b), skeleton.ancestry([hand]))
hand_world = body[hand]
body_depth = [float(-(camera.rotation[k].T @ (object_matrix[k, :3, 3] - camera.location[k]))[2]) for k in range(count)]


def project(points, slots):
    local = torch.einsum("bji,bnj->bni", camera.rotation[slots], points - camera.location[slots][:, None, :])
    safe = (-local[..., 2]).clamp(min=0.05)
    return torch.stack([width / 2 + camera.focal * local[..., 0] / safe, height / 2 - camera.focal * local[..., 1] / safe], -1)


def search(k, rotations):
    rotation_camera, location_camera = camera.rotation[k], camera.location[k]
    offsets = torch.einsum("ji,rjn->rni", rotation_camera, rotations @ (search_points - prop.centre).T)
    centroid = silhouette.centroids[k]
    ray = torch.tensor([(centroid[0] - width / 2) / camera.focal, -(centroid[1] - height / 2) / camera.focal, -1.0],
                       dtype=torch.float32, device=device)

    def pixels_at(depth):
        points = ray[None, None, :] * depth[:, None, None] + offsets
        safe = (-points[..., 2]).clamp(min=0.05)
        return torch.stack([width / 2 + camera.focal * points[..., 0] / safe, height / 2 - camera.focal * points[..., 1] / safe], -1)

    depth = torch.full((len(rotations),), max(body_depth[k], 1.0), device=device)
    spread = pixels_at(depth).var(1).sum(-1).sqrt()
    depth = (depth * spread / max(silhouette.spreads[k], 4.0)).clamp(0.3, 60.0)
    projected = pixels_at(depth)
    slots = torch.full((len(rotations),), k, device=device, dtype=torch.long)
    score = torch.zeros(len(rotations), device=device)
    start = 0
    for part in prop_parts:
        piece = projected[:, start:start + len(part.search_points)]
        start += len(part.search_points)
        cells = (piece / 8.0).long()
        inside = (cells[..., 0] >= 0) & (cells[..., 0] < width // 8) & (cells[..., 1] >= 0) & (cells[..., 1] < height // 8)
        flat = cells[..., 1].clamp(0, height // 8 - 1) * (width // 8) + cells[..., 0].clamp(0, width // 8 - 1)
        hit = torch.zeros(len(rotations), (height // 8) * (width // 8), device=device)
        hit.scatter_add_(1, flat, inside.float())
        hit = torch.nn.functional.max_pool2d((hit.view(-1, 1, height // 8, width // 8) > 0).float(), 3, 1, 1)[:, 0]
        grid = part.silhouette.grids[k]
        coverage = (hit * grid).sum((1, 2)) / grid.sum().clamp(min=1.0)
        score = score + coverage - part.precision_weight * part.silhouette.precision(piece, slots)
    world_centre = location_camera[None] + (rotation_camera @ (ray[:, None] * depth[None])).T
    return score, world_centre - torch.einsum("rij,j->ri", rotations, prop.centre)


def rotation_angle(a, b):
    trace = torch.einsum("...ij,...ij->...", a, b)
    return torch.acos(((trace - 1.0) / 2.0).clamp(-1.0, 1.0))


quaternions = torch.randn(args.orientations, 4, generator=generator, dtype=torch.float64)
orientations = quaternion_matrices(quaternions / quaternions.norm(dim=1, keepdim=True)).float().to(device)
shaft_axis = torch.tensor(prop_profile["shaft"][1], dtype=torch.float32) - torch.tensor(prop_profile["shaft"][0], dtype=torch.float32)
shaft_axis = shaft_axis / shaft_axis.norm()
rolls = axis_angle_matrices(torch.stack([shaft_axis * math.radians(angle) for angle in (0.0, 90.0, 180.0, 270.0)])).to(device)
candidates_rotation, candidates_translation = [], []
orientations_at_once = chunk(budget, bytes_each=len(search_points) * 40 + (height // 8) * (width // 8) * 16 * len(prop_parts), most=args.orientations)
for k in range(count):
    with torch.no_grad():
        found = [search(k, orientations[start:start + orientations_at_once]) for start in range(0, args.orientations, orientations_at_once)]
        score, translation = torch.cat([f[0] for f in found]), torch.cat([f[1] for f in found])
        order = torch.argsort(score, descending=True)[:300].tolist()
        best_rotations = orientations[order].cpu().numpy()
        kept, kept_slots = [], []
        for slot, index in enumerate(order):
            traces = [float((best_rotations[slot] * best_rotations[other]).sum()) for other in kept_slots]
            if all(trace < 1.0 + 2.0 * np.cos(0.45) for trace in traces):
                kept.append(index)
                kept_slots.append(slot)
            if len(kept) == args.keep:
                break
        rolled = (orientations[kept][:, None] @ rolls[None]).reshape(-1, 3, 3)
        _, rolled_translation = search(k, rolled)
    candidates_rotation.append(rolled)
    candidates_translation.append(rolled_translation)
candidates_rotation = torch.stack(candidates_rotation)
candidates_translation = torch.stack(candidates_translation)
print("searched", count, "frames", flush=True)

flat_rotation = candidates_rotation.reshape(-1, 3, 3)
flat_translation = candidates_translation.reshape(-1, 3)
flat_frame = torch.arange(count, device=device).repeat_interleave(args.keep * len(rolls))
refined_rotation, refined_translation, refined_cost = [], [], []
cover_targets = 400
candidates_at_once = chunk(budget, bytes_each=sum(len(part.search_points) for part in prop_parts) * cover_targets * 4 * 4, most=512)
print(f"[gpu] {orientations_at_once} orientations, {candidates_at_once} candidates at a time", flush=True)
for start in range(0, len(flat_frame), candidates_at_once):
    stop = start + candidates_at_once
    base_rotation = flat_rotation[start:stop]
    turn = torch.zeros(len(base_rotation), 3, device=device, requires_grad=True)
    shift = torch.zeros(len(base_rotation), 3, device=device, requires_grad=True)
    optimizer = torch.optim.Adam([turn, shift], lr=0.02)
    slots = flat_frame[start:stop]
    for step in range(150):
        optimizer.zero_grad()
        precision, coverage = fitted(prop_parts, project, base_rotation @ axis_angle_matrices(turn), flat_translation[start:stop] + shift,
                                     slots, True)
        (precision + coverage).sum().backward()
        optimizer.step()
    with torch.no_grad():
        rotation = base_rotation @ axis_angle_matrices(turn)
        precision, coverage = fitted(prop_parts, project, rotation, flat_translation[start:stop] + shift, slots, True)
        refined_rotation.append(rotation)
        refined_translation.append(flat_translation[start:stop] + shift)
        refined_cost.append(precision + coverage)
refined_rotation = torch.cat(refined_rotation).reshape(count, args.keep * len(rolls), 3, 3)
refined_translation = torch.cat(refined_translation).reshape(count, args.keep * len(rolls), 3)
refined_cost = torch.cat(refined_cost).reshape(count, args.keep * len(rolls))

with torch.no_grad():
    total = refined_cost[0].clone()
    back = []
    for k in range(1, count):
        turn = rotation_angle(refined_rotation[k - 1][:, None], refined_rotation[k][None, :])
        move = (refined_translation[k - 1][:, None] - refined_translation[k][None, :]).norm(dim=-1)
        best, previous = (total[:, None] + 2.0 * turn ** 2 + 1.0 * move ** 2).min(0)
        back.append(previous)
        total = best + refined_cost[k] * present[k]
    path = [int(total.argmin())]
    for previous in reversed(back):
        path.append(int(previous[path[-1]]))
    path.reverse()
chosen_rotation = torch.stack([refined_rotation[k, path[k]] for k in range(count)])
chosen_translation = torch.stack([refined_translation[k, path[k]] for k in range(count)])
chosen_cost = torch.stack([refined_cost[k, path[k]] for k in range(count)]).cpu().numpy()


def slerp(a, b, share):
    a = np.array(quaternion_from_matrix(a))
    b = np.array(quaternion_from_matrix(b))
    if a @ b < 0.0:
        b = -b
    angle = np.arccos(np.clip(a @ b, -1.0, 1.0))
    blended = a if angle < 1e-6 else (np.sin((1 - share) * angle) * a + np.sin(share * angle) * b) / np.sin(angle)
    return quaternion_matrices(torch.tensor(blended / np.linalg.norm(blended), dtype=torch.float64)).float().to(device)


typical = np.array([np.median(chosen_cost[max(0, k - 5):k + 6]) for k in range(count)])
seen = present.cpu().numpy() > 0
stray = ((chosen_cost > np.maximum(0.15, 3.0 * typical)) & seen) | ~seen
good = [k for k in range(count) if not stray[k]]
for k in np.nonzero(stray)[0]:
    before = [g for g in good if g < k]
    after = [g for g in good if g > k]
    if before and after:
        a, b = before[-1], after[0]
        share = (k - a) / (b - a)
        chosen_rotation[k] = slerp(chosen_rotation[a].cpu().numpy(), chosen_rotation[b].cpu().numpy(), share)
        chosen_translation[k] = (1 - share) * chosen_translation[a] + share * chosen_translation[b]
    elif before or after:
        nearest = before[-1] if before else after[0]
        chosen_rotation[k] = chosen_rotation[nearest]
        chosen_translation[k] = chosen_translation[nearest]
print("frames placed between their neighbours (their own fit strayed, or the prop is not seen there):",
      [frames[k] for k in np.nonzero(stray)[0]], flush=True)

slots = torch.arange(count, device=device)
turn = torch.zeros(count, 3, device=device, requires_grad=True)
shift = torch.zeros(count, 3, device=device, requires_grad=True)


def placement():
    return chosen_rotation @ axis_angle_matrices(turn), chosen_translation + shift


def frame_terms(chunk_slots):
    """The silhouette terms of the frames ``chunk_slots``: parts of the shot's sums."""
    rotation = chosen_rotation[chunk_slots] @ axis_angle_matrices(turn[chunk_slots])
    translation = chosen_translation[chunk_slots] + shift[chunk_slots]
    precision, coverage = fitted(prop_parts, project, rotation, translation, chunk_slots)
    shown = present[chunk_slots]
    return {"precision": (precision * shown).sum() / present.sum(), "coverage": (coverage * shown).sum() / present.sum()}


def shot_terms():
    rotation, translation = placement()
    tracked = Prop.place(rotation, translation, track_points)
    acceleration = tracked[2:] - 2 * tracked[1:-1] + tracked[:-2]
    return {"smooth": args.smooth_weight * (acceleration ** 2).sum(-1).mean()}


frames_at_once = chunk(budget, bytes_each=sum(len(part.points) * 16 + len(part.cover_points) * cover_targets * 4 * 4 for part in prop_parts),
                       most=count)
chunks = [torch.arange(start, min(count, start + frames_at_once), device=device) for start in range(0, count, frames_at_once)]
optimizer = torch.optim.Adam([turn, shift], lr=0.01)
for step in range(args.iterations):
    optimizer.zero_grad()
    values = {}
    for chunk_slots in chunks:
        terms = frame_terms(chunk_slots)
        sum(terms.values()).backward()
        for key, value in terms.items():
            values[key] = values.get(key, 0.0) + float(value)
    terms = shot_terms()
    sum(terms.values()).backward()
    values.update({key: float(value) for key, value in terms.items()})
    optimizer.step()
    if step % 100 == 0 or step == args.iterations - 1:
        print(f"step {step:4d} " + " ".join(f"{k} {v:.4f}" for k, v in values.items()), flush=True)

with torch.no_grad():
    rotation, translation = placement()
    for index, part in enumerate(prop_parts):
        outside = torch.cat([part.silhouette.outside(project(Prop.place(rotation[s], translation[s], part.points), s), s) for s in chunks])
        gaps = torch.cat([part.silhouette.gaps(project(Prop.place(rotation[s], translation[s], part.cover_points), s), s) for s in chunks])
        print(f"part {index}: frame, share outside its silhouette, median gap of the silhouette to it (px):")
        print(" ".join(f"{frame}:{float((outside[k] > 6.0).float().mean()):.2f}/{float(gaps[k].median()):.1f}" for k, frame in enumerate(frames)))
    shaft = torch.tensor(prop_profile["shaft"], dtype=torch.float32, device=device)
    ends = Prop.place(rotation, translation, shaft)
    wrist = hand_world[:, None, :3, 3]
    ends_pixels, wrist_pixels = project(ends, slots), project(wrist, slots)[:, 0]
    axis = ends_pixels[:, 1] - ends_pixels[:, 0]
    along = (((wrist_pixels - ends_pixels[:, 0]) * axis).sum(-1) / (axis * axis).sum(-1)).clamp(0.0, 1.0)
    gap = (wrist_pixels - (ends_pixels[:, 0] + along[:, None] * axis)).norm(dim=-1)
    crossing = ends[:, 0] + along[:, None] * (ends[:, 1] - ends[:, 0])

    def depth_of(points):
        return -torch.einsum("fji,fj->fi", camera.rotation, points - camera.location)[:, 2]

    sizes = depth_of(wrist[:, 0]) / depth_of(crossing).clamp(min=0.05)
    trusted = (gap < 80.0) & (present > 0)
    film_scale = float(sizes[trusted].median()) if trusted.sum() >= 5 else float(sizes.median())
    print("film scale (the film's prop over the model's):", round(film_scale, 3), "from", int(trusted.sum()), "frames", flush=True)
    prop.write_placements(frame_items, rotation, translation)
    performance["film_scales"] = {prop.name: round(film_scale, 4)}
    out = args.out or args.performance
    json.dump(performance, open(out, "w", encoding="utf-8"), indent=1)
    print("wrote", out)
