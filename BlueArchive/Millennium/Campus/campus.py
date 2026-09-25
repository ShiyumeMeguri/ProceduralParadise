"""
Millennium campus: tower generator + campus assembly.

``MIL.Campus.Tower`` builds a complete high-rise from the academy facade
system: every storey of every face is an instance of the kit curtain wall
(``MIL.Arch.CurtainWall``) plus a spandrel band, so interior rooms placed on
any storey look out through the *real* facade.

``build_campus(campus_json)`` places towers, hero buildings, the Kivotos city,
the halo rings and the sun.  Each tower gets a collection of its own
(returned as ``towers[id]``), so the tower hosting a room can be addressed
as a unit -- it is the only geometry that can hide the room's ink lines.
Room placement inside a tower is :func:`room_matrix`.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Matrix, Vector

from Core import jsonio, scene as SC
from Core.gn import GN, asset, get_asset
from .. import CW, LEVELS
from ..Kit import materials as M

HERE = os.path.dirname(os.path.abspath(__file__))


@asset("MIL.Campus.Tower", "Campus")
def tower():
    """Millennium high-rise.  Origin at base centre; storeys stack from z = 0.

    Style 0 (grid): academy curtain wall per storey + spandrel bands.
    Style 1 (stripe): full-height white fins with dark glazing between.
    """
    g = GN("MIL.Campus.Tower", tower.__doc__)
    W = g.inp("Width X", default=48.0, subtype="DISTANCE")
    D = g.inp("Width Y", default=48.0, subtype="DISTANCE")
    S = g.inp("Storeys", "INT", default=36, min=1)
    H = g.inp("Storey Height", default=LEVELS["floor_to_floor"], subtype="DISTANCE")
    crown = g.inp("Crown Height", default=10.0, subtype="DISTANCE")
    style = g.inp("Style", "INT", default=0, min=0, max=1)
    core_in = g.inp("Core Inset", default=9.0, subtype="DISTANCE")
    m_frame = g.inp("Frame Material", "MATERIAL", panel="Materials")
    m_glass = g.inp("Glass Material", "MATERIAL", panel="Materials")
    m_span = g.inp("Spandrel Material", "MATERIAL", panel="Materials")
    m_slab = g.inp("Slab Material", "MATERIAL", panel="Materials")
    m_core = g.inp("Core Material", "MATERIAL", panel="Materials")
    m_crown = g.inp("Crown Material", "MATERIAL", panel="Materials")

    hw, hd = W * 0.5, D * 0.5
    mod = CW["module"]
    top = S * H
    storeys = g.mesh_to_points(g.mesh_line(S, (0, 0, 0), g.vec(0.0, 0.0, H)))

    def cw(length):
        n = g.math("FLOOR", length / mod + 0.001) + 1.0
        return g.group(get_asset("MIL.Arch.CurtainWall"), Length=length, Mullion_Count=n,
                       Frame_Material=m_frame, Glass_Material=m_glass,
                       Sill_Material=m_frame).o

    def span(length):
        b = g.box(-0.05, 0.0, CW["head_height"] + 0.02, 0.012, length, H + CW["sill_height"])
        return g.mat(b, m_span)

    def faces(elem_w, elem_d):
        # west (-x): runs +Y ; north (+y): runs +X ; east: runs -Y ; south: runs -X
        west = g.transform(elem_d, t=g.vec(g.math("MULTIPLY", hw, -1.0), g.math("MULTIPLY", hd, -1.0), 0.0))
        north = g.transform(elem_w, t=g.vec(g.math("MULTIPLY", hw, -1.0), hd, 0.0), r=(0, 0, -1.5707963))
        east = g.transform(elem_d, t=g.vec(hw, hd, 0.0), r=(0, 0, 3.14159265))
        south = g.transform(elem_w, t=g.vec(hw, g.math("MULTIPLY", hd, -1.0), 0.0), r=(0, 0, 1.5707963))
        return g.join(west, north, east, south)

    # ---- style 0: storey curtain walls + spandrels
    storey_ring = faces(g.join(cw(W), span(W)), g.join(cw(D), span(D)))
    grid_facade = g.iop(storeys, storey_ring)

    # ---- style 1: vertical fins + dark glass
    fin = g.box(-1.2, -0.75, 0.0, 0.0, 0.75, top)
    fin = g.mat(fin, m_frame)
    def fin_row(length):
        n = g.math("FLOOR", length / 3.6) + 1.0
        pts = g.mesh_to_points(g.mesh_line(n, (0, 0, 0), (0, 3.6, 0)))
        return g.realize(g.iop(pts, fin))
    glass_w = g.mat(g.box(-0.02, 0.0, 0.0, 0.02, W, top), m_glass)
    glass_d = g.mat(g.box(-0.02, 0.0, 0.0, 0.02, D, top), m_glass)
    stripe_facade = faces(g.join(fin_row(W), glass_w), g.join(fin_row(D), glass_d))
    facade = g.switch(g.compare(style, 0.5, "GREATER_THAN"), grid_facade, stripe_facade)

    # ---- slabs (structural top 5 cm below finished floor) and core volume
    slab = g.box(g.math("ADD", g.math("MULTIPLY", hw, -1.0), 0.25), g.math("ADD", g.math("MULTIPLY", hd, -1.0), 0.25), -0.35,
                 hw - 0.25, hd - 0.25, -0.05)
    slabs = g.iop(storeys, g.mat(slab, m_slab))
    roof = g.mat(g.box(hw * -1.0, hd * -1.0, top - 0.35, hw, hd, top + 0.6), m_slab)
    cx, cy = hw - core_in, hd - core_in
    core = g.mat(g.box(cx * -1.0, cy * -1.0, 0.0, cx, cy, top), m_core)
    # crown: set-back parapet frame + plant box
    cr_w, cr_d = hw - 2.5, hd - 2.5
    crown_box = g.mat(g.box(cr_w * -1.0, cr_d * -1.0, top + 0.6, cr_w, cr_d, top + crown), m_crown)
    g.result(g.join(facade, g.realize(slabs), roof, core, crown_box))
    return g


# ------------------------------------------------------------------ assembly
def load(path=None):
    return jsonio.load(path or os.path.join(HERE, "campus.json"))


def tower_matrix(tdef):
    return (Matrix.Translation(Vector((*tdef["center"], 0.0)))
            @ Matrix.Rotation(math.radians(tdef.get("rotation", 0.0)), 4, "Z"))


def room_matrix(campus, placement):
    """World matrix of a room frame from its ``placement`` block."""
    T = {t["id"]: t for t in campus["towers"]}[placement["tower"]]
    w, d = T["size"]
    H = LEVELS["floor_to_floor"]
    z = placement["storey"] * H
    face = placement.get("facade", "west")
    off = placement.get("facade_offset", 0.0)
    # room frame: +X into the building from the glass line, +Y along facade
    if face == "west":
        local = Matrix.Translation((-w / 2, off, z))
    elif face == "east":
        local = Matrix.Translation((w / 2, -off, z)) @ Matrix.Rotation(math.pi, 4, "Z")
    elif face == "north":
        local = Matrix.Translation((off, d / 2, z)) @ Matrix.Rotation(-math.pi / 2, 4, "Z")
    else:  # south
        local = Matrix.Translation((-off, -d / 2, z)) @ Matrix.Rotation(math.pi / 2, 4, "Z")
    return tower_matrix(T) @ local


def build_campus(campus=None, collection=None, city=True, halo=True, towers=True, exterior=None):
    from Kivotos import city as KC, sky as KS
    campus = campus or load()
    ex = {"haze": [0.8, 0.92, 1.0], "haze_dist": 2600.0, "glow": 0.3}
    ex.update(exterior or {})
    hz = dict(haze=tuple(ex["haze"]), haze_dist=ex["haze_dist"])
    col = collection or SC.collection("CAMPUS_Millennium")
    out = {"towers": {}, "campus": campus}
    frame = M.get("MIL.Mullion")
    glass = M.get("MIL.Glass")
    span = M.get("MIL.FacadeSpandrel")
    slab = M.get("MIL.WallPaint")
    core = KC.plain_material("MIL.TowerCore", (0.72, 0.8, 0.88), rough=0.6, glow=0.0,
                             haze=hz["haze"], haze_dist=ex["haze_dist"] * 3.0)
    crown = M.get("MIL.TrimWhite")
    white_fin = KC.plain_material("MIL.FinWhite", (0.86, 0.91, 0.97), rough=0.4, glow=ex["glow"] * 0.5, **hz)
    dark_glass = KC.plain_material("MIL.DarkGlass", (0.42, 0.6, 0.8), rough=0.32, glow=ex["glow"] * 0.3, **hz)
    if towers:
        tcol = SC.collection("Towers", parent=col)
        for t in campus["towers"]:
            stripe = t.get("style") == "stripe"
            tc = SC.collection(f"TOWER_{t['id']}", parent=tcol)
            ob = SC.gn_object(f"TOWER_{t['id']}", get_asset("MIL.Campus.Tower"), {
                "Width X": t["size"][0], "Width Y": t["size"][1], "Storeys": t["storeys"],
                "Crown Height": t.get("crown", 8.0), "Style": 1 if stripe else 0,
                "Core Inset": t.get("core_inset", 9.0),
                "Frame Material": white_fin if stripe else frame,
                "Glass Material": dark_glass if stripe else glass,
                "Spandrel Material": span, "Slab Material": slab, "Core Material": core,
                "Crown Material": crown}, collection=tc)
            ob.matrix_world = tower_matrix(t)
            out["towers"][t["id"]] = tc
    if city:
        ccol = SC.collection("Kivotos_City", parent=col)
        mats = {
            "glass_teal": KC.facade_material("KIV.Facade.GlassTeal", glass=(0.3, 0.72, 0.8), frame=(0.75, 0.88, 0.92), vertical=True, glow=ex["glow"] * 0.3, **hz),
            "white_grid": KC.facade_material("KIV.Facade.WhiteGrid", glass=(0.55, 0.75, 0.92), frame=(0.95, 0.97, 1.0), glow=ex["glow"] * 0.3, **hz),
            "glass_blue": KC.facade_material("KIV.Facade.GlassBlue", glass=(0.35, 0.6, 0.9), frame=(0.8, 0.88, 0.95), glass_ratio=0.85, glow=ex["glow"] * 0.3, **hz),
            "glass_grey": KC.facade_material("KIV.Facade.GlassGrey", glass=(0.22, 0.4, 0.48), frame=(0.62, 0.74, 0.8), floor_h=3.6, glass_ratio=0.96, band_ratio=0.78, glow=ex["glow"] * 0.5, **hz),
        }
        c = campus["city"]
        blocks = SC.gn_object("KIV_CityBlocks", get_asset("KIV.CityBlocks"), {
            "Extent": c["extent"], "Block": c["block"], "Clear Radius": c["clear_radius"],
            "Height Min": c["height_min"], "Height Max": c["height_max"],
            "Cluster Scale": c["cluster_scale"], "Seed": c["seed"],
            "Near Height Scale": c.get("near_height_scale", 1.0),
            "Far Height Scale": c.get("far_height_scale", 0.35),
            "Material A": mats["white_grid"], "Material B": mats["glass_blue"],
            "Material C": mats["glass_teal"]}, collection=ccol)
        for h in campus.get("hero_buildings", []):
            if h["type"] == "tower":
                ob = SC.gn_object(f"KIV_{h['id']}", get_asset("KIV.Tower"), {
                    "Shape": h.get("shape", 0), "Width": h["size"][0], "Depth": h["size"][1],
                    "Height": h["height"], "Crown Height": h.get("crown", 6.0),
                    "Crown Inset": h.get("crown_inset", 3.0), "Mast Height": h.get("mast", 0.0),
                    "Material": mats[h.get("material", "white_grid")],
                    "Crown Material": mats[h.get("crown_material", h.get("material", "white_grid"))]},
                    location=(*h["center"], 0.0), collection=ccol)
            elif h["type"] == "arena":
                band = KC.plain_material("KIV.ArenaBand", (0.93, 0.96, 1.0), rough=0.4, glow=ex["glow"] * 0.6, **hz)
                ob = SC.gn_object(f"KIV_{h['id']}", get_asset("KIV.Arena"), {
                    "Radius": h["radius"], "Height": h["height"],
                    "Band Material": band, "Glass Material": mats["glass_blue"],
                    "Roof Material": KC.plain_material("KIV.ArenaRoof", (0.6, 0.66, 0.72), rough=0.5, glow=ex["glow"] * 0.3, **hz)},
                    location=(*h["center"], 0.0), collection=ccol)
        # ground plane
        gm = KC.plain_material("KIV.Ground", (0.55, 0.66, 0.72), rough=0.8, glow=0.05, **hz)
        ground = SC.gn_object("KIV_Ground", get_asset("MIL.Arch.FloorSlab"), {
            "Size X": c["extent"] * 2.6, "Size Y": c["extent"] * 2.6, "Thickness": 1.0, "Material": gm},
            location=(-c["extent"] * 1.3, -c["extent"] * 1.3, 0.0), collection=ccol)
    if halo:
        hcol = SC.collection("Kivotos_Halo", parent=col)
        out["halo"] = KS.build_halo(campus["halo"], collection=hcol)
    return out
