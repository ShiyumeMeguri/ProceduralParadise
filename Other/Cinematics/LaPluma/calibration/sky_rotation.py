"""
A shot's camera turning against a background at infinity (the sky): its
rotation every frame, its place held.

    python sky_rotation.py <frames dir> <film.json> <first> <last> <focal px> <out camera.json>
                           [--exclude DIR ...] [--exclude-darker V] [--smooth S]

Soft clouds have too few corners to track, but they flow densely: the
motion of the picture from each frame to the next (DIS optical flow) is
sampled over the background, and the rotation of a pinhole camera that
carries the one picture's rays onto the other's is fitted to it, every
sample's miss counted robustly (Cauchy, a few pixels) -- clouds that
billow, birds the masks missed.  What is not background is left out:
every ``--exclude`` mask directory (the character, her prop: ``roto.py``),
anything darker than ``--exclude-darker`` (birds against the sky) with a
margin for their blurred wings, the film's watermark and flat sky that
carries no motion.  The reference repeats some frames (the film's
``holds``): a turn measured across one is the turn of two frames.  The
turn of every frame is then solved at once -- each measured turn the sum
of the frames' it spans, a step the picture really jerks by is kept (a
sample's miss grows with the step, it is no doubt about the turn) and only
the measurement's jitter is smoothed (``--smooth``) -- and chained from
the first frame's camera, at the origin looking down -Z.

The camera keys are written as the film reads them (``calibration/<shot>.camera.json``):
the camera the shot was fitted against, turning in place (``place_shot.py --turn``).
"""
import argparse
import json
import os

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial.transform import Rotation

parser = argparse.ArgumentParser()
parser.add_argument("frames_dir")
parser.add_argument("film")
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("focal", type=float)
parser.add_argument("out")
parser.add_argument("--exclude", nargs="*", default=[])
parser.add_argument("--exclude-darker", type=int, default=0, help="leave out pixels darker than this (0-255): birds against the sky")
parser.add_argument("--smooth", type=float, default=0.3, help="how hard the turn is kept from jerking (the measured turns count 1)")
parser.add_argument("--spacing", type=int, default=8, help="pixels between flow samples")
args = parser.parse_args()
film = json.load(open(args.film, encoding="utf-8"))
holds = set(film.get("holds", ()))
masked = [tuple(box) for box in film.get("reference", {}).get("masks", ())]
shown = [frame for frame in range(args.first, args.last + 1) if frame == args.first or frame not in holds]
engine = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)


def picture(frame):
    return cv2.imread(os.path.join(args.frames_dir, "f%04d.png" % frame), cv2.IMREAD_GRAYSCALE)


def background(frame, image):
    keep = np.ones(image.shape, bool)
    if args.exclude_darker:
        keep &= ~(cv2.dilate((image < args.exclude_darker).astype(np.uint8), np.ones((31, 31), np.uint8)) > 0)
    for directory in args.exclude:
        path = os.path.join(directory, "m%04d.png" % frame)
        if os.path.exists(path):
            keep &= ~(cv2.dilate(cv2.imread(path, cv2.IMREAD_GRAYSCALE), np.ones((41, 41), np.uint8)) > 127)
    for x0, y0, x1, y1 in masked:
        keep[y0:y1, x0:x1] = False
    gradient = np.hypot(cv2.Sobel(image, cv2.CV_32F, 1, 0), cv2.Sobel(image, cv2.CV_32F, 0, 1))
    return keep & (gradient > 12.0)


def rays(points, centre):
    rays_ = np.concatenate([(points - centre) / args.focal, np.ones((len(points), 1))], 1)
    return rays_ / np.linalg.norm(rays_, axis=1, keepdims=True)


def turn_between(before, after, keep):
    """The rotation R (OpenCV camera axes, rays of ``after`` = R rays of ``before``) the background's flow shows."""
    flow = engine.calc(before, after, None)
    height, width = before.shape
    ys, xs = np.mgrid[args.spacing // 2:height:args.spacing, args.spacing // 2:width:args.spacing]
    chosen = keep[ys, xs]
    start = np.stack([xs[chosen], ys[chosen]], 1).astype(np.float64)
    end = start + flow[ys[chosen], xs[chosen]].astype(np.float64)
    centre = np.array([width / 2.0, height / 2.0])
    source = rays(start, centre)

    def misses(vector):
        turned = source @ Rotation.from_rotvec(vector).as_matrix().T
        return ((turned[:, :2] / turned[:, 2:3]) * args.focal + centre - end).ravel()

    fit = least_squares(misses, np.zeros(3), loss="cauchy", f_scale=3.0)
    residual = np.abs(fit.fun.reshape(-1, 2)).max(1)
    return fit.x, len(start), float(np.median(residual))


measured = []
before = picture(shown[0])
before_keep = background(shown[0], before)
for previous, frame in zip(shown, shown[1:]):
    after = picture(frame)
    vector, samples, median_miss = turn_between(before, after, before_keep)
    measured.append((previous, frame, vector, samples, median_miss))
    print(f"{previous}->{frame} samples {samples:6d} turn deg {np.degrees(np.linalg.norm(vector)):.3f} median miss px {median_miss:.2f}", flush=True)
    before, before_keep = after, background(frame, after)

frames = list(range(args.first, args.last + 1))
index = {frame: k for k, frame in enumerate(frames)}
steps = len(frames) - 1
weights = np.array([min(1.0, samples / 400.0) for *_, samples, _miss in measured])


def residuals(flat):
    turn = flat.reshape(steps, 3)
    data = [weights[m] * (turn[index[previous]:index[frame]].sum(0) - vector)
            for m, (previous, frame, vector, *_rest) in enumerate(measured)]
    jerk = (turn[2:] - 2.0 * turn[1:-1] + turn[:-2]) * args.smooth
    return np.concatenate([np.concatenate(data), jerk.ravel()])


sparsity = lil_matrix((3 * len(measured) + 3 * max(steps - 2, 0), 3 * steps), dtype=int)
for m, (previous, frame, *_rest) in enumerate(measured):
    for step in range(index[previous], index[frame]):
        for axis in range(3):
            sparsity[3 * m + axis, 3 * step + axis] = 1
for step in range(steps - 2):
    for offset in range(3):
        for axis in range(3):
            sparsity[3 * len(measured) + 3 * step + axis, 3 * (step + offset) + axis] = 1
turns = least_squares(residuals, np.zeros(3 * steps), jac_sparsity=sparsity).x.reshape(steps, 3)
flip = np.diag([1.0, -1.0, -1.0])
camera = flip.copy()
keys = []
for k, frame in enumerate(frames):
    if k > 0:
        camera = camera @ Rotation.from_rotvec(turns[k - 1]).as_matrix().T
    x, y, z, w = Rotation.from_matrix(camera @ flip).as_quat()
    keys.append({"frame": frame, "location": [0.0, 0.0, 0.0], "rotation": [round(float(w), 7), round(float(x), 7), round(float(y), 7), round(float(z), 7)]})
json.dump({"focal_px": args.focal, "keys": keys}, open(args.out, "w", encoding="utf-8"), indent=1)
total = Rotation.from_matrix(flip @ camera)
print("frames", len(frames), "measured steps", len(measured), "(holds spanned:", len(frames) - len(shown), ")",
      "turn of the shot (deg):", round(float(np.degrees(total.magnitude())), 2),
      "about camera x/y/z (deg):", np.round(np.degrees(total.as_rotvec()), 2).tolist())
print("wrote", args.out)
