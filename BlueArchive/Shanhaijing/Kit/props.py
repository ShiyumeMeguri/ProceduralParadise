"""
Shanhaijing props kit -- geometry-node groups (``SHJ.Prop.*``).

Tableware, porcelain, figurines, plants, guardian lions and lanterns.  Turned
objects (vases, bowls, teapot bodies) are lathed from designed profiles;
organic ones (plants, ivy, lions) are assembled procedurally with seeds, so
every instance can differ while staying in the same design language.
Local frames: origin at the centre of the footprint on the supporting
surface, Z up, "front" towards -Y.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, set_mode
from .architecture import flat_sweep, solid, STAND

TAU = math.tau


def lathe(g, pts, segments=40, scale=1.0):
    """Surface of revolution about Z from a profile [(r, z), ...] listed
    from the axis at the bottom, out, up and (optionally) back in.  ``scale``
    (constant or socket) multiplies the profile."""
    path = g.circle(1.0, segments)
    # Curve to Mesh along a unit circle: radius = 1 + profile x, z = -profile y
    prof = g.polyline([(r * scale - 1.0, z * scale * -1.0, 0.0) for r, z in pts])
    body = g.sweep(path, prof, False)
    return g.merge(g.n("GeometryNodeFlipFaces", body).o, 0.0005)


def ellipsoid(g, rx, ry, rz, seg=24, rings=16):
    s = g.n("GeometryNodeMeshUVSphere", Segments=seg, Rings=rings, Radius=1.0)["Mesh"]
    return g.transform(s, s=g.vec(rx, ry, rz))


# --------------------------------------------------------------- tableware
@asset("SHJ.Prop.Teapot", "Props")
def teapot():
    """Round brass teapot with a tall loop handle over the lid (the Shan tea
    house's signature pot), curved spout, domed lid and knob."""
    g = GN("SHJ.Prop.Teapot", teapot.__doc__)
    sc = g.inp("Scale", default=1.0)
    m = g.inp("Material", "MATERIAL")
    prof = [(0.0, 0.0), (0.05, 0.0), (0.056, 0.006), (0.075, 0.03), (0.088, 0.065), (0.085, 0.1),
            (0.07, 0.13), (0.045, 0.145), (0.043, 0.152), (0.0, 0.152)]
    body = lathe(g, prof, 40, sc)
    lid = lathe(g, [(0.0, 0.152), (0.042, 0.152), (0.035, 0.165), (0.018, 0.172), (0.012, 0.18),
                    (0.014, 0.19), (0.0, 0.195)], 32, sc)
    spout = g.polyline([(0.07, 0.0, 0.06), (0.1, 0.0, 0.08), (0.125, 0.0, 0.11), (0.14, 0.0, 0.135)])
    spout = g.transform(g.tube(spout, 0.011, 10, True), s=g.vec(sc, sc, sc))
    handle = g.polyline([(-0.06, 0.0, 0.13), (-0.07, 0.0, 0.2), (-0.035, 0.0, 0.25), (0.035, 0.0, 0.25),
                         (0.07, 0.0, 0.2), (0.06, 0.0, 0.13)])
    handle = g.fillet(handle, 0.04, 6)
    handle = g.transform(g.tube(handle, 0.006, 8, True), s=g.vec(sc, sc, sc))
    g.result(g.smooth(g.mat(g.join(body, lid, spout, handle), m), True))
    return g


@asset("SHJ.Prop.Cup", "Props")
def cup():
    """Small tea cup."""
    g = GN("SHJ.Prop.Cup", cup.__doc__)
    sc = g.inp("Scale", default=1.0)
    m = g.inp("Material", "MATERIAL")
    c = lathe(g, [(0.0, 0.0), (0.02, 0.0), (0.022, 0.006), (0.034, 0.045), (0.036, 0.05), (0.031, 0.05),
                  (0.018, 0.012), (0.0, 0.012)], 24, sc)
    g.result(g.smooth(g.mat(c, m), True))
    return g


@asset("SHJ.Prop.Tray", "Props")
def tray():
    """Round shallow tray."""
    g = GN("SHJ.Prop.Tray", tray.__doc__)
    r = g.inp("Radius", default=0.11, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    k = r / 0.11
    t = lathe(g, [(0.0, 0.0), (0.095, 0.0), (0.11, 0.018), (0.104, 0.019), (0.09, 0.006), (0.0, 0.006)],
              40, k)
    g.result(g.smooth_by_angle(g.mat(t, m), 0.8))
    return g


@asset("SHJ.Prop.SnackPlate", "Props")
def snack_plate():
    """White plate with a few round pastries."""
    g = GN("SHJ.Prop.SnackPlate", snack_plate.__doc__)
    r = g.inp("Radius", default=0.1, subtype="DISTANCE")
    n = g.inp("Count", "INT", default=4, min=0, max=8)
    seed = g.inp("Seed", "INT", default=0)
    m_plate = g.inp("Plate Material", "MATERIAL")
    m_food = g.inp("Food Material", "MATERIAL")
    k = r / 0.1
    plate = lathe(g, [(0.0, 0.0), (0.06, 0.0), (0.1, 0.012), (0.096, 0.014), (0.06, 0.005), (0.0, 0.005)],
                  36, k)
    pts = g.mesh_line(n, g.vec(r * -0.45, 0.0, r * 0.12), g.vec(r * 0.3, 0.0, 0.0))
    jit = g.random(-0.012, 0.012, seed, dtype="FLOAT_VECTOR")
    pts = g.set_pos(pts, offset=g.vmath("MULTIPLY", jit, (1.0, 1.0, 0.0)))
    ball = ellipsoid(g, 0.024, 0.024, 0.016, 12, 8)
    food = g.realize(g.iop(g.mesh_to_points(pts), ball, scale=g.vec(k, k, k)))
    g.result(g.join(g.smooth(g.mat(plate, m_plate), True), g.smooth(g.mat(food, m_food), True)))
    return g


# ---------------------------------------------------------------- porcelain
VASE_PROFILES = {
    # 0 meiping (梅瓶): broad shoulder, narrow foot, small mouth
    0: [(0.0, 0.0), (0.26, 0.0), (0.3, 0.1), (0.42, 0.55), (0.5, 0.78), (0.44, 0.9), (0.2, 0.96),
        (0.18, 1.0), (0.2, 1.02), (0.16, 1.02), (0.13, 0.96)],
    # 1 baluster / jar (罐)
    1: [(0.0, 0.0), (0.34, 0.0), (0.38, 0.06), (0.5, 0.35), (0.52, 0.55), (0.46, 0.8), (0.3, 0.92),
        (0.3, 1.0), (0.26, 1.0), (0.24, 0.94)],
    # 2 tall floor vase (flared mouth)
    2: [(0.0, 0.0), (0.3, 0.0), (0.34, 0.05), (0.44, 0.3), (0.46, 0.5), (0.38, 0.72), (0.26, 0.84),
        (0.3, 0.94), (0.38, 1.0), (0.35, 1.0), (0.24, 0.9)],
    # 3 squat jar with lid knob
    3: [(0.0, 0.0), (0.36, 0.0), (0.44, 0.12), (0.5, 0.4), (0.46, 0.66), (0.3, 0.78), (0.28, 0.84),
        (0.34, 0.86), (0.2, 0.96), (0.06, 1.0), (0.0, 1.0)],
    # 4 bottle vase (玉壶春)
    4: [(0.0, 0.0), (0.3, 0.0), (0.34, 0.05), (0.46, 0.3), (0.42, 0.5), (0.2, 0.7), (0.14, 0.86),
        (0.2, 1.0), (0.16, 1.0), (0.1, 0.86)],
}


@asset("SHJ.Prop.Vase", "Props")
def vase():
    """Porcelain vase lathed from one of several classic profiles
    (Shape 0 meiping, 1 baluster jar, 2 floor vase, 3 lidded jar, 4 bottle)
    scaled to Height x Width."""
    g = GN("SHJ.Prop.Vase", vase.__doc__)
    shape = g.inp("Shape", "INT", default=0, min=0, max=4)
    Hh = g.inp("Height", default=0.4, subtype="DISTANCE")
    Wd = g.inp("Width", default=0.25, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    shapes = []
    for k in range(5):
        shapes.append(lathe(g, VASE_PROFILES[k], 40, 1.0))
    v = g.index_switch(shape, shapes, "GEOMETRY")
    # profiles are unit height with radius ~0.5 -> scale
    v = g.transform(v, s=g.vec(Wd, Wd, Hh))
    g.result(g.smooth(g.mat(v, m), True))
    return g


@asset("SHJ.Prop.Bowl", "Props")
def bowl():
    """Porcelain bowl (Diameter across the rim)."""
    g = GN("SHJ.Prop.Bowl", bowl.__doc__)
    d = g.inp("Diameter", default=0.3, subtype="DISTANCE")
    h = g.inp("Height", default=0.1, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    b = lathe(g, [(0.0, 0.0), (0.2, 0.0), (0.22, 0.05), (0.36, 0.45), (0.48, 0.92), (0.5, 1.0),
                  (0.47, 1.0), (0.34, 0.5), (0.0, 0.2)], 36, 1.0)
    b = g.transform(b, s=g.vec(d, d, h))
    g.result(g.smooth(g.mat(b, m), True))
    return g


@asset("SHJ.Prop.Panda", "Props")
def panda():
    """Seated porcelain panda figurine (white body, dark-blue patches)."""
    g = GN("SHJ.Prop.Panda", panda.__doc__)
    Hh = g.inp("Height", default=0.5, subtype="DISTANCE")
    m_w = g.inp("White Material", "MATERIAL")
    m_k = g.inp("Dark Material", "MATERIAL")
    body = g.move(ellipsoid(g, 0.3, 0.26, 0.32), z=0.3)
    head = g.move(ellipsoid(g, 0.24, 0.21, 0.21), z=0.74)
    muzzle = g.move(ellipsoid(g, 0.09, 0.07, 0.06, 12, 8), 0.0, -0.18, 0.69)
    white = g.join(body, head, muzzle)
    ears = g.join(g.move(ellipsoid(g, 0.075, 0.05, 0.075, 12, 8), -0.17, 0.0, 0.92),
                  g.move(ellipsoid(g, 0.075, 0.05, 0.075, 12, 8), 0.17, 0.0, 0.92))
    eyes = g.join(g.move(ellipsoid(g, 0.06, 0.03, 0.075, 12, 8), -0.085, -0.19, 0.76),
                  g.move(ellipsoid(g, 0.06, 0.03, 0.075, 12, 8), 0.085, -0.19, 0.76))
    nose = g.move(ellipsoid(g, 0.03, 0.02, 0.02, 10, 6), 0.0, -0.245, 0.71)
    arms = g.join(g.transform(ellipsoid(g, 0.08, 0.08, 0.2, 12, 8), t=(-0.25, -0.1, 0.38), r=(0.3, 0.35, 0.0)),
                  g.transform(ellipsoid(g, 0.08, 0.08, 0.2, 12, 8), t=(0.25, -0.1, 0.38), r=(0.3, -0.35, 0.0)))
    legs = g.join(g.transform(ellipsoid(g, 0.1, 0.16, 0.09, 12, 8), t=(-0.16, -0.2, 0.08)),
                  g.transform(ellipsoid(g, 0.1, 0.16, 0.09, 12, 8), t=(0.16, -0.2, 0.08)))
    band = g.move(ellipsoid(g, 0.31, 0.27, 0.07, 24, 8), z=0.5)
    dark = g.join(ears, eyes, nose, arms, legs, band)
    geo = g.join(g.mat(white, m_w), g.mat(dark, m_k))
    geo = g.transform(geo, s=g.vec(Hh, Hh, Hh))
    g.result(g.smooth(geo, True))
    return g


# ------------------------------------------------------------------ plants
@asset("SHJ.Prop.Planter", "Props")
def planter():
    """Oval shallow porcelain planter with a mound of soil."""
    g = GN("SHJ.Prop.Planter", planter.__doc__)
    L = g.inp("Length", default=0.5, subtype="DISTANCE")
    Wd = g.inp("Width", default=0.3, subtype="DISTANCE")
    Hh = g.inp("Height", default=0.16, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    m_soil = g.inp("Soil Material", "MATERIAL")
    pot = lathe(g, [(0.0, 0.0), (0.36, 0.0), (0.4, 0.1), (0.49, 0.7), (0.5, 0.95), (0.52, 1.0),
                    (0.47, 1.0), (0.45, 0.85)], 40, 1.0)
    pot = g.transform(pot, s=g.vec(L, Wd, Hh))
    soil = g.transform(ellipsoid(g, 0.46, 0.46, 0.12, 24, 8), t=g.vec(0.0, 0.0, Hh * 0.8), s=g.vec(L, Wd, Hh))
    g.result(g.join(g.smooth(g.mat(pot, m), True), g.mat(soil, m_soil)))
    return g


def _leaf(g, w=0.05, l=0.08):
    """Single leaf card: a pointed oval, lying in XY, stem at the origin
    pointing +X."""
    pts = [(0.0, 0.0, 0.0), (l * 0.3, w * 0.5, 0.0), (l * 0.75, w * 0.35, 0.0), (l, 0.0, 0.0),
           (l * 0.75, -w * 0.35, 0.0), (l * 0.3, -w * 0.5, 0.0)]
    return g.fill(g.polyline(pts, cyclic=True))


@asset("SHJ.Prop.Ivy", "Props")
def ivy():
    """Trailing ivy spilling from a planter: a rosette of runners that arch
    out and hang down (Drop), clad in leaves.  Origin at the planter top."""
    g = GN("SHJ.Prop.Ivy", ivy.__doc__)
    n = g.inp("Runners", "INT", default=9, min=1)
    spread = g.inp("Spread", default=0.3, subtype="DISTANCE")
    drop = g.inp("Drop", default=0.45, subtype="DISTANCE")
    leaf_s = g.inp("Leaf Size", default=0.07, subtype="DISTANCE")
    seed = g.inp("Seed", "INT", default=0)
    m = g.inp("Material", "MATERIAL")
    # runners: instance a template arc around Z with random length/angle
    arc = g.polyline([(0.0, 0.0, 0.03), (0.35, 0.0, 0.1), (0.7, 0.0, 0.05), (0.9, 0.0, -0.3),
                      (1.0, 0.0, -0.7), (1.02, 0.0, -1.0)])
    arc = g.resample(arc, 24)
    base = g.mesh_line(n, (0, 0, 0), (0, 0, 0))
    ang = g.index() * (TAU / 1.0) / g.math("MAXIMUM", n, 1.0) + g.random(-0.4, 0.4, seed)
    rnd = g.random(0.5, 1.1, seed + 3)
    rnd_d = g.random(0.2, 1.1, seed + 5)
    runners = g.iop(g.mesh_to_points(base), arc, rot=g.vec(0.0, 0.0, ang),
                    scale=g.vec(spread * rnd, spread * rnd, drop * rnd_d))
    runners = g.realize(runners)
    # leaves along the runners
    pts = g.n("GeometryNodeCurveToPoints", runners, props={"mode": "COUNT"}, Count=14)
    pts_o = pts["Points"]
    lrot = g.random(-3.1416, 3.1416, seed + 7, dtype="FLOAT_VECTOR")
    lsc = g.random(0.6, 1.2, seed + 9)
    leaves = g.iop(pts_o, _leaf(g, 0.6, 0.9), rot=lrot, scale=g.vec(leaf_s * lsc, leaf_s * lsc, leaf_s * lsc))
    stems = g.tube(runners, 0.003, 4, False)
    g.result(g.mat(g.join(g.realize(leaves), stems), m))
    return g


@asset("SHJ.Prop.Bush", "Props")
def bush():
    """Round leafy shrub (dense clipped foliage ball) on a short stem."""
    g = GN("SHJ.Prop.Bush", bush.__doc__)
    r = g.inp("Radius", default=0.2, subtype="DISTANCE")
    Hh = g.inp("Height", default=0.35, subtype="DISTANCE", desc="centre height of the foliage")
    dens = g.inp("Density", default=260.0)
    seed = g.inp("Seed", "INT", default=0)
    m = g.inp("Material", "MATERIAL")
    ball = g.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=2)["Mesh"]
    ball = g.transform(ball, t=g.vec(0.0, 0.0, Hh), s=g.vec(r, r, r * 0.9))
    pts = g.n("GeometryNodeDistributePointsOnFaces", ball, Density=dens, Seed=seed,
              props={"distribute_method": "RANDOM"})
    rot = g.random(-3.1416, 3.1416, seed + 1, dtype="FLOAT_VECTOR")
    sc = g.random(0.6, 1.1, seed + 2)
    leaves = g.iop(pts["Points"], _leaf(g, 0.5, 0.9), rot=rot, scale=g.vec(sc * 0.07, sc * 0.07, sc * 0.07))
    core = g.transform(ball, s=(0.85, 0.85, 0.85))
    stem = g.rod((0.0, 0.0, 0.0), g.vec(0.0, 0.0, Hh), 0.012, 6)
    g.result(g.mat(g.join(g.realize(leaves), core, stem), m))
    return g


@asset("SHJ.Prop.Grass", "Props")
def grass():
    """Tall ornamental grass / young bamboo tuft: long narrow arching blades
    fanning out of a pot."""
    g = GN("SHJ.Prop.Grass", grass.__doc__)
    n = g.inp("Blades", "INT", default=26, min=1)
    Hh = g.inp("Height", default=1.2, subtype="DISTANCE")
    spread = g.inp("Spread", default=0.35, subtype="DISTANCE")
    bw = g.inp("Blade Width", default=0.018, subtype="DISTANCE")
    seed = g.inp("Seed", "INT", default=0)
    m = g.inp("Material", "MATERIAL")
    # one blade: a flat strip arching out along +X, tapering to a point
    strip = g.grid(1.0, 1.0, 2, 14)
    gx, gy, _ = g.sep(g.position())
    t = gy + 0.5
    blade_m = g.set_pos(strip, pos=g.vec(t * t * 0.6, gx * (1.0 - t * 0.92), t * (2.0 - t)))
    base = g.mesh_line(n, (0, 0, 0), (0, 0, 0))
    ang = g.random(0.0, 6.2832, seed)
    tilt = g.random(0.2, 1.0, seed + 1)
    hs = g.random(0.6, 1.05, seed + 2)
    blades = g.iop(g.mesh_to_points(base), blade_m, rot=g.vec(0.0, 0.0, ang),
                   scale=g.vec(spread * tilt, bw, Hh * hs))
    g.result(g.smooth(g.mat(g.realize(blades), m), True))
    return g


# ------------------------------------------------------------------- lions
@asset("SHJ.Prop.Lion", "Props")
def lion():
    """Seated guardian lion (石狮) in pale stone: haunches, chest, curly
    mane, big head with brows and open mouth, one fore-paw raised on a ball.
    Height is the overall height; Mirror flips the raised paw side."""
    g = GN("SHJ.Prop.Lion", lion.__doc__)
    Hh = g.inp("Height", default=1.0, subtype="DISTANCE")
    mir = g.inp("Mirror", "BOOL", default=False)
    m = g.inp("Material", "MATERIAL")
    parts = [
        g.move(ellipsoid(g, 0.2, 0.26, 0.2), 0.0, 0.08, 0.2),            # haunches
        g.transform(ellipsoid(g, 0.17, 0.16, 0.27), t=(0.0, -0.04, 0.42), r=(0.25, 0.0, 0.0)),  # chest
        g.move(ellipsoid(g, 0.23, 0.2, 0.2), 0.0, -0.06, 0.7),           # mane
        g.move(ellipsoid(g, 0.19, 0.17, 0.17), 0.0, -0.13, 0.76),        # head
        g.move(ellipsoid(g, 0.11, 0.08, 0.08, 16, 10), 0.0, -0.27, 0.71),  # muzzle
        g.move(ellipsoid(g, 0.08, 0.05, 0.035, 12, 8), 0.0, -0.3, 0.64),   # jaw
        g.move(ellipsoid(g, 0.16, 0.06, 0.05, 16, 8), 0.0, -0.24, 0.83),   # brows
        g.transform(ellipsoid(g, 0.055, 0.06, 0.22, 12, 10), t=(-0.1, -0.16, 0.22), r=(0.15, 0.0, 0.0)),  # foreleg
        g.move(ellipsoid(g, 0.07, 0.09, 0.05, 12, 8), -0.1, -0.22, 0.04),  # paw
        g.transform(ellipsoid(g, 0.055, 0.06, 0.16, 12, 10), t=(0.11, -0.2, 0.28), r=(0.7, 0.0, 0.0)),  # raised leg
        g.move(g.n("GeometryNodeMeshUVSphere", Segments=20, Rings=12, Radius=0.08)["Mesh"], 0.12, -0.27, 0.12),  # ball
        g.move(ellipsoid(g, 0.08, 0.14, 0.06, 12, 8), -0.17, 0.02, 0.05),  # hind paw
        g.move(ellipsoid(g, 0.08, 0.14, 0.06, 12, 8), 0.17, 0.02, 0.05),
        g.transform(ellipsoid(g, 0.05, 0.12, 0.05, 12, 8), t=(0.0, 0.3, 0.3), r=(-0.9, 0.0, 0.0)),  # tail
        g.move(ellipsoid(g, 0.05, 0.035, 0.06, 10, 8), -0.14, -0.08, 0.9),  # ears
        g.move(ellipsoid(g, 0.05, 0.035, 0.06, 10, 8), 0.14, -0.08, 0.9),
    ]
    body = g.join(*parts)
    # mane curls: little knobs scattered on the mane/head back
    mane = g.move(ellipsoid(g, 0.22, 0.19, 0.19), 0.0, -0.04, 0.72)
    pts = g.n("GeometryNodeDistributePointsOnFaces", mane, Seed=3,
              props={"distribute_method": "POISSON"}, Distance_Min=0.035, Density_Max=900.0)
    front = g.compare(g.sep(g.position())[1], -0.15, "GREATER_THAN")
    curl = g.n("GeometryNodeMeshUVSphere", Segments=8, Rings=6, Radius=0.024)["Mesh"]
    curls = g.realize(g.iop(pts["Points"], curl, sel=front))
    geo = g.join(body, curls)
    geo = g.switch(mir, geo, g.n("GeometryNodeFlipFaces", g.transform(geo, s=(-1.0, 1.0, 1.0))).o)
    geo = g.transform(geo, s=g.vec(Hh, Hh, Hh))
    g.result(g.smooth(g.mat(geo, m), True))
    return g


# ---------------------------------------------------------------- lanterns
@asset("SHJ.Prop.Lantern", "Props")
def lantern():
    """Round red silk lantern: ribbed glowing body, gold top and bottom caps
    with rings, a gold 'fu' medallion front and back, and a tassel.  Origin
    at the top of the cap (hanging point), body below."""
    g = GN("SHJ.Prop.Lantern", lantern.__doc__)
    D = g.inp("Diameter", default=0.6, subtype="DISTANCE")
    Hr = g.inp("Height Ratio", default=0.82)
    tassel = g.inp("Tassel", "BOOL", default=True)
    m_paper = g.inp("Paper Material", "MATERIAL")
    m_gold = g.inp("Gold Material", "MATERIAL")
    m_tassel = g.inp("Tassel Material", "MATERIAL")
    r = D * 0.5
    bh = D * Hr
    cap_h = D * 0.16
    cap_r = D * 0.26
    body = ellipsoid(g, 1.0, 1.0, 1.0, 32, 20)
    body = g.transform(body, t=g.vec(0.0, 0.0, cap_h * -1.0 - bh * 0.5 + 0.02),
                       s=g.vec(r, r, bh * 0.5))
    top = g.cylinder(cap_r, cap_h, 32)
    top = g.move(top, z=cap_h * -0.5)
    bot = g.move(g.cylinder(cap_r, cap_h, 32), z=cap_h * -1.5 - bh + 0.04)
    rings = g.join(g.move(g.cylinder(cap_r + 0.01, 0.012, 32), z=cap_h * -0.12),
                   g.move(g.cylinder(cap_r + 0.01, 0.012, 32), z=cap_h * -0.88),
                   g.move(g.cylinder(cap_r + 0.01, 0.012, 32), z=cap_h * -1.12 - bh + 0.04),
                   g.move(g.cylinder(cap_r + 0.01, 0.012, 32), z=cap_h * -1.88 - bh + 0.04))
    # 'fu' medallion: a rotated square frame with a cross-hatched centre
    med = g.join(flat_sweep(g, g.transform(g.rect(1.0, 1.0), r=(0.0, 0.0, math.pi / 4.0)), 0.07, 0.02),
                 flat_sweep(g, g.rect(0.36, 0.36), 0.06, 0.02),
                 g.box(-0.2, -0.03, -0.01, 0.2, 0.03, 0.01), g.box(-0.03, -0.2, -0.01, 0.03, 0.2, 0.01))
    med = g.transform(med, r=STAND)
    zc = cap_h * -1.0 - bh * 0.5 + 0.02
    med = g.transform(med, t=g.vec(0.0, 0.0, zc), s=g.vec(D * 0.22, 0.5, D * 0.22))
    # wrap onto the ellipsoidal body: y from the surface equation
    mx, my, mz = g.sep(g.position())
    k = 1.0 - (mx / r) * (mx / r) - ((mz - zc) / (bh * 0.5)) * ((mz - zc) / (bh * 0.5))
    ys = r * g.math("SQRT", g.max(k, 0.0))
    front = g.set_pos(med, pos=g.vec(mx, ys * -1.0 - 0.004 + my, mz))
    back = g.transform(front, s=(1.0, -1.0, 1.0))
    medals = g.join(front, g.n("GeometryNodeFlipFaces", back).o)
    tas = g.join(g.rod(g.vec(0.0, 0.0, cap_h * -2.0 - bh + 0.04), g.vec(0.0, 0.0, cap_h * -2.0 - bh - D * 0.12),
                       0.006, 6),
                 g.move(g.cylinder(D * 0.035, D * 0.45, 12), z=cap_h * -2.0 - bh - D * 0.35))
    tas = g.switch(tassel, None, tas)
    geo = g.join(g.smooth(g.mat(body, m_paper), True), g.mat(g.join(top, bot, rings, medals), m_gold),
                 g.mat(tas, m_tassel))
    g.result(geo)
    return g


@asset("SHJ.Prop.LanternString", "Props")
def lantern_string():
    """A cord hanging from the origin with Count lanterns stacked below it,
    starting Drop below the hanging point and Pitch apart."""
    g = GN("SHJ.Prop.LanternString", lantern_string.__doc__)
    cnt = g.inp("Count", "INT", default=3, min=1)
    D = g.inp("Diameter", default=0.6, subtype="DISTANCE")
    drop = g.inp("Drop", default=0.6, subtype="DISTANCE")
    pitch = g.inp("Pitch", default=0.7, subtype="DISTANCE")
    m_paper = g.inp("Paper Material", "MATERIAL")
    m_gold = g.inp("Gold Material", "MATERIAL")
    m_cord = g.inp("Cord Material", "MATERIAL")
    lan = g.group(get_asset("SHJ.Prop.Lantern"), Diameter=D, Tassel=False, Paper_Material=m_paper,
                  Gold_Material=m_gold, Tassel_Material=m_cord).o
    pts = g.mesh_line(cnt, g.vec(0.0, 0.0, drop * -1.0), g.vec(0.0, 0.0, pitch * -1.0))
    lans = g.realize(g.iop(g.mesh_to_points(pts), lan))
    bottom = drop + pitch * (cnt - 1.0) + D * 0.9
    cord = g.rod((0.0, 0.0, 0.0), g.vec(0.0, 0.0, bottom * -1.0), 0.005, 6)
    tas = g.move(g.cylinder(D * 0.035, D * 0.45, 12), z=bottom * -1.0 - D * 0.2)
    g.result(g.join(lans, g.mat(g.join(cord, tas), m_cord)))
    return g


# ------------------------------------------------------------- merchandise
@asset("SHJ.Prop.Box", "Props")
def box_prop():
    """Tea box / gift box: body with a contrasting lid band."""
    g = GN("SHJ.Prop.Box", box_prop.__doc__)
    sx = g.inp("Size X", default=0.2, subtype="DISTANCE")
    sy = g.inp("Size Y", default=0.2, subtype="DISTANCE")
    sz = g.inp("Size Z", default=0.25, subtype="DISTANCE")
    lid = g.inp("Lid", default=0.3, desc="lid band height as a fraction")
    m = g.inp("Material", "MATERIAL")
    m_lid = g.inp("Lid Material", "MATERIAL")
    body = g.box(sx * -0.5, sy * -0.5, 0.0, sx * 0.5, sy * 0.5, sz * (1.0 - lid))
    top = g.box(sx * -0.51, sy * -0.51, sz * (1.0 - lid), sx * 0.51, sy * 0.51, sz)
    g.result(g.join(g.mat(body, m), g.mat(top, m_lid)))
    return g


@asset("SHJ.Prop.Tablet", "Props")
def tablet():
    """Menu tablet on a small stand, screen facing -Y."""
    g = GN("SHJ.Prop.Tablet", tablet.__doc__)
    w = g.inp("Width", default=0.24, subtype="DISTANCE")
    h = g.inp("Height", default=0.32, subtype="DISTANCE")
    m = g.inp("Screen Material", "MATERIAL")
    m_b = g.inp("Body Material", "MATERIAL")
    scr = g.box(w * -0.5, -0.004, 0.0, w * 0.5, 0.004, h)
    scr = g.transform(scr, r=(-0.35, 0.0, 0.0))
    stand = g.box(-0.04, -0.02, 0.0, 0.04, 0.08, 0.01)
    g.result(g.join(g.mat(scr, m), g.mat(stand, m_b)))
    return g
