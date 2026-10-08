"""
A shot's overlays tracked on the reference frame by frame -- groups of its overlay items that move as one (a title and its
hatched letters, a card, a rule, the block of her name and rarity), found on every frame where the shot's overlays, drawn
together, cover what the reference shows of them best, and keyed there:

    python fit_overlays.py <frames dir> <shot> <spec.json> [<masks dir> ...] --blender <blender> [--write]
                           [--inspect <folder>] [--placements <file> [--refit <first item> ...]]

The spec lists the ``groups``: each its ``items`` (overlays or underlays of the shot, read off the reference; the first is
the one its size is taken about), the items that only ride along (``riding``: too fine or too faint to be read, keyed with
it), the ``frames`` [first, last] it is keyed over, the ``anchor`` frame it is found on first (where it stands whole in the
picture), whether it is ``sized`` (its size tracked too), which of its outlines' measures are fitted (``shaped``: a
rectangle's Width, Height, Slant, Round, Angle; ``Corners``, a triangle's) on the frames they show together
(``shaped_on``, a list: a card whose either end hides behind her on every frame, not the same end on all; the anchor when
not given) and, for a group with hatched items, the ``hatch`` window [frame, x0, y0, x1, y1] (reference pixels
inside its stripes); and the items the fit ``replaces``.  What stands in front of the underlays is masked (``roto.py``
folders: an object a folder, ``m####.png``).

Every item is drawn as the shot draws it -- a rectangle as the kit draws it (a parallelogram, its corners filleted in the
design system's ``corner_segments``), a triangle by its corners, the rest their assets built in Blender
(``overlay_shapes.py``) -- in its ink (the display value of its Color), its stripes as its Hatch lays them, and all the
groups found on a frame are laid over one another as the shot layers them (underlays behind her, overlays in front, each
list back to front): items of one ink overlap (the title over the card), and a group read alone took the others' ink for
its own.  A pixel of the reference is in an ink when that ink is the nearest of the overlays' and the pixel lies less than
half way from it to the frame's background (the median of what is within ``INK`` of no ink): a soft edge is read where it
is half ink -- read only where nearly pure, the thin rules came out half as thick as they are.

A group's placement on a frame (a move and, sized, a scale about its first item's Position) scores the share of the
overlays' ink the layered drawing explains near the group (within ``NEAR`` of its outline there and of its outline where
it is looked for from): the pixels drawn as an item where the reference is in that item's ink, against all the pixels
drawn there or in one of the group's own inks -- leaving out those the others explain with or without it: the title
spread its letters over the card of their ink, which explains them either way, and grew.  Counted near its outline
alone, a title moving off its own letters was not charged for the ink it left and slid over the card, its letters all
excused there; counted farther off, a yellow rule took the ink of a rule not yet fitted for its own and stood on it; in
every ink, the clouds bright enough to read as the name tag's white sank the score of a yellow rule.  The film's masks
are left out, and what stands in front of the underlays where no overlay is drawn.

On the anchor the group is found over a grid of moves (and sizes) round where the shot has it (its first item's keys
there, an earlier fit's, or where its slides carry it), then refined (Nelder-Mead, kept within the grid); from there it
is tracked both ways frame by frame, each frame looked for round where the motion of the last frames found surely
carries it, as far round as that motion goes in a frame (``TRACK_REACH`` at least: a title sliding in a third of a unit
a frame outran a fixed reach and stuck on a neighbouring letter) -- while that motion is not known yet (fewer than two
frames found surely) as far round as the anchor was (a card sliding in a seventh of a unit a frame outran the first step
and stood still through its entrance), and a frame found less surely looked for again that far round, the better kept.
A frame scoring under ``SURE`` of the median of those tracked before it is lost (carried on from, it would throw the
track off the picture); one found less surely takes its place from the sure ones (straight between them, or carried on
at the speed of the last two).  A sized group keeps one size -- of sizes about the median of those the frames found surely (scoring ``SURE`` of
the group's median frame or more) were found at, the one at which those frames, each moved round where it was found,
explain the most together: a frame blind to the size (letters over a card of their own ink) has no say in it, where the
median took such frames' drift for their size -- and is looked for again with it held on every frame, round where it
was found (tracked anew from the anchor it went the wrong way along its own line of letters).  The stripes' direction
and period are the peak of the hatch window's spectrum; their phase and inked share are read off the same window (its
frame the anchor), its pixels folded onto a period from where the anchor puts the hatched item: the run of the period
darker than half way between its darkest and lightest -- fitted with the placement at the fit's half size, where the
stripes are four pixels a period, they came out solid.  The outlines' measures the spec names are fitted on their frames together, each frame with its own
move from where the group was found there, and the group looked for again with them on every frame.

The groups are fitted in the spec's order, each with the ones before it where they were found -- the big items of an ink
before the small ones -- then each fitted again with all the others where the first round found them, from where it
found it: a title fitted before the card under it took the card's ink for its own letters and grew over it, and the
card, fitted first, takes the title's letters for its own ink until the title is there.  Last each is refined frame by
frame round where it was found, with all the others where they were found (searched afresh the second time, a yellow
rule took its neighbour's ink and thinned itself to nothing).  The placements are kept in the ``placements`` file; given
one already made, the fit is written from it without fitting again -- but for the groups ``refit`` names (by their first
item), fitted again with the others where the file puts them, each from where the file has it (or from the shot's own
inputs, not in the file), and then every group refined.

With ``inspect`` every group is drawn where it was found over the frames it is keyed on (``o####.jpg``, an outline a
group).  With ``write`` the items are keyed frame by frame -- Position (a triangle's corners), sized their Size -- their
slides and drifts dropped (their fades kept: read off the picture, opacities came out unsound), shown over the frames
keyed; the stripes and outlines are set as measured and the items the spec replaces removed -- in the shot as it stands
then (read again: other fits may have written its sky or look meanwhile).
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
BITMAP = 300.0
NEAR = 25
INK = 24
SURE = 0.85
GROWN = 7
ANCHOR_REACH = 0.4
ANCHOR_STEP = 0.02
ANCHOR_SIZES = np.geomspace(0.5, 2.5, 15)
TRACK_REACH = 0.08
TRACK_STEP = 0.01
HELD_SIZES = np.geomspace(0.7, 1.4, 15)
HELD_FINE = np.geomspace(0.96, 1.04, 9)
FOLD_BINS = 48
MOVING = ("Slide In", "Slide Time", "Slide Ease", "Drift", "Slide Out", "Slide Out Time")
OUTLINED = {"CIN.Overlay.Rect": "rect", "CIN.Overlay.Triangle": "triangle"}
MEASURES = {"Width": ("Size", 0, 0.01), "Height": ("Size", 1, 0.005), "Slant": ("Slant", None, 0.02), "Round": ("Round", None, 0.01),
            "Angle": ("Angle", None, 0.2)}
CORNER_STEP = 0.02
LUMINANCE = np.array([0.0722, 0.7152, 0.2126], np.float32)
INSPECT_COLORS = ((0, 0, 255), (255, 128, 0), (0, 200, 0), (255, 0, 255), (0, 255, 255), (255, 255, 0), (128, 0, 255), (0, 128, 255))


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir")
    parser.add_argument("shot")
    parser.add_argument("spec")
    parser.add_argument("masks", nargs="*")
    parser.add_argument("--blender", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--inspect")
    parser.add_argument("--placements")
    parser.add_argument("--refit", nargs="*", default=[])
    return parser.parse_args()


def _display(color):
    """The display value (0-255, blue green red) of a linear colour."""
    linear = np.clip(np.array(color[:3], np.float64), 0.0, 1.0)
    encoded = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1.0 / 2.4) - 0.055)
    return (encoded * 255.0)[::-1].astype(np.float32)


def _offset(inputs, frame):
    """Where an item has moved by ``frame`` from its place (``Kit.overlays._inked``)."""
    slide = np.array(inputs.get("Slide In", (0.0, 0.0, 0.0))[:2])
    start, duration = inputs.get("Slide Time", (0.0, 0.0, 0.0))[:2]
    ease = inputs.get("Slide Ease", 2.0)
    drift = np.array(inputs.get("Drift", (0.0, 0.0, 0.0))[:2])
    leaving_start, leaving_duration = inputs.get("Slide Out Time", (100000.0, 0.0, 0.0))[:2]
    arriving = min(max((frame - start) / max(duration, 0.001), 0.0), 1.0)
    leaving = min(max((frame - leaving_start) / max(leaving_duration, 0.001), 0.0), 1.0) ** ease
    return (slide * (1.0 - arriving) ** ease + drift * max(frame - start, 0.0)
            + np.array(inputs.get("Slide Out", (0.0, 0.0, 0.0))[:2]) * leaving)


def _outline(inputs, kind, segments):
    """A rectangle's or triangle's outline as the kit draws it, in picture units at its place: a rectangle a parallelogram
    its top edge ``Slant`` to the right of its foot, its corners filleted to ``Round`` in ``segments`` pieces, turned
    ``Angle`` about ``Position`` (``Kit.overlays.rect``)."""
    if kind == "triangle":
        return np.array([inputs[corner][:2] for corner in ("A", "B", "C")], np.float64)
    width, height = inputs["Size"][:2]
    slant = inputs.get("Slant", 0.0)
    corners = np.array([[width / 2 + slant / 2, height / 2], [-width / 2 + slant / 2, height / 2],
                        [-width / 2 - slant / 2, -height / 2], [width / 2 - slant / 2, -height / 2]])
    radius = max(inputs.get("Round", 0.0), 0.0)
    points = []
    for index, corner in enumerate(corners):
        before, after = corners[index - 1], corners[(index + 1) % 4]
        toward_before = (before - corner) / np.linalg.norm(before - corner)
        toward_after = (after - corner) / np.linalg.norm(after - corner)
        opening = math.acos(float(np.clip(toward_before @ toward_after, -1.0, 1.0)))
        reach = min(radius / math.tan(opening / 2.0), np.linalg.norm(before - corner) / 2.0, np.linalg.norm(after - corner) / 2.0)
        if reach <= 0.0:
            points.append(corner)
            continue
        fitted = reach * math.tan(opening / 2.0)
        bisector = (toward_before + toward_after) / np.linalg.norm(toward_before + toward_after)
        middle = corner + bisector * (fitted / math.sin(opening / 2.0))
        first = math.atan2(*(corner + toward_before * reach - middle)[::-1])
        last = math.atan2(*(corner + toward_after * reach - middle)[::-1])
        sweep = (last - first + math.pi) % (2.0 * math.pi) - math.pi
        points.extend(middle + fitted * np.array([math.cos(first + sweep * step / segments), math.sin(first + sweep * step / segments)])
                      for step in range(segments + 1))
    turn = math.radians(inputs.get("Angle", 0.0))
    rotation = np.array([[math.cos(turn), -math.sin(turn)], [math.sin(turn), math.cos(turn)]])
    return np.array(points) @ rotation.T + np.array(inputs.get("Position", (0.0, 0.0, 0.0))[:2])


class Shape:
    """An item's triangles (picture units, at its place) as a bitmap, drawn moved and scaled about a point."""

    def __init__(self, points, triangles):
        self.low, self.high = points.min(axis=0), points.max(axis=0)
        width, height = (self.high - self.low) * BITMAP
        self.bitmap = np.zeros((int(math.ceil(height)) + 4, int(math.ceil(width)) + 4), np.uint8)
        pixels = np.stack([(points[:, 0] - self.low[0]) * BITMAP + 2.0, (self.high[1] - points[:, 1]) * BITMAP + 2.0], axis=1)
        for triangle in triangles:
            cv2.fillConvexPoly(self.bitmap, np.round(pixels[triangle] * 16).astype(np.int32), 255, cv2.LINE_8, shift=4)

    def bounds(self, move, scale, about, half, columns):
        """The pixel box (x0, y0, x1, y1) it covers drawn so."""
        placed = about + scale * (np.array([self.low, self.high]) - about) + move
        xs = columns / 2.0 + placed[:, 0] * half
        ys = half - placed[:, 1] * half
        return xs.min(), ys.min(), xs.max(), ys.max()

    def draw(self, move, scale, about, half, columns, window):
        """Its mask over ``window`` (x0, y0, x1, y1 pixels of a picture ``half`` pixels a unit, ``columns`` wide)."""
        x0, y0, x1, y1 = window
        unit = half * scale / BITMAP
        shift_x = columns / 2.0 + half * (about[0] * (1.0 - scale) + move[0]) + half * scale * self.low[0] - 2.0 * unit
        shift_y = half - half * (about[1] * (1.0 - scale) + move[1]) - half * scale * self.high[1] - 2.0 * unit
        matrix = np.array([[unit, 0.0, shift_x - x0], [0.0, unit, shift_y - y0]])
        return cv2.warpAffine(self.bitmap, matrix, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR) > 127


class Part:
    """An item of a group: its shape, ink, stripes, and its number among all the parts drawn."""

    def __init__(self, item, shape, segments):
        self.item, self.segments = item, segments
        self.kind = OUTLINED.get(item["asset"])
        self.shape = shape
        self.reshape()
        inputs = item["inputs"]
        self.ink = _display(inputs.get("Color", (1.0, 1.0, 1.0, 1.0))) * float(inputs.get("Glow", 1.0))
        self.position = np.array(inputs.get("Position", (0.0, 0.0, 0.0))[:2], np.float64)
        hatch = inputs.get("Hatch", (0.0, 0.0, 0.5))
        self.hatch = [float(value) for value in hatch[:3]] if hatch[0] > 0.0 else None
        self.phase = float(inputs.get("Hatch Phase", 0.0))
        self.number = -1

    def reshape(self):
        """Its shape drawn again from its inputs (a rectangle or triangle)."""
        if self.kind is not None:
            outline = _outline(self.item["inputs"], self.kind, self.segments)
            fan = np.array([[0, index, index + 1] for index in range(1, len(outline) - 1)], np.int32)
            self.shape = Shape(outline, fan)

    def stripes(self, origin, grid):
        """Where its stripes ink, laid from ``origin`` (its Position as drawn) over the picture units ``grid``."""
        period, angle, share = self.hatch
        turn = math.radians(angle)
        along = ((grid[0] - origin[0]) * math.cos(turn) + (grid[1] - origin[1]) * math.sin(turn)) / period + self.phase
        return np.mod(along, 1.0) < share


class Group:
    """Items moving as one, read off the reference and keyed together; ``layer`` where they stand among the shot's
    overlays (back to front), ``front`` whether they are drawn in front of her."""

    def __init__(self, spec, parts, riding, front, layer):
        self.spec, self.parts, self.riding, self.front, self.layer = spec, parts, riding, front, layer
        self.frames = list(range(spec["frames"][0], spec["frames"][1] + 1))
        self.about = parts[0].position.copy()
        self.found = {}

    def placement(self, frame):
        move, scale, _score = self.found[frame]
        return move, scale


class Reading:
    """The reference as the fit reads it: frames at ``SCALE``, what stands in front, which overlay inks each pixel is in."""

    def __init__(self, frames_dir, masks, film, frames, parts):
        width, height = film["resolution"]
        self.rows, self.columns = int(height * SCALE), int(width * SCALE)
        self.half = self.rows / 2.0
        ys, xs = np.mgrid[0:self.rows, 0:self.columns].astype(np.float64)
        self.grid = ((xs + 0.5 - self.columns / 2.0) / self.half, (self.half - ys - 0.5) / self.half)
        inks = []
        for part in parts:
            known = [index for index, ink in enumerate(inks) if np.abs(ink - part.ink).max() < 0.5]
            if not known:
                inks.append(part.ink)
            part.colour = known[0] if known else len(inks) - 1
        self.colour_of = np.array([part.colour for part in parts], np.uint8)
        self.in_front = np.array([False] * len(parts))
        self.pictures, self.behind, self.masked, self.bits = {}, {}, {}, {}
        for frame in frames:
            picture = cv2.imread(os.path.join(frames_dir, "f%04d.png" % frame))
            picture = cv2.resize(picture, (self.columns, self.rows), interpolation=cv2.INTER_AREA).astype(np.float32)
            self.pictures[frame] = picture
            distances = np.stack([np.abs(picture - ink).max(axis=2) for ink in inks])
            nearest = distances.argmin(axis=0)
            background = np.median(picture[distances.min(axis=0) >= INK], axis=0)
            halfway = np.array([np.abs(background - ink).max() / 2.0 for ink in inks], np.float32)
            inked = np.take_along_axis(distances, nearest[None], axis=0)[0] < halfway[nearest]
            self.bits[frame] = np.where(inked, np.left_shift(1, nearest), 0).astype(np.uint8)
            masked = np.zeros((self.rows, self.columns), bool)
            for x0, y0, x1, y1 in film.get("reference", {}).get("masks", ()):
                masked[int(y0 * SCALE):int(y1 * SCALE), int(x0 * SCALE):int(x1 * SCALE)] = True
            behind = np.zeros_like(masked)
            for path in [os.path.join(folder, name, "m%04d.png" % frame) for folder in masks for name in sorted(os.listdir(folder))]:
                if os.path.isfile(path):
                    mask = cv2.resize(cv2.imread(path, cv2.IMREAD_GRAYSCALE), (self.columns, self.rows), interpolation=cv2.INTER_NEAREST) > 127
                    behind |= cv2.dilate(mask.astype(np.uint8), np.ones((GROWN, GROWN), np.uint8)) > 0
            self.masked[frame], self.behind[frame] = masked, behind

    def window(self, box, margin):
        x0, y0, x1, y1 = box
        return (int(max(math.floor(x0 - margin), 0)), int(max(math.floor(y0 - margin), 0)),
                int(min(math.ceil(x1 + margin), self.columns)), int(min(math.ceil(y1 + margin), self.rows)))


def _labelled(group, reading, move, scale, window, striped=True):
    """The group drawn over ``window``: the number of the part shown at each pixel (-1 none)."""
    return _drawn(group, reading, move, scale, window, striped)[0]


def _drawn(group, reading, move, scale, window, striped=True):
    """The group drawn over ``window``: (the number of the part shown at each pixel, -1 none; its outline)."""
    x0, y0, x1, y1 = window
    grid = (reading.grid[0][y0:y1, x0:x1], reading.grid[1][y0:y1, x0:x1])
    labels = np.full((y1 - y0, x1 - x0), -1, np.int16)
    outline = np.zeros((y1 - y0, x1 - x0), bool)
    for part in group.parts:
        mask = part.shape.draw(move, scale, group.about, reading.half, reading.columns, window)
        outline |= mask
        if striped and part.hatch is not None:
            mask &= part.stripes(group.about + scale * (part.position - group.about) + move, grid)
        labels[mask] = part.number
    return labels, outline


def _context(group, groups, reading, frame, window, placed):
    """The rest of the overlays over ``window`` on ``frame`` where they were found, as the reference reads there:
    (drawn in front of ``group``, drawn behind it, the overlay inks each pixel is in, the film's masks kept out, her,
    where they explain the reference without ``group``, within ``NEAR`` of ``group`` where it is looked for from:
    ``placed``, a move and a scale)."""
    x0, y0, x1, y1 = window
    front = np.full((y1 - y0, x1 - x0), -1, np.int16)
    back = front.copy()
    for other in sorted(groups, key=lambda candidate: candidate.layer):
        if other is group or frame not in other.found:
            continue
        labels = _labelled(other, reading, *other.placement(frame), window)
        target = front if other.layer > group.layer else back
        target[labels >= 0] = labels[labels >= 0]
    bits = reading.bits[frame][y0:y1, x0:x1]
    alone = np.where(front >= 0, front, back)
    explained = (alone >= 0) & (((bits >> reading.colour_of[np.maximum(alone, 0)]) & 1) > 0)
    return (front, back, bits, ~reading.masked[frame][y0:y1, x0:x1], reading.behind[frame][y0:y1, x0:x1], explained,
            _near(_drawn(group, reading, *placed, window, striped=False)[1]))


def _near(outline):
    """Within ``NEAR`` of an outline."""
    return cv2.dilate(outline.astype(np.uint8), np.ones((2 * NEAR + 1, 2 * NEAR + 1), np.uint8)) > 0


def _layered(labels, context):
    """The group's ``labels`` laid between the rest of the overlays."""
    front, back = context[0], context[1]
    return np.where(front >= 0, front, np.where(labels >= 0, labels, back))


def _explained(group, reading, move, scale, window, context, striped=True):
    """The share of the overlays' ink the layered drawing, the group drawn so, explains near the group and near where it
    is looked for from -- the pixels the rest explain with or without it left out."""
    _front, _back, bits, unmasked, behind, alone, around = context
    labels, outline = _drawn(group, reading, move, scale, window, striped)
    shown_as = _layered(labels, context)
    shown = shown_as >= 0
    numbers = np.where(shown, shown_as, 0)
    near = _near(outline) | around
    matched = shown & (((bits >> reading.colour_of[numbers]) & 1) > 0)
    own = np.bitwise_or.reduce([1 << int(part.colour) for part in group.parts])
    counted = (near & unmasked & (~behind | (shown & reading.in_front[numbers])) & ~(matched & alone)
               & (shown | ((bits & own) > 0)))
    union = counted.sum()
    return float((matched & counted).sum() / union) if union else 0.0


def _box(group, reading, move, scale):
    boxes = np.array([part.shape.bounds(move, scale, group.about, reading.half, reading.columns) for part in group.parts])
    return boxes[:, 0].min(), boxes[:, 1].min(), boxes[:, 2].max(), boxes[:, 3].max()


def _search(group, groups, reading, frame, start, scale, reach, step, sizes, striped=True):
    """The best placement round ``start``: a grid of moves ``reach`` about it ``step`` apart (at each of ``sizes`` times
    ``scale`` when given), then Nelder-Mead (the size free when ``sizes`` are given), kept within the grid."""
    scales = [scale] if sizes is None else [scale * value for value in sizes]
    window = reading.window(_box(group, reading, start, max(scales)), reach * reading.half + NEAR + 2)
    if window[2] - window[0] < 4 or window[3] - window[1] < 4:
        return np.array(start, float), scale, 0.0
    context = _context(group, groups, reading, frame, window, (start, scale))
    offsets = np.arange(-reach, reach + step * 0.5, step)
    best = max(((_explained(group, reading, start + np.array([dx, dy]), trial, window, context, striped), dx, dy, trial)
                for trial in scales for dx in offsets for dy in offsets), key=lambda candidate: candidate[0])
    begin = np.array([start[0] + best[1], start[1] + best[2], math.log(best[3])])
    free = sizes is not None
    count = 3 if free else 2
    simplex = [begin[:count]] + [begin[:count] + np.eye(count)[index] * (0.03 if index == 2 else step) for index in range(count)]
    result = minimize(lambda values: -_explained(group, reading, values[:2], math.exp(values[2]) if free else scale, window, context,
                                                 striped),
                      begin[:count], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-5, "maxiter": 300, "initial_simplex": simplex})
    if np.abs(result.x[:2] - start).max() > reach + step or -result.fun < best[0]:
        return begin[:2], best[3], best[0]
    return result.x[:2], math.exp(result.x[2]) if free else scale, -result.fun


def _tracked(group, groups, reading, anchor_move, anchor_scale, free):
    """The group tracked both ways from the anchor: {frame: (move, scale, score)}."""
    anchor = group.spec["anchor"]
    found = {}
    sizes = np.array([1.0]) if free else None
    for order in (group.frames[group.frames.index(anchor):], list(reversed(group.frames[:group.frames.index(anchor) + 1]))):
        sure, scores = [], []
        for frame in order:
            reach = TRACK_REACH
            if len(sure) >= 2:
                (before, early, _), (last, late, scale) = sure[-2], sure[-1]
                speed = (late - early) / (last - before)
                start = late + speed * (frame - last)
                reach = max(TRACK_REACH, float(np.abs(speed).max()))
            elif sure:
                start, scale = sure[-1][1], sure[-1][2]
                reach = ANCHOR_REACH
            else:
                start, scale = anchor_move, anchor_scale
            move, found_scale, score = _search(group, groups, reading, frame, start, scale, reach, reach * TRACK_STEP / TRACK_REACH, sizes)
            if score < SURE * float(np.median(scores + [score])) and reach < ANCHOR_REACH:
                wider = _search(group, groups, reading, frame, start, scale, ANCHOR_REACH, ANCHOR_REACH * TRACK_STEP / TRACK_REACH, sizes)
                if wider[2] > score:
                    move, found_scale, score = wider
            found[frame] = (move, found_scale, score)
            scores.append(score)
            if score >= SURE * float(np.median(scores)):
                sure.append((frame, move, found_scale))
            print(f"[overlays] {group.spec['items'][0]} {frame}: {np.round(move, 4).tolist()} x{found_scale:.4f} ({score:.3f})", flush=True)
    return found


def _sure(group, found):
    """The frames found surely: scoring ``SURE`` of the group's median frame or more."""
    typical = float(np.median([found[frame][2] for frame in group.frames]))
    return [frame for frame in group.frames if found[frame][2] >= SURE * typical]


def _settled(group, found):
    """Frames found less surely placed from the sure ones: straight between them, carried on at the ends."""
    sure = _sure(group, found)
    if len(sure) < 2:
        raise RuntimeError(f"{group.spec['items'][0]}: fewer than two frames found surely")
    settled = {}
    for frame in group.frames:
        if frame in sure:
            settled[frame] = found[frame]
            continue
        before = [value for value in sure if value < frame]
        after = [value for value in sure if value > frame]
        if before and after:
            low, high = before[-1], after[0]
        elif after:
            low, high = after[0], after[1]
        else:
            low, high = before[-2], before[-1]
        share = (frame - low) / (high - low)
        placed = found[low][0] + (found[high][0] - found[low][0]) * share
        settled[frame] = (placed, found[low][1] + (found[high][1] - found[low][1]) * share, found[frame][2])
    return settled


def _measured_hatch(frames_dir, window):
    """The stripes' (normal direction in degrees, period in picture units) off a reference window: its spectrum's peak."""
    frame, x0, y0, x1, y1 = window
    picture = cv2.imread(os.path.join(frames_dir, "f%04d.png" % frame)).astype(np.float32)
    lightness = picture[y0:y1, x0:x1] @ LUMINANCE
    signal = (lightness - lightness.mean()) * np.outer(np.hanning(y1 - y0), np.hanning(x1 - x0))
    side = 2048
    padded = np.zeros((side, side), np.float32)
    padded[:y1 - y0, :x1 - x0] = signal
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(padded)))
    middle = side // 2
    spectrum[middle - 8:middle + 9, middle - 8:middle + 9] = 0.0
    row, column = np.unravel_index(np.argmax(spectrum), spectrum.shape)
    fy, fx = (row - middle) / side, (column - middle) / side
    return math.degrees(math.atan2(-fy, fx)) % 180.0, 1.0 / math.hypot(fx, fy) / (picture.shape[0] / 2.0)


def _hatch_phase(frames_dir, window, angle, period, origin):
    """The phase and inked share of stripes (normal ``angle`` degrees, ``period`` picture units) laid from ``origin``
    (picture units) over a reference window [frame, x0, y0, x1, y1]: its pixels folded onto a period, the longest run
    of the period darker than half way between its darkest and lightest (``Kit.overlays``: inked where the fraction of
    the distance along the normal over the period, plus the phase, is under the share)."""
    frame, x0, y0, x1, y1 = window
    picture = cv2.imread(os.path.join(frames_dir, "f%04d.png" % frame)).astype(np.float32)
    half = picture.shape[0] / 2.0
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float64)
    across = (xs + 0.5 - picture.shape[1] / 2.0) / half - origin[0]
    up = (half - ys - 0.5) / half - origin[1]
    turn = math.radians(angle)
    folded = np.mod((across * math.cos(turn) + up * math.sin(turn)) / period, 1.0)
    index = np.minimum((folded * FOLD_BINS).astype(int), FOLD_BINS - 1).ravel()
    lightness = (picture[y0:y1, x0:x1] @ LUMINANCE).ravel()
    profile = np.bincount(index, lightness, FOLD_BINS) / np.maximum(np.bincount(index, minlength=FOLD_BINS), 1)
    ink = profile < (profile.min() + profile.max()) / 2.0
    runs = []
    for first in (step for step in range(FOLD_BINS) if ink[step] and not ink[step - 1]):
        length = 0
        while ink[(first + length) % FOLD_BINS] and length < FOLD_BINS:
            length += 1
        runs.append((length, first))
    length, first = max(runs)
    return (-first / FOLD_BINS) % 1.0, length / FOLD_BINS


def _start(group, frame):
    """Where the shot has the group on ``frame``: (move, scale) of its first item's keys nearest it when an earlier fit keyed
    it (its slides dropped then), else where its slides carry it."""
    part = group.parts[0]
    inputs, keys = part.item["inputs"], part.item.get("keys", {})
    point = "A" if part.kind == "triangle" else "Position"
    if point not in keys:
        return _offset(inputs, frame), 1.0

    def keyed(name):
        return min(keys[name], key=lambda key: abs(key[0] - frame))[1]
    move = np.array(keyed(point)[:2], float) - np.array(inputs.get(point, (0.0, 0.0, 0.0))[:2], float)
    if "Size" not in keys:
        return move, 1.0
    size, base = keyed("Size"), inputs["Size"]
    return move, (size[0] if isinstance(size, list) else size) / (base[0] if isinstance(base, list) else base)


def _anchored(group, groups, reading, frames_dir, start):
    """The group found on its anchor round ``start`` (move, scale; where the shot has it when None), its stripes fitted
    there: (move, scale)."""
    anchor = group.spec["anchor"]
    begin, size = _start(group, anchor) if start is None else start
    sizes = ANCHOR_SIZES if group.spec.get("sized") else None
    hatched = [part for part in group.parts if part.hatch is not None]
    move, scale, score = _search(group, groups, reading, anchor, np.array(begin, float), size, ANCHOR_REACH, ANCHOR_STEP, sizes,
                                 striped=not hatched)
    print(f"[overlays] {group.spec['items'][0]} anchor {anchor}: {np.round(move, 4).tolist()} x{scale:.4f} ({score:.3f})", flush=True)
    if not hatched:
        return move, scale
    if group.spec["hatch"][0] != anchor:
        raise ValueError(f"{group.spec['items'][0]}: its hatch window must be on its anchor ({anchor})")
    angle, period = _measured_hatch(frames_dir, group.spec["hatch"])
    for part in hatched:
        origin = group.about + scale * (part.position - group.about) + move
        part.phase, share = _hatch_phase(frames_dir, group.spec["hatch"], angle, period, origin)
        part.hatch = [period, angle, share]
    print(f"[overlays] {group.spec['items'][0]}: stripes {angle:.2f} deg, period {period:.5f}, phase {hatched[0].phase:.3f}, "
          f"share {hatched[0].hatch[2]:.3f}", flush=True)
    return move, scale


def _shaped(group, groups, reading, frames, found):
    """The group's outlines fitted on ``frames`` together (the measures its spec names under ``shaped``), each frame with
    its move from where the group was ``found`` there -- a triangle's corners with the moves held."""
    named = group.spec.get("shaped", [])
    parts = [part for part in group.parts if part.kind is not None]
    if not named or not parts:
        return
    placed = [found[frame][:2] for frame in frames]
    windows = [reading.window(_box(group, reading, move, scale), TRACK_REACH * reading.half + NEAR + 2) for move, scale in placed]
    contexts = [_context(group, groups, reading, frame, window, start) for frame, window, start in zip(frames, windows, placed)]
    original = [json.loads(json.dumps(part.item["inputs"])) for part in parts]
    moving = all(part.kind == "rect" for part in parts)
    lead = 2 * len(frames) if moving else 0
    steps = [TRACK_STEP] * lead + [step for part in parts for step in
                                   ([CORNER_STEP] * 6 if part.kind == "triangle" else [MEASURES[name][2] for name in named])]

    def applied(values):
        offset = lead
        for part, inputs in zip(parts, original):
            fresh = json.loads(json.dumps(inputs))
            if part.kind == "triangle":
                for index, corner in enumerate(("A", "B", "C")):
                    fresh[corner] = [inputs[corner][0] + values[offset + 2 * index], inputs[corner][1] + values[offset + 2 * index + 1], 0.0]
                offset += 6
            else:
                for name in named:
                    key, component, _step = MEASURES[name]
                    if component is None:
                        fresh[key] = inputs.get(key, 0.0) + values[offset]
                    else:
                        fresh[key][component] = abs(inputs[key][component] + values[offset])
                    offset += 1
                fresh["Round"] = abs(fresh.get("Round", 0.0))
            part.item["inputs"] = fresh
            part.reshape()
        if moving:
            return [np.array(values[2 * index:2 * index + 2]) for index in range(len(frames))]
        return [move for move, _scale in placed]

    def explained(values):
        return float(np.mean([_explained(group, reading, move, scale, window, context)
                              for move, (_move, scale), window, context in zip(applied(values), placed, windows, contexts)]))

    start = np.zeros(len(steps))
    if moving:
        start[:lead] = np.concatenate([move for move, _scale in placed])
    simplex = [start] + [start + np.eye(len(steps))[index] * step for index, step in enumerate(steps)]
    result = minimize(lambda values: -explained(values), start, method="Nelder-Mead",
                      options={"xatol": 1e-5, "fatol": 1e-6, "maxiter": 400 * len(steps), "initial_simplex": simplex})
    applied(result.x)
    measures = {part.item["name"]: {key: part.item["inputs"].get(key) for key in ("Size", "Slant", "Round", "Angle", "A", "B", "C")
                                    if key in part.item["inputs"]} for part in parts}
    print(f"[overlays] {group.spec['items'][0]} outlines on {frames}: {measures} ({-result.fun:.3f})", flush=True)


def _again(group, groups, reading, found, scale):
    """The group looked for again on every frame round where it was ``found``, at ``scale`` (that frame's own when None)."""
    again = {}
    for frame in group.frames:
        move, own, _score = found[frame]
        again[frame] = _search(group, groups, reading, frame, move, own if scale is None else scale, TRACK_REACH, TRACK_STEP, None)
        print(f"[overlays] {group.spec['items'][0]} {frame} again: {np.round(again[frame][0], 4).tolist()} ({again[frame][2]:.3f})",
              flush=True)
    return again


def _refined(group, groups, reading):
    """The group refined on every frame round where it was found, with the others where they were found."""
    return _settled(group, _again(group, groups, reading, group.found, None))


def _held(group, groups, reading, found):
    """The one size a sized group keeps: of sizes about the median of those its sure frames were found at, the one at
    which those frames, each moved round where it was found, explain the most together."""
    sure = _sure(group, found)
    typical = float(np.median([found[frame][1] for frame in sure]))
    views = {}
    for frame in sure:
        window = reading.window(_box(group, reading, found[frame][0], typical * HELD_SIZES.max()), TRACK_REACH * reading.half + NEAR + 2)
        views[frame] = (window, _context(group, groups, reading, frame, window, found[frame][:2]))

    def explained(size):
        total = 0.0
        for frame in sure:
            window, context = views[frame]
            move = np.array(found[frame][0], float)
            simplex = [move, move + np.array([TRACK_STEP, 0.0]), move + np.array([0.0, TRACK_STEP])]
            result = minimize(lambda values: -_explained(group, reading, values, size, window, context), move, method="Nelder-Mead",
                              options={"xatol": 1e-4, "fatol": 1e-5, "maxiter": 100, "initial_simplex": simplex})
            total += -result.fun
        return total / len(sure)

    coarse = typical * HELD_SIZES
    best = float(coarse[int(np.argmax([explained(size) for size in coarse]))])
    fine = best * HELD_FINE
    scores = [explained(size) for size in fine]
    held = float(fine[int(np.argmax(scores))])
    print(f"[overlays] {group.spec['items'][0]}: size held at {held:.4f} ({max(scores):.3f} over {len(sure)} sure frames; "
          f"their median {typical:.4f})", flush=True)
    return held


def _fitted(group, groups, reading, frames_dir, start=None):
    """The group fitted with the others where they were found, found first on its anchor round ``start`` (move, scale;
    where the shot has it when None): {frame: (move, scale, score)} over its frames."""
    move, scale = _anchored(group, groups, reading, frames_dir, start)
    found = _tracked(group, groups, reading, move, scale, group.spec.get("sized", False))
    anchor = group.spec["anchor"]
    if group.spec.get("sized"):
        found = _again(group, groups, reading, _settled(group, found), _held(group, groups, reading, found))
    if group.spec.get("shaped"):
        _shaped(group, groups, reading, group.spec.get("shaped_on", [anchor]), _settled(group, found))
        found = _again(group, groups, reading, _settled(group, found), None)
    return _settled(group, found)


def _keys(group):
    """The keys of every item of the group: {name: {input: [[frame, value], ...]}}."""
    keys = {}
    for part in group.parts + group.riding:
        inputs = part.item["inputs"]
        track = {}
        for frame in group.frames:
            move, scale = group.placement(frame)

            def placed(point):
                return [round(float(value), 4) for value in group.about + scale * (np.array(point[:2]) - group.about) + move] + [0.0]
            if part.item["asset"] == "CIN.Overlay.Triangle":
                for corner in ("A", "B", "C"):
                    track.setdefault(corner, []).append([frame, placed(inputs[corner])])
            else:
                track.setdefault("Position", []).append([frame, placed(inputs.get("Position", (0.0, 0.0, 0.0)))])
            if group.spec.get("sized"):
                size = inputs["Size"]
                value = [round(float(component) * scale, 4) for component in size] if isinstance(size, list) else round(size * scale, 4)
                track.setdefault("Size", []).append([frame, value])
        keys[part.item["name"]] = track
    return keys


def _inspected(groups, reading, folder):
    """Every group drawn where it was found over the frames it is keyed on, into ``folder``."""
    os.makedirs(folder, exist_ok=True)
    whole = (0, 0, reading.columns, reading.rows)
    for frame in sorted({frame for group in groups for frame in group.frames}):
        picture = reading.pictures[frame].astype(np.uint8)
        for number, group in enumerate(groups):
            if frame not in group.found:
                continue
            move, scale = group.placement(frame)
            outline = _labelled(group, reading, move, scale, whole, striped=False) >= 0
            edge = outline & ~(cv2.erode(outline.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            color = INSPECT_COLORS[number % len(INSPECT_COLORS)]
            picture[edge] = color
            ys, xs = np.nonzero(outline)
            if len(xs):
                spot = (int(min(xs.min(), reading.columns - 160)), int(max(ys.min() - 4, 12)))
                cv2.putText(picture, f"{group.spec['items'][0]} {group.found[frame][2]:.2f}", spot, cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        cv2.putText(picture, str(frame), (8, reading.rows - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imwrite(os.path.join(folder, "o%04d.jpg" % frame), picture)


def _kept(groups, path):
    """The groups' placements, outlines and stripes kept in the file ``path``."""
    kept = {group.spec["items"][0]: {
        "found": {str(frame): [[float(value) for value in move], float(scale), float(score)]
                  for frame, (move, scale, score) in group.found.items()},
        "inputs": {part.item["name"]: part.item["inputs"] for part in group.parts},
        "hatch": {part.item["name"]: part.hatch for part in group.parts if part.hatch is not None},
        "phase": {part.item["name"]: part.phase for part in group.parts if part.hatch is not None}} for group in groups}
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(kept, handle, ensure_ascii=False)


def main():
    args = _arguments()
    spec = json.load(open(args.spec, encoding="utf-8"))
    shot_path = os.path.join(FILM, "shots", f"{args.shot}.json")
    shot = json.load(open(shot_path, encoding="utf-8"))
    film = json.load(open(os.path.join(FILM, "film.json"), encoding="utf-8"))
    segments = json.load(open(DESIGN, encoding="utf-8"))["corner_segments"]
    layering = [item["name"] for item in shot.get("underlays", {}).get("items", [])] + [item["name"] for item in shot.get("overlays", [])]
    overlays = {item["name"]: item for item in shot.get("overlays", [])}
    items = {**{item["name"]: item for item in shot.get("underlays", {}).get("items", [])}, **overlays}
    names = [name for group in spec["groups"] for name in group["items"] + group.get("riding", []) if items[name]["asset"] not in OUTLINED]
    request = os.path.join(tempfile.mkdtemp(prefix="fit_overlays_"), "request.json")
    with open(request, "w", encoding="utf-8") as handle:
        json.dump({"items": [items[name] for name in names]}, handle, ensure_ascii=False)
    shapes_file = os.path.join(os.path.dirname(request), "shapes.npz")
    subprocess.run([args.blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "overlay_shapes.py"), "--", request, shapes_file],
                   check=True, capture_output=True)
    shapes = np.load(shapes_file)
    shape_of = {name: Shape(shapes[f"{number}_points"], shapes[f"{number}_triangles"]) for number, name in enumerate(names)}
    groups = [Group(entry, [Part(items[name], shape_of.get(name), segments) for name in entry["items"]],
                    [Part(items[name], shape_of.get(name), segments) for name in entry.get("riding", [])],
                    all(name in overlays for name in entry["items"]), layering.index(entry["items"][0]))
              for entry in spec["groups"]]
    parts = [part for group in groups for part in group.parts]
    for number, part in enumerate(parts):
        part.number = number
    frames = sorted({frame for group in groups for frame in group.frames})
    reading = Reading(args.frames_dir, args.masks, film, frames, parts)
    reading.in_front = np.array([group.front for group in groups for _part in group.parts])
    if args.placements and os.path.isfile(args.placements):
        kept = json.load(open(args.placements, encoding="utf-8"))
        for group in groups:
            entry = kept.get(group.spec["items"][0])
            if entry is None:
                continue
            group.found = {int(frame): (np.array(move), scale, score) for frame, (move, scale, score) in entry["found"].items()}
            for part in group.parts:
                part.item["inputs"] = entry["inputs"][part.item["name"]]
                part.reshape()
                part.hatch = entry["hatch"].get(part.item["name"])
                part.phase = entry["phase"].get(part.item["name"], 0.0)
        print(f"[overlays] placements read from {args.placements}", flush=True)
        refitted = [group for group in groups if group.spec["items"][0] in args.refit]
        for group in refitted:
            start = group.placement(group.spec["anchor"]) if group.spec["anchor"] in group.found else None
            group.found = _fitted(group, groups, reading, args.frames_dir, start)
        if refitted:
            for group in groups:
                group.found = _refined(group, groups, reading)
            print(f"[overlays] refitted {[group.spec['items'][0] for group in refitted]}, all refined", flush=True)
            _kept(groups, args.placements)
    else:
        for group in groups:
            group.found = _fitted(group, groups, reading, args.frames_dir)
        print("[overlays] found", flush=True)
        for group in groups:
            group.found = _fitted(group, groups, reading, args.frames_dir, group.placement(group.spec["anchor"]))
        print("[overlays] found again with all the others", flush=True)
        for group in groups:
            group.found = _refined(group, groups, reading)
        print("[overlays] refined", flush=True)
        if args.placements:
            _kept(groups, args.placements)
    if args.inspect:
        _inspected(groups, reading, args.inspect)
    if not args.write:
        return
    for group in groups:
        keys = _keys(group)
        for part in group.parts + group.riding:
            item = part.item
            for key in MOVING:
                item["inputs"].pop(key, None)
            if part.hatch is not None:
                item["inputs"]["Hatch"] = [round(value, 5) for value in part.hatch]
                item["inputs"]["Hatch Phase"] = round(part.phase % 1.0, 4)
            item["keys"] = keys[item["name"]]
            if part in group.parts:
                item["shown"] = list(group.spec["frames"])
    fitted = {part.item["name"]: part.item for group in groups for part in group.parts + group.riding}
    shot = json.load(open(shot_path, encoding="utf-8"))
    replaced = set(spec.get("replaces", []))
    shot["underlays"]["items"] = [fitted.get(item["name"], item) for item in shot["underlays"]["items"] if item["name"] not in replaced]
    shot["overlays"] = [fitted.get(item["name"], item) for item in shot.get("overlays", []) if item["name"] not in replaced]
    note = (f"Its overlays are keyed frame by frame as the reference draws them (calibration/fit_overlays.py with "
            f"{os.path.basename(args.spec)}).")
    shot["notes"] = [text for text in shot.get("notes", []) if not text.startswith("Its overlays are keyed")] + [note]
    with open(shot_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(shot, indent=1, ensure_ascii=False) + "\n")
    print(f"[overlays] written into {shot_path}", flush=True)


if __name__ == "__main__":
    main()
