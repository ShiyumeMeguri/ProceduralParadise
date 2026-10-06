"""
Plane-sweep stereo over a match-moved stretch of a shot: the depth of
every pixel of a reference frame, measured on planes of a chosen axis.

    python stereo.py <world.json> <frames dir> <reference frame> <frame,frame,...> <out prefix>
                     [--axis Y] [--range 0.2 1.4] [--planes 400] [--scale 0.5] [--window 7]
                     [--mask x0,y0,x1,y1 ...]

``world.json`` holds the solved cameras in the set's measuring frame
(``facade_frame``): ``position`` and ``rotation_world_from_camera``
(OpenCV axes) of each frame and the ``focal`` length in pixels.  Planes
of constant ``axis`` (Y: parallel to a facade) are swept over ``range``;
each reference pixel takes the plane where the other frames agree with it
best (zero-mean normalised cross-correlation over a ``window``, averaged
over the frames).  Writes ``<prefix>_depth.npy`` (the axis value per pixel,
NaN where no plane is clearly best), ``<prefix>_points.npy`` (X, Y, Z,
r, g, b of the confident pixels) and a colour-coded preview.
"""
import argparse
import json

import cv2
import numpy as np
import torch
import torch.nn.functional as F

parser = argparse.ArgumentParser()
parser.add_argument("world")
parser.add_argument("frames_dir")
parser.add_argument("reference", type=int)
parser.add_argument("others")
parser.add_argument("out")
parser.add_argument("--axis", default="Y")
parser.add_argument("--range", type=float, nargs=2, default=(0.2, 1.4))
parser.add_argument("--planes", type=int, default=400)
parser.add_argument("--scale", type=float, default=0.5)
parser.add_argument("--window", type=int, default=7)
parser.add_argument("--mask", nargs="*", default=[])
args = parser.parse_args()
device = "cuda"
world = json.load(open(args.world))
axis = "XYZ".index(args.axis)
focal = world["focal"] * args.scale


def load(frame):
    image = cv2.imread(f"{args.frames_dir}/f{frame:04d}.png")
    image = cv2.resize(image, None, fx=args.scale, fy=args.scale, interpolation=cv2.INTER_AREA)
    return torch.tensor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), dtype=torch.float32, device=device) / 255.0, image


def camera(frame):
    entry = world["cameras"][str(frame)]
    return (torch.tensor(entry["position"], dtype=torch.float32, device=device),
            torch.tensor(entry["rotation_world_from_camera"], dtype=torch.float32, device=device))


reference, reference_color = load(args.reference)
height, width = reference.shape
others = [int(value) for value in args.others.split(",")]
images = [load(frame)[0] for frame in others]
position, rotation = camera(args.reference)
v, u = torch.meshgrid(torch.arange(height, device=device, dtype=torch.float32),
                      torch.arange(width, device=device, dtype=torch.float32), indexing="ij")
rays_camera = torch.stack([(u + 0.5 - width / 2) / focal, (v + 0.5 - height / 2) / focal, torch.ones_like(u)], -1)
rays = rays_camera @ rotation.T


def windowed(x):
    return F.avg_pool2d(x[None, None], args.window, stride=1, padding=args.window // 2)[0, 0]


reference_mean = windowed(reference)
reference_centered_var = windowed(reference * reference) - reference_mean ** 2
values = torch.linspace(args.range[0], args.range[1], args.planes, device=device)
best_score = torch.full((height, width), -2.0, device=device)
second_score = torch.full((height, width), -2.0, device=device)
best_value = torch.zeros((height, width), device=device)
scores_all = []
for value in values:
    distance = (value - position[axis]) / rays[..., axis]
    points = position + rays * distance[..., None]
    valid_depth = distance > 0.02
    total = torch.zeros((height, width), device=device)
    count = torch.zeros((height, width), device=device)
    for frame, image in zip(others, images):
        other_position, other_rotation = camera(frame)
        local = (points - other_position) @ other_rotation
        z = local[..., 2].clamp(min=1e-4)
        x = focal * local[..., 0] / z + width / 2 - 0.5
        y = focal * local[..., 1] / z + height / 2 - 0.5
        grid = torch.stack([x / (width - 1) * 2 - 1, y / (height - 1) * 2 - 1], -1)
        warped = F.grid_sample(image[None, None], grid[None], align_corners=True, padding_mode="zeros")[0, 0]
        inside = (x >= 0) & (x <= width - 1) & (y >= 0) & (y <= height - 1) & (local[..., 2] > 0.02)
        warped_mean = windowed(warped)
        covariance = windowed(warped * reference) - warped_mean * reference_mean
        variance = windowed(warped * warped) - warped_mean ** 2
        ncc = covariance / torch.sqrt((variance * reference_centered_var).clamp(min=1e-6))
        total += torch.where(inside, ncc, torch.zeros_like(ncc))
        count += inside.float()
    score = torch.where((count > len(others) * 0.5) & valid_depth, total / count.clamp(min=1), torch.full_like(total, -2.0))
    better = score > best_score
    second_score = torch.where(better, best_score, torch.maximum(second_score, score))
    best_value = torch.where(better, value, best_value)
    best_score = torch.where(better, score, best_score)
texture = reference_centered_var.sqrt()
confident = (best_score > 0.6) & (texture > 0.02)
for x0, y0, x1, y1 in (tuple(int(int(v) * args.scale) for v in item.split(",")) for item in args.mask):
    confident[y0:y1, x0:x1] = False
depth = torch.where(confident, best_value, torch.full_like(best_value, float("nan"))).cpu().numpy()
np.save(args.out + "_depth.npy", depth)
distance = (best_value - position[axis]) / rays[..., axis]
points = (position + rays * distance[..., None]).cpu().numpy()
colors = cv2.cvtColor(reference_color, cv2.COLOR_BGR2RGB).reshape(-1, 3)
keep = confident.cpu().numpy().ravel()
np.save(args.out + "_points.npy", np.hstack([points.reshape(-1, 3)[keep], colors[keep]]))
low, high = args.range
preview = np.nan_to_num((depth - low) / (high - low), nan=0.0)
preview = cv2.applyColorMap((np.clip(preview, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
preview[~confident.cpu().numpy()] = (reference_color[~confident.cpu().numpy()] * 0.3).astype(np.uint8)
cv2.imwrite(args.out + "_preview.png", preview)
print(f"confident pixels {keep.mean() * 100:.1f}%  {args.axis} range {np.nanpercentile(depth, 2):.3f}..{np.nanpercentile(depth, 98):.3f}")
