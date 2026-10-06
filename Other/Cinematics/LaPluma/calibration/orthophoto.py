"""
Orthographic views of measured points (``stereo.py`` output): an
elevation (X right, Z up) coloured by depth (Y) and a plan (X right, Y up)
of the points' density, on a labelled grid.

    python orthophoto.py <points.npy> [<points.npy> ...] --out <prefix>
                         [--x -0.3 2.2] [--y 0.2 0.6] [--z -0.5 1.0] [--density 1200] [--grid 0.05]

Points are ``X, Y, Z, r, g, b`` rows in the set's measuring frame.
"""
import argparse

import cv2
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("points", nargs="+")
parser.add_argument("--out", required=True)
parser.add_argument("--x", type=float, nargs=2, default=(-0.3, 2.2))
parser.add_argument("--y", type=float, nargs=2, default=(0.2, 0.6))
parser.add_argument("--z", type=float, nargs=2, default=(-0.5, 1.0))
parser.add_argument("--density", type=float, default=1200.0)
parser.add_argument("--grid", type=float, default=0.05)
args = parser.parse_args()
data = np.concatenate([np.load(path) for path in args.points])
x, y, z = data[:, 0], data[:, 1], data[:, 2]
inside = (x >= args.x[0]) & (x <= args.x[1]) & (z >= args.z[0]) & (z <= args.z[1]) & (y >= args.y[0]) & (y <= args.y[1])
x, y, z, colors = x[inside], y[inside], z[inside], data[inside, 3:6]


def canvas(span_u, span_v):
    width = int((span_u[1] - span_u[0]) * args.density)
    height = int((span_v[1] - span_v[0]) * args.density)
    return np.full((height, width, 3), 255, np.uint8), width, height


def grid(image, span_u, span_v):
    height, width = image.shape[:2]
    for value in np.arange(np.ceil(span_u[0] / args.grid) * args.grid, span_u[1], args.grid):
        column = int((value - span_u[0]) * args.density)
        major = abs(value / (args.grid * 2) - round(value / (args.grid * 2))) < 1e-6
        cv2.line(image, (column, 0), (column, height), (150, 150, 255) if major else (215, 215, 255), 1)
        if major:
            cv2.putText(image, f"{value:.2f}", (column + 2, 12), cv2.FONT_HERSHEY_PLAIN, 0.9, (0, 0, 200), 1)
    for value in np.arange(np.ceil(span_v[0] / args.grid) * args.grid, span_v[1], args.grid):
        row = int((span_v[1] - value) * args.density)
        major = abs(value / (args.grid * 2) - round(value / (args.grid * 2))) < 1e-6
        cv2.line(image, (0, row), (width, row), (150, 150, 255) if major else (215, 215, 255), 1)
        if major:
            cv2.putText(image, f"{value:.2f}", (2, row - 2), cv2.FONT_HERSHEY_PLAIN, 0.9, (0, 0, 200), 1)


elevation, width, height = canvas(args.x, args.z)
grid(elevation, args.x, args.z)
order = np.argsort(-y)
shade = np.clip((y - args.y[0]) / (args.y[1] - args.y[0]), 0, 1)
palette = cv2.applyColorMap((shade * 255).astype(np.uint8)[:, None], cv2.COLORMAP_TURBO)[:, 0]
columns = ((x - args.x[0]) * args.density).astype(int)
rows = ((args.z[1] - z) * args.density).astype(int)
for k in order:
    cv2.circle(elevation, (columns[k], rows[k]), 1, palette[k].tolist(), -1)
cv2.imwrite(args.out + "_elevation.png", elevation)
plan, width, height = canvas(args.x, args.y)
histogram, _, _ = np.histogram2d(y, x, bins=[height, width], range=[args.y, args.x])
shade = np.log1p(histogram[::-1])
plan[:] = (255 - 255 * shade / max(shade.max(), 1e-6))[..., None].astype(np.uint8)
grid(plan, args.x, args.y)
cv2.imwrite(args.out + "_plan.png", plan)
print(len(x), "points")
