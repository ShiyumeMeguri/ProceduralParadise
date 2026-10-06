"""
Video masks of one object of the reference (SAM 2).

    python masks.py <frames dir> <first> <last> <out dir> <prompt frame> <x0,y0,x1,y1> [<x,y> ...]
                    [--checkpoint sam2.1_hiera_large.pt --config configs/sam2.1/sam2.1_hiera_l.yaml]

The object is prompted on one frame with a box round it (and points on
it, optional, and ``--negative`` points on what is not it -- a character
in front of what she holds) and tracked through the shot both ways; every frame's
mask is written as ``m####.png`` (white = the object).  Needs the ``sam2``
package and its checkpoint.
"""
import argparse
import os
import shutil
import tempfile

import cv2
import numpy as np
import torch
from sam2.build_sam import build_sam2_video_predictor

parser = argparse.ArgumentParser()
parser.add_argument("frames_dir")
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("out")
parser.add_argument("prompt_frame", type=int)
parser.add_argument("box")
parser.add_argument("points", nargs="*")
parser.add_argument("--negative", nargs="*", default=[], help="x,y points that are not the object")
parser.add_argument("--checkpoint", required=True)
parser.add_argument("--config", default="configs/sam2.1/sam2.1_hiera_l.yaml")
args = parser.parse_args()
os.makedirs(args.out, exist_ok=True)
staging = tempfile.mkdtemp(prefix="sam2_")
frames = list(range(args.first, args.last + 1))
for k, frame in enumerate(frames):
    image = cv2.imread(os.path.join(args.frames_dir, "f%04d.png" % frame))
    cv2.imwrite(os.path.join(staging, "%05d.jpg" % k), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
predictor = build_sam2_video_predictor(args.config, args.checkpoint, device="cuda")
with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    state = predictor.init_state(video_path=staging, offload_video_to_cpu=True, offload_state_to_cpu=True)
    box = np.array([float(v) for v in args.box.split(",")], np.float32)
    positive = [[float(v) for v in point.split(",")] for point in args.points]
    negative = [[float(v) for v in point.split(",")] for point in args.negative]
    points = np.array(positive + negative, np.float32) if positive or negative else None
    labels = np.array([1] * len(positive) + [0] * len(negative), np.int32) if points is not None else None
    predictor.add_new_points_or_box(state, frame_idx=frames.index(args.prompt_frame), obj_id=1, box=box, points=points, labels=labels)
    masks = {}
    for reverse in (False, True):
        for k, _ids, logits in predictor.propagate_in_video(state, start_frame_idx=frames.index(args.prompt_frame), reverse=reverse):
            masks[frames[k]] = (logits[0, 0] > 0.0).cpu().numpy()
for frame, mask in masks.items():
    cv2.imwrite(os.path.join(args.out, "m%04d.png" % frame), mask.astype(np.uint8) * 255)
shutil.rmtree(staging, ignore_errors=True)
print("masks for", len(masks), "frames ->", args.out)
