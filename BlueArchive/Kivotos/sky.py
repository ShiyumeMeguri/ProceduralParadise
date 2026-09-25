"""
Kivotos sky: stylised daytime atmosphere + the holographic halo rings.

* ``build_world(cfg)`` -- world shader: zenith/mid/horizon gradient and a
  cumulus layer.  Clouds are mapped by azimuth/elevation (so they stay puffy
  down to the horizon instead of streaking) and can be art-directed with
  ``clusters`` (direction + radius + density), exactly like a matte painter
  blocking cloud masses -- yet they live in world space, so every camera sees
  the same sky.
* ``KIV.HaloRing`` / ``build_halo`` -- real geometry: systems of concentric
  glowing rings (tubes of constant apparent width, arcs, dotted rings, node
  markers) floating over the city.
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
    "mid_pos": 0.14,          # sin(elevation) of the mid colour stop
    "zenith_pos": 0.6,
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
    grad = S.ramp(t, up, [(0.0, (*c["horizon"], 1)), (c.get("mid_pos", 0.14), (*c["mid"], 1)),
                          (c.get("zenith_pos", 0.6), (*c["zenith"], 1)), (1.0, (*c["zenith"], 1))])["Color"]

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
@asset("KIV.HaloRing", "Kivotos")
def halo_ring():
    """One holographic halo ring in the local XY plane, centred on the origin.

    The ring is a thin round tube, so it reads as a line of constant width
    from any direction.  ``Gap`` breaks it into arcs (seeded), ``Dotted``
    replaces the line by a row of dots, and ``Markers`` adds short brighter
    node dashes along the ring."""
    g = GN("KIV.HaloRing", halo_ring.__doc__)
    R = g.inp("Radius", default=300.0, subtype="DISTANCE")
    th = g.inp("Thickness", default=4.0, subtype="DISTANCE", desc="tube diameter")
    gap = g.inp("Gap", default=0.0, subtype="FACTOR", desc="share of the ring left open")
    seed = g.inp("Seed", "INT", default=0)
    dotted = g.inp("Dotted", "BOOL", default=False)
    ndots = g.inp("Dot Count", "INT", default=180, min=3)
    marks = g.inp("Markers", "INT", default=3, min=0)
    mlen = g.inp("Marker Length", default=14.0, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")

    # edge loop -> delete gap vertices -> arcs (mesh-to-curve splits at gaps)
    loop = g.sweep(g.circle(R, 720), None, False)
    px, py, _ = g.sep(g.position())
    ang = g.math("ARCTAN2", py, px)
    sd = g.math("MULTIPLY", seed, 7.31)
    nz = g.n("ShaderNodeTexNoise", g.vec(g.cos(ang) * 1.3, g.sin(ang) * 1.3, sd), Scale=1.0,
             Detail=0.0, props={"noise_dimensions": "3D"})["Fac"]
    loop = g.delete(loop, g.compare(nz, g.map_range(gap, 0.0, 1.0, 0.2, 0.8), "LESS_THAN"))
    arcs = g.n("GeometryNodeMeshToCurve", loop).o
    solid = g.tube(arcs, th * 0.5, 6, caps=True)
    dpts = g.n("GeometryNodeCurveToPoints", arcs, Count=ndots, props={"mode": "COUNT"}).o
    dot = g.n("GeometryNodeMeshUVSphere", Segments=8, Rings=4, Radius=1.0)["Mesh"]
    dots = g.realize(g.iop(dpts, dot, scale=th * 0.9))
    ring = g.switch(dotted, solid, dots)

    # node markers: short dashes tangent to the ring at seeded angles
    mp = g.mesh_to_points(g.mesh_line(marks, (0, 0, 0), (0, 0, 0)))
    a = g.random(0.0, 6.2831853, g.math("ADD", seed, 11), g.index())
    mp = g.set_pos(mp, pos=g.vec(g.cos(a) * R, g.sin(a) * R, 0.0))
    dash = g.transform(g.cylinder(1.0, 1.0, 8), r=(1.5707963, 0.0, 0.0), s=(1.0, 1.0, 1.0))
    mk = g.iop(mp, dash, rot=g.vec(0.0, 0.0, a), scale=g.vec(th * 1.1, mlen, th * 1.1))
    g.result(g.mat(g.join(ring, g.realize(mk)), m))
    return g


def halo_material(name="Kivotos.Halo", color=(0.55, 0.95, 1.0), strength=5.0, alpha=0.9):
    def build(t):
        em = t.n("ShaderNodeEmission", Color=(*color, 1), Strength=strength)["Emission"]
        tr = t.n("ShaderNodeBsdfTransparent")["BSDF"]
        return t.n("ShaderNodeMixShader", alpha, tr, em)["Shader"]
    return S.material(name, build)


def build_halo(cfg, collection=None, name="KIV_Halo"):
    """Place the halo field described by ``cfg``::

        {"color": [...], "strength": 3.0,
         "systems": [{"id", "center": [x,y,z], "normal": [nx,ny,nz],
                      "rings": [{"radius", "thickness", "gap", "seed",
                                 "dotted", "dots", "markers"}, ...]}, ...]}

    Each system is a set of concentric rings in one plane (an empty carries
    the plane, the rings are its children), so a system can be moved or
    re-tilted as a unit.  Returns the list of system empties."""
    from Core import scene as SC
    from Core.gn import get_asset
    mat = halo_material(color=tuple(cfg.get("color", (0.6, 0.96, 1.0))),
                        strength=cfg.get("strength", 3.0))
    roots = []
    for s in cfg["systems"]:
        n = Vector(s["normal"]).normalized()
        root = SC.empty(f"{name}_{s['id']}", location=tuple(s["center"]),
                        rotation=n.to_track_quat("Z", "Y").to_euler(), collection=collection,
                        display="CIRCLE", size=50.0)
        for i, r in enumerate(s["rings"]):
            SC.gn_object(f"{name}_{s['id']}_{i}", get_asset("KIV.HaloRing"), {
                "Radius": r["radius"], "Thickness": r.get("thickness", s.get("thickness", 4.0)),
                "Gap": r.get("gap", 0.0), "Seed": r.get("seed", i),
                "Dotted": bool(r.get("dotted", False)), "Dot Count": r.get("dots", 180),
                "Markers": r.get("markers", 0), "Marker Length": r.get("marker_length", 14.0),
                "Material": mat}, collection=collection, parent=root)
        roots.append(root)
    return roots
