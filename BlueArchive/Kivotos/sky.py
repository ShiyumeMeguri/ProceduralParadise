"""
Kivotos sky: stylised daytime atmosphere + the holographic halo rings.

* ``build_world(cfg)`` -- world shader: zenith/mid/horizon gradient and a
  cumulus layer.  Clouds are mapped by azimuth/elevation (so they stay puffy
  down to the horizon instead of streaking) and can be art-directed with
  ``clusters`` (direction + radius + density), exactly like a matte painter
  blocking cloud masses -- yet they live in world space, so every camera sees
  the same sky.
* ``KIV.HaloRings`` -- real geometry: concentric glowing bands of constant
  width, dotted rings and node markers.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Euler, Matrix, Vector

from Core import shaders as S
from Core.nodes import Tree
from Core.gn import GN, asset


DEFAULT_SKY = {
    "zenith": [0.03, 0.3, 0.95],
    "mid": [0.12, 0.62, 1.0],
    "horizon": [0.35, 0.88, 1.0],
    "ground": [0.45, 0.62, 0.78],
    "strength": 1.0,
    "camera_boost": 1.0,
    "glossy_boost": 1.0,
    "cloud": {
        "scale": 6.0, "coverage": 0.62, "softness": 0.08,
        "color": [1.0, 1.0, 1.0], "shadow": [0.62, 0.8, 0.97], "strength": 1.3,
        "seed": [3.1, 7.7, 0.0],
        "clusters": []
    },
}


def _dir_vec(az_deg, el_deg):
    az, el = math.radians(az_deg), math.radians(el_deg)
    return (math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el))


def build_world(cfg=None, name="Kivotos.Sky"):
    """World shader.  ``cfg`` follows DEFAULT_SKY's layout.  Cloud clusters:
    ``{"az": deg (0 = +Y/north, 90 = east), "el": deg, "radius": deg,
    "density": 0..1}`` raise cloud density around a direction."""
    c = {**DEFAULT_SKY, **(cfg or {})}
    cl = {**DEFAULT_SKY["cloud"], **(c.get("cloud") or {})}
    w = S.new_world(name)
    t = Tree.wrap(w.node_tree, clear=True)
    out = t.n("ShaderNodeOutputWorld")
    d = t.vmath("NORMALIZE", t.n("ShaderNodeTexCoord")["Generated"])
    dx, dy, dz = t.sep(d)
    up = t.map_range(dz, 0.0, 1.0, 0.0, 1.0)
    grad = S.ramp(t, up, [(0.0, (*c["horizon"], 1)), (0.14, (*c["mid"], 1)),
                          (0.6, (*c["zenith"], 1)), (1.0, (*c["zenith"], 1))])["Color"]

    # ---- cumulus layer in azimuth/elevation space
    az = t.math("ARCTAN2", dx, dy)                        # radians, 0 = +Y
    el = t.math("ARCSINE", t.clamp01(dz))
    uv = t.vec(az, el * 1.6, 0.0) + tuple(cl["seed"])
    n1 = t.n("ShaderNodeTexNoise", uv, Scale=cl["scale"], Detail=7.0, Roughness=0.55,
             Distortion=0.15, props={"noise_dimensions": "3D"})["Fac"]
    n2 = t.n("ShaderNodeTexNoise", uv, Scale=cl["scale"] * 3.2, Detail=5.0, Roughness=0.62,
             props={"noise_dimensions": "3D"})["Fac"]
    dens = n1 * 0.8 + n2 * 0.35
    boost = 0.0
    for k in cl.get("clusters", []):
        cv = _dir_vec(k["az"], k["el"])
        cosang = t.vmath("DOT_PRODUCT", d, cv)
        r = math.radians(k.get("radius", 15.0))
        g = t.map_range(cosang, math.cos(r), 1.0, 0.0, 1.0, interp="SMOOTHSTEP")
        boost = boost + g * k.get("density", 0.3)
    if not isinstance(boost, float):
        dens = dens + boost
    cov = cl["coverage"]
    mask = t.map_range(dens, cov, cov + cl["softness"], 0.0, 1.0)
    fade = t.map_range(dz, 0.005, 0.05, 0.0, 1.0) * t.map_range(dz, 0.8, 0.45, 0.0, 1.0)
    mask = mask * fade
    shade = t.map_range(dens, cov, cov + 0.45, 0.0, 1.0)
    ccol = S.mix_rgb(t, shade, (*cl["shadow"], 1), (*cl["color"], 1))
    sky = S.mix_rgb(t, mask, grad, t.vmath("SCALE", ccol, scale=cl["strength"]))
    is_below = t.map_range(dz, 0.0, -0.03, 0.0, 1.0)
    sky = S.mix_rgb(t, is_below, sky, (*c["ground"], 1))

    # Painted-BG exposure: optionally show the sky brighter to cameras /
    # reflections than the light it casts (holds for every camera).
    lp = t.n("ShaderNodeLightPath")
    boost_c = c.get("camera_boost", 1.0)
    boost_g = c.get("glossy_boost", 1.0)
    strength = c["strength"]
    if boost_c != 1.0 or boost_g != 1.0:
        k = 1.0 + (boost_c - 1.0) * lp["Is Camera Ray"] + (boost_g - 1.0) * lp["Is Glossy Ray"]
        strength = k * c["strength"]
    bg = t.n("ShaderNodeBackground", sky, strength)
    t.link(bg, out.n.inputs["Surface"])
    t.layout()
    return w


def add_sun(azimuth_deg, elevation_deg, strength=4.0, color=(1.0, 0.98, 0.95), angle_deg=1.2,
            name="Kivotos.Sun", collection=None):
    """Sun lamp.  Azimuth: direction the light comes *from*, clockwise from
    north (+Y): 0 = north, 90 = east, 180 = south, 270 = west."""
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = strength
    ld.color = color
    ld.angle = math.radians(angle_deg)
    ob = bpy.data.objects.new(name, ld)
    (collection or bpy.context.scene.collection).objects.link(ob)
    d = -Vector(_dir_vec(azimuth_deg, elevation_deg))
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


# ------------------------------------------------------------------ halo rings
@asset("KIV.HaloRings", "Kivotos")
def halo_rings():
    """Holographic halo: concentric glowing bands of constant width (some
    broken into arcs), dotted rings, centred on the origin in the XY plane."""
    g = GN("KIV.HaloRings", halo_rings.__doc__)
    r0 = g.inp("Inner Radius", default=150.0, subtype="DISTANCE")
    r1 = g.inp("Outer Radius", default=1000.0, subtype="DISTANCE")
    n = g.inp("Rings", "INT", default=8, min=1)
    wdt = g.inp("Band Width", default=6.0, subtype="DISTANCE")
    seed = g.inp("Seed", "INT", default=4)
    gaps = g.inp("Arc Gaps", default=0.62, subtype="FACTOR", desc="higher = fewer gaps")
    dots = g.inp("Dots per Ring", "INT", default=90)
    dsize = g.inp("Dot Size", default=5.0, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    pts = g.mesh_to_points(g.mesh_line(n, (0, 0, 0), (1, 0, 0)))
    idx = g.index()
    t = idx / g.max(g.math("SUBTRACT", n, 1), 1)
    jitter = g.random(-0.3, 0.3, seed, idx) / g.max(n, 1)
    rad = r0 + (r1 - r0) * g.math("POWER", g.clamp01(t + jitter), 1.3)
    pts = g.store(pts, "ring_r", rad, dtype="FLOAT")
    circle = g.circle(1.0, 360)
    rr = g.n("GeometryNodeInputNamedAttribute", Name="ring_r", props={"data_type": "FLOAT"}).o
    rings = g.realize(g.iop(pts, circle, scale=g.vec(rr, rr, rr)))
    P = g.position()
    px, py, pz = g.sep(P)
    ang = g.math("ARCTAN2", py, px)
    rr2 = g.n("GeometryNodeInputNamedAttribute", Name="ring_r", props={"data_type": "FLOAT"}).o
    gap = g.n("ShaderNodeTexNoise", g.vec(ang * 1.2, rr2 * 0.01, 0.0), Scale=1.4,
              props={"noise_dimensions": "3D"})["Fac"]
    rings = g.delete(rings, g.compare(gap, gaps, "GREATER_THAN"))
    bands = g.sweep(rings, g.rect(wdt, g.math("MULTIPLY", wdt, 0.1)), False)
    rad3 = r0 * 1.35 + g.index() * (r1 - r0) * 0.27
    drings = g.realize(g.iop(g.mesh_to_points(g.mesh_line(3, (0, 0, 0), (1, 0, 0))), circle,
                             scale=g.vec(rad3, rad3, 1.0)))
    dpts = g.n("GeometryNodeCurveToPoints", drings, Count=dots, props={"mode": "COUNT"}).o
    dot = g.n("GeometryNodeMeshUVSphere", Segments=10, Rings=5, Radius=1.0)["Mesh"]
    dotted = g.realize(g.iop(dpts, dot, scale=g.vec(dsize, dsize, g.math("MULTIPLY", dsize, 0.2))))
    g.result(g.mat(g.join(bands, dotted), m))
    return g


def halo_material(name="Kivotos.Halo", color=(0.55, 0.95, 1.0), strength=5.0, alpha=0.9):
    def build(t):
        em = t.n("ShaderNodeEmission", Color=(*color, 1), Strength=strength)["Emission"]
        tr = t.n("ShaderNodeBsdfTransparent")["BSDF"]
        return t.n("ShaderNodeMixShader", alpha, tr, em)["Shader"]
    return S.material(name, build)


def place_halo(ob, center, tilt_toward=None, tilt_deg=0.0):
    """Position the halo; optionally tilt its plane by ``tilt_deg`` about the
    horizontal axis perpendicular to the direction of ``tilt_toward`` (e.g.
    the viewer), so the near side dips towards it."""
    ob.location = Vector(center)
    if tilt_toward is not None and tilt_deg:
        v = Vector(tilt_toward) - Vector(center)
        v.z = 0.0
        if v.length > 1e-6:
            v.normalize()
            axis = Vector((-v.y, v.x, 0.0))
            ob.rotation_euler = Matrix.Rotation(math.radians(-tilt_deg), 4, axis).to_euler()
    return ob
