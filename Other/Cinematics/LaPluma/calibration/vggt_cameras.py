"""
A shot's first cameras: VGGT on every few reference frames, for the match-move to start from
(``matchmove.py``).

    python vggt_cameras.py <frames dir> <shot.matchmove.json> <out shot.vggt.json>

The shot's match-move data (``vggt``: first and last frame, how many frames apart) names the
frames.  Written per frame: the camera from world (OpenCV: x right, y down, z forward) and its
intrinsics at the model's input size -- the shot's data the match-move starts from.  Only the
cameras are wanted, so only the model's aggregator and camera head are built
(facebook/VGGT-1B, downloaded on first use), the aggregator held in bfloat16 (its products are
bfloat16 under autocast anyway) and only its last layer kept: every frame is seen at once and
the card must hold them all within the claim (``gpu_budget.py``: a ceiling, not a swap file).
"""
import argparse
import json
import os

import torch
from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images
from vggt.utils.pose_enc import pose_encoding_to_extri_intri

from gpu_budget import claim

parser = argparse.ArgumentParser()
parser.add_argument("frames_dir")
parser.add_argument("shot")
parser.add_argument("out")
args = parser.parse_args()
settings = json.load(open(args.shot, encoding="utf-8"))["vggt"]
frames = list(range(settings["first"], settings["last"] + 1, settings["every"]))
claim()
model = VGGT(enable_point=False, enable_depth=False, enable_track=False)
weights = torch.hub.load_state_dict_from_url("https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt")
model.load_state_dict({key: value for key, value in weights.items() if key.split(".")[0] in ("aggregator", "camera_head")})
model.aggregator.cached_layer_indices = {model.aggregator.depth - 1}
model.aggregator.to(torch.bfloat16)
model = model.to("cuda").eval()
images = load_and_preprocess_images([os.path.join(args.frames_dir, "f%04d.png" % frame) for frame in frames], mode="pad").to("cuda")
with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
    batch = images[None]
    tokens, _ = model.aggregator(batch)
    pose = model.camera_head(tokens)[-1]
    extrinsic, intrinsic = pose_encoding_to_extri_intri(pose, batch.shape[-2:])
json.dump({"frames": frames, "input_size": list(images.shape[-2:]),
           "extrinsic": extrinsic[0].float().cpu().double().tolist(), "intrinsic": intrinsic[0].float().cpu().double().tolist()},
          open(args.out, "w", encoding="utf-8"))
print("cameras of", len(frames), "frames ->", args.out)
