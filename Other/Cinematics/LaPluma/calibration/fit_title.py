"""
A title behind her -- a line of display type, its last letters hatched, sliding in and growing as the shot's camera
pushes in -- tracked on the reference frame by frame:

    python fit_title.py <frames dir> <shot> <spec.json> [<masks dir> ...] --blender <blender> [--write]

The spec names the shot's two items of the title (``solid``: its solid letters; ``hatched``: the hatched ones that
follow them, the same size and as far after them as the items stand), the ``frames`` [first, last] it is tracked over,
the frame it is found on first (``anchor``: where its hatched letters stand whole in the picture), the band under it
(``band``: a rectangle item in the same ink, left out of the picture read where the shot draws it), its ink in the
reference (``ink``: [lowest, highest] display value; ``grey``: the most its channels part), the items the fit replaces
(``replaces``) and how it fades (``fade_out``).  What stands in front of it is masked (``roto.py`` folders: an object a
folder, ``m####.png``).

The letters are set as ``Kit.overlays`` sets them (``title_glyphs.py``: Blender's own layout of the design system's
``title`` font) and drawn over the picture at a Size and a Position, turned the items' Angle.  The hatched letters are
read off the picture by their stripes -- where the ink covers about half of a few periods of the hatch round a pixel
(the item's ``Hatch`` period), in a region wide enough to be letters, not the soft edge of solid ink -- and the solid
ones as the ink itself, the band left out: solid ink would let solid letters sink into the band, but stripes are the
title's alone.  On the anchor the hatched letters are found over the whole picture (a grid of places
and sizes, then Nelder-Mead); from there the title is tracked frame by frame both ways, each frame from its neighbour's
(Nelder-Mead), so that the drawn letters cover what is read of them nearby (within ``NEAR`` pixels of where they are
drawn) as nearly as can be: by the hatched letters wherever ``SEEN`` of them is drawn inside the picture and in front, by
the solid ones before the hatched come in.  The frames tracked surely (covering ``SURE`` or more) give the title's path:
a cubic of each of its place and the log of its size over them, keying every frame -- one slide or ease-out was too stiff
(the reference's title keeps moving to the shot's end, ever slower) and a frame tracked alone jitters.  With ``write``
the items are keyed frame by frame with the path (``keys``: Position and Size), shown over the frames, the items the
spec ``replaces`` removed.
"""
import argparse
import json
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
FILM = os.path.join(HERE, "..")
DESIGN = os.path.join(HERE, "..", "..", "Cinematics.json")
SCALE = 0.5
BITMAP = 600.0
GROWN = 7
NEAR = 41
STRIPED = (0.25, 0.75)
SIZES = (0.9, 1.0, 1.1, 1.2)
GRID = 0.04
SURE = 0.5
SEEN = 0.3
BAND_MARGIN = 9


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir")
    parser.add_argument("shot")
    parser.add_argument("spec")
    parser.add_argument("masks", nargs="*")
    parser.add_argument("--blender", required=True)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def _items(shot):
    return {item["name"]: item for item in shot.get("overlays", []) + shot.get("underlays", {}).get("items", [])}


class Glyphs:
    """A line of type at size 1 as a bitmap, ready to be drawn at a size, angle and place."""

    def __init__(self, points, triangles, stretch, align):
        self.stretch, self.align = stretch, align
        self.low, self.high = points.min(axis=0), points.max(axis=0)
        width, height = (self.high - self.low) * BITMAP
        self.bitmap = np.zeros((int(math.ceil(height)) + 4, int(math.ceil(width)) + 4), np.uint8)
        pixels = np.stack([(points[:, 0] - self.low[0]) * BITMAP + 2.0, (self.high[1] - points[:, 1]) * BITMAP + 2.0], axis=1)
        for triangle in triangles:
            cv2.fillConvexPoly(self.bitmap, np.round(pixels[triangle] * 16).astype(np.int32), 255, cv2.LINE_8, shift=4)

    def anchor(self, size):
        """The point of the line (size ``size``, stretched) its Position places, in its own units."""
        low = np.array([self.low[0] * size * self.stretch, self.low[1] * size])
        high = np.array([self.high[0] * size * self.stretch, self.high[1] * size])
        return np.array([low[0] + (high[0] - low[0]) * self.align, (low[1] + high[1]) * 0.5])

    def draw(self, size, angle, position, shape):
        """The line's mask on a picture ``shape`` (rows, columns) at ``SCALE`` of the film's size."""
        rows, columns = shape
        half = rows / 2.0
        turn = math.radians(angle)
        rotation = np.array([[math.cos(turn), -math.sin(turn)], [math.sin(turn), math.cos(turn)]])
        anchor = self.anchor(size)
        to_local = np.array([[size * self.stretch / BITMAP, 0.0, (self.low[0] - 2.0 / BITMAP) * size * self.stretch - anchor[0]],
                             [0.0, -size / BITMAP, (self.high[1] + 2.0 / BITMAP) * size - anchor[1]]])
        placed = rotation @ to_local
        placed[:, 2] += position
        to_picture = np.array([[half, 0.0, columns / 2.0], [0.0, -half, half]])
        matrix = to_picture[:, :2] @ placed
        matrix[:, 2] += to_picture[:, 2]
        return cv2.warpAffine(self.bitmap, matrix, (columns, rows), flags=cv2.INTER_LINEAR) > 127


def _read(frames_dir, frame, masks, film, spec, period, shape, band):
    """What of the reference ``frame`` is the title's: (solid ink, striped region, what stands in front)."""
    picture = cv2.resize(cv2.imread(os.path.join(frames_dir, "f%04d.png" % frame)), (shape[1], shape[0]), interpolation=cv2.INTER_AREA)
    lightness = picture.astype(np.float32) @ np.array([0.0722, 0.7152, 0.2126], np.float32)
    parting = picture.max(axis=2).astype(np.float32) - picture.min(axis=2).astype(np.float32)
    ink = (lightness >= spec["ink"][0]) & (lightness <= spec["ink"][1]) & (parting <= spec["grey"])
    window = int(period * 2.5) | 1
    share = cv2.blur(ink.astype(np.float32), (window, window))
    striped = ((share > STRIPED[0]) & (share < STRIPED[1])).astype(np.uint8)
    wide = int(period * 1.6) | 1
    striped = cv2.morphologyEx(cv2.morphologyEx(striped, cv2.MORPH_OPEN, np.ones((wide, wide), np.uint8)), cv2.MORPH_CLOSE,
                               np.ones((wide, wide), np.uint8)) > 0
    excluded = np.zeros(shape, bool)
    for path in [os.path.join(folder, name, "m%04d.png" % frame) for folder in masks for name in sorted(os.listdir(folder))]:
        if os.path.isfile(path):
            mask = cv2.resize(cv2.imread(path, cv2.IMREAD_GRAYSCALE), (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST) > 127
            excluded |= cv2.dilate(mask.astype(np.uint8), np.ones((GROWN, GROWN), np.uint8)) > 0
    for x0, y0, x1, y1 in film.get("reference", {}).get("masks", []):
        excluded[int(y0 * SCALE):int(y1 * SCALE), int(x0 * SCALE):int(x1 * SCALE)] = True
    first, last = band.get("shown", (frame, frame))
    if first <= frame <= last:
        excluded |= cv2.dilate(_rect_mask(band["inputs"], frame, shape).astype(np.uint8), np.ones((BAND_MARGIN, BAND_MARGIN), np.uint8)) > 0
    solid = ink & ~(cv2.dilate(striped.astype(np.uint8), np.ones((wide, wide), np.uint8)) > 0) & ~excluded
    return solid, striped & ~excluded, excluded


def _offset(inputs, frame):
    """Where an item has moved by ``frame`` from its place: its slide in and drift (``Kit.overlays._inked``)."""
    slide = np.array(inputs.get("Slide In", (0.0, 0.0, 0.0))[:2])
    start, duration = inputs.get("Slide Time", (0.0, 0.0, 0.0))[:2]
    ease = inputs.get("Slide Ease", 2.0)
    drift = np.array(inputs.get("Drift", (0.0, 0.0, 0.0))[:2])
    arriving = min(max((frame - start) / max(duration, 0.001), 0.0), 1.0)
    return slide * (1.0 - arriving) ** ease + drift * max(frame - start, 0.0)


def _rect_mask(inputs, frame, shape):
    """A CIN.Overlay.Rect item's mask on ``frame``."""
    rows, columns = shape
    half = rows / 2.0
    width, height = inputs["Size"][:2]
    centre = np.array(inputs.get("Position", (0.0, 0.0, 0.0))[:2]) + _offset(inputs, frame)
    turn = math.radians(inputs.get("Angle", 0.0))
    rotation = np.array([[math.cos(turn), -math.sin(turn)], [math.sin(turn), math.cos(turn)]])
    corners = np.array([[-width, -height], [width, -height], [width, height], [-width, height]]) * 0.5 @ rotation.T + centre
    pixels = np.stack([columns / 2.0 + corners[:, 0] * half, half - corners[:, 1] * half], axis=1)
    mask = np.zeros(shape, np.uint8)
    cv2.fillPoly(mask, [np.round(pixels * 16).astype(np.int32)], 1, cv2.LINE_8, shift=4)
    return mask > 0


def _near(drawn, read, excluded):
    """How well ``drawn`` covers ``read`` near it: the share of the two the one covers of their union, within ``NEAR``
    pixels of what is drawn, where nothing stands in front."""
    around = (cv2.dilate(drawn.astype(np.uint8), np.ones((NEAR, NEAR), np.uint8)) > 0) & ~excluded
    union = ((drawn | read) & around).sum()
    return (drawn & read & around).sum() / union if union else 0.0


def main():
    args = _arguments()
    spec = json.load(open(args.spec, encoding="utf-8"))
    shot_path = os.path.join(FILM, "shots", f"{args.shot}.json")
    shot = json.load(open(shot_path, encoding="utf-8"))
    items = _items(shot)
    solid, hatched = items[spec["solid"]], items[spec["hatched"]]
    design = json.load(open(DESIGN, encoding="utf-8"))
    font = os.path.join(os.environ["WINDIR"], "Fonts", design["fonts"]["title"])
    glyph_file = os.path.join(tempfile.mkdtemp(prefix="fit_title_"), "glyphs.npz")
    subprocess.run([args.blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "title_glyphs.py"), "--", font,
                    str(solid["inputs"].get("Spacing", 1.0)), glyph_file, solid["inputs"]["Text"], hatched["inputs"]["Text"]],
                   check=True, capture_output=True)
    data = np.load(glyph_file)
    lines = [Glyphs(data[f"{number}_points"], data[f"{number}_triangles"], item["inputs"].get("Stretch", 1.0), item["inputs"].get("Align", 0.5))
             for number, item in enumerate((solid, hatched))]
    angle = solid["inputs"].get("Angle", 0.0)
    size0 = solid["inputs"]["Size"]
    gap = (np.array(hatched["inputs"]["Position"][:2]) - np.array(solid["inputs"]["Position"][:2])) / size0
    film = json.load(open(os.path.join(FILM, "film.json"), encoding="utf-8"))
    width, height = film["resolution"]
    shape = (int(height * SCALE), int(width * SCALE))
    period = hatched["inputs"]["Hatch"][0] * shape[0] / 2.0
    frames = list(range(spec["frames"][0], spec["frames"][1] + 1))
    band = items[spec["band"]]
    seen = {frame: _read(args.frames_dir, frame, args.masks, film, spec, period, shape, band) for frame in frames}

    def drawn(values):
        x, y, log_size = values
        grown = math.exp(log_size)
        return (lines[0].draw(grown, angle, np.array([x, y]), shape),
                lines[1].draw(grown, angle, np.array([x, y]) + gap * grown, shape))

    whole = [lines[1].draw(1.0, angle, np.zeros(2), (shape[0] * 4, shape[1] * 4)).sum() / 16.0]

    def score(frame, values):
        solid_ink, striped, excluded = seen[frame]
        letters, stripes = drawn(values)
        if (stripes & ~excluded).sum() >= SEEN * whole[0] * math.exp(2.0 * values[2]):
            return -_near(stripes, striped, excluded)
        return -_near(letters, solid_ink, excluded)

    anchor = spec["anchor"]
    _solid_ink, striped, excluded = seen[anchor]
    aspect = shape[1] / shape[0]

    def found_hatched(values):
        stripes = lines[1].draw(math.exp(values[2]), angle, np.array(values[:2]), shape) & ~excluded
        return (stripes & striped).sum() / max((stripes | striped).sum(), 1)

    best = max((np.array([x, y, math.log(grown)]) for x in np.arange(-aspect, aspect, GRID) for y in np.arange(-1.0, 1.0, GRID)
                for grown in SIZES), key=found_hatched)
    best = minimize(lambda values: -found_hatched(values), best, method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-4}).x
    start = np.array([best[0] - gap[0] * math.exp(best[2]), best[1] - gap[1] * math.exp(best[2]), best[2]])
    print(f"[title] hatched letters on {anchor}: {np.round(best, 4).tolist()} (covering {found_hatched(best):.3f})", flush=True)
    found = {}
    for order in (frames[frames.index(anchor):], list(reversed(frames[:frames.index(anchor) + 1]))):
        values = start
        for frame in order:
            simplex = np.vstack([values, values + [0.03, 0.0, 0.0], values + [0.0, 0.03, 0.0], values + [0.0, 0.0, 0.05]])
            result = minimize(lambda trial: score(frame, trial), values, method="Nelder-Mead",
                              options={"initial_simplex": simplex, "xatol": 1e-4, "fatol": 1e-4, "maxiter": 300})
            values = result.x
            found[frame] = (values[:2].copy(), math.exp(values[2]), -result.fun)
    sure = [frame for frame in frames if found[frame][2] >= SURE]
    print(f"[title] tracked surely on {sure}", flush=True)
    path = [np.polyfit(np.array(sure, float) - anchor, values, 3)
            for values in (np.array([found[frame][0][0] for frame in sure]), np.array([found[frame][0][1] for frame in sure]),
                           np.log([found[frame][1] for frame in sure]))]
    for frame in frames:
        place = np.array([np.polyval(path[0], frame - anchor), np.polyval(path[1], frame - anchor)])
        log_size = np.polyval(path[2], frame - anchor)
        covered = -score(frame, np.array([*place, log_size]))
        print(f"[title] {frame}: tracked {np.round(found[frame][0], 4).tolist()} {found[frame][1]:.4f} ({found[frame][2]:.3f}), "
              f"path {np.round(place, 4).tolist()} {math.exp(log_size):.4f} ({covered:.3f})", flush=True)
        found[frame] = (place, math.exp(log_size), covered)
    if args.write:
        for item, offset in ((solid, np.zeros(2)), (hatched, gap)):
            for key in ("Slide In", "Slide Time", "Slide Ease", "Drift"):
                item["inputs"].pop(key, None)
            item["shown"] = list(spec["frames"])
            if "fade_out" in spec:
                item["inputs"]["Fade Out"] = [float(spec["fade_out"][0]), float(spec["fade_out"][1]), 0.0]
            item["keys"] = {"Position": [[frame, [round(float(value), 4) for value in found[frame][0] + offset * found[frame][1]] + [0.0]]
                                         for frame in frames],
                            "Size": [[frame, round(float(found[frame][1]), 4)] for frame in frames]}
        replaced = set(spec.get("replaces", []))
        shot["underlays"]["items"] = [item for item in shot["underlays"]["items"] if item["name"] not in replaced]
        shot["overlays"] = [item for item in shot.get("overlays", []) if item["name"] not in replaced]
        note = (f"The title behind her ({spec['solid']}, {spec['hatched']}) is keyed frame by frame as the reference draws it "
                f"(calibration/fit_title.py with {os.path.basename(args.spec)}).")
        shot["notes"] = [text for text in shot.get("notes", []) if not text.startswith("The title behind her")] + [note]
        with open(shot_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(shot, indent=1, ensure_ascii=False) + "\n")
        print(f"[title] written into {shot_path}", flush=True)


if __name__ == "__main__":
    main()
