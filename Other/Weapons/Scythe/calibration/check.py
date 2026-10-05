"""
Measure a render of the ``Sheet`` shot against the design sheet.

The render is the transparent film of the shot (``--no-look``: no paper
laid under it), so its alpha is the weapon's silhouette; for the tones it
is laid on white paper here.

* **Silhouette**: the weapon on the sheet is what is darker than ``DARK``
  (halfway between the paper and the dark parts, where the tracer puts
  their edges), the light parts -- areas lighter than that but darker than
  ``LIGHT`` that are wider than an edge's ramp -- and every enclosed light
  area that is not bare paper (the white enamel and the polished steel are
  printed with a halftone and never reach ``PAPER``; the paper seen through
  a slot does in its brightest quarter, the ink round a small opening
  darkening only its rim).  Reported against the render's alpha as the intersection over
  union and the distance from every outline pixel of one to the nearest of
  the other (mean and 95th percentile, in sheet pixels), within the
  weapon's reach (the blade's tip, drawn over another figure, and the
  sheet's other drawings are left out; so is ``GLARE``, where the blade's
  polished steel is printed as white as the paper and its edge cannot be
  read).
* **Tone**: the mean absolute difference of the two images, both blurred
  by ``SOFTEN`` px so the print's halftone screen does not count, over the
  weapon, overall and part by part (``REGIONS``), with its sign (positive:
  the render is lighter).

Plain Python with numpy and OpenCV::

    blender -b -P Other/build.py -- Weapons/Scythe --no-save --no-look --render film.png
    python Other/Weapons/Scythe/calibration/check.py film.png [--heat heat.png]
"""
from __future__ import annotations

import argparse
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET = os.path.join(os.path.dirname(HERE), "Reference", "Sheet.jpg")
SOFTEN = 2.0
DARK = 147.0
LIGHT = 227.0
RAMP = 2
PAPER = 250.0
REACH = 9
TIP = 2560
GLARE = [(2140, 515, 2350, 650)]
REGIONS = {"head": (425, 180, 1340, 730), "blade": (1240, 200, TIP, 1000), "linkage": (720, 620, 1010, 960),
           "shaft": (960, 720, 1130, 1517), "grip": (860, 1500, 1170, 1720), "rails": (970, 1700, 1110, 2300),
           "foot": (940, 2160, 1140, 2460)}


def outline(mask):
    edge = np.zeros(mask.shape, bool)
    edge[:, 1:] |= mask[:, 1:] != mask[:, :-1]
    edge[1:, :] |= mask[1:, :] != mask[:-1, :]
    return edge


def distances(source, target):
    """Distance from every ``source`` pixel to the nearest ``target`` pixel."""
    field = cv2.distanceTransform((~target).astype(np.uint8), cv2.DIST_L2, 5)
    return field[source]


def drawn_weapon(grey, reach):
    """The weapon on the sheet within ``reach``: the dark print, the light
    parts wider than an edge's ramp, and the enclosed light areas that are
    not bare paper."""
    light = (grey >= DARK) & (grey < LIGHT)
    kernel = np.ones((2 * RAMP + 1, 2 * RAMP + 1), np.uint8)
    cores = cv2.dilate(cv2.erode(light.astype(np.uint8), kernel), kernel) > 0
    dark = ((grey < DARK) | (cores & light)) & reach
    count, labels = cv2.connectedComponents((~dark).astype(np.uint8), connectivity=4)
    outside = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    weapon = dark.copy()
    for label in range(count):
        if label in outside:
            continue
        area = labels == label
        if np.percentile(grey[area], 75) < PAPER and reach[area].all():
            weapon |= area
    return weapon


def measure(render_path, heat_path=None):
    film = cv2.imread(render_path, cv2.IMREAD_UNCHANGED).astype(np.float32)
    alpha = film[..., 3:] / 255.0
    render = film[..., :3] * alpha + 255.0 * (1.0 - alpha)
    sheet = cv2.imread(SHEET).astype(np.float32)
    shown = alpha[..., 0] > 0.5
    reach = cv2.dilate(shown.astype(np.uint8), np.ones((2 * REACH + 1, 2 * REACH + 1), np.uint8)) > 0
    reach[:, TIP:] = False
    for u0, v0, u1, v1 in GLARE:
        reach[v0:v1, u0:u1] = False
    shown &= reach
    drawn = drawn_weapon(cv2.GaussianBlur(sheet, (0, 0), 1.3).mean(axis=2), reach)
    iou = (drawn & shown).sum() / max((drawn | shown).sum(), 1)
    sheet_edge, render_edge = outline(drawn) & reach, outline(shown) & reach
    gaps = np.concatenate([distances(sheet_edge, render_edge), distances(render_edge, sheet_edge)])
    print(f"silhouette IoU {iou:.4f}; outline distance mean {gaps.mean():.2f} px, 95% {np.percentile(gaps, 95):.2f} px")
    soft_render = cv2.GaussianBlur(render, (0, 0), SOFTEN)
    soft_sheet = cv2.GaussianBlur(sheet, (0, 0), SOFTEN)
    error = np.abs(soft_render - soft_sheet).mean(axis=2)
    signed = (soft_render - soft_sheet).mean(axis=2)
    weapon = shown | drawn
    print(f"tone error {error[weapon].mean():.1f} / 255 over {weapon.sum()} px")
    for name, (u0, v0, u1, v1) in REGIONS.items():
        part = np.zeros_like(weapon)
        part[v0:v1, u0:u1] = True
        part &= weapon
        print(f"  {name:8s} {error[part].mean():5.1f}  ({signed[part].mean():+5.1f})")
    if heat_path:
        heat = cv2.applyColorMap((np.clip(error / 80.0, 0.0, 1.0) * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        heat[~weapon] = 255
        cv2.imwrite(heat_path, heat)
    return dict(iou=iou, mean=gaps.mean(), p95=np.percentile(gaps, 95), tone=error[weapon].mean())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("render")
    parser.add_argument("--heat", default=None)
    args = parser.parse_args(argv)
    measure(args.render, args.heat)


if __name__ == "__main__":
    main()
