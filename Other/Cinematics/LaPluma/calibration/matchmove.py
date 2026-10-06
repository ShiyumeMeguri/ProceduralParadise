"""
Match-move a shot: a camera per frame, the still scene's points and the building's vertical
and horizontal (along its facade) directions.

    python matchmove.py <frames dir> <shot.matchmove.json> <shot.vggt.json> <out.json> [--masks DIR]

Corners (Shi-Tomasi) are tracked through every frame (pyramidal Lucas-Kanade, checked
forwards and backwards), never on the character (``--masks``, dilated) nor in the shot's
``exclude`` boxes (the watermark).  The cameras start from VGGT's (``<shot>.vggt.json``, from
``vggt_cameras.py``: every few frames, interpolated), the tracks are triangulated, and a
bundle adjustment refines every camera and every point, the focal length held (``focal_px``)
or fitted.  Tracks that do not fit a still scene (birds, debris, smoke) are dropped between
rounds.

Tracks only say how a camera moved from the frames around it; where smoke leaves a few
tracks a frame, small turns add up and the camera drifts.  The building says where it faces
in every frame: its columns run to the vertical's vanishing point and its floors to the
facade's.  Long straight segments of the picture (off the character) that run, within a few
degrees, to either vanishing point pull that frame's camera to face the building as it does;
the two directions are solved with the cameras (starting from the reference frame's
vanishing points, the shot's ``facade``).  Braces and debris that run elsewhere fall out.

What the picture says is weighed robustly (a Cauchy loss on each track's miss and each
segment's), how the camera moves is not: its turn and its path are held smooth (squared
second differences) by a prior no outlier test may discount.  The first camera fixes where
the scene is and how it is turned, and the distance from the first camera to the last its
scale (``span``, solve units: what the set's metres per unit were measured in).

Output: the focal length, per frame the camera (``rotvec``, camera from world, OpenCV axes:
x right, y down, z forward, and ``center``) and how many tracks saw it, the vertical
(``up``) and the facade's horizontal (``along``), the points and the tracks -- in the solve's
own frame and units (``facade_frame.py`` measures it).
"""
import argparse
import json
import os

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial.transform import Rotation, Slerp

parser = argparse.ArgumentParser()
parser.add_argument("frames_dir")
parser.add_argument("shot")
parser.add_argument("vggt", help="VGGT's first cameras (vggt_cameras.py)")
parser.add_argument("out")
parser.add_argument("--masks", default=None, help="the character's masks (roto.py): no corner or segment is taken on her")
args = parser.parse_args()
shot = json.load(open(args.shot, encoding="utf-8"))
settings = shot["matchmove"]
facade = shot["facade"]
WIDTH, HEIGHT = 1920, 1080
CENTRE = np.array([WIDTH / 2, HEIGHT / 2])
SMOOTH = 0.3
SEGMENT_SCALE = 3.0
frames = list(range(settings["first"], settings["last"] + 1))
frame_index = {frame: k for k, frame in enumerate(frames)}


def character(frame, grow):
    if not args.masks:
        return None
    path = os.path.join(args.masks, "m%04d.png" % frame)
    if not os.path.exists(path):
        return None
    return cv2.dilate(cv2.imread(path, cv2.IMREAD_GRAYSCALE), np.ones((grow, grow), np.uint8)) > 127


def excluded(x, y):
    return any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in settings["exclude"])


lucas_kanade = dict(winSize=(31, 31), maxLevel=5, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.01))
segment_detector = cv2.createLineSegmentDetector()
tracks, active, previous = [], [], None
segment_frames, segment_ends, segment_lengths = [], [], []
for frame in frames:
    image = cv2.imread(os.path.join(args.frames_dir, "f%04d.png" % frame), cv2.IMREAD_GRAYSCALE)
    if previous is not None and active:
        points = np.array([tracks[track][-1][1] for track in active], np.float32).reshape(-1, 1, 2)
        moved, status, _ = cv2.calcOpticalFlowPyrLK(previous, image, points, None, **lucas_kanade)
        back, status_back, _ = cv2.calcOpticalFlowPyrLK(image, previous, moved, None, **lucas_kanade)
        error = np.linalg.norm(back - points, axis=2)[:, 0]
        blocked = character(frame, 15)
        survivors = []
        for k, track in enumerate(active):
            x, y = moved[k, 0]
            if blocked is not None and 0 <= x < WIDTH and 0 <= y < HEIGHT and blocked[int(y), int(x)]:
                continue
            if status[k, 0] and status_back[k, 0] and error[k] < 0.5 and 2 <= x < WIDTH - 2 and 2 <= y < HEIGHT - 2:
                tracks[track].append((frame, (float(x), float(y))))
                survivors.append(track)
        active = survivors
    allowed = np.full((HEIGHT, WIDTH), 255, np.uint8)
    for x0, y0, x1, y1 in settings["exclude"]:
        allowed[y0:y1, x0:x1] = 0
    blocked = character(frame, 31)
    if blocked is not None:
        allowed[blocked] = 0
    for track in active:
        x, y = tracks[track][-1][1]
        cv2.circle(allowed, (int(x), int(y)), 12, 0, -1)
    fresh = cv2.goodFeaturesToTrack(image, 3000, 0.006, 12, mask=allowed, blockSize=7)
    if fresh is not None:
        for x, y in fresh[:, 0]:
            tracks.append([(frame, (float(x), float(y)))])
            active.append(len(tracks) - 1)
    previous = image
    blocked = character(frame, 15)
    for x0, y0, x1, y1 in segment_detector.detect(image)[0].reshape(-1, 4):
        middle_x, middle_y = (x0 + x1) / 2, (y0 + y1) / 2
        length = float(np.hypot(x1 - x0, y1 - y0))
        if length < 60 or excluded(middle_x, middle_y) or (blocked is not None and blocked[int(middle_y), int(middle_x)]):
            continue
        segment_frames.append(frame_index[frame])
        segment_ends.append(((x0 - CENTRE[0], y0 - CENTRE[1]), (x1 - CENTRE[0], y1 - CENTRE[1])))
        segment_lengths.append(length)
tracks = [track for track in tracks if len(track) >= 8]
segment_frames = np.array(segment_frames)
segment_ends = np.array(segment_ends, dtype=np.float64)
segment_lengths = np.array(segment_lengths)
print("tracks", len(tracks), "observations", sum(len(track) for track in tracks), "segments", len(segment_frames), flush=True)

vggt = json.load(open(args.vggt, encoding="utf-8"))
vggt_frames = np.array(vggt["frames"])
vggt_extrinsic = np.array(vggt["extrinsic"])
focal = float(settings.get("focal_px") or np.median(np.array(vggt["intrinsic"])[:, 0, 0]) * WIDTH / float(vggt["input_size"][1]))
fixed_focal = "focal_px" in settings
clipped = np.clip(frames, vggt_frames[0], vggt_frames[-1])
rotations = Slerp(vggt_frames, Rotation.from_matrix(vggt_extrinsic[:, :, :3]))(clipped)
vggt_centres = np.array([-extrinsic[:, :3].T @ extrinsic[:, 3] for extrinsic in vggt_extrinsic])
centres = np.stack([np.interp(clipped, vggt_frames, vggt_centres[:, axis]) for axis in range(3)], 1)
cameras = np.hstack([rotations.as_rotvec(), centres])


def vanishing_direction(pixel, upward):
    ray = np.array([pixel[0] - CENTRE[0], pixel[1] - CENTRE[1], focal])
    ray /= np.linalg.norm(ray)
    return -ray if upward and ray[1] > 0 else ray


reference = Rotation.from_rotvec(cameras[frame_index[facade["reference"]], :3]).as_matrix()
directions = np.stack([reference.T @ vanishing_direction(facade["vertical"], True), reference.T @ vanishing_direction(facade["along"], False)])


def segment_planes(focal):
    """Each segment's interpretation plane (camera axes): the normal of the plane through the
    camera and the segment, the plane any direction the segment runs along lies in."""
    first = np.c_[segment_ends[:, 0], np.full(len(segment_ends), focal)]
    second = np.c_[segment_ends[:, 1], np.full(len(segment_ends), focal)]
    normals = np.cross(first, second)
    return normals / np.linalg.norm(normals, axis=1, keepdims=True)


def assign(cameras, directions, focal, tolerance):
    """Which direction (0 vertical, 1 along the facade, -1 neither) each segment runs to, within ``tolerance`` degrees."""
    normals = segment_planes(focal)
    facing = Rotation.from_rotvec(cameras[segment_frames, :3])
    misses = np.stack([np.abs((normals * facing.apply(np.broadcast_to(direction / np.linalg.norm(direction), normals.shape))).sum(1))
                       for direction in directions], 1)
    family = misses.argmin(1)
    family[misses.min(1) > np.sin(np.radians(tolerance))] = -1
    return family


def project(rotvec, centre, focal, point):
    camera_point = Rotation.from_rotvec(rotvec).apply(point - centre)
    return focal * camera_point[..., :2] / camera_point[..., 2:3] + CENTRE


def triangulate(track):
    rows = []
    for frame, (u, v) in track:
        k = frame_index[frame]
        rotation = Rotation.from_rotvec(cameras[k, :3]).as_matrix()
        matrix = np.diag([focal, focal, 1.0]) @ np.hstack([rotation, (-rotation @ cameras[k, 3:])[:, None]])
        rows.append((u - CENTRE[0]) * matrix[2] - matrix[0])
        rows.append((v - CENTRE[1]) * matrix[2] - matrix[1])
    homogeneous = np.linalg.svd(np.array(rows))[2][-1]
    return homogeneous[:3] / homogeneous[3]


points, kept = [], []
for track in tracks:
    point = triangulate(track)
    if any(Rotation.from_rotvec(cameras[frame_index[frame], :3]).apply(point - cameras[frame_index[frame], 3:])[2] <= 0 for frame, _ in track):
        continue
    misses = [np.linalg.norm(project(cameras[frame_index[frame], :3], cameras[frame_index[frame], 3:], focal, point) - np.array(uv)) for frame, uv in track]
    if np.median(misses) < 25:
        points.append(point)
        kept.append(track)
tracks, points = kept, np.array(points)
print("points", len(points), flush=True)
span = settings["span"]
depth_scale = float(np.median([d for d in Rotation.from_rotvec(cameras[0, :3]).apply(points - cameras[0, 3:])[:, 2] if d > 0]))


def robustly(miss, scale):
    """Rows (N, D) rescaled so their squares sum to the Cauchy cost of each row's length."""
    squared = (miss ** 2).sum(1)
    return miss * np.sqrt(scale ** 2 * np.log1p(squared / scale ** 2) / np.maximum(squared, 1e-12))[:, None]


def solve(cameras, points, directions, focal, tracks, family, cauchy_scale):
    observations = [(frame_index[frame], p, uv) for p, track in enumerate(tracks) for frame, uv in track]
    seen_by = np.array([o[0] for o in observations])
    point_of = np.array([o[1] for o in observations])
    seen_at = np.array([o[2] for o in observations])
    used = np.nonzero(family >= 0)[0]
    used_frames, used_family = segment_frames[used], family[used]
    used_weight = np.sqrt(segment_lengths[used] / 100.0)
    count = len(cameras)
    free = list(range(1, count))
    slot = {camera: k for k, camera in enumerate(free)}
    point_column = 6 * len(free)
    direction_column = point_column + 3 * len(points)
    focal_column = direction_column + 6

    def unpack(x):
        solved = cameras.copy()
        solved[free] = x[:point_column].reshape(-1, 6)
        return (solved, x[point_column:direction_column].reshape(-1, 3), x[direction_column:focal_column].reshape(2, 3),
                focal if fixed_focal else x[focal_column])

    def residuals(x):
        solved, solved_points, solved_directions, solved_focal = unpack(x)
        camera_points = Rotation.from_rotvec(solved[seen_by, :3]).apply(solved_points[point_of] - solved[seen_by, 3:])
        miss = solved_focal * camera_points[:, :2] / camera_points[:, 2:3] + CENTRE - seen_at
        unit = solved_directions / np.linalg.norm(solved_directions, axis=1, keepdims=True)
        normals = segment_planes(solved_focal)[used]
        running = (normals * Rotation.from_rotvec(solved[used_frames, :3]).apply(unit[used_family])).sum(1) * solved_focal * used_weight
        scale = np.array([(np.linalg.norm(solved[-1, 3:] - solved[0, 3:]) - span) * 1000.0])
        turn = (solved[:-2, :3] - 2 * solved[1:-1, :3] + solved[2:, :3]).ravel() * solved_focal * SMOOTH
        path = (solved[:-2, 3:] - 2 * solved[1:-1, 3:] + solved[2:, 3:]).ravel() * solved_focal * SMOOTH / depth_scale
        return np.concatenate([robustly(miss, cauchy_scale).ravel(), robustly(running[:, None], SEGMENT_SCALE)[:, 0], scale, turn, path])

    segment_row = 2 * len(observations)
    scale_row = segment_row + len(used)
    smooth_row = scale_row + 1
    rows = smooth_row + 6 * (count - 2)
    columns = focal_column + 1
    sparsity = lil_matrix((rows, columns), dtype=np.int8)
    for k, (camera, point) in enumerate(zip(seen_by, point_of)):
        if camera in slot:
            sparsity[2 * k:2 * k + 2, 6 * slot[camera]:6 * slot[camera] + 6] = 1
        sparsity[2 * k:2 * k + 2, point_column + 3 * point:point_column + 3 * point + 3] = 1
        sparsity[2 * k:2 * k + 2, focal_column] = 1
    for k, (camera, which) in enumerate(zip(used_frames, used_family)):
        if camera in slot:
            sparsity[segment_row + k, 6 * slot[camera]:6 * slot[camera] + 3] = 1
        sparsity[segment_row + k, direction_column + 3 * which:direction_column + 3 * which + 3] = 1
        sparsity[segment_row + k, focal_column] = 1
    sparsity[scale_row, 6 * slot[count - 1] + 3:6 * slot[count - 1] + 6] = 1
    for k in range(1, count - 1):
        for neighbour in (k - 1, k, k + 1):
            if neighbour in slot:
                column = 6 * slot[neighbour]
                sparsity[smooth_row + 3 * (k - 1):smooth_row + 3 * k, column:column + 3] = 1
                sparsity[smooth_row + 3 * (count - 2) + 3 * (k - 1):smooth_row + 3 * (count - 2) + 3 * k, column + 3:column + 6] = 1
        sparsity[smooth_row + 3 * (k - 1):smooth_row + 3 * k, focal_column] = 1
        sparsity[smooth_row + 3 * (count - 2) + 3 * (k - 1):smooth_row + 3 * (count - 2) + 3 * k, focal_column] = 1
    start = np.concatenate([cameras[free].ravel(), points.ravel(), directions.ravel(), [focal]])
    result = least_squares(residuals, start, jac_sparsity=sparsity.tocsr(), loss="linear", x_scale="jac", max_nfev=300)
    solved, solved_points, solved_directions, solved_focal = unpack(result.x)
    camera_points = Rotation.from_rotvec(solved[seen_by, :3]).apply(solved_points[point_of] - solved[seen_by, 3:])
    misses = np.linalg.norm(solved_focal * camera_points[:, :2] / camera_points[:, 2:3] + CENTRE - seen_at, axis=1)
    return solved, solved_points, solved_directions / np.linalg.norm(solved_directions, axis=1, keepdims=True), solved_focal, misses, point_of


def segment_report(cameras, directions, focal, family):
    normals = segment_planes(focal)
    used = family >= 0
    running = np.abs((normals[used] * Rotation.from_rotvec(cameras[segment_frames[used], :3]).apply(directions[family[used]])).sum(1))
    return f"segments {int(used.sum())} ({int((family == 0).sum())} vertical, {int((family == 1).sum())} along), median {np.degrees(np.median(np.arcsin(running))):.2f} deg"


for threshold, cauchy_scale, tolerance in ((12.0, 8.0, 3.0), (6.0, 4.0, 3.0), (3.0, 2.0, 2.0), (2.0, 1.5, 1.5)):
    family = assign(cameras, directions, focal, tolerance)
    cameras, points, directions, focal, misses, point_of = solve(cameras, points, directions, focal, tracks, family, cauchy_scale)
    per_track = np.array([np.median(misses[point_of == p]) for p in range(len(points))])
    print(f"round: focal {focal:.1f}, median miss {np.median(misses):.2f} px, tracks {len(tracks)}, "
          f"dropping {int(np.sum(per_track > threshold))} over {threshold} px; {segment_report(cameras, directions, focal, family)}", flush=True)
    good = per_track <= threshold
    tracks = [track for track, ok in zip(tracks, good) if ok]
    points = points[good]
family = assign(cameras, directions, focal, 1.5)
cameras, points, directions, focal, misses, point_of = solve(cameras, points, directions, focal, tracks, family, 1.5)
print(f"final: focal {focal:.1f}, median miss {np.median(misses):.2f} px, 90% {np.percentile(misses, 90):.2f} px, tracks {len(tracks)}; "
      f"{segment_report(cameras, directions, focal, family)}; up and along {np.degrees(np.arccos(abs(directions[0] @ directions[1]))):.2f} deg apart", flush=True)
seen = {}
for track in tracks:
    for frame, _ in track:
        seen[frame] = seen.get(frame, 0) + 1
steps = np.linalg.norm(np.diff(cameras[:, 3:], axis=0), axis=1)
print("largest camera steps (frame, units):", [(frames[k + 1], round(float(steps[k]), 4)) for k in np.argsort(steps)[::-1][:5]], flush=True)
json.dump({"focal": focal, "width": WIDTH, "height": HEIGHT, "up": directions[0].tolist(), "along": directions[1].tolist(),
           "cameras": {str(frame): {"rotvec": cameras[k, :3].tolist(), "center": cameras[k, 3:].tolist(), "tracks": seen.get(frame, 0)}
                       for k, frame in enumerate(frames)},
           "points": points.tolist(),
           "tracks": [[[frame, uv[0], uv[1]] for frame, uv in track] for track in tracks]},
          open(args.out, "w"))
print("cameras of", len(frames), "frames ->", args.out)
