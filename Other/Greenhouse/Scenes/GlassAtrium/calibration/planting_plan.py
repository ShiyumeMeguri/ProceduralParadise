"""
Planting plan of the garden, read from the painting.

The garden floor is divided into 0.5 m cells.  For every cell the plant
heights ``HEIGHTS`` above the soil are projected through the solved camera
into the figure-free painting, the soil itself first (a point above the
cell projects higher in the image, where a plant further back may stand,
so only the cell's own soil tells whether the cell is paved): a cell may carry plants as tall as the
highest of those points that all land on painted foliage (saturated
yellow-green through the teal shade to its blue depths, in blobs wider
than the glazing bars -- not the sun patches on the floor, which are
orange-yellow, under 48 degrees of hue, and paler than sunlit leaves) or
outside the frame; a point landing on the pale floor, on the pink haze or on the sky
caps the height below it.  A point hidden behind glassware (its boxes come
from the scene) tells nothing: a cell seen only through glassware takes
the class most of its seen neighbours within ``NEIGHBOURHOOD`` cells have.
Cells the camera cannot see at all are planted by design.  The foot of
the stair and the court along the north wall (the pale floor seen through
the balustrade, where the painted canopy behind is the trees outside) are
kept clear, and so is the floor under the garden furniture of the scene
(``FURNITURE_MARGIN`` round it).

    python Other/Greenhouse/Scenes/GlassAtrium/calibration/planting_plan.py

writes ``data/planting.json``: cell meshes ``ground`` (up to ``GROUND`` m),
``understory`` (up to ``UNDERSTORY`` m), ``shrubs`` (taller), ``designed``
(unseen) and ``beds`` (all planted cells), which scene.json plants.
Development tool: needs numpy and OpenCV (the scene build does not).
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SCENE, "..", "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from Core.jsonio import dump  # noqa: E402

REFERENCE = os.path.join(SCENE, "Reference", "Nitia_clean.webp")
SHOT = os.path.join(SCENE, "shots", "Nitia.json")
SCENE_JSON = os.path.join(SCENE, "scene.json")
OUT = os.path.join(SCENE, "data", "planting.json")
SOIL = -3.08
HEIGHTS = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.2, 2.6]
GROUND = 0.9
UNDERSTORY = 1.8
CELL = 0.5
EXTENT = (-12.3, 13.3, -5.8, 15.8)
KEEP_CLEAR = [(-4.62, -3.12, 0.32, 8.0), (-9.5, 2.5, 9.5, 15.8)]
FURNITURE_MARGIN = 0.15
BLOB = 15
WINDOW = 6
NEIGHBOURHOOD = 3


class Pinhole:
    """The shot's camera (``Core.camera`` conventions: yaw about Z, pitch
    about the camera X, roll about the view axis; 0 looks along +Y)."""

    def __init__(self, solve):
        self.f = solve["focal_px"]
        self.cx, self.cy = solve["principal_px"]
        self.C = np.array(solve["location"], float)
        yaw, pitch, roll = (math.radians(solve[key]) for key in ("yaw_deg", "pitch_deg", "roll_deg"))
        rz = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]])
        base = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
        rr = np.array([[math.cos(roll), -math.sin(roll), 0], [math.sin(roll), math.cos(roll), 0], [0, 0, 1]])
        self.R = (rz @ rx @ base.T @ rr).T

    def project(self, points):
        local = (np.atleast_2d(points) - self.C) @ self.R.T
        return np.c_[self.f * local[:, 0] / local[:, 2] + self.cx, self.f * local[:, 1] / local[:, 2] + self.cy], local[:, 2]


def foliage_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = (hsv[..., k].astype(int) for k in range(3))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BLOB, BLOB))
    foliage = (hue >= 24) & (hue <= 100) & (saturation >= 70) & (value >= 40)
    return cv2.morphologyEx(foliage.astype(np.uint8), cv2.MORPH_OPEN, kernel) > 0


def glassware_mask(camera, shape, scene):
    mask = np.zeros(shape, np.uint8)
    for item in scene["collections"]["Gallery"] + scene["collections"]["Terraria"]:
        x, y, z = item["loc"]
        inputs = item.get("inputs", {})
        size = max(inputs.get("Width", 0.0), inputs.get("Depth", 0.0), inputs.get("Radius", 0.15) * 2.0, 0.3)
        height = inputs.get("Height", 0.0) + inputs.get("Neck Length", 0.0) + inputs.get("Radius", 0.0) * 2.0 + 0.3
        if "Drop" in inputs:
            z -= inputs["Drop"] + inputs.get("Radius", 0.2)
        corners = np.array([[x + dx * size * 0.6, y + dy * size * 0.6, z + dz * height] for dx in (-1, 1) for dy in (-1, 1) for dz in (0, 1)])
        pixels, depth = camera.project(corners)
        if (depth > 0).all():
            cv2.fillConvexPoly(mask, cv2.convexHull(pixels.astype(np.int32)), 1)
    return mask > 0


def quads(mask, x0, y0):
    vertices, faces = [], []
    for i, j in zip(*np.nonzero(mask)):
        x, y = x0 + i * CELL, y0 + j * CELL
        k = len(vertices)
        vertices += [[round(x, 3), round(y, 3), 0.0], [round(x + CELL, 3), round(y, 3), 0.0],
                     [round(x + CELL, 3), round(y + CELL, 3), 0.0], [round(x, 3), round(y + CELL, 3), 0.0]]
        faces.append([k, k + 1, k + 2, k + 3])
    return {"vertices": vertices, "faces": faces}


def main():
    with open(SHOT, encoding="utf-8") as handle:
        camera = Pinhole(json.load(handle)["camera"])
    with open(SCENE_JSON, encoding="utf-8") as handle:
        scene = json.load(handle)
    image = cv2.imread(REFERENCE)
    height, width = image.shape[:2]
    foliage = foliage_mask(image)
    hidden = glassware_mask(camera, (height, width), scene)
    integral = cv2.integral(foliage.astype(np.float32))
    hidden_integral = cv2.integral(hidden.astype(np.float32))

    def window_mean(table, u, v):
        u0, u1 = max(u - WINDOW, 0), min(u + WINDOW + 1, width)
        v0, v1 = max(v - WINDOW, 0), min(v + WINDOW + 1, height)
        area = max((u1 - u0) * (v1 - v0), 1)
        return (table[v1, u1] - table[v0, u1] - table[v1, u0] + table[v0, u0]) / area

    x0, x1, y0, y1 = EXTENT
    nx, ny = int(round((x1 - x0) / CELL)), int(round((y1 - y0) / CELL))
    allowed = np.full((nx, ny), np.inf)
    seen = np.zeros((nx, ny), bool)
    behind_glass = np.zeros((nx, ny), bool)
    for i in range(nx):
        for j in range(ny):
            cx, cy = x0 + (i + 0.5) * CELL, y0 + (j + 0.5) * CELL
            points = np.array([[cx, cy, SOIL + h] for h in HEIGHTS])
            pixels, depth = camera.project(points)
            for h, (u, v), d in zip(HEIGHTS, pixels, depth):
                if d <= 0 or not (0 <= u < width and 0 <= v < height):
                    continue
                u, v = int(u), int(v)
                if window_mean(hidden_integral, u, v) > 0.5:
                    behind_glass[i, j] = True
                    continue
                seen[i, j] = True
                if window_mean(integral, u, v) < 0.5:
                    allowed[i, j] = min(allowed[i, j], h - 0.3)
                    break
    for i, j in zip(*np.nonzero(behind_glass & ~seen)):
        window = (slice(max(i - NEIGHBOURHOOD, 0), i + NEIGHBOURHOOD + 1), slice(max(j - NEIGHBOURHOOD, 0), j + NEIGHBOURHOOD + 1))
        known = seen[window]
        if known.any():
            heights = allowed[window][known]
            seen[i, j] = True
            allowed[i, j] = np.median(np.where(np.isinf(heights), HEIGHTS[-1], heights))
    centres_x = x0 + (np.arange(nx) + 0.5) * CELL
    centres_y = y0 + (np.arange(ny) + 0.5) * CELL
    clear = np.zeros((nx, ny), bool)
    boxes = list(KEEP_CLEAR)
    for item in scene["collections"]["Garden"]:
        if item.get("asset", "").startswith("GH.Furniture."):
            x, y, _ = item["loc"]
            reach = item["inputs"]["Radius"] + FURNITURE_MARGIN
            boxes.append((x - reach, x + reach, y - reach, y + reach))
    for left, right, bottom, top in boxes:
        clear |= ((centres_x[:, None] >= left) & (centres_x[:, None] <= right) & (centres_y[None, :] >= bottom) & (centres_y[None, :] <= top))
    visible = seen & ~clear
    ground = visible & (allowed >= 0.3) & (allowed < GROUND)
    understory = visible & (allowed >= GROUND) & (allowed < UNDERSTORY)
    shrubs = visible & (allowed >= UNDERSTORY)
    designed = ~seen & ~clear
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    dump({"notes": "Garden cells (0.5 m) from calibration/planting_plan.py: plants may reach GROUND (0.9 m), UNDERSTORY (1.8 m) or more "
                   "where the painting shows foliage up to that height; designed = unseen from the painting's camera; beds = every planted cell.",
          "ground": quads(ground, x0, y0), "understory": quads(understory, x0, y0), "shrubs": quads(shrubs, x0, y0),
          "designed": quads(designed, x0, y0), "beds": quads(ground | understory | shrubs | designed, x0, y0)}, OUT)
    print("cells: ground %d, understory %d, shrubs %d, open %d, designed %d -> %s"
          % (ground.sum(), understory.sum(), shrubs.sum(), (visible & (allowed < 0.3)).sum(), designed.sum(), OUT))


if __name__ == "__main__":
    main()
