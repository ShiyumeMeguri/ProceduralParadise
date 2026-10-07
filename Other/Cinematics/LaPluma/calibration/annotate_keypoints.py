"""
Joints set by hand where the detector cannot see her (keypoints.py).

    python annotate_keypoints.py <keypoints.npz> <joints.json> <out.npz>

``joints.json`` names a span of frames whose detections are not used
(``cleared``: [first, last] -- seen from below through her billowing coat
the detector finds faces in its lining) and, on some of its frames, the
joints read off the picture by eye (``frames``: frame -> COCO-WholeBody body
joint name -> pixel).  A joint set by hand counts as surely as a detection
can, and is marked so (``by_hand``: frames by keypoints): the fit never lets
it go; the frames between are left to the fit's smoothness.  The frames
annotated are listed in the keypoints written (``annotated``): the fit reads
their left and right as given.
"""
import json
import sys

import numpy as np

JOINTS = ("nose", "eye_l", "eye_r", "ear_l", "ear_r", "shoulder_l", "shoulder_r", "elbow_l", "elbow_r", "wrist_l", "wrist_r",
          "hip_l", "hip_r", "knee_l", "knee_r", "ankle_l", "ankle_r")
SURE = 6.0

source, joints_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
data = dict(np.load(source))
spec = json.load(open(joints_path, encoding="utf-8"))
first, last = spec["cleared"]
frames = [int(frame) for frame in data["frames"]]
points, scores = data["points"].copy(), data["scores"].copy()
by_hand = np.zeros(scores.shape, bool)
for k, frame in enumerate(frames):
    if first <= frame <= last:
        scores[k] = 0.0
    for name, (x, y) in spec["frames"].get(str(frame), {}).items():
        points[k, JOINTS.index(name)] = (x, y)
        scores[k, JOINTS.index(name)] = SURE
        by_hand[k, JOINTS.index(name)] = True
annotated = sorted(int(frame) for frame in spec["frames"])
missing = sorted(set(annotated) - set(frames))
if missing:
    raise SystemExit(f"{joints_path}: frames {missing} are not in {source}")
np.savez_compressed(out, frames=data["frames"], points=points, scores=scores, annotated=np.array(annotated), by_hand=by_hand)
print("cleared", first, "-", last, "annotated", annotated, "->", out)
