"""
Trace the scythe's outlines on its design sheet (``Reference/Sheet.jpg``)
into ``trace.json``.

Every outline is a region of ``regions.json``, a polygon drawn round a part
on the sheet (pixel centres at whole numbers) and what of the sheet inside
it the part is:

    "tone": [low, high]   where the descreened grey (0-255, the sheet blurred
                          by ``sigma`` pixels to dissolve the print's halftone
                          screen) lies between low and high -- a dark part on
                          the white paper is [0, 147], its edge halfway from
                          its grey to the paper's; with ``"channel": "green"``
                          the tone is how much greener than red and blue the
                          sheet is (the green lights)
    no "tone"             the polygon itself

The outline runs where the tone leaves the range or the polygon ends,
whichever comes first: the zero line of min(tone margin, signed distance
to the polygon), the tone margin being the grey's distance from the range
over the slope of a printed edge.  Along the paper it follows the drawn
edge to a fraction of a pixel, along a cut through a part it follows the
polygon; small islands of halftone noise (under ``min_area`` px) are
dropped and the rest simplified to within ``simplify`` px; with
``"holes": false`` only the outermost outlines are kept (a dark part
keeps the light marks painted on it).  ``"minus": [names]`` leaves out
the outlines traced for other regions (listed before it), so two parts
meet exactly along one edge; ``"within": [names]`` keeps only what lies
inside them -- a mark painted on a part never spills onto the paper round
it.  A region can also take the strands of
others (``"join": [names]``).

An edge running the length of a long part -- the blade's back, the line
of its grind, its cutting edge -- is a ``profile``: one open strand,
found down every sheet column from ``columns[0]`` to ``columns[1]``
between the rows of ``within`` ([[u, v_top, v_bottom], ...], interpolated
along u) and fitted with a smoothing spline (``smooth``: its roughness penalty,
chosen by cross-validation when not given) that bridges the columns listed
in ``skip`` ([[u0, u1], ...]) with the least bending,
where a slot or a painted mark breaks the edge.  ``through`` points are
fixed (measured by hand where the sheet's drawing is too faint to find),
``extend`` carries the strand on straight to that column (where a part
runs on hidden under another) and ``below`` keeps it below another
profile's strand.
``find`` is what the edge is, read down the column:

    "top"      the first step from the paper into the part
    "bottom"   the last step from the part out to the paper
    "grind"    the steepest step from the dark back of a blade into its
               lighter grind

Lettering too small for the print to resolve -- the blade's bold capitals,
its slashed zeros -- is written out as the centre lines of its strokes
(``"strokes": [[[u, v], ...], ...]``, each placed in the ink box measured
on the sheet), passed on as open strands for ``WPN.Strokes`` to paint.


Plain Python with numpy, OpenCV and scikit-image::

    python Other/Weapons/Scythe/calibration/trace.py [--preview out.png] [--only name ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import cv2
import numpy as np
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(FOLDER)))
REFERENCE = os.path.join(FOLDER, "Reference", "Sheet.jpg")
REGIONS = os.path.join(HERE, "regions.json")
TRACE = os.path.join(FOLDER, "trace.json")
EDGE_SLOPE = 60.0
MARGIN = 4

sys.path.insert(0, ROOT)
from Core.jsonio import dumps  # noqa: E402


def grey(sigma, channel="grey", cache={}):
    """The descreened sheet: its grey, or for ``"green"`` how much greener
    than red and blue it is (the indicator lights)."""
    key = (sigma, channel)
    if key not in cache:
        if "sheet" not in cache:
            cache["sheet"] = cv2.imread(REFERENCE).astype(np.float32)
        blurred = cv2.GaussianBlur(cache["sheet"], (0, 0), sigma)
        blue, green, red = blurred[..., 0], blurred[..., 1], blurred[..., 2]
        cache[key] = blurred.mean(axis=2) if channel == "grey" else green - np.maximum(red, blue)
    return cache[key]


def signed_distance(polygon, us, vs):
    """Distance of the points (us, vs) to the polygon's edges, positive
    inside (even-odd)."""
    points = np.stack([us, vs], axis=-1)
    nearest = np.full(us.shape, np.inf)
    inside = np.zeros(us.shape, bool)
    count = len(polygon)
    for index in range(count):
        a = np.asarray(polygon[index], float)
        b = np.asarray(polygon[(index + 1) % count], float)
        edge = b - a
        share = np.clip(((points - a) @ edge) / max(edge @ edge, 1e-12), 0.0, 1.0)
        nearest = np.minimum(nearest, np.linalg.norm(points - (a + share[..., None] * edge), axis=-1))
        crosses = (a[1] > vs) != (b[1] > vs)
        at = a[0] + (vs - a[1]) * edge[0] / np.where(edge[1] == 0, 1e-12, edge[1])
        inside ^= crosses & (us < at)
    return np.where(inside, nearest, -nearest)


def area(points):
    u, v = points[:, 0], points[:, 1]
    return 0.5 * abs(np.dot(u, np.roll(v, 1)) - np.dot(v, np.roll(u, 1)))


def crossing(column, start, stop, level):
    """Sub-pixel row in [start, stop) where ``column`` first crosses
    ``level``, either way."""
    for v in range(max(start, 0), min(stop, len(column) - 1)):
        a, b = column[v], column[v + 1]
        if (a - level) * (b - level) <= 0.0 and a != b:
            return v + (level - a) / (b - a)
    return None


def edge_row(column, top, bottom, find):
    """Row of the edge ``find`` in ``column`` between ``top`` and ``bottom``."""
    paper = float(np.median(column[top:top + 4])) if find != "bottom" else float(np.median(column[bottom - 4:bottom]))
    if find == "bottom":
        for v in range(bottom, top, -1):
            if column[v] < paper - 12.0:
                part = float(np.median(column[v - 8:v - 2]))
                return crossing(column, v - 4, v + 6, (paper + part) * 0.5)
        return None
    first = next((v for v in range(top, bottom) if column[v] < paper - 40.0), None)
    if first is None:
        return None
    if find == "top":
        part = float(np.median(column[first + 3:first + 9]))
        return crossing(column, first - 6, first + 4, (paper + part) * 0.5)
    window = column[first + 20:bottom]
    if len(window) < 8:
        return None
    rise = first + 21 + int(np.argmax(window[2:] - window[:-2]))
    dark = float(np.median(column[rise - 10:rise - 4]))
    bevel = float(np.median(column[rise + 4:rise + 10]))
    if bevel - dark < 20.0:
        return None
    return crossing(column, rise - 5, rise + 5, (dark + bevel) * 0.5)


def profiled(spec, trace):
    from scipy.interpolate import make_smoothing_spline
    sheet = grey(spec.get("sigma", 1.3))
    u0, u1 = spec["columns"]
    within = np.asarray(spec["within"], float)
    skip = spec.get("skip", [])
    found_u, found_v = [], []
    for u in range(int(u0), int(u1) + 1):
        if any(a <= u <= b for a, b in skip):
            continue
        top = int(np.interp(u, within[:, 0], within[:, 1]))
        bottom = int(np.interp(u, within[:, 0], within[:, 2]))
        row = edge_row(sheet[:, u], top, bottom, spec["find"])
        if row is not None:
            found_u.append(u)
            found_v.append(row)
    found_u, found_v = np.asarray(found_u, float), np.asarray(found_v, float)
    through = np.asarray(spec.get("through", np.zeros((0, 2))), float).reshape(-1, 2)
    free = ~np.isin(found_u, through[:, 0])
    keep = free
    for _ in range(3):
        us = np.concatenate([found_u[keep], through[:, 0]])
        vs = np.concatenate([found_v[keep], through[:, 1]])
        weights = np.concatenate([np.ones(keep.sum()), np.full(len(through), 30.0)])
        order = np.argsort(us, kind="stable")
        spline = make_smoothing_spline(us[order], vs[order], w=weights[order], lam=spec.get("smooth"))
        residual = found_v - spline(found_u)
        rms = float(np.sqrt(np.mean(residual[keep] ** 2)))
        keep = free & (np.abs(residual) < max(3.0 * rms, 1.5))
    print(f"  {spec['find']}: {keep.sum()} of {len(found_u)} columns, rms {rms:.2f} px")
    spacing = spec.get("spacing", 6.0)
    samples = np.linspace(u0, u1, max(int(round((u1 - u0) / spacing)), 2) + 1)
    rows = spline(samples)
    root = spec.get("extend")
    if root is not None:
        slope = float(spline.derivative()(u0))
        extra = np.arange(root, u0, spacing)
        samples = np.concatenate([extra, samples])
        rows = np.concatenate([float(spline(u0)) + slope * (extra - u0), rows])
    if "below" in spec:
        above = np.asarray(trace[spec["below"]][0], float)
        rows = np.maximum(rows, np.interp(samples, above[:, 0], above[:, 1]))
    return [[[round(float(u), 2), round(float(v), 2)] for u, v in zip(samples, rows)]]


def nested(strand, others):
    """Whether ``strand`` lies inside another of ``others`` (even-odd)."""
    u, v = strand[0]
    for other in others:
        if other is strand:
            continue
        if signed_distance(np.asarray(other, float), np.array([u]), np.array([v]))[0] > 0.0:
            return True
    return False


def traced(spec, trace):
    if "find" in spec:
        return profiled(spec, trace)
    if "strokes" in spec:
        return [[list(map(float, point)) for point in stroke] for stroke in spec["strokes"]]
    polygon = np.asarray(spec["region"], float)
    if "tone" not in spec and not spec.get("within") and not spec.get("minus"):
        return [polygon.tolist()]
    sheet = grey(spec.get("sigma", 1.3), spec.get("channel", "grey"))
    u0 = max(int(np.floor(polygon[:, 0].min())) - MARGIN, 0)
    v0 = max(int(np.floor(polygon[:, 1].min())) - MARGIN, 0)
    u1 = min(int(np.ceil(polygon[:, 0].max())) + MARGIN + 1, sheet.shape[1])
    v1 = min(int(np.ceil(polygon[:, 1].max())) + MARGIN + 1, sheet.shape[0])
    vs, us = np.mgrid[v0:v1, u0:u1].astype(float)
    field = signed_distance(polygon, us, vs)
    if "tone" in spec:
        low, high = spec["tone"]
        tones = sheet[v0:v1, u0:u1]
        field = np.minimum(field, np.minimum(tones - low, high - tones) / EDGE_SLOPE)
    for other in spec.get("minus", []):
        for strand in trace[other]:
            field = np.minimum(field, -signed_distance(np.asarray(strand, float), us, vs))
    if spec.get("within"):
        inside = np.full(field.shape, -np.inf)
        for other in spec["within"]:
            for strand in trace[other]:
                inside = np.maximum(inside, signed_distance(np.asarray(strand, float), us, vs))
        field = np.minimum(field, inside)
    field[0, :] = field[-1, :] = field[:, 0] = field[:, -1] = -1.0
    strands = []
    for contour in measure.find_contours(field, 0.0):
        points = np.stack([contour[:, 1] + u0, contour[:, 0] + v0], axis=-1)
        if area(points) < spec.get("min_area", 6.0):
            continue
        simple = cv2.approxPolyDP(points.astype(np.float32).reshape(-1, 1, 2), spec.get("simplify", 0.3), True).reshape(-1, 2)
        if len(simple) >= 3:
            strands.append([[round(float(u), 2), round(float(v), 2)] for u, v in simple])
    if not spec.get("holes", True):
        strands = [strand for strand in strands if not nested(strand, strands)]
    return strands


def preview(trace, regions, path):
    sheet = cv2.imread(REFERENCE)
    scale = 2
    canvas = cv2.resize(sheet, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    canvas = (canvas.astype(np.float32) * 0.6 + 255 * 0.4).astype(np.uint8)
    for name, strands in trace.items():
        hue = (hash(name) % 180)
        color = cv2.cvtColor(np.uint8([[[hue, 255, 220]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        for strand in strands:
            points = (np.asarray(strand) * scale + scale * 0.5).astype(np.int32)
            spec = regions.get(name, {})
            cv2.polylines(canvas, [points], "find" not in spec and "strokes" not in spec, color, 1, cv2.LINE_AA)
    cv2.imwrite(path, canvas)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--preview", default=None)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args(argv)
    with open(REGIONS, encoding="utf-8") as handle:
        regions = json.load(handle)
    trace = {}
    if os.path.exists(TRACE) and args.only:
        with open(TRACE, encoding="utf-8") as handle:
            trace = json.load(handle)
    for name, spec in regions.items():
        if args.only and name not in args.only:
            continue
        if "join" in spec:
            continue
        trace[name] = traced(spec, trace)
        print(f"{name}: {len(trace[name])} strands, {sum(len(s) for s in trace[name])} points")
    for name, spec in regions.items():
        if "join" in spec:
            trace[name] = [strand for other in spec["join"] for strand in trace[other]]
    with open(TRACE, "w", encoding="utf-8") as handle:
        handle.write(dumps(trace) + "\n")
    if args.preview:
        preview(trace, regions, args.preview)


if __name__ == "__main__":
    main()
