"""
Light balancing as a linear inverse problem.

Light transport is linear in the light intensities, so the room is rendered
once with every fixture family in its own Cycles *light group*; the
per-group images I_g are then combined as  sum_g w_g * I_g  and the
non-negative weights w_g that best reproduce the painting (in linear light,
blurred to be tolerant of small misalignments) are solved with NNLS.

    python BlueArchive/Shanhaijing/Rooms/TeaHouse/calibration/fit_lights.py [--samples 24] [--scale 0.5] [--apply]

Prints the weights; ``--apply`` multiplies the corresponding light powers in
room.json (and the emissive look parameters in the shot) by them.
Development tool: needs numpy + scipy (the scene build itself does not).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOM = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(ROOM, "..", "..", "..", ".."))
for p in (ROOT, os.path.join(ROOT, "BlueArchive")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

PREFIX = "TeaHouse."


def group_of(ob):
    """Fixture family of a light / emissive object (None = not a source)."""
    n = ob.name
    if not n.startswith(PREFIX):
        return None
    base = n[len(PREFIX):].split(".")[0]
    z = ob.matrix_world.translation.z
    x = ob.matrix_world.translation.x
    if base in ("DownlightSpot", "Downlight"):          # the spot and its glowing disc
        return "plaster_dl" if z > 5.8 else ("timber_dl" if x < 9.65 else "right_dl")
    if base == "PanelWash":
        return "panel_L" if x < 3.5 else ("shelf" if x < 9.0 else ("panel_M" if x < 14.0 else "panel_R"))
    table = {"WallWasher": "washers", "LanternLight": "lanterns", "CounterLight": "counter",
             "LogoWash": "logo", "ArchitraveUplight": "arch_up",
             "GardenLamp": "garden", "CourtyardLamp": "globes", "CourtyardWall": "backdrop",
             "FrontPanel": "front_fill", "GiftBox": "counter", "MenuTablet": "counter", "LogoWall": "logo"}
    if base.startswith("Lanterns"):
        return "lanterns"
    if base == "BeamUplight":
        return "beam_up_L" if x < 3.0 else ("beam_up_M" if x < 10.0 else "beam_up_R")
    if base == "FillDown":
        y = ob.matrix_world.translation.y
        return "fill_R" if x > 9.65 else ("fill_F" if y < 9 else ("fill_M" if y < 13 else "fill_B"))
    if base == "BounceUp":
        y = ob.matrix_world.translation.y
        return "bounce_R" if x > 9.65 else ("bounce_F" if y < 9 else ("bounce_M" if y < 13 else "bounce_B"))
    return table.get(base)


def _load_exr(path):
    import bpy
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1, :, :3]


def render_groups(samples=24, scale=0.5):
    import bpy
    import build as B
    args = B.parse(["x", "Shanhaijing/Rooms/TeaHouse", "--no-save", "--no-look", "--animation", "none",
                    "--samples", str(samples)])
    ctx = B.build(args)
    B.activate_still(ctx)
    sc = bpy.context.scene
    sc.render.resolution_percentage = int(scale * 100)
    vl = sc.view_layers[0]
    bpy.context.view_layer.update()          # world matrices of parented lights
    groups = set()
    for ob in sc.objects:
        g = group_of(ob)
        if g:
            ob.lightgroup = g
            groups.add(g)
    if sc.world:
        sc.world.lightgroup = "world"
        groups.add("world")
    for g in sorted(groups):
        if g not in [lg.name for lg in vl.lightgroups]:
            vl.lightgroups.add(name=g)
    # compositor: render layer lightgroup passes -> one float EXR each
    tmp = tempfile.mkdtemp(prefix="shj_lg_")
    ng = bpy.data.node_groups.new("LG", "CompositorNodeTree")
    if hasattr(sc, "compositing_node_group"):
        sc.compositing_node_group = ng
    else:
        sc.use_nodes = True
        ng = sc.node_tree
        ng.nodes.clear()
    rl = ng.nodes.new("CompositorNodeRLayers")
    fo = ng.nodes.new("CompositorNodeOutputFile")
    if hasattr(fo, "directory"):
        fo.directory = tmp
        fo.file_name = ""
    else:
        fo.base_path = tmp + os.sep
    if hasattr(fo.format, "media_type"):
        fo.format.media_type = "IMAGE"
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    items = getattr(fo, "file_output_items", None)
    for g in sorted(groups):
        sock = next((s for s in rl.outputs if s.name.endswith(g) and getattr(s, "enabled", True)), None)
        if sock is None:
            sock = next(s for s in rl.outputs if g in s.name)
        if items is not None:
            it = items.new("RGBA", g)
            dst = fo.inputs[g]
        else:
            fo.file_slots.new(g)
            dst = fo.inputs[-1]
        ng.links.new(sock, dst)
    try:
        sc.render.use_compositing = True
    except AttributeError:
        pass
    sc.render.filepath = os.path.join(tmp, "combined.png")
    bpy.ops.render.render(write_still=True)
    imgs = {}
    for f in os.listdir(tmp):
        for g in groups:
            if f.startswith(g) and f.endswith(".exr"):
                imgs[g] = _load_exr(os.path.join(tmp, f))
    return imgs


def fit(imgs, ref_path, blur=3, fixed=("world",), prior=0.02, rel=0.08):
    """NNLS for the group weights.  ``fixed`` groups keep weight 1; a ridge
    prior pulls weights towards 1 (``prior`` relative to the data term) and
    residuals are weighted by 1 / (reference + ``rel``), i.e. roughly a
    relative (log-like) error so dark and bright areas count alike."""
    import cv2
    from scipy.optimize import nnls
    from Core import compare as C
    names = sorted(imgs)
    h, w = imgs[names[0]].shape[:2]
    ref = C.load_image(ref_path, size=(w, h))
    ref_lin = np.where(ref <= 0.04045, ref / 12.92, ((ref + 0.055) / 1.055) ** 2.4)

    def prep(a):
        return cv2.GaussianBlur(a.astype(np.float32), (0, 0), blur).reshape(-1)

    b = prep(ref_lin)
    for n in fixed:
        if n in imgs:
            b = b - prep(imgs[n])
    free = [n for n in names if n not in fixed]
    A = np.stack([prep(imgs[n]) for n in free], 1)
    wgt = 1.0 / (prep(ref_lin) + rel)
    A = A * wgt[:, None]
    b = b * wgt
    lam = np.sqrt(prior * float((A ** 2).sum()) / len(free))
    A2 = np.vstack([A, lam * np.eye(len(free))])
    b2 = np.concatenate([b, lam * np.ones(len(free))])
    x, _ = nnls(A2, b2, maxiter=5000)
    out = dict(zip(free, x))
    for n in fixed:
        out[n] = 1.0
    return out


def main(argv):
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 24
    scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.5
    imgs = render_groups(samples, scale)
    w = fit(imgs, os.path.join(ROOM, "Reference", "BG_ShanTeaHouse_Night.webp"))
    print(json.dumps({k: round(float(v), 3) for k, v in w.items()}, indent=1))
    np.savez_compressed(os.path.join(tempfile.gettempdir(), "shj_lightgroups.npz"), **imgs)
    return w


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
