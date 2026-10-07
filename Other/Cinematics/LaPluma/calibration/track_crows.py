"""
The crows of a shot's reference, found frame by frame and followed through it.

    python track_crows.py <frames dir> <shot.json> <out.json> [<masks dir> ...] [--darkest 90] [--least 120]
           [--longest-gap 1] [--rejoin 6] [--first F] [--last L] [--apart]

A crow is a dark blot against the sky: pixels darker than ``darkest`` (the near crows, blurred by the lens and their
own flight, are dark slate, the sky behind them never so dark), closed over 9 pixels so a wing parted from its body
by a lighter feather stays one crow, away from what the shot's masks hold (the cast and what it holds,
``<masks dir>/<object>/m####.png``, grown by 12 pixels) and the watermark (the film's ``reference.masks``); a blot of
at least ``least`` pixels is one crow (its centre, its area, its box) -- with ``apart``, only one that touches nothing
the masks hold: where the masks miss part of her (a coat the roto took for sky), what hangs on her is not a crow.  Crows are followed from frame to frame: each
followed crow is looked for where its last two frames say it goes, among the blots within 6 % of the picture's width
of that and from half to twice its area, the nearest taken first; a crow not found for more than ``longest-gap``
frames ends.  A crow found again within
``rejoin`` frames of being lost -- where its course said it would be, of a like size -- is the same crow.  Every crow
seen on four frames or more is written (on the shot's frames, or from ``first`` to ``last`` of them: before the crows
take wing the dark of a building is all a blot can be):

    {"shot": id, "frames": [first, last], "crows": [{"frames": [f, ...], "centres": [[x, y], ...],
     "areas": [pixels, ...], "boxes": [[x0, y0, x1, y1], ...]}, ...]}
"""
import argparse
import json
import os

import cv2
import numpy as np


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir")
    parser.add_argument("shot")
    parser.add_argument("out")
    parser.add_argument("masks", nargs="*")
    parser.add_argument("--darkest", type=float, default=90.0)
    parser.add_argument("--least", type=int, default=120)
    parser.add_argument("--longest-gap", type=int, default=1)
    parser.add_argument("--rejoin", type=int, default=6)
    parser.add_argument("--first", type=int, default=None)
    parser.add_argument("--last", type=int, default=None)
    parser.add_argument("--apart", action="store_true")
    return parser.parse_args()


def blots(picture, hidden, darkest, least, apart=False):
    """The dark blots of ``picture`` (BGR) outside ``hidden`` (with ``apart``, not touching it): (centre, area, box) each."""
    luminance = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
    dark = (luminance < darkest) & ~hidden
    dark = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    dark = ((cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0) & ~hidden).astype(np.uint8)
    count, labels, stats, centres = cv2.connectedComponentsWithStats(dark, connectivity=8)
    touching = set(np.unique(labels[cv2.dilate(hidden.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0]).tolist()) if apart else set()
    found = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if area >= least and label not in touching:
            found.append((tuple(float(value) for value in centres[label]), int(area), [int(x), int(y), int(x + width), int(y + height)]))
    return found


def _step(crow):
    """The crow's last move a frame in the picture."""
    if len(crow["frames"]) < 2:
        return np.zeros(2)
    return (np.array(crow["centres"][-1]) - np.array(crow["centres"][-2])) / (crow["frames"][-1] - crow["frames"][-2])


def joined(crows, reach, gap):
    """The crows with every one that was lost and found again (within ``gap`` frames, where its course said, of a like
    size) made one."""
    crows = sorted(crows, key=lambda crow: crow["frames"][0])
    merged = True
    while merged:
        merged = False
        for crow in crows:
            for other in crows:
                lost = other["frames"][0] - crow["frames"][-1]
                if other is crow or not 1 <= lost <= gap:
                    continue
                guess = np.array(crow["centres"][-1]) + _step(crow) * lost
                ratio = other["areas"][0] / crow["areas"][-1]
                if np.linalg.norm(np.array(other["centres"][0]) - guess) < reach * lost and 0.5 <= ratio <= 2.0:
                    for key in ("frames", "centres", "areas", "boxes"):
                        crow[key] += other[key]
                    crows.remove(other)
                    merged = True
                    break
            if merged:
                break
    return crows


def main():
    args = _arguments()
    shot = json.load(open(args.shot, encoding="utf-8"))
    film = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.shot))), "film.json"), encoding="utf-8"))
    first, last = shot["frames"]
    first, last = max(first, args.first or first), min(last, args.last or last)
    width = film["resolution"][0]
    reach = 0.06 * width
    live, done = [], []
    for frame in range(first, last + 1):
        picture = cv2.imread(os.path.join(args.frames_dir, f"f{frame:04d}.png"))
        hidden = np.zeros(picture.shape[:2], bool)
        for x0, y0, x1, y1 in film.get("reference", {}).get("masks", []):
            hidden[y0:y1, x0:x1] = True
        for folder in args.masks:
            for name in sorted(os.listdir(folder)):
                mask = cv2.imread(os.path.join(folder, name, f"m{frame:04d}.png"), cv2.IMREAD_GRAYSCALE)
                if mask is not None:
                    hidden |= cv2.dilate(mask, np.ones((25, 25), np.uint8)) > 127
        found = blots(picture, hidden, args.darkest, args.least, args.apart)
        taken = set()
        pairs = []
        for index, crow in enumerate(live):
            gap = frame - crow["frames"][-1]
            guess = np.array(crow["centres"][-1]) + _step(crow) * gap
            for blot_index, (centre, area, _box) in enumerate(found):
                ratio = area / crow["areas"][-1]
                distance = float(np.linalg.norm(np.array(centre) - guess))
                if distance < reach * gap and 0.5 <= ratio <= 2.0:
                    pairs.append((distance, index, blot_index))
        followed = set()
        for distance, index, blot_index in sorted(pairs):
            if index in followed or blot_index in taken:
                continue
            centre, area, box = found[blot_index]
            crow = live[index]
            crow["frames"].append(frame)
            crow["centres"].append([round(centre[0], 1), round(centre[1], 1)])
            crow["areas"].append(area)
            crow["boxes"].append(box)
            followed.add(index)
            taken.add(blot_index)
        still = []
        for index, crow in enumerate(live):
            if index in followed or frame - crow["frames"][-1] <= args.longest_gap:
                still.append(crow)
            else:
                done.append(crow)
        live = still
        for blot_index, (centre, area, box) in enumerate(found):
            if blot_index not in taken:
                live.append({"frames": [frame], "centres": [[round(centre[0], 1), round(centre[1], 1)]], "areas": [area], "boxes": [box]})
        print(f"[crows] {shot['id']} {frame}: {len(found)} blots, {len(live)} followed", flush=True)
    done = joined(done + live, reach, args.rejoin)
    crows = [crow for crow in done if len(crow["frames"]) >= 4]
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"shot": shot["id"], "frames": [first, last], "crows": crows}, separators=(",", ":")) + "\n")
    print(f"[crows] {shot['id']}: {len(crows)} crows seen on four frames or more -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
