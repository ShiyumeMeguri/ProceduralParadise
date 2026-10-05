"""
Read the scythe's relief -- which part stands proud of which, how the
rotor's turned face rises and falls -- off a normal map painted from its
design sheet (``Reference/Normals.png``), and hold the model against it.

The map is a picture of the sheet's scythe as a relief would shade it, not
a measurement: square where the sheet is not, its blade's tip drifting off
the sheet's, a soft halo round some edges, its flat colour wandering by a
quarter of full tilt across the picture, details the sheet never drew (teeth
round the rotor) and every step drawn as the same bevel whatever its
height.  What it does carry is the sign of the relief: a bevel lies on the
higher side of an edge, facing the lower, and a turned face leans the way
it slopes.  So it is read only locally and only for signs and shapes; the
heights come from the end view and the sheet.

* **Registration.**  An affine map lays the picture's silhouette (what
  differs from its corner's background) on the weapon's (ECC on the
  blurred silhouettes, coarse to fine, the blade's tip left out, past
  ``TIP``).  A smooth field then lays its edges on the sheet's: in tiles
  across the weapon the edge strength of the picture is matched to the
  sheet's (normalised cross-correlation), each match weighted by how
  sharply it peaks in each direction -- a tile holding one straight edge
  pins only across it -- and a field on a ``SPACING`` grid, bending as
  little as a membrane and a plate, is solved through the matches by least
  squares, the search narrowing round by round (``ROUNDS``: search reach,
  stiffness), matches far off the field dropped.
* **Conventions.**  Red rises with the surface facing right and green with
  it facing up (OpenGL); printed as the correlation of each with the
  outward direction round the silhouette, where every surface faces out.
* **Rotor.**  Ring by ring about ``ROTOR["centre"]`` the picture's tilt is
  split into a part leaning out from the centre, one leaning round it and
  a tilt common to the whole ring (the wandering flat), over the sectors
  where nothing else lies on the rotor or round it (``ROTOR["excluded"]``:
  start, end, from radius).  The outward lean, integrated from the outside
  in, is the face's profile; its scale is fixed by the two heights the end
  view and the sheet give: the rim's crest stands ``ROTOR["crest"]`` out of
  the mid-plane, the full thickness the end view measures over the rotor,
  and the face reaches the housing's face, ``ROTOR["base"]``, at the
  profile's outer end.
* **Steps.**  Where two parts of a model meet on the sheet, the picture's
  tilt across the boundary (towards the second part) is averaged within
  ``BAND`` px of it, less the same over the faces beyond (``BASELINE``):
  positive where the first part is the higher.  Printed against the
  model's own step there, the boundaries where they disagree first.

The model is a render of the ``Sheet`` shot that keeps, per pixel, the
point's depth and which part it is.  Two steps, because Blender's Python
has no OpenCV::

    blender -b --factory-startup -P Other/Weapons/Scythe/calibration/relief.py -- render <folder>
    python Other/Weapons/Scythe/calibration/relief.py compare <folder> [--registered map.png] [--figure figure.png]

``--figure`` draws the head three times: the sheet, the registered picture
and the model's relief drawn the way the picture draws one (its height
softened by ``SOFTEN`` px, steps becoming bevels, tilts capped at
``CAP``).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(FOLDER)))
SHEET = os.path.join(FOLDER, "Reference", "Sheet.jpg")
NORMALS = os.path.join(FOLDER, "Reference", "Normals.png")
MODEL = "model.exr"
PARTS = "parts.json"
OFFSET = 1.0
TIP = 2300
CORNER = 30
SMALL = 0.25
SIGMAS = (12.0, 6.0, 3.0, 1.5)
TILE = 96
STRIDE = 24
SPACING = 48
ROUNDS = ((40, 4.0), (20, 2.0), (10, 1.0), (6, 0.5), (6, 0.5))
BAND = 6
BASELINE = (9, 16)
STEP = 2.0
FIGURE = (400, 150, 1330, 760)
SOFTEN = 1.5
CAP = 0.7
ROTOR = {"centre": [1019.48, 463.69], "radius": 216.0, "crest": 37.65, "base": 35.25,
         "excluded": [[25.0, 75.0, 0.0], [185.0, 207.0, 0.0], [280.0, 335.0, 0.0], [207.0, 280.0, 187.0]]}


def render_model(folder):
    """The ``Sheet`` shot with every surface showing its point's X (plus
    ``OFFSET``), its depth out of the sheet and its part's index -- small
    positive numbers, which the film keeps exactly."""
    import bpy
    sys.path.insert(0, os.path.join(ROOT, "Other"))
    sys.path.insert(0, ROOT)
    import build
    from Core import shaders as S
    build.main(["build.py", "Weapons/Scythe", "--no-save", "--no-look"])
    scene = bpy.context.scene
    names = {}
    for index, item in enumerate([o for o in scene.objects if o.type == "MESH"], start=1):
        item.pass_index = index
        names[index] = item.name

    def coded(tree):
        position = tree.sep(tree.n("ShaderNodeNewGeometry")["Position"])
        identity = tree.n("ShaderNodeObjectInfo")["Object Index"]
        colour = tree.n("ShaderNodeCombineColor", position[0] + OFFSET, position[1] * -1.0, identity).o
        return tree.n("ShaderNodeEmission", colour, 1.0)["Emission"]

    scene.view_layers[0].material_override = S.material("__relief_code", coded)
    scene.eevee.taa_render_samples = 1
    scene.render.filter_size = 0.0
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.use_compositing = False
    settings = scene.render.image_settings
    settings.file_format = "OPEN_EXR"
    settings.color_depth = "32"
    settings.color_mode = "RGBA"
    os.makedirs(folder, exist_ok=True)
    scene.render.filepath = os.path.join(folder, MODEL)
    bpy.ops.render.render(write_still=True)
    with open(os.path.join(folder, PARTS), "w", encoding="utf-8") as handle:
        json.dump(names, handle, indent=1)


def load_model(folder):
    """The model's coverage, height out of the sheet (sheet units, towards
    the viewer) and part index per sheet pixel, and the parts' names."""
    import cv2
    import numpy as np
    from Core import jsonio
    scale = jsonio.load(os.path.join(FOLDER, "weapon.json"))["sheet"]["metres_per_unit"]
    image = cv2.imread(os.path.join(folder, MODEL), cv2.IMREAD_UNCHANGED)
    shown = image[..., 3] > 0.5
    height = np.where(shown, image[..., 1] / scale, np.nan)
    part = np.where(shown, np.round(image[..., 0]), 0).astype(np.int32)
    with open(os.path.join(folder, PARTS), encoding="utf-8") as handle:
        names = {int(key): value for key, value in json.load(handle).items()}
    return shown, height, part, names


def silhouette(normals):
    import cv2
    import numpy as np
    background = np.median(normals[:CORNER, :CORNER].reshape(-1, 3), axis=0)
    difference = np.abs(normals - background).max(axis=2)
    mask = (cv2.GaussianBlur(difference, (0, 0), 1.0) > 12.0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    return labels == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]), background


def affine(mask, weapon):
    """The affine map of the picture onto the sheet laying ``mask`` on
    ``weapon``."""
    import cv2
    import numpy as np
    ys, xs = np.nonzero(mask)
    vs, us = np.nonzero(weapon)
    scale = ((us.max() - us.min()) / (xs.max() - xs.min()) + (vs.max() - vs.min()) / (ys.max() - ys.min())) * 0.5
    warp = np.array([[scale, 0.0, us.min() - scale * xs.min()], [0.0, scale, vs.min() - scale * ys.min()]], np.float32)
    weight = np.ones(weapon.shape, np.float32)
    weight[:, TIP:] = 0.0
    shrink = np.diag([1.0 / SMALL, 1.0 / SMALL, 1.0])
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-7)
    for sigma in SIGMAS:
        source = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma / scale)
        template = cv2.resize(cv2.GaussianBlur(weapon.astype(np.float32), (0, 0), sigma) * weight, None, fx=SMALL, fy=SMALL,
                              interpolation=cv2.INTER_AREA)
        estimate = (np.vstack([cv2.invertAffineTransform(warp), [0.0, 0.0, 1.0]]) @ shrink)[:2].astype(np.float32)
        _, estimate = cv2.findTransformECC(template, source, estimate, cv2.MOTION_AFFINE, criteria, None, 5)
        warp = cv2.invertAffineTransform((np.vstack([estimate, [0.0, 0.0, 1.0]]) @ np.linalg.inv(shrink))[:2].astype(np.float32))
    return warp


class Field:
    """A smooth displacement field on a ``SPACING`` grid over the sheet."""

    def __init__(self, shape):
        import numpy as np
        import scipy.sparse as sparse
        self.height, self.width = shape
        self.rows = int(np.ceil(self.height / SPACING)) + 1
        self.columns = int(np.ceil(self.width / SPACING)) + 1
        self.count = self.rows * self.columns
        self.nodes = np.zeros((self.rows, self.columns, 2))
        entries = []
        for y in range(self.rows):
            for x in range(self.columns):
                base = y * self.columns + x
                if x < self.columns - 1:
                    entries.append([(base, 0.3), (base + 1, -0.3)])
                if y < self.rows - 1:
                    entries.append([(base, 0.3), (base + self.columns, -0.3)])
                if 0 < x < self.columns - 1:
                    entries.append([(base - 1, 1.0), (base, -2.0), (base + 1, 1.0)])
                if 0 < y < self.rows - 1:
                    entries.append([(base - self.columns, 1.0), (base, -2.0), (base + self.columns, 1.0)])
                if x < self.columns - 1 and y < self.rows - 1:
                    entries.append([(base, 1.0), (base + 1, -1.0), (base + self.columns, -1.0), (base + self.columns + 1, 1.0)])
        rows = [row for row, entry in enumerate(entries) for _ in entry]
        columns = [column for entry in entries for column, _ in entry]
        values = [value for entry in entries for _, value in entry]
        self.bending = sparse.csr_matrix((values, (rows, columns)), shape=(len(entries), self.count))

    def weights(self, points):
        import numpy as np
        gx, gy = points[:, 0] / SPACING, points[:, 1] / SPACING
        x0 = np.clip(np.floor(gx).astype(int), 0, self.columns - 2)
        y0 = np.clip(np.floor(gy).astype(int), 0, self.rows - 2)
        fx, fy = gx - x0, gy - y0
        corners = np.stack([y0 * self.columns + x0, y0 * self.columns + x0 + 1, (y0 + 1) * self.columns + x0,
                            (y0 + 1) * self.columns + x0 + 1], 1)
        shares = np.stack([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy], 1)
        return corners, shares

    def at(self, nodes, points):
        corners, shares = self.weights(points)
        return (nodes.reshape(-1, 2)[corners] * shares[..., None]).sum(1)

    def solve(self, centres, shifts, informations, stiffness):
        """The increment through the matches (``shifts`` at ``centres``,
        each weighted by its 2x2 ``information``) bending as little as
        ``stiffness`` allows."""
        import numpy as np
        import scipy.sparse as sparse
        import scipy.sparse.linalg as sparse_linalg
        corners, shares = self.weights(centres)
        values, vectors = np.linalg.eigh(informations)
        roots = np.einsum("nij,nj,nkj->nik", vectors, np.sqrt(np.maximum(values, 0.0)), vectors)
        rows, columns, data = [], [], []
        for axis in range(2):
            for component in range(2):
                for corner in range(4):
                    rows.append(np.arange(len(centres)) * 2 + component)
                    columns.append(axis * self.count + corners[:, corner])
                    data.append(roots[:, component, axis] * shares[:, corner])
        matrix = sparse.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(columns))),
                                   shape=(len(centres) * 2, 2 * self.count))
        target = np.einsum("nij,nj->ni", roots, shifts).ravel()
        bending = sparse.block_diag([self.bending, self.bending]) * stiffness
        system = sparse.vstack([matrix, bending, sparse.identity(2 * self.count) * 1e-3]).tocsr()
        rhs = np.concatenate([target, np.zeros(bending.shape[0] + 2 * self.count)])
        solution = sparse_linalg.lsqr(system, rhs, atol=1e-10, btol=1e-10, iter_lim=20000)[0]
        return np.stack([solution[:self.count].reshape(self.rows, self.columns), solution[self.count:].reshape(self.rows, self.columns)], -1)

    def dense(self):
        import cv2
        import numpy as np
        grid_x, grid_y = np.meshgrid(np.arange(self.width, dtype=np.float32) / SPACING, np.arange(self.height, dtype=np.float32) / SPACING)
        return np.stack([cv2.remap(self.nodes[..., c].astype(np.float32), grid_x, grid_y, cv2.INTER_LINEAR) for c in range(2)], -1)


def edges(image, sigma, weapon, soft):
    """Edge strength, its floor and its local level taken out, faded away
    from the weapon."""
    import cv2
    import numpy as np
    blurred = cv2.GaussianBlur(image, (0, 0), sigma)
    magnitude = np.sqrt(cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3) ** 2 + cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3) ** 2)
    if magnitude.ndim == 3:
        magnitude = magnitude.sum(axis=2)
    magnitude = np.maximum(magnitude - np.percentile(magnitude[weapon], 55), 0.0)
    local = np.sqrt(cv2.GaussianBlur(magnitude ** 2, (0, 0), 24.0))
    local = np.maximum(local, np.percentile(local[weapon], 40))
    return (magnitude / local * soft).astype(np.float32)


def matches(sheet_edges, picture_edges, weapon, reach):
    """Tile by tile, where the picture's edges lie off the sheet's: the
    shift, and its information (the sharpness of the correlation peak)."""
    import cv2
    import numpy as np
    height, width = weapon.shape
    centres, shifts, informations = [], [], []
    dy, dx = np.mgrid[-2:3, -2:3]
    design = np.column_stack([np.ones(25), dx.ravel(), dy.ravel(), dx.ravel() ** 2, dx.ravel() * dy.ravel(), dy.ravel() ** 2])
    for top in range(reach, height - TILE - reach, STRIDE):
        for left in range(reach, width - TILE - reach, STRIDE):
            if not weapon[top + TILE // 2, left + TILE // 2]:
                continue
            template = sheet_edges[top:top + TILE, left:left + TILE]
            if template.std() < 0.2:
                continue
            search = picture_edges[top - reach:top + TILE + reach, left - reach:left + TILE + reach]
            response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
            _, peak, _, (column, row) = cv2.minMaxLoc(response)
            if peak < 0.3 or not (2 <= column < response.shape[1] - 2 and 2 <= row < response.shape[0] - 2):
                continue
            rival = response.copy()
            cv2.circle(rival, (column, row), 5, -1.0, -1)
            if rival.max() > 0.92 * peak:
                continue
            fit = np.linalg.lstsq(design, response[row - 2:row + 3, column - 2:column + 3].astype(np.float64).ravel(), rcond=None)[0]
            hessian = np.array([[2.0 * fit[3], fit[4]], [fit[4], 2.0 * fit[5]]])
            values, vectors = np.linalg.eigh(-hessian)
            if values.max() <= 1e-4:
                continue
            information = vectors @ np.diag(np.maximum(values, 1e-6)) @ vectors.T
            offset = np.linalg.solve(information, fit[1:3])
            if np.abs(offset).max() > 1.5:
                continue
            centres.append((left + TILE / 2 - 0.5, top + TILE / 2 - 0.5))
            shifts.append((column + offset[0] - reach, row + offset[1] - reach))
            informations.append(information * peak)
    return np.array(centres), np.array(shifts), np.array(informations)


def register(shown):
    """The normal map laid on the sheet, as float BGR."""
    import cv2
    import numpy as np
    sheet = cv2.imread(SHEET)
    height, width = sheet.shape[:2]
    picture = cv2.imread(NORMALS).astype(np.float32)
    mask, background = silhouette(picture)
    warp = affine(mask, shown)
    flat = tuple(float(value) for value in background)
    laid = cv2.warpAffine(picture, warp, (width, height), flags=cv2.INTER_CUBIC, borderValue=flat)
    weapon = cv2.dilate(shown.astype(np.uint8), np.ones((21, 21), np.uint8)) > 0
    weapon[:, TIP:] = False
    soft = cv2.GaussianBlur(weapon.astype(np.float32), (0, 0), 6.0)
    sheet_edges = edges(cv2.cvtColor(sheet, cv2.COLOR_BGR2GRAY).astype(np.float32), 3.0, weapon, soft)
    field = Field((height, width))
    pixel_x, pixel_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    moved = laid
    for reach, stiffness in ROUNDS:
        centres, shifts, informations = matches(sheet_edges, edges(moved, 2.5, weapon, soft), weapon, reach)
        keep = np.ones(len(centres), bool)
        for _ in range(2):
            increment = field.solve(centres[keep], shifts[keep], informations[keep], stiffness)
            error = shifts - field.at(increment, centres)
            normalised = informations / np.maximum(np.trace(informations, axis1=1, axis2=2)[:, None, None], 1e-9)
            keep = np.einsum("ni,nij,nj->n", error, normalised, error) < 9.0
        field.nodes = field.nodes + increment
        dense = field.dense()
        moved = cv2.remap(laid, pixel_x + dense[..., 0], pixel_y + dense[..., 1], cv2.INTER_CUBIC, borderValue=flat)
        print(f"  reach {reach:2d}: {keep.sum()} of {len(centres)} tiles, field moved by up to {np.abs(increment).max():.1f} px")
    magnitude = np.sqrt((dense ** 2).sum(-1))[shown]
    print(f"registered: affine scale {np.sqrt(abs(np.linalg.det(warp[:, :2]))):.4f}, field median {np.median(magnitude):.1f} px, "
          f"95% {np.percentile(magnitude, 95):.1f} px")
    return moved


def tilts(picture):
    """Rightward and upward tilt of the registered picture (BGR)."""
    return (picture[..., 2] - 128.0) / 127.0, (picture[..., 1] - 128.0) / 127.0


def conventions(picture, shown):
    import cv2
    import numpy as np
    soft = cv2.GaussianBlur(shown.astype(np.float32), (0, 0), 2.0)
    out_x, out_up = -cv2.Sobel(soft, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(soft, cv2.CV_32F, 0, 1, ksize=3)
    length = np.hypot(out_x, out_up)
    rim = (length > 0.05) & shown & (cv2.erode(shown.astype(np.uint8), np.ones((9, 9), np.uint8)) == 0)
    rim[:, TIP:] = False
    right, up = tilts(picture)
    print(f"conventions: red with facing right {np.corrcoef(right[rim], out_x[rim] / length[rim])[0, 1]:+.2f}, "
          f"green with facing up {np.corrcoef(up[rim], out_up[rim] / length[rim])[0, 1]:+.2f} (OpenGL: both positive)")


def rotor(picture, shown):
    """The rotor's turned profile: radius, outward lean, height."""
    import numpy as np
    right, up = tilts(picture)
    height, width = shown.shape
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    dx, dy = xs - ROTOR["centre"][0], ROTOR["centre"][1] - ys
    radius = np.hypot(dx, dy)
    angle = np.degrees(np.arctan2(dy, dx)) % 360.0
    usable = shown & (radius < ROTOR["radius"])
    for start, end, inner in ROTOR["excluded"]:
        usable &= ~((angle >= start) & (angle < end) & (radius >= inner))
    bands = np.arange(0.0, ROTOR["radius"], STEP)
    lean = np.full(len(bands), np.nan)
    for index, low in enumerate(bands):
        ring = usable & (radius >= low) & (radius < low + STEP)
        if ring.sum() < 40:
            continue
        c, s = dx[ring] / np.maximum(radius[ring], 1e-6), dy[ring] / np.maximum(radius[ring], 1e-6)
        count = ring.sum()
        design = np.zeros((2 * count, 4))
        design[:count, 0], design[count:, 0] = c, s
        design[:count, 1], design[count:, 1] = -s, c
        design[:count, 2], design[count:, 3] = 1.0, 1.0
        lean[index] = np.linalg.lstsq(design, np.concatenate([right[ring], up[ring]]), rcond=None)[0][0]
    tilt = np.clip(np.nan_to_num(lean), -0.95, 0.95)
    slope = tilt / np.sqrt(1.0 - tilt * tilt)
    rise = np.zeros(len(bands))
    for index in range(len(bands) - 2, -1, -1):
        rise[index] = rise[index + 1] + 0.5 * (slope[index] + slope[index + 1]) * STEP
    crest = int(np.argmax(np.where(bands > ROTOR["radius"] * 0.75, rise, -np.inf)))
    scale = (ROTOR["crest"] - ROTOR["base"]) / rise[crest]
    print(f"rotor: crest at r {bands[crest] + STEP / 2:.0f}, the picture's slopes times {scale:.3f}")
    print(f"  {'r':>5} {'lean':>7} {'height':>7}")
    for low, value, raised in zip(bands, lean, rise):
        print(f"  {low + STEP / 2:5.0f} {value:+7.3f} {ROTOR['base'] + raised * scale:7.2f}")


def steps(picture, shown, height, part, names):
    """Boundary by boundary, which side the picture and the model raise."""
    import numpy as np
    from scipy import ndimage
    import cv2
    right, up = tilts(picture)
    raised = np.where(shown, np.nan_to_num(height), -200.0)
    found = {}
    for first, second, (ys, xs), along in ((part[:, :-1], part[:, 1:], np.nonzero(part[:, :-1] != part[:, 1:]), (0.0, 0.5)),
                                           (part[:-1, :], part[1:, :], np.nonzero(part[:-1, :] != part[1:, :]), (0.5, 0.0))):
        for y, x in zip(ys, xs):
            a, b = int(first[y, x]), int(second[y, x])
            found.setdefault((min(a, b), max(a, b)), []).append((y + along[0], x + along[1]))
    offsets = np.arange(-BASELINE[1], BASELINE[1] + 0.5, 1.0)
    rows = []
    for (a, b), points in found.items():
        if len(points) < 25:
            continue
        points = np.array(points)
        towards = cv2.GaussianBlur((part == b).astype(np.float32) - (part == a).astype(np.float32), (0, 0), 2.0)
        gy = ndimage.map_coordinates(cv2.Sobel(towards, cv2.CV_32F, 0, 1, ksize=3), points.T, order=1)
        gx = ndimage.map_coordinates(cv2.Sobel(towards, cv2.CV_32F, 1, 0, ksize=3), points.T, order=1)
        length = np.hypot(gx, gy) + 1e-9
        nx, ny = gx / length, gy / length
        across = np.array([ndimage.map_coordinates(right, [points[:, 0] + ny * o, points[:, 1] + nx * o], order=1) * nx
                           - ndimage.map_coordinates(up, [points[:, 0] + ny * o, points[:, 1] + nx * o], order=1) * ny for o in offsets])
        across -= np.median(across[np.abs(offsets) >= BASELINE[0]], axis=0)
        score = across[np.abs(offsets) <= BAND].mean(axis=0)
        model = np.median(ndimage.map_coordinates(raised, [points[:, 0] - ny * 2.5, points[:, 1] - nx * 2.5], order=0)
                          - ndimage.map_coordinates(raised, [points[:, 0] + ny * 2.5, points[:, 1] + nx * 2.5], order=0))
        rows.append((names.get(a, "(paper)"), names.get(b, "(paper)"), len(points), float(np.median(score)), float(np.mean(score > 0)), model))
    disagree = [row for row in rows if abs(row[5]) >= 0.2 and np.sign(row[3]) != np.sign(row[5]) and abs(row[3]) >= 0.1
                and (row[4] <= 0.3 or row[4] >= 0.7)]
    print(f"steps: {len(rows)} boundaries, {len(disagree)} where the picture firmly raises the other side")
    print(f"  {'first':>22} {'second':>22} {'px':>6} {'picture':>8} {'model':>7}")
    for first, second, count, score, _, model in sorted(disagree, key=lambda row: -row[2]):
        print(f"  {first[:22]:>22} {second[:22]:>22} {count:6d} {score:+8.3f} {model:+7.2f}")


def modelled(height, shown):
    """The model's relief as BGR normals, drawn as the picture draws one."""
    import cv2
    import numpy as np
    floor = np.nanmin(height[shown]) - 20.0
    raised = cv2.GaussianBlur(np.where(shown, np.nan_to_num(height, nan=floor), floor).astype(np.float32), (0, 0), SOFTEN)
    right = -cv2.Sobel(raised, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    up = cv2.Sobel(raised, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    length = np.hypot(right, up)
    capped = np.minimum(length, CAP) / np.maximum(length, 1e-6)
    right, up = right * capped, up * capped
    facing = np.sqrt(np.maximum(1.0 - right ** 2 - up ** 2, 0.0))
    drawn = np.stack([128.0 + 127.0 * facing, 128.0 + 127.0 * up, 128.0 + 127.0 * right], -1)
    drawn[~shown] = (255.0, 128.0, 128.0)
    return drawn


def figure(path, picture, height, shown):
    import cv2
    import numpy as np
    left, top, right, bottom = FIGURE
    gap = np.full((bottom - top, 16, 3), 255.0)
    panels = [cv2.imread(SHEET).astype(np.float32), picture, modelled(height, shown)]
    row = np.hstack([part for panel in panels for part in (panel[top:bottom, left:right], gap)][:-1])
    cv2.imwrite(path, np.clip(row, 0, 255).astype(np.uint8))


def compare(folder, registered=None, drawing=None):
    os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
    import cv2
    import numpy as np
    sys.path.insert(0, ROOT)
    shown, height, part, names = load_model(folder)
    picture = register(shown)
    if registered:
        cv2.imwrite(registered, np.clip(picture, 0, 255).astype(np.uint8))
    if drawing:
        figure(drawing, picture, height, shown)
    conventions(picture, shown)
    rotor(picture, shown)
    steps(picture, shown, height, part, names)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if argv[0] == "render":
        render_model(os.path.abspath(argv[1]))
    else:
        options = dict(zip(argv[2::2], argv[3::2]))
        compare(os.path.abspath(argv[1]), options.get("--registered"), options.get("--figure"))
