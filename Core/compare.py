"""
Core.compare -- render-vs-reference verification tools (Blender + numpy only).

* :func:`edge_map`      fast geometric line render of the current camera:
  two emission-only override renders (object-id colours, normals) whose
  discontinuities give occlusion-correct silhouette and crease lines.
* :func:`overlay`       draws those lines (and reference edges) over the
  reference so misalignment is visible pixel by pixel.
* :func:`side_by_side`  and :func:`metrics` for the final look comparison.

All image IO goes through ``bpy.data.images`` so the tools run inside any
Blender build without extra packages.
"""
from __future__ import annotations

import os

import bpy
import numpy as np

from .nodes import Tree
from . import shaders as S

__all__ = ["load_image", "save_image", "edge_map", "overlay", "side_by_side", "metrics"]


# ------------------------------------------------------------------ image IO
def load_image(path, size=None):
    """Load an image as float32 RGB array (H, W, 3), sRGB-encoded values 0..1,
    top row first.  Optional ``size=(W, H)`` resamples (nearest/box)."""
    img = bpy.data.images.load(os.path.abspath(path), check_existing=False)
    w, h = img.size
    is_float = img.is_float
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    a = px.reshape(h, w, 4)[::-1, :, :3]
    if size and (w, h) != tuple(size):
        a = _resize(a, size)
    # byte images (png/jpg/webp) come back display-encoded already; float
    # images (exr) are scene-linear and get encoded for comparison
    return _lin_to_srgb(a) if is_float else a


def save_image(path, arr):
    arr = np.clip(arr, 0, 1).astype(np.float32)
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, -1)
    rgba = np.concatenate([arr, np.ones((h, w, 1), np.float32)], -1)
    img = bpy.data.images.new("__cmp_out", w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "sRGB"
    img.pixels.foreach_set(rgba[::-1].ravel())   # byte buffer: display values
    img.filepath_raw = os.path.abspath(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return path


def _srgb_to_lin(a):
    a = a.copy()
    c = a[..., :3]
    a[..., :3] = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return a


def _lin_to_srgb(c):
    c = np.clip(c, 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def _resize(a, size):
    W, H = size
    h, w = a.shape[:2]
    ys = (np.arange(H) + 0.5) * h / H
    xs = (np.arange(W) + 0.5) * w / W
    return a[ys.astype(int).clip(0, h - 1)][:, xs.astype(int).clip(0, w - 1)]


# ------------------------------------------------------------------ edges
def _gray(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def sobel_edges(a, thresh=0.12):
    g = _gray(a) if a.ndim == 3 else a
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1, :] = g[2:, :] - g[:-2, :]
    mag = np.hypot(gx, gy)
    return mag > thresh


def _override_material(kind):
    name = f"__override_{kind}"
    def build(t: Tree):
        if kind == "id":
            rnd = t.n("ShaderNodeObjectInfo")["Random"]
            col = t.n("ShaderNodeCombineColor", rnd, t.math("FRACT", rnd * 7.13),
                      t.math("FRACT", rnd * 13.7), props={"mode": "HSV"} if False else None).o
            return t.n("ShaderNodeEmission", col, 1.0)["Emission"]
        n = t.n("ShaderNodeNewGeometry")["Normal"]
        col = n * 0.5 + (0.5, 0.5, 0.5)
        return t.n("ShaderNodeEmission", col, 1.0)["Emission"]
    return S.material(name, build)


def edge_map(out_png=None, id_thresh=0.02, normal_thresh=0.18, hide=()):
    """Render occlusion-correct geometry lines for the active camera.

    Returns a boolean (H, W) array.  Objects whose names are in ``hide`` are
    excluded (e.g. glass or the exterior)."""
    sc = bpy.context.scene
    vl = sc.view_layers[0]
    saved = dict(engine=sc.render.engine, samples=sc.cycles.samples, denoise=sc.cycles.use_denoising,
                 bounces=sc.cycles.max_bounces, override=vl.material_override,
                 filepath=sc.render.filepath, view=sc.view_settings.view_transform,
                 look=sc.view_settings.look, comp=getattr(sc.render, "use_compositing", True),
                 film=sc.render.film_transparent, filt=sc.cycles.filter_width,
                 world=sc.world)
    hidden = []
    for ob in sc.objects:
        if ob.name in hide or any(ob.name.startswith(h) for h in hide):
            if not ob.hide_render:
                ob.hide_render = True
                hidden.append(ob)
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 0
    sc.cycles.filter_width = 0.01
    sc.view_settings.view_transform = "Standard"
    try:
        sc.view_settings.look = "None"
    except TypeError:
        pass
    try:
        sc.render.use_compositing = False
    except AttributeError:
        pass
    tmp = bpy.app.tempdir or "/tmp/"
    maps = {}
    for kind in ("id", "normal"):
        vl.material_override = _override_material(kind)
        p = os.path.join(tmp, f"__edge_{kind}.png")
        sc.render.filepath = p
        sc.render.image_settings.file_format = "PNG"
        bpy.ops.render.render(write_still=True)
        maps[kind] = load_image(p)
    # restore
    vl.material_override = saved["override"]
    sc.render.engine = saved["engine"]
    sc.cycles.samples = saved["samples"]
    sc.cycles.use_denoising = saved["denoise"]
    sc.cycles.max_bounces = saved["bounces"]
    sc.cycles.filter_width = saved["filt"]
    sc.view_settings.view_transform = saved["view"]
    try:
        sc.view_settings.look = saved["look"]
    except TypeError:
        pass
    try:
        sc.render.use_compositing = saved["comp"]
    except AttributeError:
        pass
    sc.render.filepath = saved["filepath"]
    for ob in hidden:
        ob.hide_render = False
    idm, nm = maps["id"], maps["normal"]
    e = np.zeros(idm.shape[:2], bool)
    for m, th in ((idm, id_thresh), (nm, normal_thresh)):
        dx = np.abs(np.diff(m, axis=1)).max(-1) > th
        dy = np.abs(np.diff(m, axis=0)).max(-1) > th
        e[:, 1:] |= dx
        e[1:, :] |= dy
    if out_png:
        save_image(out_png, e.astype(np.float32))
    return e


def overlay(ref, lines, out_png, ref_edges=True, dim=0.55, color=(1.0, 0.1, 0.05),
            ref_color=(0.0, 0.85, 1.0)):
    """Draw ``lines`` (bool HxW) in red over the dimmed reference (HxWx3);
    reference edges in cyan underneath."""
    base = ref * dim + (1 - dim) * 0.5 * _gray(ref)[..., None]
    out = base.copy()
    if ref_edges:
        re = sobel_edges(ref, 0.10)
        out[re] = out[re] * 0.3 + np.array(ref_color) * 0.7
    out[lines] = color
    save_image(out_png, out)
    return out_png


def side_by_side(a, b, out_png, gap=8):
    h = max(a.shape[0], b.shape[0])
    w = a.shape[1] + b.shape[1] + gap
    c = np.ones((h, w, 3), np.float32)
    c[:a.shape[0], :a.shape[1]] = a
    c[:b.shape[0], a.shape[1] + gap:] = b
    save_image(out_png, c)
    return out_png


def metrics(render, ref):
    """Simple global/regional error measures between two sRGB images."""
    d = np.abs(render - ref)
    out = {"mae": float(d.mean()), "mae_rgb": [float(x) for x in d.reshape(-1, 3).mean(0)]}
    H, W = ref.shape[:2]
    # 4x4 grid of regional mean-colour errors
    reg = []
    for j in range(4):
        row = []
        for i in range(4):
            y0, y1 = j * H // 4, (j + 1) * H // 4
            x0, x1 = i * W // 4, (i + 1) * W // 4
            row.append(float(np.abs(render[y0:y1, x0:x1].mean((0, 1)) - ref[y0:y1, x0:x1].mean((0, 1))).mean()))
        reg.append(row)
    out["regional_mean_err"] = reg
    # edge agreement: fraction of reference edges with a render edge within 2 px
    re = sobel_edges(ref, 0.12)
    ee = sobel_edges(render, 0.12)
    dil = ee.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            dil |= np.roll(np.roll(ee, dy, 0), dx, 1)
    out["edge_recall_2px"] = float((re & dil).sum() / max(re.sum(), 1))
    out["ssim"] = ssim(render, ref)
    return out


def ssim(a, b, r=4):
    """Mean structural similarity (luma, box window) -- sensitive to local
    contrast and detail, which mean colour errors ignore."""
    x, y = _gray(a).astype(np.float64), _gray(b).astype(np.float64)

    def bb(z):
        k = 2 * r + 1
        p = np.pad(z, r, mode="edge")
        c = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)
    mx, my = bb(x), bb(y)
    vx, vy, cxy = bb(x * x) - mx * mx, bb(y * y) - my * my, bb(x * y) - mx * my
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    s = ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2))
    return float(s.mean())
