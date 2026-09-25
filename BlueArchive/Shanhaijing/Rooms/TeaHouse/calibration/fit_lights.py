"""
Light balancing as an inverse problem.

Light transport is linear in the light intensities, so the room is rendered
once with every fixture family in its own Cycles *light group*; any balance
of the families is then  sum_g w_g * I_g.  The non-negative weights w_g are
solved so that this sum, after the Standard view transform (sRGB encoding,
clipping at white), reproduces the painting: a robust (Charbonnier) error on
downsampled, slightly blurred display values, optimised over log-weights
with L-BFGS, a weak prior keeping every weight near 1.

    python BlueArchive/Shanhaijing/Rooms/TeaHouse/calibration/fit_lights.py [--samples 64] [--scale 0.5] [--apply]

Prints the weights; ``--apply`` multiplies them into room.json (light and
downlight powers, the lantern lights) and into the emissive look parameters
of the shot (lanterns, downlight discs, courtyard globes, backdrop...), so a
fit is one command.  Render ungraded (the grade is refitted afterwards with
fit_grade.py).  Development tool: needs numpy + scipy + OpenCV (the scene
build itself does not).
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
SHOT = os.path.join(ROOM, "shots", "BG_ShanTeaHouse_Night.json")
REF = os.path.join(ROOM, "Reference", "BG_ShanTeaHouse_Night.webp")

# emissive look parameters (shot "materials") that belong to a family
EMISSIVE = {"lanterns": ["lantern_emission", "lantern_gold_emission"], "backdrop": ["backdrop_strength"],
            "backdrop_bay": ["bay_backdrop_strength"],
            "globes": ["globe_emission"], "counter": ["gift_glow"], "logo": ["cloud_glow"],
            "timber_dl": ["downlight_emission"]}
EMISSIVE_DEFAULTS = {"lantern_emission": 1.0, "lantern_gold_emission": 0.3, "backdrop_strength": 0.5,
                     "bay_backdrop_strength": 1.5,
                     "globe_emission": 12.0, "gift_glow": 0.4, "cloud_glow": 0.35, "downlight_emission": 40.0}
NAMED = {"WallWasher": "washers", "LanternLight": "lanterns", "CounterLight": "counter",
         "LogoWash": "logo", "ArchitraveUplight": "arch_up", "GardenLamp": "garden",
         "CourtyardLamp": "globes", "CourtyardWall": "backdrop", "BayBackdrop": "backdrop_bay",
         "FrontPanel": "front_fill",
         "LeftWindowFill": "left_window", "GiftBox": "counter", "MenuTablet": "counter", "LogoWall": "logo"}


def family(base, x, y, z):
    """Fixture family of a light / emissive object named ``base`` at (x, y, z)
    in the room frame (None = not a light source)."""
    if base in ("DownlightSpot", "Downlight"):             # the spot and its glowing disc
        if z > 5.8:                                        # concealed plaster-ceiling spots
            return "plaster_dl_R" if x > 9.65 else ("plaster_dl_F" if y < 5 else ("plaster_dl_M" if y < 8 else "plaster_dl_B"))
        return "timber_dl" if x < 9.65 else "right_dl"
    if base == "PanelWash":
        return "panel_L" if x < 3.5 else ("shelf" if x < 9.0 else ("panel_M" if x < 14.0 else "panel_R"))
    if base == "BeamUplight":
        return "beam_up_L" if x < 3.0 else ("beam_up_M" if x < 10.0 else "beam_up_R")
    if base == "BounceUp":
        return "bounce_R" if x > 9.65 else ("bounce_F" if y < 9 else ("bounce_M" if y < 13 else "bounce_B"))
    if base == "FillDown":
        return "fill_R" if x > 9.65 else ("fill_F" if y < 9 else ("fill_M" if y < 13 else "fill_B"))
    if base.startswith("Lanterns"):
        return "lanterns"
    return NAMED.get(base)


def group_of(ob):
    """Family of a scene object (the room root sits at the world origin)."""
    n = ob.name
    if not n.startswith(PREFIX):
        return None
    t = ob.matrix_world.translation
    return family(n[len(PREFIX):].split(".")[0], t.x, t.y, t.z)


def _load_exr(path):
    import bpy
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1, :, :3]


def render_groups(samples=64, scale=0.5):
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
            items.new("RGBA", g)
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


def _srgb(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 1e-8), 1.0 / 2.4) - 0.055)


def fit(imgs, ref, size=(320, 225), blur=1.5, fixed=("world",), prior=0.002, iters=300):
    """Display-space fit.  ``imgs``: {family: linear HxWx3}, ``ref``: sRGB
    image of the same size.  Returns {family: weight}."""
    import cv2
    from scipy.optimize import minimize

    def prep(a):
        a = cv2.resize(a.astype(np.float32), size, interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(a, (0, 0), blur)

    names = sorted(imgs)
    free = [n for n in names if n not in fixed]
    A = np.stack([prep(imgs[n]) for n in free], 0)
    base = sum(prep(imgs[n]) for n in fixed if n in imgs)
    R = prep(ref)

    def f(lx):
        w = np.exp(lx)
        C = np.maximum(base + np.tensordot(w, A, 1), 0.0)
        S = np.minimum(_srgb(C), 1.0)
        r = S - R
        e = np.sqrt(r * r + 1e-4)                             # Charbonnier
        dS = np.where(C <= 0.0031308, 12.92, 1.055 / 2.4 * np.power(np.maximum(C, 1e-8), 1.0 / 2.4 - 1.0))
        dS = np.where(S >= 1.0, 0.0, dS)
        gi = (r / e) * dS / r.size
        grad = np.array([(gi * A[i]).sum() for i in range(len(free))]) * w + 2.0 * prior * lx / len(free)
        return e.mean() + prior * np.mean(lx ** 2), grad

    res = minimize(f, np.zeros(len(free)), jac=True, method="L-BFGS-B", bounds=[(-9.0, 4.0)] * len(free),
                   options={"maxiter": iters})
    out = dict(zip(free, (float(v) for v in np.exp(res.x))))
    for n in fixed:
        out[n] = 1.0
    return out


def apply(weights):
    """Multiply the weights into room.json and the shot's emissive parameters."""
    from Core.jsonio import dump
    path = os.path.join(ROOM, "room.json")
    with open(path, encoding="utf-8") as fh:
        R = json.load(fh)
    for l in R.get("lights", []):
        g = family(l["name"], *l["loc"])
        if g in weights:
            l["power"] = round(l["power"] * weights[g], 3)
    for d in R.get("downlights", {}).get("sets", []):
        x, y, z = d["at"][0]
        g = family("DownlightSpot", x, y, z - 0.02)
        if g in weights:
            d["power"] = round(d["power"] * weights[g], 3)
    if "lanterns" in weights and "light_power" in R.get("lanterns", {}):
        R["lanterns"]["light_power"] = round(R["lanterns"]["light_power"] * weights["lanterns"], 4)
    dump(R, path)
    with open(SHOT, encoding="utf-8") as fh:
        shot = json.load(fh)
    mats = shot.setdefault("materials", {})
    for g, keys in EMISSIVE.items():
        if g in weights:
            for k in keys:
                mats[k] = round(mats.get(k, EMISSIVE_DEFAULTS[k]) * weights[g], 4)
    dump(shot, SHOT)


def main(argv):
    from Core import compare as C
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
    scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.5
    imgs = render_groups(samples, scale)
    h, w = next(iter(imgs.values())).shape[:2]
    weights = fit(imgs, C.load_image(REF, size=(w, h)))
    print(json.dumps({k: round(v, 3) for k, v in sorted(weights.items())}, indent=1))
    np.savez_compressed(os.path.join(tempfile.gettempdir(), "shj_lightgroups.npz"), **imgs)
    if "--apply" in argv:
        apply(weights)
        print("weights applied to room.json and", os.path.basename(SHOT))
    return weights


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
