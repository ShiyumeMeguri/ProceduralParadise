"""
The frames of the reference that repeat the one before it -- the film's ``holds``.

    python holds.py <frames dir> <film.json> [--ratio R] [--ceiling D]

The reference was made at a lower rate and padded to 30 fps by repeating
frames: a repeat differs from the frame before only by the video's
compression, while its neighbours move.  A frame is a hold when its mean
absolute difference from the one before (the watermark left out) is under
``--ratio`` of the median difference of the six frames round it and under
``--ceiling`` grey levels.  A still picture (a logo held on screen) is no
hold and needs none: rendering it again gives the same picture.  The
holds are written into the film (``film.json``), which shows the frame
before at each of them.
"""
import argparse
import json
import os

import cv2
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("frames_dir")
parser.add_argument("film")
parser.add_argument("--ratio", type=float, default=0.15)
parser.add_argument("--ceiling", type=float, default=1.0)
args = parser.parse_args()
film = json.load(open(args.film, encoding="utf-8"))
first, last = film["frames"]
masked = [tuple(box) for box in film.get("reference", {}).get("masks", ())]
differences = {}
previous = None
for frame in range(first, last + 1):
    image = cv2.imread(os.path.join(args.frames_dir, "f%04d.png" % frame), cv2.IMREAD_GRAYSCALE).astype(np.int16)
    for x0, y0, x1, y1 in masked:
        image[y0:y1, x0:x1] = 0
    if previous is not None:
        differences[frame] = float(np.abs(image - previous).mean())
    previous = image
holds = []
for frame, difference in differences.items():
    around = [differences[k] for k in range(frame - 3, frame + 4) if k != frame and k in differences]
    if difference < args.ratio * float(np.median(around)) and difference < args.ceiling:
        holds.append(frame)
film["holds"] = holds
open(args.film, "w", encoding="utf-8", newline="\n").write(json.dumps(film, indent=2, ensure_ascii=False) + "\n")
print("holds", len(holds), holds)
