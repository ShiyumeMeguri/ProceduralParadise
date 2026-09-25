"""
Core.grade -- fit a global colour grade that maps a render onto a painted
reference, and express it as compositor nodes.

The grade is deliberately *global* (one 3x3 colour matrix + offset followed
by three per-channel tone curves, all in display-encoded sRGB): it reproduces
the painting's palette and tonality for every camera without ever sampling
the reference image at render time.

Workflow::

    g = fit_grade(render_srgb, reference_srgb)   # numpy arrays (H,W,3)
    json_dump(g.to_json())                       # store in the shot file
    look["grade"] = g                            # Core.render.compositor applies it
"""
from __future__ import annotations

import numpy as np

__all__ = ["fit_grade", "apply_grade", "grade_nodes"]


def _box_blur(a, r):
    if r <= 0:
        return a
    k = 2 * r + 1
    pad = np.pad(a, ((r, r), (r, r), (0, 0)), mode="edge")
    c = pad.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0), (0, 0)))
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s / (k * k)


def _grad(a):
    g = a.mean(-1)
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = np.abs(g[:, 2:] - g[:, :-2])
    gy[1:-1] = np.abs(g[2:] - g[:-2])
    return gx + gy


def fit_grade(render, ref, blur=4, edge_q=0.7, weights=None, n_knots=9, reg=0.02,
              curve_blend=0.65, min_slope=0.45, offset_reg=0.5):
    """Return dict(matrix=3x3, offset=3, curves={R,G,B: [[x,y],...]}).

    ``weights`` (H,W) optionally emphasises regions.  Pixels near edges in
    either image are dropped so small geometric misalignments do not bias
    the fit."""
    R = _box_blur(render.astype(np.float64), blur)
    T = _box_blur(ref.astype(np.float64), blur)
    ge = _grad(render) + _grad(ref)
    ge = _box_blur(ge[..., None], 2)[..., 0]
    mask = ge < np.quantile(ge, edge_q)
    w = mask.astype(np.float64)
    if weights is not None:
        w = w * weights
    X = R.reshape(-1, 3)
    Y = T.reshape(-1, 3)
    W = w.reshape(-1)
    sel = W > 0
    X, Y, W = X[sel], Y[sel], W[sel]
    # affine colour matrix (ridge towards identity for stability)
    Xa = np.concatenate([X, np.ones((len(X), 1))], 1)
    sw = np.sqrt(W)[:, None]
    A = Xa * sw
    B = Y * sw
    lam = reg * len(X)
    prior = np.vstack([np.eye(3), np.zeros((1, 3))])
    L = lam * np.eye(4)
    L[3, 3] = offset_reg * len(X)          # keep blacks down: penalise lift
    M = np.linalg.solve(A.T @ A + L, A.T @ B + L @ prior)
    Z = np.clip(Xa @ M, 0, 1)
    # per-channel monotone tone curves on the residual (binned medians)
    curves = {}
    knots = np.linspace(0, 1, n_knots)
    for c, name in enumerate("RGB"):
        z, y = Z[:, c], Y[:, c]
        ys = []
        for k in knots:
            m = np.abs(z - k) < (0.5 / (n_knots - 1)) * 1.5
            ys.append(np.median(y[m]) if m.sum() > 50 else np.nan)
        ys = np.array(ys)
        # fill gaps with identity-offset interpolation, then enforce monotone
        valid = ~np.isnan(ys)
        if valid.sum() < 2:
            ys = knots.copy()
        else:
            ys = np.interp(knots, knots[valid], ys[valid])
        # contrast-preserving regularisation: blend towards identity and
        # enforce a minimum slope so no tonal range is flattened
        ys = curve_blend * ys + (1.0 - curve_blend) * knots
        step = knots[1] - knots[0]
        for i in range(1, len(ys)):
            ys[i] = max(ys[i], ys[i - 1] + min_slope * step)
        ys = np.clip(ys, 0, 1)
        curves[name] = [[float(x), float(v)] for x, v in zip(knots, ys)]
    return {"matrix": M[:3].T.tolist(), "offset": M[3].tolist(), "curves": curves}


def apply_grade(img, g):
    """Apply a grade dict to an sRGB image (numpy) -- used to preview/verify."""
    M = np.array(g["matrix"])
    o = np.array(g["offset"])
    z = np.clip(img @ M.T + o, 0, 1)
    out = np.empty_like(z)
    for c, name in enumerate("RGB"):
        k = np.array(g["curves"][name])
        out[..., c] = np.interp(z[..., c], k[:, 0], k[:, 1])
    return out


def grade_nodes(t, img, g):
    """Build compositor nodes applying ``g`` to scene-linear ``img`` (a Sock).

    Linear -> sRGB, matrix + offset, per-channel curves, sRGB -> linear, so
    the Standard view transform afterwards yields exactly the fitted mapping.
    Values above 1 (lights, sun glints) pass through the matrix unclamped."""
    gamma = t.resolve("CompositorNodeGamma", "ShaderNodeGamma")
    enc = t.n(gamma, img, 1.0 / 2.2).o
    sep = t.n("CompositorNodeSeparateColor", enc)
    r, gg, b = sep[0], sep[1], sep[2]
    M = g["matrix"]
    o = g["offset"]
    ch = []
    for i in range(3):
        v = r * M[i][0] + gg * M[i][1] + b * M[i][2] + o[i]
        ch.append(v)
    comb = t.n("CompositorNodeCombineColor", ch[0], ch[1], ch[2], 1.0).o
    cv = t.n("CompositorNodeCurveRGB")
    t.link(comb, cv.n.inputs["Image"])
    mapping = cv.n.mapping
    for idx, name in ((0, "R"), (1, "G"), (2, "B")):
        pts = g["curves"][name]
        curve = mapping.curves[idx]
        while len(curve.points) > 2:
            curve.points.remove(curve.points[1])
        curve.points[0].location = pts[0]
        curve.points[-1].location = pts[-1]
        for x, y in pts[1:-1]:
            curve.points.new(x, y)
    mapping.update()
    dec = t.n(gamma, cv.o, 2.2).o
    return dec


def fit_grade_hist(render, ref, n_knots=17, smooth=0.5, min_slope=0.35, max_slope=3.0,
                   mask=None):
    """Distribution-matching grade: per-channel tone curves that map the
    render's cumulative histogram onto the reference's.  Unlike a pixelwise
    regression it cannot 'regress to the mean', so contrast is preserved.
    Returns the same dict layout as :func:`fit_grade` (identity matrix)."""
    qs = np.linspace(0.0, 1.0, 201)
    curves = {}
    for c, name in enumerate("RGB"):
        a = render[..., c].ravel()
        b = ref[..., c].ravel()
        if mask is not None:
            a = a[mask.ravel()]
            b = b[mask.ravel()]
        qa = np.quantile(a, qs)
        qb = np.quantile(b, qs)
        knots = np.linspace(0, 1, n_knots)
        # invert render CDF: for each knot x find the quantile level, then
        # read the reference value at that level
        lvl = np.interp(knots, qa, qs, left=0.0, right=1.0)
        ys = np.interp(lvl, qs, qb)
        # outside the render's range extrapolate with unit slope
        ys = np.where(knots < qa[0], qb[0] - (qa[0] - knots), ys)
        ys = np.where(knots > qa[-1], qb[-1] + (knots - qa[-1]), ys)
        ys = smooth * ys + (1 - smooth) * np.convolve(np.pad(ys, 1, mode="edge"),
                                                      [1 / 3, 1 / 3, 1 / 3], "valid")
        step = knots[1] - knots[0]
        for i in range(1, len(ys)):
            ys[i] = min(max(ys[i], ys[i - 1] + min_slope * step), ys[i - 1] + max_slope * step)
        ys = np.clip(ys, 0, 1)
        curves[name] = [[float(x), float(v)] for x, v in zip(knots, ys)]
    return {"matrix": np.eye(3).tolist(), "offset": [0.0, 0.0, 0.0], "curves": curves}


def fit_grade_patches(render_patches, ref_patches, n_knots=17, min_slope=0.3, max_slope=3.0,
                      reg=0.05):
    """Colour-chart style calibration: ``render_patches`` / ``ref_patches``
    are (N,3) arrays of mean sRGB colours of the same semantic regions
    (sky, walls, lit/shadowed floor, desk tops, chairs...).

    Step 1 fits a 3x3 matrix + offset (ridge towards identity) on the patch
    pairs; step 2 fits per-channel monotone curves through the residual
    (isotonic regression + linear interpolation between patch values,
    unit-slope extrapolation at the ends).  Because patches are reliable
    region means, the fit neither smears contrast (pixelwise regression)
    nor depends on image composition (histogram matching)."""
    X = np.asarray(render_patches, float)
    Y = np.asarray(ref_patches, float)
    Xa = np.concatenate([X, np.ones((len(X), 1))], 1)
    lam = reg * len(X)
    prior = np.vstack([np.eye(3), np.zeros((1, 3))])
    L = lam * np.eye(4)
    L[3, 3] = lam * 4.0
    M = np.linalg.solve(Xa.T @ Xa + L, Xa.T @ Y + L @ prior)
    Z = Xa @ M
    knots = np.linspace(0, 1, n_knots)
    curves = {}
    for c, name in enumerate("RGB"):
        order = np.argsort(Z[:, c])
        z, y = Z[order, c], Y[order, c].copy()
        # isotonic regression (pool adjacent violators)
        blocks = [[v, 1] for v in y]
        i = 0
        while i < len(blocks) - 1:
            if blocks[i][0] > blocks[i + 1][0]:
                v = (blocks[i][0] * blocks[i][1] + blocks[i + 1][0] * blocks[i + 1][1]) / (blocks[i][1] + blocks[i + 1][1])
                blocks[i] = [v, blocks[i][1] + blocks[i + 1][1]]
                del blocks[i + 1]
                i = max(i - 1, 0)
            else:
                i += 1
        yi = np.concatenate([[b[0]] * b[1] for b in blocks])
        ys = np.interp(knots, z, yi)
        ys = np.where(knots < z[0], yi[0] - (z[0] - knots), ys)
        ys = np.where(knots > z[-1], yi[-1] + (knots - z[-1]), ys)
        step = knots[1] - knots[0]
        for k in range(1, len(ys)):
            ys[k] = min(max(ys[k], ys[k - 1] + min_slope * step), ys[k - 1] + max_slope * step)
        curves[name] = [[float(a), float(np.clip(b, 0, 1))] for a, b in zip(knots, ys)]
    return {"matrix": M[:3].T.tolist(), "offset": M[3].tolist(), "curves": curves}
