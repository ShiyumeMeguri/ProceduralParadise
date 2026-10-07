"""
Where a shot's reference shows cloud, as a map over the floor of its sky's cloud deck (the clouds' ``map``).

    blender -b --factory-startup -P cloud_map.py -- <frames dir> <shot> <out.json> [<masks dir> ...]
            [--every 3] [--block 4] [--cell 20] [--above 100] [--darkest 55] [--margin 2] [--least 12]

The shot's camera -- built by the film's own builder from its keys and place -- looks at the reference frame by
frame (every ``every`` frames, ``<frames dir>/f####.png``) in blocks of ``block`` pixels; what of it shows sky is
:mod:`sky_reads`'.  A sky block reads as cloud by how little colour it has: its saturation between the shot's blue
(the 85th percentile of every sky block's) and its cloud (the 10th) gives its share of cloud.  Its ray from the
camera meets the plane ``above`` metres over the floor of the shot's cloud deck (its sky's ``clouds``) at a point of
the map, if within the deck; every cell of the map (``cell`` metres) keeps the mean share of the rays that met it,
over the smallest neighbourhood (up to 16 cells round) that ``least`` rays met -- far off, where the rays thin out,
a cell is read wider -- and cells further from every ray stay empty.  The map covers the box the rays met:

    {"plane": metres up, "cell": metres, "box": [x0, y0, x1, y1], "frames": [first, last, every],
     "shares": [[percent or null, ...], ...]}   (rows from y0 upwards, columns from x0)
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sky_reads  # noqa: E402


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("frames")
    parser.add_argument("shot")
    parser.add_argument("out")
    parser.add_argument("masks", nargs="*")
    parser.add_argument("--every", type=int, default=3)
    parser.add_argument("--block", type=int, default=4)
    parser.add_argument("--cell", type=float, default=20.0)
    parser.add_argument("--above", type=float, default=100.0)
    parser.add_argument("--darkest", type=float, default=55.0)
    parser.add_argument("--margin", type=int, default=2)
    parser.add_argument("--least", type=float, default=12.0)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def _blurred(values, sigma):
    radius = int(np.ceil(sigma * 3.0))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    rows = np.apply_along_axis(lambda line: np.convolve(line, kernel, mode="same"), 1, values)
    return np.apply_along_axis(lambda line: np.convolve(line, kernel, mode="same"), 0, rows)


def _filled(total, count, least):
    """Each cell's mean share over the smallest neighbourhood holding ``least`` reads (none within 16 cells: empty)."""
    values = np.full(total.shape, np.nan)
    for sigma in (0.0, 1.0, 2.0, 4.0, 8.0, 16.0):
        summed, weight = (total, count) if sigma == 0.0 else (_blurred(total, sigma), _blurred(count, sigma))
        take = np.isnan(values) & (weight >= least)
        values[take] = summed[take] / weight[take]
    return values


def main():
    args = _arguments()
    reads = sky_reads.ShotSky(args.shot, args.block, args.darkest, args.margin)
    deck = reads.sky["clouds"]
    middle, reach = np.array(deck["loc"], float), np.array(deck["scale"], float)
    plane = middle[2] - reach[2] + args.above
    first, last = reads.shot["frames"]
    found = []
    for frame in range(first, last + 1, args.every):
        colour, blocked = reads.read(args.frames, args.masks, frame)
        brightest, dullest = colour.max(axis=2), colour.min(axis=2)
        saturation = (brightest - dullest) / np.maximum(brightest, 1.0)
        origin, rays = reads.rays(frame)
        climbing = rays[..., 2] > 0.02
        distance = np.where(climbing, (plane - origin[2]) / np.where(climbing, rays[..., 2], 1.0), 0.0)
        hits = origin[:2] + rays[..., :2] * distance[..., None]
        within = np.all(np.abs(hits - middle[:2]) < reach[:2], axis=-1)
        keep = climbing & within & ~blocked
        keep &= ~reads.hidden_by_set(origin, rays, keep, distance)
        found.append((hits[keep], saturation[keep]))
        print(f"[cloud map] {args.shot} {frame}: {int(keep.sum())} sky blocks of {keep.size}", flush=True)
    every_saturation = np.concatenate([saturation for _, saturation in found])
    blue, cloud = np.percentile(every_saturation, 85), np.percentile(every_saturation, 10)
    points = np.concatenate([hits for hits, _ in found])
    shares = np.concatenate([np.clip((blue - saturation) / max(blue - cloud, 1e-6), 0.0, 1.0) for _, saturation in found])
    low = np.floor(points.min(axis=0) / args.cell) * args.cell
    high = np.ceil(points.max(axis=0) / args.cell) * args.cell
    cells = np.round((high - low) / args.cell).astype(int)
    index = np.clip(((points - low) / args.cell).astype(int), 0, cells - 1)
    total = np.zeros((cells[1], cells[0]))
    count = np.zeros((cells[1], cells[0]))
    np.add.at(total, (index[:, 1], index[:, 0]), shares)
    np.add.at(count, (index[:, 1], index[:, 0]), 1.0)
    mean = _filled(total, count, args.least)
    rows = [[None if np.isnan(value) else int(round(value * 100.0)) for value in row] for row in mean]
    result = {"plane": plane, "cell": args.cell, "box": [float(low[0]), float(low[1]), float(high[0]), float(high[1])],
              "frames": [first, last, args.every], "blue": round(float(blue), 3), "cloud": round(float(cloud), 3), "shares": rows}
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, separators=(",", ":")) + "\n")
    print(f"[cloud map] {args.shot}: {cells[0]} x {cells[1]} cells over {result['box']}, blue {blue:.2f} cloud {cloud:.2f}, "
          f"{int((count > 0).sum())} cells read, mean share {np.nanmean(mean):.2f} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
