"""
Video masks of the reference's objects, prompted from data (SAM 2).

    python roto.py <frames dir> <prompts.json> <first> <last> <out dir>
                   --checkpoint sam2.1_hiera_large.pt [--config configs/sam2.1/sam2.1_hiera_l.yaml]

A shot's prompts (``<shot>.roto.json``) are groups of objects -- the
character, her scythe, its blade, its hub, her two legs -- and, on keyframes
picked by eye, where each one is: points on it (``points``), a box round it
(``boxes``), and points on what it is not (``negative``).  The objects of a
group are tracked together and never overlap: an object's points are not
any other object of its group, so objects alike in colour (two legs) keep
apart where they cross, and one hidden behind the other says where it is
not; a pixel goes to the object most sure of it.  Objects that do overlap
(the scythe and its blade) are in groups of their own.  Which leg is which
is read on the keyframe from what tells them apart (the knee pad, the straps
on that thigh); a keypoint detector seeing her from behind swaps them.
Every object is tracked through the shot from all its keyframes at once,
both ways, and every frame's mask is written as
``<out dir>/<object>/m####.png`` (white = the object).
"""
import argparse
import json
import os
import shutil
import tempfile

import cv2
import numpy as np
import torch
from sam2.build_sam import build_sam2_video_predictor

from gpu_budget import GIGABYTE, claim

parser = argparse.ArgumentParser()
parser.add_argument("frames_dir")
parser.add_argument("prompts")
parser.add_argument("first", type=int)
parser.add_argument("last", type=int)
parser.add_argument("out")
parser.add_argument("--checkpoint", required=True)
parser.add_argument("--config", default="configs/sam2.1/sam2.1_hiera_l.yaml")
args = parser.parse_args()
groups = json.load(open(args.prompts, encoding="utf-8"))["groups"]
frames = list(range(args.first, args.last + 1))

staging = tempfile.mkdtemp(prefix="sam2_")
for k, frame in enumerate(frames):
    image = cv2.imread(os.path.join(args.frames_dir, "f%04d.png" % frame))
    cv2.imwrite(os.path.join(staging, "%05d.jpg" % k), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
claim(least=3 * GIGABYTE)
predictor = build_sam2_video_predictor(args.config, args.checkpoint, device="cuda", hydra_overrides_extra=["++model.non_overlap_masks=true"])
for group in groups:
    objects = group["objects"]
    keys = sorted(int(frame) for frame in group["keys"] if args.first <= int(frame) <= args.last)
    if not keys:
        print("no keyframe of", ", ".join(objects), "in", args.first, "..", args.last)
        continue
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        state = predictor.init_state(video_path=staging, offload_video_to_cpu=True, offload_state_to_cpu=True)
        for frame in keys:
            key = group["keys"][str(frame)]
            points = key.get("points", {})
            boxes = key.get("boxes", {})
            for number, name in enumerate(objects, start=1):
                if name not in points and name not in boxes:
                    continue
                positive = points.get(name, [])
                negative = [point for other, others in points.items() if other != name for point in others] + key.get("negative", [])
                coordinates = np.array(positive + negative, np.float32).reshape(-1, 2)
                labels = np.array([1] * len(positive) + [0] * len(negative), np.int32)
                box = np.array(boxes[name], np.float32) if name in boxes else None
                predictor.add_new_points_or_box(state, frame_idx=frames.index(frame), obj_id=number,
                                                points=coordinates if len(coordinates) else None, labels=labels if len(coordinates) else None, box=box)
        logits_by_frame = {}
        for reverse in (False, True):
            for k, object_ids, logits in predictor.propagate_in_video(state, start_frame_idx=frames.index(keys[0]), reverse=reverse):
                logits_by_frame[frames[k]] = (list(object_ids), logits[:, 0].float().cpu().numpy())
    for name in objects:
        os.makedirs(os.path.join(args.out, name), exist_ok=True)
    for frame, (object_ids, logits) in logits_by_frame.items():
        best = logits.argmax(0)
        for slot, number in enumerate(object_ids):
            mask = (logits[slot] > 0.0) & (best == slot)
            cv2.imwrite(os.path.join(args.out, objects[number - 1], "m%04d.png" % frame), mask.astype(np.uint8) * 255)
    print("masks of", ", ".join(objects), "for", len(logits_by_frame), "frames ->", args.out, flush=True)
shutil.rmtree(staging, ignore_errors=True)
