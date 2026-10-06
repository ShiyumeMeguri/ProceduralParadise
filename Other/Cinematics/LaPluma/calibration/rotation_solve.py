"""
Camera rotation (and focal length) over a stretch of a shot whose camera
turns far more than it moves, from what lies far away.

    python rotation_solve.py <frames dir> <first> <last> <anchor frame> <anchor.json> <out.json>
                             [--region x0,y0,x1,y1] [--masks DIR] [--focal F | --free-focal]

Corners are tracked (pyramidal Lucas-Kanade, checked forwards and backwards)
inside ``region`` and outside the ``masks`` (the character, ``m####.png``
white).  Seen from a camera that only turns, a point far away moves by the
homography K R K^-1: every frame's rotation relative to the ``anchor``
frame (whose camera is known, ``anchor.json``: ``rotation_world_from_camera``
in the measuring frame) is fitted to all its tracks at once with a robust
loss, so birds, debris and the near building fall out as outliers.  With
``--free-focal`` one focal length for the whole stretch is fitted too.
Writes every frame's ``rotation_world_from_camera`` and the focal length.
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
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("anchor", type=int)
parser.add_argument("anchor_json")
parser.add_argument("out")
parser.add_argument("--region", default="0,0,1920,1080")
parser.add_argument("--exclude", nargs="*", default=["1560,0,1920,130"])
parser.add_argument("--masks", default=None)
parser.add_argument("--focal", type=float, default=1315.0)
parser.add_argument("--free-focal", action="store_true")
parser.add_argument("--min-length", type=int, default=5)
args = parser.parse_args()
WIDTH, HEIGHT = 1920, 1080
frames = list(range(args.first, args.last + 1))
x0, y0, x1, y1 = (int(v) for v in args.region.split(","))


def allowed(frame):
    mask = np.zeros((HEIGHT, WIDTH), np.uint8)
    mask[y0:y1, x0:x1] = 255
    for item in args.exclude:
        a, b, c, d = (int(v) for v in item.split(","))
        mask[b:d, a:c] = 0
    if args.masks:
        path = os.path.join(args.masks, "m%04d.png" % frame)
        if os.path.exists(path):
            character = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            mask[cv2.dilate(character, np.ones((25, 25), np.uint8)) > 127] = 0
    return mask


tracks, active = [], []
previous = None
for frame in frames:
    image = cv2.imread(os.path.join(args.frames_dir, "f%04d.png" % frame), cv2.IMREAD_GRAYSCALE)
    mask = allowed(frame)
    if previous is not None and active:
        points = np.array([tracks[t][-1][1] for t in active], np.float32).reshape(-1, 1, 2)
        moved, status, _ = cv2.calcOpticalFlowPyrLK(previous, image, points, None, winSize=(31, 31), maxLevel=5)
        back, status_back, _ = cv2.calcOpticalFlowPyrLK(image, previous, moved, None, winSize=(31, 31), maxLevel=5)
        error = np.linalg.norm(back - points, axis=2)[:, 0]
        survivors = []
        for k, t in enumerate(active):
            x, y = moved[k, 0]
            if status[k, 0] and status_back[k, 0] and error[k] < 0.5 and 0 <= x < WIDTH and 0 <= y < HEIGHT and mask[int(y), int(x)]:
                tracks[t].append((frame, (float(x), float(y))))
                survivors.append(t)
        active = survivors
    for t in active:
        x, y = tracks[t][-1][1]
        cv2.circle(mask, (int(x), int(y)), 10, 0, -1)
    fresh = cv2.goodFeaturesToTrack(image, 2500, 0.005, 10, mask=mask, blockSize=7)
    if fresh is not None:
        for x, y in fresh[:, 0]:
            tracks.append([(frame, (float(x), float(y)))])
            active.append(len(tracks) - 1)
    previous = image
tracks = [track for track in tracks if len(track) >= args.min_length]
print("tracks", len(tracks))
index = {frame: k for k, frame in enumerate(frames)}
anchor_rotation = np.array(json.load(open(args.anchor_json))["rotation_world_from_camera"])
observations = [(index[frame], t, uv) for t, track in enumerate(tracks) for frame, uv in track]
camera_of = np.array([o[0] for o in observations])
track_of = np.array([o[1] for o in observations])
pixels = np.array([o[2] for o in observations])
anchor_index = index[args.anchor]
free = [k for k in range(len(frames)) if k != anchor_index]
centre = np.array([WIDTH / 2, HEIGHT / 2])


def unpack(x):
    rotations = np.zeros((len(frames), 3))
    rotations[free] = x[:3 * len(free)].reshape(-1, 3)
    directions = x[3 * len(free):3 * len(free) + 3 * len(tracks)].reshape(-1, 3)
    focal = x[-1] if args.free_focal else args.focal
    return rotations, directions, focal


def residuals(x):
    rotations, directions, focal = unpack(x)
    camera_from_anchor = Rotation.from_rotvec(rotations[camera_of]).inv()
    local = camera_from_anchor.apply(directions[track_of])
    projected = focal * local[:, :2] / np.clip(local[:, 2:3], 1e-3, None) + centre
    return (projected - pixels).ravel()


rotations0 = np.zeros((len(frames), 3))
for k in range(1, len(frames)):
    pairs = [(dict(tr)[frames[k - 1]], dict(tr)[frames[k]]) for tr in tracks
             if frames[k - 1] in dict(tr) and frames[k] in dict(tr)]
    if len(pairs) >= 8:
        a = np.array([p[0] for p in pairs]) - centre
        b = np.array([p[1] for p in pairs]) - centre
        K = np.array([[args.focal, 0, 0], [0, args.focal, 0], [0, 0, 1.0]])
        H, _ = cv2.findHomography(a, b, cv2.RANSAC, 2.0)
        if H is not None:
            R = np.linalg.inv(K) @ H @ K
            u_, _, vt = np.linalg.svd(R)
            R = u_ @ vt
            step = Rotation.from_matrix(R).inv()
            rotations0[k] = (Rotation.from_rotvec(rotations0[k - 1]) * step).as_rotvec()
    else:
        rotations0[k] = rotations0[k - 1]
base = Rotation.from_rotvec(rotations0[anchor_index])
rotations0 = np.array([(base.inv() * Rotation.from_rotvec(r)).as_rotvec() for r in rotations0])
directions0 = np.zeros((len(tracks), 3))
for t, track in enumerate(tracks):
    frame, (u, v) = track[0]
    ray = np.array([(u - centre[0]) / args.focal, (v - centre[1]) / args.focal, 1.0])
    directions0[t] = Rotation.from_rotvec(rotations0[index[frame]]).apply(ray)
x0_ = np.concatenate([rotations0[free].ravel(), directions0.ravel()] + ([np.array([args.focal])] if args.free_focal else []))
m = 2 * len(observations)
n = len(x0_)
A = lil_matrix((m, n), dtype=np.int8)
position = {k: j for j, k in enumerate(free)}
for row, (ci, ti) in enumerate(zip(camera_of, track_of)):
    if ci in position:
        A[2 * row:2 * row + 2, 3 * position[ci]:3 * position[ci] + 3] = 1
    A[2 * row:2 * row + 2, 3 * len(free) + 3 * ti:3 * len(free) + 3 * ti + 3] = 1
    if args.free_focal:
        A[2 * row:2 * row + 2, n - 1] = 1
for scale in (8.0, 3.0, 1.5):
    result = least_squares(residuals, x0_, jac_sparsity=A.tocsr(), loss="cauchy", f_scale=scale, x_scale="jac", max_nfev=200,
                           verbose=1)
    x0_ = result.x
    error = np.linalg.norm(result.fun.reshape(-1, 2), axis=1)
    print(f"f_scale {scale}: median {np.median(error):.2f}px, inliers(<2px) {np.mean(error < 2) * 100:.0f}%")
rotations, directions, focal = unpack(x0_)
per_frame = {}
for (ci, _, _), e in zip(observations, error):
    per_frame.setdefault(frames[ci], []).append(e)
result = {"focal": float(focal), "anchor": args.anchor, "cameras": {}}
for k, frame in enumerate(frames):
    world_from_camera = anchor_rotation @ Rotation.from_rotvec(rotations[k]).as_matrix()
    errors = np.array(per_frame.get(frame, [np.nan]))
    result["cameras"][str(frame)] = {"rotation_world_from_camera": world_from_camera.tolist(),
                                     "tracks": int(np.sum(errors < 2)), "median_error": float(np.nanmedian(errors))}
json.dump(result, open(args.out, "w"), indent=1)
print("focal", focal, "->", args.out)
