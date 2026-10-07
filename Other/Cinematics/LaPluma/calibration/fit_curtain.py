"""
A curtain of light read off the reference band by band and frame by frame (``CIN.Overlay.Curtain``).

    python fit_curtain.py <frames folder> <shot.json> <spec.json>

``spec.json`` names the curtain's bands (``bands``: their count across the picture, each a curtain item ``<name> <k>`` of the
shot, the first on the left), the frames read (``frames``: [first, last]), the rows read as the heads and the feet
(``head_rows``, ``foot_rows``: [top, bottom]), the overlap of neighbouring bands (``feather``, picture units: each band
fades in over the one to its left) and the
contrast where the picture hides it (``hidden``).  On every frame, for each band:

- the contrast of its head and of its foot is the spread of the logarithm of their green across its columns; where the
  picture clips or crushes the green it shows hardly any streaks (``hidden``);
- its head's and foot's colours are their rows' medians; a channel the picture clips there is read at the highest of the
  quarter, tenth and twentieth percentiles it does not clip and brought up by the contrast to the median it would have
  had (the curtain draws its median column in the colours themselves), every channel by the same rule;
- the turn of each column of it is the height and softness at which the curtain's own passing from its foot's colour to
  its head's (mixed in linear light, clipped as the picture clips) best draws the column's green row by row: their
  median the turn's height, their spread its spread, the columns' softness its softness (columns whose head and foot
  are alike have no turn to read).

The bands' keys and placings are written into the shot.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
from Core import jsonio

CLIPPED = 245.0
CRUSHED = 10.0
PERCENTILES = ((50, 0.0), (25, -0.6745), (10, -1.2816), (5, -1.6449))
SPREAD_Z = 2.0 * 1.2816
STRIP = 30
COLUMN = 16
LEAST_TURN = 12.0
HEIGHTS = np.arange(-0.1, 1.1001, 0.01)
SOFTNESSES = np.array([0.01, 0.02, 0.03, 0.05, 0.07, 0.1, 0.13, 0.17, 0.22, 0.28, 0.35, 0.45])


def linear(display):
    value = np.asarray(display, np.float64) / 255.0
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def picture(folder, frame):
    image = cv2.imread(os.path.join(folder, f"f{frame:04d}.png"))
    if image is None:
        raise FileNotFoundError(f"{folder}: no frame {frame}")
    return image[..., ::-1].astype(np.float64)


def contrast(region, hidden):
    values = region[..., 1].ravel()
    low, high = np.percentile(values, 10), np.percentile(values, 90)
    if high < CLIPPED and low > CRUSHED:
        return round(float((np.log(linear(high)) - np.log(linear(low))) / SPREAD_Z), 3)
    return hidden


def colour(region, spread):
    result = []
    for channel in range(3):
        values = region[..., channel].ravel()
        for percentile, z in PERCENTILES:
            reading = np.percentile(values, percentile)
            if reading < CLIPPED:
                result.append(float(linear(reading)) / np.exp(z * spread))
                break
        else:
            result.append(1.1 / np.exp(PERCENTILES[-1][1] * spread))
    return [round(value, 4) for value in result] + [1.0]


def display(light):
    light = np.clip(light, 0.0, 1.0)
    return np.where(light <= 0.0031308, light * 12.92, 1.055 * np.power(light, 1.0 / 2.4) - 0.055) * 255.0


def passings(rows):
    rises = 1.0 - (np.arange(rows // STRIP) + 0.5) * STRIP / rows
    low = (HEIGHTS[:, None] - SOFTNESSES[None, :])[..., None]
    span = (2.0 * SOFTNESSES)[None, :, None]
    share = np.clip((rises[None, None, :] - low) / span, 0.0, 1.0)
    return share * share * (3.0 - 2.0 * share)


def turn(band, rows_read, band_light, previous):
    (head_top, head_bottom), (foot_top, foot_bottom) = rows_read
    rows = band.shape[0]
    passing = passings(rows)
    heights, softnesses = [], []
    for x in range(0, band.shape[1] - COLUMN + 1, COLUMN):
        green = band[:, x:x + COLUMN, 1]
        head_value, foot_value = np.median(green[head_top:head_bottom]), np.median(green[foot_top:foot_bottom])
        if abs(head_value - foot_value) < LEAST_TURN:
            continue
        head_light = float(linear(head_value)) if head_value < CLIPPED else band_light[0]
        foot_light = float(linear(foot_value)) if foot_value < CLIPPED else band_light[1]
        profile = np.array([np.median(green[y:y + STRIP]) for y in range(0, rows - STRIP + 1, STRIP)])
        drawn = display(foot_light + (head_light - foot_light) * passing)
        misfit = ((drawn - profile[None, None, :]) ** 2).sum(axis=2)
        best_height, best_softness = np.unravel_index(np.argmin(misfit), misfit.shape)
        heights.append(HEIGHTS[best_height])
        softnesses.append(SOFTNESSES[best_softness])
    if len(heights) < 3:
        return previous
    return [round(float(np.median(heights)), 3), round(min(float(np.std(heights)), 0.3), 3), round(float(np.median(softnesses)), 3)]


folder, shot_path, spec_path = sys.argv[1], sys.argv[2], sys.argv[3]
spec = json.load(open(spec_path, encoding="utf-8"))
shot = json.load(open(shot_path, encoding="utf-8"))
count = spec["bands"]
first, last = spec["frames"]
head_top, head_bottom = spec["head_rows"]
foot_top, foot_bottom = spec["foot_rows"]
sample = picture(folder, first)
height, width = sample.shape[:2]
aspect = width / height
band_width = width // count
keys = [{"Head": [], "Foot": [], "Turn": [], "Contrast": []} for _ in range(count)]
turns = [[0.5, 0.0, 0.25] for _ in range(count)]
items = {item["name"]: item for item in shot.get("overlays", []) + shot.get("underlays", {}).get("items", [])}
for frame in range(first, last + 1):
    image = picture(folder, frame)
    for k in range(count):
        band = image[:, k * band_width:(k + 1) * band_width]
        head_region, foot_region = band[head_top:head_bottom], band[foot_top:foot_bottom]
        head_spread, foot_spread = contrast(head_region, spec["hidden"]), contrast(foot_region, spec["hidden"])
        head, foot = colour(head_region, head_spread), colour(foot_region, foot_spread)
        keys[k]["Head"].append([frame, head])
        keys[k]["Foot"].append([frame, foot])
        keys[k]["Contrast"].append([frame, [head_spread, foot_spread, 0.0]])
        turns[k] = turn(band, ((head_top, head_bottom), (foot_top, foot_bottom)), (head[1], foot[1]), turns[k])
        keys[k]["Turn"].append([frame, list(turns[k])])
unit = 2.0 / height
for k in range(count):
    name = f"{spec['name']} {k + 1}"
    if name not in items:
        raise KeyError(f"{shot_path}: no overlay or underlay '{name}'")
    left = -aspect + k * band_width * unit - spec["feather"] * 0.5
    right = -aspect + (k + 1) * band_width * unit + spec["feather"] * 0.5
    item = items[name]
    item["inputs"]["Across"] = [round(left, 4), round(right, 4), 0.0]
    item["inputs"]["Feather"] = [spec["feather"] if k > 0 else 0.0, 0.0, 0.0]
    item["keys"] = keys[k]
    heads = [value[0] for _, value in keys[k]["Contrast"]]
    print(f"{name}: head contrast {min(heads):.2f}-{max(heads):.2f}, across {item['inputs']['Across'][:2]}")
with open(shot_path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(jsonio.dumps(shot, indent=1) + "\n")
