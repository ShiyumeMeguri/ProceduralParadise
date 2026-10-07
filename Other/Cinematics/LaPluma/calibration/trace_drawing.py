"""
A flat piece of the reference's artwork as a drawing (``Other/Cinematics/Drawings``), read off frames where it stands still
on black.

    python trace_drawing.py <frames folder> <spec.json> <out.json>

``spec.json`` names the frames whose median is the artwork (``frames``: [first, last]), boxes of it covered on all of them
read instead off one other frame brought up to the same brightness (``patches``: [{"frame", "gain", "box": [x0, y0, x1, y1]}]),
the box the artwork lies in (``box``) and the band of rows whose nearly level or upright edges are set square (``square``:
[top, bottom]).  The ink's brightness about a point is that of the solid ink there (what is near the brightest about it,
not the soft edges of thin lines); ink is what is brighter than half of it, its outline followed at a quarter of a pixel and
simplified, each point carrying the brightness of the ink about it as a share of the brightest (``tone``).  The loops are
kept as shapes, an outline and the holes in it, in the picture's units (half its height is 1, the middle 0); a shape whose
outline lies in the squared band is the drawing's lettering (``part``), the rest its artwork.
"""
import json
import os
import sys

import cv2
import numpy as np

SCALE = 4
FLOOR = 7.0
NEIGHBOURHOOD = 5.0
SQUARE_TURN = 0.25
SQUARE_LENGTH = 2.0
SMALLEST = 3.0
SOLID = 0.7


def grey(folder, frame):
    image = cv2.imread(os.path.join(folder, f"f{frame:04d}.png"))
    if image is None:
        raise FileNotFoundError(f"{folder}: no frame {frame}")
    return image.astype(np.float32).mean(axis=2)


def squared(points):
    kinds = []
    count = len(points)
    for k in range(count):
        (ax, ay), (bx, by) = points[k], points[(k + 1) % count]
        across, up = abs(bx - ax), abs(by - ay)
        long_enough = np.hypot(across, up) > SQUARE_LENGTH
        if long_enough and up < across * SQUARE_TURN:
            kinds.append(("level", (ay + by) * 0.5))
        elif long_enough and across < up * SQUARE_TURN:
            kinds.append(("upright", (ax + bx) * 0.5))
        else:
            kinds.append((None, None))
    result = []
    for k in range(count):
        x, y = points[k]
        for kind, value in (kinds[k - 1], kinds[k]):
            if kind == "level":
                y = value
            elif kind == "upright":
                x = value
        result.append((x, y))
    return result


folder, spec_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
spec = json.load(open(spec_path, encoding="utf-8"))
first, last = spec["frames"]
artwork = np.median(np.stack([grey(folder, frame) for frame in range(first, last + 1)]), axis=0)
for patch in spec.get("patches", []):
    x0, y0, x1, y1 = patch["box"]
    source = cv2.medianBlur(np.clip(grey(folder, patch["frame"]) * patch["gain"], 0, 255).astype(np.uint8), 3).astype(np.float32)
    artwork[y0:y1, x0:x1] = source[y0:y1, x0:x1]
left, top, right, bottom = spec["box"]
image = cv2.GaussianBlur(artwork[top:bottom, left:right], (0, 0), 0.8)
peak = cv2.GaussianBlur(cv2.dilate(image, np.ones((7, 7), np.uint8)), (0, 0), 2.0)
solid = ((image > FLOOR) & (image > SOLID * peak)).astype(np.float32)
weight = cv2.GaussianBlur(solid, (0, 0), NEIGHBOURHOOD)
level = cv2.GaussianBlur(image * solid, (0, 0), NEIGHBOURHOOD) / np.maximum(weight, 1e-3)
level = np.where(weight > 0.02, level, 0.0)
fine = cv2.resize(image, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
fine_level = cv2.resize(level, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_LINEAR)
ink = ((fine > 0.5 * fine_level) & (fine_level > FLOOR - 2.0)).astype(np.uint8)
brightest = float(np.percentile(level[(image > 0.5 * level) & (level > FLOOR - 2.0)], 99.5))
contours, hierarchy = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
square_top, square_bottom = spec["square"]
height, width = level.shape


def loop(contour):
    points = contour[:, 0, :].astype(np.float64) / SCALE + (0.5 / SCALE - 0.5)
    lettering = square_top <= top + points[:, 1].mean() <= square_bottom
    tolerance = (0.6 if lettering else 0.3) * SCALE
    simple = cv2.approxPolyDP((points * SCALE).astype(np.float32).reshape(-1, 1, 2), tolerance, True)[:, 0, :].astype(np.float64) / SCALE
    if len(simple) < 3:
        return None
    simple = squared([tuple(point) for point in simple]) if lettering else [tuple(point) for point in simple]
    result = []
    for x, y in simple:
        tone = level[min(max(int(round(y)), 0), height - 1), min(max(int(round(x)), 0), width - 1)] / brightest
        result.append([round((left + x - 960.0) / 540.0, 4), round((540.0 - (top + y)) / 540.0, 4), round(float(min(max(tone, 0.0), 1.0)), 3)])
    return result


shapes = []
for index, contour in enumerate(contours):
    if hierarchy[0][index][3] != -1 or cv2.contourArea(contour) < SMALLEST * SCALE * SCALE:
        continue
    outline = loop(contour)
    if outline is None:
        continue
    holes = []
    child = hierarchy[0][index][2]
    while child != -1:
        if cv2.contourArea(contours[child]) >= SMALLEST * SCALE * SCALE:
            hole = loop(contours[child])
            if hole is not None:
                holes.append(hole)
        child = hierarchy[0][child][0]
    lettering = square_top <= top + np.mean([540.0 - y * 540.0 - top for _, y, _ in outline]) <= square_bottom
    shapes.append({"part": "lettering" if lettering else "artwork", "loops": [outline] + holes})
drawing = {"note": spec["note"], "shapes": shapes}
with open(out, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(json.dumps(drawing, separators=(",", ":")) + "\n")
print(f"{out}: {len(shapes)} shapes ({sum(shape['part'] == 'lettering' for shape in shapes)} lettering), "
      f"{sum(len(shape['loops']) for shape in shapes)} loops, {sum(len(points) for shape in shapes for points in shape['loops'])} points; "
      f"brightest ink {brightest:.1f} of 255")
