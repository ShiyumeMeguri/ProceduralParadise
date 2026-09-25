"""
Kivotos procedural city.

* ``KIV.CityBlocks``   -- fills a square district with block buildings on a
  street grid (heights from noise 'downtown' clusters), leaving a clear radius
  around a campus.
* ``KIV.Tower``        -- parametric high-rise (box or cylinder) with facade
  fins and a crown, for hero buildings placed from campus data.
* ``KIV.Arena``        -- round banded building (the dome/arena seen from
  Millennium).
* ``facade_material``  -- window-grid facade shader with distance haze.
"""
from __future__ import annotations

import math

import bpy

from Core import shaders as S
from Core.nodes import Tree
from Core.gn import GN, asset


# ----------------------------------------------------------------- materials
def facade_material(name, glass=(0.45, 0.72, 0.95), frame=(0.88, 0.92, 0.96),
                    floor_h=4.0, bay_w=3.2, glass_ratio=0.72, band_ratio=0.62,
                    haze=(0.75, 0.9, 1.0), haze_dist=2600.0, glow=0.35, vertical=False,
                    roof=(0.56, 0.61, 0.66)):
    """Window-grid facade.  ``vertical`` -> strip windows (vertical fins);
    upward faces get the ``roof`` colour (plant decks, not facade)."""
    def build(t: Tree):
        P = t.n("ShaderNodeTexCoord")["Object"]
        N = t.n("ShaderNodeNewGeometry")["True Normal"]
        px, py, pz = t.sep(P)
        nx, ny, nz = t.sep(N)
        horiz = t.mix(t.map_range(t.abs(nx), 0.4, 0.6, 0.0, 1.0), px, py)
        fu = t.math("FRACT", horiz / bay_w)
        fv = t.math("FRACT", pz / floor_h)
        if vertical:
            win = t.map_range(t.abs(fu - 0.5), glass_ratio * 0.5, glass_ratio * 0.5 + 0.02, 1.0, 0.0)
        else:
            wu = t.map_range(t.abs(fu - 0.5), glass_ratio * 0.5, glass_ratio * 0.5 + 0.02, 1.0, 0.0)
            wv = t.map_range(t.abs(fv - 0.5), band_ratio * 0.5, band_ratio * 0.5 + 0.02, 1.0, 0.0)
            win = wu * wv
        is_roof = t.map_range(t.abs(nz), 0.6, 0.8, 0.0, 1.0)
        win = win * (1.0 - is_roof)
        # per-building tint variation
        bid = t.n("ShaderNodeAttribute", props={"attribute_name": "bld_rand",
                                                "attribute_type": "GEOMETRY"})["Fac"]
        tint = S.ramp(t, bid, [(0.0, (0.92, 0.96, 1.0, 1)), (0.5, (1.0, 1.0, 1.0, 1)),
                               (1.0, (0.85, 0.93, 1.0, 1))])["Color"]
        fr = S.mix_rgb(t, 1.0, (*frame, 1), tint, blend="MULTIPLY")
        base = S.mix_rgb(t, win, fr, (*glass, 1))
        base = S.mix_rgb(t, is_roof, base, (*roof, 1))
        rough = t.mix(win, 0.45, 0.22)
        b = S.bsdf(t, Base_Color=base, Roughness=rough, Specular_IOR_Level=0.6,
                   Metallic=t.mix(win, 0.0, 0.3), Emission_Color=base,
                   Emission_Strength=glow)["BSDF"]
        dist = t.n("ShaderNodeCameraData")["View Distance"]
        fog = t.map_range(dist, 0.0, haze_dist, 0.0, 0.85, interp="SMOOTHSTEP")
        hz = t.n("ShaderNodeEmission", Color=(*haze, 1), Strength=1.0)["Emission"]
        return t.n("ShaderNodeMixShader", fog, b, hz)["Shader"]
    return S.material(name, build)


def plain_material(name, color, rough=0.5, haze=(0.75, 0.9, 1.0), haze_dist=2600.0, glow=0.2):
    def build(t: Tree):
        b = S.bsdf(t, Base_Color=(*color, 1), Roughness=rough, Emission_Color=(*color, 1),
                   Emission_Strength=glow)["BSDF"]
        dist = t.n("ShaderNodeCameraData")["View Distance"]
        fog = t.map_range(dist, 0.0, haze_dist, 0.0, 0.85, interp="SMOOTHSTEP")
        hz = t.n("ShaderNodeEmission", Color=(*haze, 1), Strength=1.0)["Emission"]
        return t.n("ShaderNodeMixShader", fog, b, hz)["Shader"]
    return S.material(name, build)


# ------------------------------------------------------------------- city
@asset("KIV.CityBlocks", "Kivotos")
def city_blocks():
    """District of block buildings on a street grid.  Heights follow a noise
    field ('downtown' clusters) with a radial falloff; a clear zone is kept
    around ``Clear Center`` (the campus)."""
    g = GN("KIV.CityBlocks", city_blocks.__doc__)
    E = g.inp("Extent", default=2500.0, subtype="DISTANCE")
    B = g.inp("Block", default=60.0, subtype="DISTANCE")
    cc = g.inp("Clear Center", "VECTOR", default=(0, 0, 0))
    cr = g.inp("Clear Radius", default=260.0, subtype="DISTANCE")
    hmin = g.inp("Height Min", default=12.0, subtype="DISTANCE")
    hmax = g.inp("Height Max", default=160.0, subtype="DISTANCE")
    nfreq = g.inp("Cluster Scale", default=0.0012)
    near_k = g.inp("Near Height Scale", default=1.0, desc="height multiplier at the clear radius")
    far_k = g.inp("Far Height Scale", default=0.35, desc="height multiplier at the extent")
    fmin = g.inp("Footprint Min", default=0.45, subtype="FACTOR")
    fmax = g.inp("Footprint Max", default=0.8, subtype="FACTOR")
    seed = g.inp("Seed", "INT", default=1)
    ma = g.inp("Material A", "MATERIAL", panel="Materials")
    mb = g.inp("Material B", "MATERIAL", panel="Materials")
    mc = g.inp("Material C", "MATERIAL", panel="Materials")

    n = g.math("CEIL", (E * 2.0) / B)
    grid = g.grid(E * 2.0, E * 2.0, n, n)
    pts = g.mesh_to_points(grid)
    P = g.position()
    d = g.vmath("DISTANCE", P, cc)
    r = g.vmath("LENGTH", P)
    far = g.compare(r, E, "GREATER_THAN")
    near = g.compare(d, cr, "LESS_THAN")
    pts = g.delete(pts, g.bool_or(far, near))
    # jitter
    idx = g.id()
    jx = g.random(-0.08, 0.08, seed, idx) * B
    jy = g.random(-0.08, 0.08, g.math("ADD", seed, 1), idx) * B
    pts = g.set_pos(pts, offset=g.vec(jx, jy, 0.0))
    # heights
    nz = g.n("ShaderNodeTexNoise", g.position() * nfreq, Scale=1.0, Detail=2.0,
             props={"noise_dimensions": "3D"})["Fac"]
    cluster = g.map_range(nz, 0.42, 0.7, 0.0, 1.0)
    rnd = g.random(0.0, 1.0, g.math("ADD", seed, 2), idx)
    fall = g.map_range(r, cr, E, near_k, far_k)
    hh = hmin + (hmax - hmin) * cluster * cluster * (0.35 + rnd * 0.65) * fall
    tall = g.compare(g.random(0.0, 1.0, g.math("ADD", seed, 9), idx), 0.035, "LESS_THAN")
    hh = g.switch(tall, hh, hh * 1.9 + 40.0, input_type="FLOAT")
    fw = g.random(fmin, fmax, g.math("ADD", seed, 3), idx) * B
    fd = g.random(fmin, fmax, g.math("ADD", seed, 4), idx) * B
    pts = g.store(pts, "bld_rand", g.random(0.0, 1.0, g.math("ADD", seed, 5), idx))
    pts = g.store(pts, "bld_pick", g.random(0.0, 3.0, g.math("ADD", seed, 6), idx))
    unit = g.move(g.cube((1, 1, 1)), z=0.5)
    inst = g.iop(pts, unit, scale=g.vec(fw, fd, hh))
    geo = g.realize(inst)
    pick = g.n("GeometryNodeInputNamedAttribute", Name="bld_pick", props={"data_type": "FLOAT"}).o
    geo = g.mat(geo, ma)
    geo = g.mat(geo, mb, sel=g.compare(pick, 1.0, "GREATER_THAN"))
    geo = g.mat(geo, mc, sel=g.compare(pick, 2.2, "GREATER_THAN"))
    g.result(geo)
    return g


@asset("KIV.Tower", "Kivotos")
def tower():
    """Hero high-rise: rectangular (Shape 0) or cylindrical (Shape 1) shaft
    with a set-back crown and an optional roof mast.  Origin at the base
    centre."""
    g = GN("KIV.Tower", tower.__doc__)
    shape = g.inp("Shape", "INT", default=0, min=0, max=1)
    w = g.inp("Width", default=40.0, subtype="DISTANCE")
    dd = g.inp("Depth", default=30.0, subtype="DISTANCE")
    h = g.inp("Height", default=180.0, subtype="DISTANCE")
    crown = g.inp("Crown Height", default=10.0, subtype="DISTANCE")
    inset = g.inp("Crown Inset", default=3.0, subtype="DISTANCE")
    fins = g.inp("Fin Spacing", default=0.0, subtype="DISTANCE", desc="0 = no fins")
    mast_h = g.inp("Mast Height", default=0.0, subtype="DISTANCE", desc="0 = no roof mast")
    m = g.inp("Material", "MATERIAL")
    m2 = g.inp("Crown Material", "MATERIAL")
    is_cyl = g.compare(shape, 0.5, "GREATER_THAN")
    shaft_box = g.box(w * -0.5, dd * -0.5, 0.0, w * 0.5, dd * 0.5, h)
    cyl = g.cylinder(1.0, 1.0, 48)
    shaft_cyl = g.transform(cyl, t=g.vec(0.0, 0.0, h * 0.5), s=g.vec(w * 0.5, w * 0.5, h))
    shaft = g.switch(is_cyl, shaft_box, shaft_cyl)
    cw = w - inset * 2.0
    cd = dd - inset * 2.0
    crown_box = g.box(cw * -0.5, cd * -0.5, h, cw * 0.5, cd * 0.5, h + crown)
    crown_cyl = g.transform(cyl, t=g.vec(0.0, 0.0, h + crown * 0.5), s=g.vec(cw * 0.5, cw * 0.5, crown))
    cr = g.switch(is_cyl, crown_box, crown_cyl)
    mast = g.transform(g.cylinder(0.6, 1.0, 8), t=g.vec(0.0, 0.0, h + crown + mast_h * 0.5),
                       s=g.vec(1.0, 1.0, g.max(mast_h, 0.001)))
    mast = g.switch(g.compare(mast_h, 0.01, "GREATER_THAN"), None, mast)
    g.result(g.join(g.mat(shaft, m), g.mat(g.join(cr, mast), m2)))
    return g


@asset("KIV.Arena", "Kivotos")
def arena():
    """Round banded building (stacked rings with recessed glazing) with a
    shallow roof.  Origin at the base centre."""
    g = GN("KIV.Arena", arena.__doc__)
    R = g.inp("Radius", default=70.0, subtype="DISTANCE")
    H = g.inp("Height", default=45.0, subtype="DISTANCE")
    bands = g.inp("Bands", "INT", default=9, min=1)
    m_band = g.inp("Band Material", "MATERIAL")
    m_glass = g.inp("Glass Material", "MATERIAL")
    m_roof = g.inp("Roof Material", "MATERIAL")
    core = g.transform(g.cylinder(1.0, 1.0, 96), t=g.vec(0.0, 0.0, H * 0.5), s=g.vec(R * 0.97, R * 0.97, H))
    step = H / g.math("ADD", bands, 0.0)
    ring = g.transform(g.cylinder(1.0, 1.0, 96), s=g.vec(R, R, step * 0.35))
    pts = g.mesh_to_points(g.mesh_line(bands, g.vec(0.0, 0.0, step * 0.8), g.vec(0.0, 0.0, step)))
    rings = g.realize(g.iop(pts, ring))
    roof = g.transform(g.n("GeometryNodeMeshUVSphere", Segments=64, Rings=16, Radius=1.0)["Mesh"],
                       t=g.vec(0.0, 0.0, H), s=g.vec(R * 0.92, R * 0.92, R * 0.12))
    g.result(g.join(g.mat(core, m_glass), g.mat(rings, m_band), g.mat(roof, m_roof)))
    return g
