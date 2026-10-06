"""
Whole-body keypoints of the reference frames (DWPose / RTMW through rtmlib).

    python keypoints.py <frames dir> <first> <last> <out.npz>

For every frame: the 133 COCO-WholeBody keypoints (body, feet, face,
hands) of the best-scoring person and their scores, in reference pixels.
Needs ``rtmlib`` and ``onnxruntime`` (the models download on first use).
"""
import os
import sys

import cv2
import numpy as np
from rtmlib import Wholebody

frames_dir, first, last, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
model = Wholebody(mode="performance", backend="onnxruntime", device="cpu", to_openpose=False)
frames, points, scores = [], [], []
for frame in range(first, last + 1):
    image = cv2.imread(os.path.join(frames_dir, "f%04d.png" % frame))
    keypoints, confidence = model(image)
    if len(keypoints) == 0:
        keypoints = np.zeros((1, 133, 2))
        confidence = np.zeros((1, 133))
    best = int(np.argmax(confidence[:, :23].mean(1)))
    frames.append(frame)
    points.append(keypoints[best])
    scores.append(confidence[best])
np.savez_compressed(out, frames=np.array(frames), points=np.array(points, np.float32), scores=np.array(scores, np.float32))
print("keypoints for", len(frames), "frames ->", out)
