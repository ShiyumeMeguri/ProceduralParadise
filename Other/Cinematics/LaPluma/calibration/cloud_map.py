"""
Where a shot's reference shows cloud, as a map over the floor of its sky's cloud deck (the clouds' ``map``).

    blender -b --factory-startup -P cloud_map.py -- <frames dir> <shot> <out.json> [<masks dir> ...]
            [--every 3] [--range first,last] [--windows 1] [--block 4] [--cell 20] [--degrees 1] [--above 100]
            [--darkest 55] [--margin 2] [--least 12]

The shot's camera -- built by the film's own builder from its keys and place -- looks at the reference frame by
frame (every ``every`` frames of the shot, or of its ``range``: a title's grey card reads as cloud over the frames it
stands on; ``<frames dir>/f####.png``) in blocks of ``block`` pixels; what of it shows sky is
:mod:`sky_reads`'.  A sky block reads as cloud by how little colour it has: its saturation between the shot's blue
(the 85th percentile of every sky block's) and its cloud (the 10th) gives its share of cloud.  Its ray from the
camera meets the plane ``above`` metres over the floor of the shot's cloud deck (its sky's ``clouds``) at a point of
the map, if within the deck; every cell of the map (``cell`` metres) keeps the mean share of the rays that met it,
over the smallest neighbourhood (up to 16 cells round) that ``least`` rays met -- far off, where the rays thin out,
a cell is read wider -- and cells further from every ray stay empty.  The map covers the box the rays met.

An AI picture's clouds are not still: they swell and drift from second to second (two frames of the title shot 20
apart, as the solved camera sees them, correlate 0.4-0.6 where a still sky is over 0.9, and a small turn of the camera
mends little), and one map of the whole shot averages them into mush.  So the frames are read in ``windows`` stretches
of equal length, each its own map over the same cells -- filled, where its rays did not look, from the map of all the
frames -- kept at the stretch's middle frame (``times``); the cloud material blends the two maps whose times the frame
lies between:

    {"plane": metres up, "cell": metres, "box": [x0, y0, x1, y1], "frames": [first, last, every],
     "times": [frame, ...], "shares": [[[percent or null, ...], ...], ...]}   (a map a time: rows from y0 upwards, columns from x0)

A deck that is a shell (its ``shell``, :mod:`Kit.clouds`) is mapped by direction instead: where a block's ray (made
unit: the camera's rays reach a depth of one across the picture's breadth, and unnormalised a corner's met the sphere
past it and read as straight up) meets the sphere half way through the shell, as an azimuth (degrees from east towards
north) and elevation from its middle, in cells of ``degrees`` -- laid on a plane, the sky of a camera turning where it
stands streaks out wherever its rays run low:

    {"centre": [x, y, z], "radius": metres, "cell": degrees, "box": [azimuth0, elevation0, azimuth1, elevation1], ...}
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
    parser.add_argument("--range", default=None)
    parser.add_argument("--windows", type=int, default=1)
    parser.add_argument("--block", type=int, default=4)
    parser.add_argument("--cell", type=float, default=20.0)
    parser.add_argument("--degrees", type=float, default=1.0)
    parser.add_argument("--above", type=float, default=100.0)
    parser.add_argument("--darkest", type=float, default=55.0)
    parser.add_argument("--margin", type=int, default=2)
    parser.add_argument("--least", type=float, default=12.0)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def _blurred(values, sigma):
    radius = int(np.ceil(sigma * 3.0))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)

    def along(line):
        return np.convolve(line, kernel)[radius:radius + len(line)]
    rows = np.apply_along_axis(along, 1, values)
    return np.apply_along_axis(along, 0, rows)


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
    shell = deck.get("shell")
    plane = middle[2] - reach[2] + args.above
    radius = reach[0] * (shell + 1.0) / 2.0 if shell is not None else None
    cell = args.degrees if shell is not None else args.cell
    first, last = reads.shot["frames"] if args.range is None else [int(value) for value in args.range.split(",")]
    if not reads.shot["frames"][0] <= first <= last <= reads.shot["frames"][1]:
        raise ValueError(f"range {first},{last} is not within the shot's frames {reads.shot['frames']}")
    found = []
    for frame in range(first, last + 1, args.every):
        colour, blocked = reads.read(args.frames, args.masks, frame)
        brightest, dullest = colour.max(axis=2), colour.min(axis=2)
        saturation = (brightest - dullest) / np.maximum(brightest, 1.0)
        origin, rays = reads.rays(frame)
        if shell is not None:
            rays = rays / np.linalg.norm(rays, axis=-1, keepdims=True)
            offset = origin - middle
            along = rays @ offset
            distance = -along + np.sqrt(np.maximum(along * along - (offset @ offset - radius * radius), 0.0))
            points = (origin + rays * distance[..., None] - middle) / radius
            hits = np.stack([np.degrees(np.arctan2(points[..., 1], points[..., 0])), np.degrees(np.arcsin(np.clip(points[..., 2], -1.0, 1.0)))],
                            axis=-1)
            keep = (distance > 0.0) & ~blocked
        else:
            climbing = rays[..., 2] > 0.02
            distance = np.where(climbing, (plane - origin[2]) / np.where(climbing, rays[..., 2], 1.0), 0.0)
            hits = origin[:2] + rays[..., :2] * distance[..., None]
            within = np.all(np.abs(hits - middle[:2]) < reach[:2], axis=-1)
            keep = climbing & within & ~blocked
        keep &= ~reads.hidden_by_set(origin, rays, keep, distance)
        found.append((frame, hits[keep], saturation[keep]))
        print(f"[cloud map] {args.shot} {frame}: {int(keep.sum())} sky blocks of {keep.size}", flush=True)
    every_saturation = np.concatenate([saturation for _, _, saturation in found])
    blue, cloud = np.percentile(every_saturation, 85), np.percentile(every_saturation, 10)
    points = np.concatenate([hits for _, hits, _ in found])
    low = np.floor(points.min(axis=0) / cell) * cell
    high = np.ceil(points.max(axis=0) / cell) * cell
    cells = np.round((high - low) / cell).astype(int)

    def mapped(reads_of):
        total = np.zeros((cells[1], cells[0]))
        count = np.zeros((cells[1], cells[0]))
        for _frame, hits, saturation in reads_of:
            index = np.clip(((hits - low) / cell).astype(int), 0, cells - 1)
            np.add.at(total, (index[:, 1], index[:, 0]), np.clip((blue - saturation) / max(blue - cloud, 1e-6), 0.0, 1.0))
            np.add.at(count, (index[:, 1], index[:, 0]), 1.0)
        return _filled(total, count, args.least), count

    whole, count = mapped(found)
    span = (last - first + 1) / args.windows
    maps, times = [], []
    for window in range(args.windows):
        start, end = first + window * span, first + (window + 1) * span
        own, _ = mapped([read for read in found if start <= read[0] < end])
        maps.append(np.where(np.isnan(own), whole, own))
        times.append(round((start + end - 1.0) / 2.0, 2))
    shares = [[[None if np.isnan(value) else int(round(value * 100.0)) for value in row] for row in mean] for mean in maps]
    placed = {"centre": [float(value) for value in middle], "radius": float(radius)} if shell is not None else {"plane": plane}
    result = {**placed, "cell": cell, "box": [float(low[0]), float(low[1]), float(high[0]), float(high[1])],
              "frames": [first, last, args.every], "blue": round(float(blue), 3), "cloud": round(float(cloud), 3), "times": times,
              "shares": shares}
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, separators=(",", ":")) + "\n")
    print(f"[cloud map] {args.shot}: {cells[0]} x {cells[1]} cells over {result['box']} in {args.windows} stretches {times}, blue "
          f"{blue:.2f} cloud {cloud:.2f}, {int((count > 0).sum())} cells read, mean share {np.nanmean(whole):.2f} -> {args.out}",
          flush=True)


if __name__ == "__main__":
    main()
