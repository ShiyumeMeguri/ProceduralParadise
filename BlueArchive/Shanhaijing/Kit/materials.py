"""
Shanhaijing material library (``SHJ.*``).

Every material is procedural (no bitmaps): wood grain, plank joints, lacquer
motifs, blue-and-white porcelain decoration and cloud patterns are all
generated in object space, so any camera sees the same surfaces.  Base colours
come from the academy palette (``Academy.json``); a shot may override look
parameters through ``PARAMS`` before the materials are built.
"""
from __future__ import annotations

import math

import bpy

from Core.nodes import Tree
from Core import shaders as S
from .. import PALETTE, FLOOR, TIMBER

_BUILDERS = {}
# look parameters that shots may override before materials are built
PARAMS = {}


def _reg(name):
    def deco(fn):
        _BUILDERS[name] = fn
        return fn
    return deco


def get(name):
    m = bpy.data.materials.get(name)
    if m is not None and m.get("shj_built"):
        return m
    m = _BUILDERS[name]()
    m["shj_built"] = True
    return m


def all_names():
    return sorted(_BUILDERS)


def C(key, a=1.0):
    r, g, b = PARAMS.get("color:" + key, PALETTE[key])
    return (r, g, b, a)


def P(key, default):
    return PARAMS.get(key, default)


# ------------------------------------------------------------------ helpers
def _obj(t):
    return t.n("ShaderNodeTexCoord")["Object"]


def _grain(t, P3, scale=(1.0, 14.0, 14.0), strength=0.35, seed=0.0, rings=6.0):
    """Wood grain along object X: long streaks from anisotropically scaled
    noise plus soft growth rings.  Returns a 0..1 factor (1 = dark grain)."""
    q = t.vmath("MULTIPLY", P3, scale)
    q = q + (seed, seed * 1.7, seed * 0.3)
    n = S.noise(t, q, scale=1.3, detail=6.0, rough=0.62, distortion=0.4)["Fac"]
    ring = t.n("ShaderNodeTexWave", q, Scale=rings * 0.1, Distortion=6.0, Detail=3.0,
               props={"wave_type": "RINGS", "rings_direction": "X", "wave_profile": "SIN"})["Fac"]
    g = t.map_range(n, 0.35, 0.7, 0.0, 1.0) * 0.6 + ring * 0.4
    return t.clamp01(g * strength * 2.0)


def wood(name, base, dark, rough=0.45, coat=0.0, coat_rough=0.1, scale=(0.8, 12.0, 12.0),
         strength=0.35, spec=0.4):
    def build(t: Tree):
        P3 = _obj(t)
        g = _grain(t, P3, scale, strength)
        col = S.mix_rgb(t, g, base, dark)
        kw = dict(Base_Color=col, Roughness=t.mix(g, rough, min(rough + 0.15, 1.0)),
                  Specular_IOR_Level=spec)
        if coat:
            kw.update(Coat_Weight=coat, Coat_Roughness=coat_rough)
        return S.bsdf(t, **kw)["BSDF"]
    return S.material(name, build)


def _cells(t, P2, scale, seed=0.0):
    """Voronoi cells on a 2D coordinate: (distance to feature, cell random)."""
    v = t.n("ShaderNodeTexVoronoi", P2, Scale=scale, Randomness=0.85,
            props={"voronoi_dimensions": "2D", "feature": "F1", "distance": "EUCLIDEAN"})
    return v["Distance"], v["Color"]


# ------------------------------------------------------------------ floor
@_reg("SHJ.FloorWood")
def floor_wood():
    """Wood-look porcelain planks in running bond along object X.

    Plank length/width/stagger come from the academy design system; each
    plank gets its own tone, grain offset and a slightly different gloss, the
    joints are thin dark grout lines.  The pattern is laid in the floor
    object's local XY (= room frame), so rooms control the alignment."""
    L, W, st = FLOOR["plank_length"], FLOOR["plank_width"], FLOOR["stagger"]
    L, W, st = P("plank_length", L), P("plank_width", W), P("plank_stagger", st)

    ox, oy = P("plank_offset", (0.0, 0.0))

    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        px = px + ox
        py = py - oy
        row = t.math("FLOOR", py / W)
        # running bond: every row shifted by the stagger fraction (+ a small
        # per-row random so the joints do not form a perfect staircase)
        rrow = t.n("ShaderNodeTexWhiteNoise", row, props={"noise_dimensions": "1D"})["Value"]
        shift = t.math("FRACT", row * st) * L + rrow * P("plank_jitter", 0.18)
        u = (px + shift) / L
        col_i = t.math("FLOOR", u)
        fu = t.math("FRACT", u)
        fv = t.math("FRACT", py / W)
        du = t.min(fu, 1.0 - fu) * L
        dv = t.min(fv, 1.0 - fv) * W
        jw = P("plank_joint", 0.0022)
        joint = t.map_range(t.min(du, dv), jw, jw + 0.0025, 1.0, 0.0)
        cell = t.vec(col_i, row, 0.0)
        rnd = t.n("ShaderNodeTexWhiteNoise", cell, props={"noise_dimensions": "3D"})["Color"]
        rx, ry, rz = t.sep(rnd)
        # grain: long streaks along X, offset per plank
        q = t.vec(px * 0.9 + rx * 40.0, py * 16.0 + ry * 40.0, pz)
        streak = S.noise(t, q, scale=1.0, detail=5.0, rough=0.6, distortion=0.25)["Fac"]
        fine = S.noise(t, t.vec(px * 3.0 + rz * 20.0, py * 60.0, 0.0), scale=1.0,
                       detail=3.0, rough=0.5)["Fac"]
        g = t.clamp01(t.map_range(streak, 0.38, 0.68, 0.0, 1.0) * 0.75 +
                      t.map_range(fine, 0.4, 0.65, 0.0, 0.35))
        tone = rx * P("plank_tone_var", 0.35) - P("plank_tone_var", 0.35) * 0.5
        base = S.mix_rgb(t, t.clamp01(0.5 + tone), C("floor_grain"), C("floor_light"))
        base = S.mix_rgb(t, t.clamp01(0.5 - tone * 0.6), C("floor_light"), base)
        col = S.mix_rgb(t, g * P("floor_grain_strength", 0.55), base, C("floor_grain"))
        col = S.mix_rgb(t, joint, col, (0.12, 0.09, 0.06, 1.0))
        rough = P("floor_roughness", 0.32) + ry * 0.08
        b = S.bsdf(t, Base_Color=col, Roughness=t.mix(joint, rough, 0.7),
                   Specular_IOR_Level=P("floor_specular", 0.45),
                   Coat_Weight=P("floor_coat", 0.12), Coat_Roughness=P("floor_coat_roughness", 0.1))
        return b["BSDF"]
    return S.material("SHJ.FloorWood", build)


# ------------------------------------------------------------ architecture
@_reg("SHJ.Plaster")
def plaster():
    def build(t: Tree):
        n = S.noise(t, _obj(t), scale=1.2, detail=4.0, rough=0.55)["Fac"]
        col = S.mix_rgb(t, t.map_range(n, 0.3, 0.7, 0.0, 1.0), C("plaster"),
                        tuple(c * 0.9 for c in C("plaster")[:3]) + (1.0,))
        return S.bsdf(t, Base_Color=col, Roughness=0.9, Specular_IOR_Level=0.3)["BSDF"]
    return S.material("SHJ.Plaster", build)


@_reg("SHJ.PlasterBand")
def plaster_band():
    return S.principled("SHJ.PlasterBand", C("plaster_band"), roughness=0.85, specular=0.3)


@_reg("SHJ.WallCream")
def wall_cream():
    """Cream plaster wall panels with a soft painted mottling."""
    def build(t: Tree):
        n = S.noise(t, _obj(t), scale=0.9, detail=3.0, rough=0.5)["Fac"]
        col = S.mix_rgb(t, t.map_range(n, 0.3, 0.7, 0.0, 1.0), C("wall_cream"),
                        tuple(c * 0.86 for c in C("wall_cream")[:3]) + (1.0,))
        return S.bsdf(t, Base_Color=col, Roughness=0.85, Specular_IOR_Level=0.3)["BSDF"]
    return S.material("SHJ.WallCream", build)


@_reg("SHJ.TimberDark")
def timber_dark():
    return wood("SHJ.TimberDark", C("timber_dark"),
                tuple(c * 0.55 for c in C("timber_dark")[:3]) + (1.0,), rough=0.55)


@_reg("SHJ.TimberRed")
def timber_red():
    """Reddish-brown stained beams (the big longitudinal beams)."""
    return wood("SHJ.TimberRed", C("timber_red"),
                tuple(c * 0.6 for c in C("timber_red")[:3]) + (1.0,), rough=0.45,
                coat=0.15, coat_rough=0.2)


def _planks(name, key, width=None, contrast=None):
    """Board cladding: boards run along object Y/Z, joints every ``width``
    (default: the academy's plank width) along object X; every board its own
    tone."""
    w = width or TIMBER["plank_width"]

    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        u = px / w
        board = t.math("FLOOR", u)
        fu = t.math("FRACT", u)
        d = t.min(fu, 1.0 - fu) * w
        joint = t.map_range(d, 0.002, 0.006, 1.0, 0.0)
        rnd = t.n("ShaderNodeTexWhiteNoise", board, props={"noise_dimensions": "1D"})["Value"]
        g = _grain(t, t.vec(py + pz, px * 3.0 + rnd * 11.0, 0.0), (0.7, 1.0, 1.0), 0.3)
        k = contrast if contrast is not None else P("plank_contrast", 0.45)
        base = S.mix_rgb(t, rnd, tuple(c * (1.0 - k) for c in C(key)[:3]) + (1.0,),
                         tuple(c * (1.0 + k * 1.4) for c in C(key)[:3]) + (1.0,))
        col = S.mix_rgb(t, g, base, tuple(c * 0.6 for c in C(key)[:3]) + (1.0,))
        col = S.mix_rgb(t, joint, col, (0.01, 0.007, 0.005, 1.0))
        return S.bsdf(t, Base_Color=col, Roughness=0.6, Specular_IOR_Level=0.35)["BSDF"]
    return S.material(name, build)


@_reg("SHJ.TimberPlanks")
def timber_planks():
    """Vertical board cladding of the walls."""
    return _planks("SHJ.TimberPlanks", "timber_plank")


@_reg("SHJ.CeilingBoards")
def ceiling_boards():
    """The darker board ceiling above the timber beam grid."""
    return _planks("SHJ.CeilingBoards", "ceiling_board")


@_reg("SHJ.LacquerBlack")
def lacquer_black():
    return S.principled("SHJ.LacquerBlack", C("lacquer_black"), roughness=0.3, specular=0.5,
                        coat=0.5, coat_roughness=0.12)


def _motif_mask(t, P3, rows=26.0, cols=9.0, keep=0.45, size=0.23):
    """Sparse little calligraphic motifs in cylindrical coordinates
    (angle x height) -- the gold decoration on the lacquered columns."""
    px, py, pz = t.sep(P3)
    ang = t.math("ARCTAN2", py, px)
    uv = t.vec(ang * (cols / 6.2832), pz * rows * 0.35, 0.0)
    dist, rnd = _cells(t, uv, 1.0)
    r1 = t.sep(rnd)[0]
    keep_m = t.math("LESS_THAN", r1, keep)
    blob = t.map_range(dist, size * 0.7, size, 1.0, 0.0)
    # break blobs into strokes with a stretched noise
    n = S.noise(t, t.vec(t.sep(uv)[0] * 3.0, t.sep(uv)[1] * 9.0, 0.0), scale=3.0,
                detail=2.0)["Fac"]
    strokes = t.map_range(n, 0.45, 0.55, 0.0, 1.0)
    return blob * keep_m * strokes


@_reg("SHJ.LacquerBlackGold")
def lacquer_black_gold():
    """Blue-black lacquer with sparse calligraphic motifs (the structural
    columns); the motif colour is the palette's ``column_motif`` -- pale
    silver in the tea house (the name stays for the gilded variants)."""
    def build(t: Tree):
        m = _motif_mask(t, _obj(t), rows=P("motif_rows", 7.0), cols=P("motif_cols", 5.0))
        col = S.mix_rgb(t, m, C("lacquer_blue_black"), C("column_motif"))
        return S.bsdf(t, Base_Color=col, Metallic=m * P("column_motif_metal", 0.0), Roughness=t.mix(m, 0.35, 0.35),
                      Specular_IOR_Level=0.5, Coat_Weight=t.mix(m, 0.2, 0.0),
                      Coat_Roughness=0.12)["BSDF"]
    return S.material("SHJ.LacquerBlackGold", build)


@_reg("SHJ.LacquerSlate")
def lacquer_slate():
    """Slate-blue lacquer with sparse gold motifs (the hall's front columns)."""
    def build(t: Tree):
        m = _motif_mask(t, _obj(t), rows=P("motif_rows", 7.0), cols=P("motif_cols", 5.0))
        col = S.mix_rgb(t, m, P("slate", (0.1, 0.14, 0.19, 1.0)), P("slate_motif", (0.7, 0.72, 0.74, 1.0)))
        return S.bsdf(t, Base_Color=col, Metallic=m * P("slate_motif_metal", 0.0), Roughness=t.mix(m, 0.35, 0.35),
                      Specular_IOR_Level=0.5, Coat_Weight=t.mix(m, 0.4, 0.0),
                      Coat_Roughness=0.15)["BSDF"]
    return S.material("SHJ.LacquerSlate", build)


@_reg("SHJ.LacquerBrown")
def lacquer_brown():
    """Dark brown lacquer (colonnade architrave)."""
    return S.principled("SHJ.LacquerBrown", P("lacquer_brown", (0.13, 0.085, 0.055)), roughness=0.3,
                        specular=0.5, coat=0.5, coat_roughness=0.12)


@_reg("SHJ.TimberLight")
def timber_light():
    """Lighter board ceiling (right hall, lit by its downlights)."""
    return wood("SHJ.TimberLight", P("timber_light", (0.34, 0.2, 0.1, 1.0)),
                (0.22, 0.12, 0.06, 1.0), rough=0.5, scale=(12.0, 0.6, 1.0), strength=0.3)


@_reg("SHJ.LacquerRed")
def lacquer_red():
    """Red lacquer column sleeve with a faint darker diaper pattern."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        ang = t.math("ARCTAN2", py, px)
        uv = t.vec(ang * 1.6, pz * 6.0, 0.0)
        dist, rnd = _cells(t, uv, 1.0)
        m = t.map_range(dist, 0.12, 0.2, 0.55, 0.0)
        col = S.mix_rgb(t, m, C("lacquer_red"), tuple(c * 0.45 for c in C("lacquer_red")[:3]) + (1.0,))
        return S.bsdf(t, Base_Color=col, Roughness=0.35, Specular_IOR_Level=0.5,
                      Coat_Weight=0.4, Coat_Roughness=0.15)["BSDF"]
    return S.material("SHJ.LacquerRed", build)


@_reg("SHJ.Gold")
def gold():
    return S.principled("SHJ.Gold", C("gold"), roughness=0.32, metallic=0.9, specular=0.6)


@_reg("SHJ.GoldOlive")
def gold_olive():
    """Olive-gold lacquered edging of the display shelf."""
    return S.principled("SHJ.GoldOlive", C("gold_olive"), roughness=0.4, metallic=0.45,
                        specular=0.5)


@_reg("SHJ.Plaque")
def plaque():
    """Black lacquered board with rows of small gold characters."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        # object X = along the board, Z = up (rows of text)
        h = P("plaque_height", 0.53)
        v = (pz - h * 0.5) / h
        rows = t.map_range(t.abs(v), 0.18, 0.22, 1.0, 0.0)
        cells_u = px * 9.0
        dist, rnd = _cells(t, t.vec(cells_u, pz * 30.0, 0.0), 1.0)
        chars = t.map_range(dist, 0.25, 0.35, 1.0, 0.0) * t.map_range(t.sep(rnd)[0], 0.15, 0.2, 0.0, 1.0)
        m = t.clamp01(rows * chars) * P("plaque_text", 0.45)
        col = S.mix_rgb(t, m, C("lacquer_black"), P("plaque_ink", (0.55, 0.5, 0.4, 1.0)))
        return S.bsdf(t, Base_Color=col, Metallic=m * 0.4, Roughness=0.4,
                      Specular_IOR_Level=0.5, Coat_Weight=0.3)["BSDF"]
    return S.material("SHJ.Plaque", build)


@_reg("SHJ.CloudPanel")
def cloud_panel():
    """Warm lacquered panel written with light-blue cursive glyphs in tight
    vertical columns (the panels flanking the Shanhaijing logo).  Each glyph
    is a few brush strokes: contour bands of a per-glyph noise field inside an
    elliptical glyph box, with a random share of the boxes left empty.
    Object X runs along the panel, Z up."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        u = px / P("glyph_pitch", 0.16)
        v = pz / P("glyph_rows", 0.12)
        cell = t.vec(t.math("FLOOR", u), t.math("FLOOR", v), 0.0)
        rnd = t.n("ShaderNodeTexWhiteNoise", cell, props={"noise_dimensions": "3D"})["Color"]
        rx, ry, rz = t.sep(rnd)
        fu = t.math("FRACT", u) - 0.5 + (rx - 0.5) * 0.12
        fv = t.math("FRACT", v) - 0.5
        n = S.noise(t, t.vec(fu * 2.2 + rx * 37.0, fv * 2.2 + ry * 37.0, rz * 11.0), scale=1.4,
                    detail=1.0, rough=0.4)["Fac"]
        stroke = t.map_range(t.abs(n - 0.5), 0.025, 0.055, 1.0, 0.0)
        blob = t.map_range(n, 0.6, 0.64, 0.0, 1.0) * 0.9
        e = (fu / 0.36) * (fu / 0.36) + (fv / 0.44) * (fv / 0.44)
        box = t.map_range(e, 0.6, 1.0, 1.0, 0.0)
        keep = t.map_range(rz, 0.12, 0.14, 0.0, 1.0)
        m = t.clamp01(t.clamp01(stroke + blob) * box * keep)
        col = S.mix_rgb(t, m, C("cloud_panel"), C("cloud_blue"))
        return S.bsdf(t, Base_Color=col, Roughness=0.45, Specular_IOR_Level=0.45,
                      Emission_Color=C("cloud_blue"), Emission_Strength=m * P("cloud_glow", 0.35))["BSDF"]
    return S.material("SHJ.CloudPanel", build)


@_reg("SHJ.LogoPaper")
def logo_paper():
    return S.principled("SHJ.LogoPaper", C("logo_paper"), roughness=0.7, specular=0.35)


@_reg("SHJ.LogoInk")
def logo_ink():
    return S.principled("SHJ.LogoInk", C("logo_ink"), roughness=0.5, specular=0.4)


@_reg("SHJ.JadePanel")
def jade_panel():
    """Dark green lacquered base panels with a gold key-fret border."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        uv = t.vec(px * 22.0, pz * 22.0, 0.0)
        cx = t.math("FRACT", t.sep(uv)[0])
        cz = t.math("FRACT", t.sep(uv)[1])
        fret = t.clamp01(t.map_range(t.abs(cx - 0.5), 0.3, 0.34, 1.0, 0.0) +
                         t.map_range(t.abs(cz - 0.5), 0.3, 0.34, 1.0, 0.0)) * 0.5
        col = S.mix_rgb(t, fret, C("jade_green"), C("gold_olive"))
        return S.bsdf(t, Base_Color=col, Roughness=0.35, Specular_IOR_Level=0.5,
                      Coat_Weight=0.3)["BSDF"]
    return S.material("SHJ.JadePanel", build)


@_reg("SHJ.FretBand")
def fret_band():
    """Black lacquer band with a gold key-fret (回纹) meander, laid out along
    the band in object X/Y and Z (the display cabinet's plinth, shelf edge
    and top rail)."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        k = P("fret_scale", 14.0)
        u = t.math("FRACT", (px + py) * k)
        v = t.math("FRACT", pz * k)
        d = t.max(t.abs(u - 0.5), t.abs(v - 0.5))            # square rings

        def ring(r0, r1):
            return t.clamp01(t.map_range(d, r0 - 0.02, r0, 0.0, 1.0) * t.map_range(d, r1, r1 + 0.02, 1.0, 0.0))
        # outer ring broken on one side + inner ring = a stylised key fret
        gap = t.map_range(t.abs(v - 0.62), 0.06, 0.08, 0.0, 1.0)
        outer = ring(0.39, 0.415) * t.max(gap, t.map_range(u, 0.52, 0.54, 1.0, 0.0))
        gold = t.clamp01(outer + ring(0.16, 0.185)) * P("fret_gold", 0.8)
        col = S.mix_rgb(t, gold, P("ebony", (0.025, 0.02, 0.016, 1.0)), C("gold"))
        return S.bsdf(t, Base_Color=col, Roughness=t.mix(gold, 0.55, 0.3), Metallic=t.mix(gold, 0.0, 0.85),
                      Specular_IOR_Level=0.35)["BSDF"]
    return S.material("SHJ.FretBand", build)


@_reg("SHJ.EbonyMatte")
def ebony_matte():
    """Satin black-stained frame wood (display cabinet)."""
    return S.principled("SHJ.EbonyMatte", P("ebony", (0.025, 0.02, 0.016, 1.0)), roughness=0.55, specular=0.35)


@_reg("SHJ.DoorWood")
def door_wood():
    """Narrow vertical boards of the moon-gate door."""
    return _planks("SHJ.DoorWood", "door_wood", width=0.065, contrast=0.25)


@_reg("SHJ.GateRim")
def gate_rim():
    return S.principled("SHJ.GateRim", P("gate_rim", (0.06, 0.08, 0.07)), roughness=0.35, specular=0.5, coat=0.4)


@_reg("SHJ.LatticeWood")
def lattice_wood():
    return S.principled("SHJ.LatticeWood", (0.09, 0.05, 0.03), roughness=0.5, specular=0.4)


@_reg("SHJ.LatticeBlue")
def lattice_blue():
    """Blue-black lacquered grid lattice (left window wall)."""
    return S.principled("SHJ.LatticeBlue", (0.02, 0.035, 0.07), roughness=0.4, specular=0.4,
                        coat=0.3)


@_reg("SHJ.GlassNight")
def glass_night():
    """Window glass: clear with a slight blue tint and real reflections."""
    return S.glass_mat("SHJ.GlassNight", P("night_glass_tint", (0.75, 0.85, 1.0)),
                       roughness=0.02, ior=1.5, reflect=0.6)


@_reg("SHJ.GlassFrosted")
def glass_frosted():
    """Frosted (acid-etched) window glass: light from behind scatters
    diffusely through the pane (translucent), so the night courtyard reads as
    a dusky blue and the garden lamps behind it as large soft warm glows;
    a thin glossy film on top."""
    def build(t: Tree):
        fres = t.n("ShaderNodeFresnel", IOR=1.5)["Fac"]
        tint = P("frost_tint", (0.92, 0.94, 1.0, 1.0))
        tr = t.n("ShaderNodeBsdfTranslucent", Color=tint)["BSDF"]
        # part of the light goes straight through, blurred: the lamps stay soft blobs
        blur = t.n("ShaderNodeBsdfGlass", Color=tint, Roughness=P("frost_roughness", 0.3), IOR=1.0)["BSDF"]
        body = t.n("ShaderNodeMixShader", P("frost_clear", 0.55), tr, blur)["Shader"]
        gl = t.n("ShaderNodeBsdfGlossy", Color=(1, 1, 1, 1), Roughness=0.12)["BSDF"]
        return t.n("ShaderNodeMixShader", fres * 0.5, body, gl)["Shader"]
    return S.material("SHJ.GlassFrosted", build)


@_reg("SHJ.Globe")
def globe():
    return S.emission_mat("SHJ.Globe", P("globe_color", (1.0, 0.58, 0.2)), P("globe_emission", 12.0))


@_reg("SHJ.GlassCase")
def glass_case():
    return S.glass_mat("SHJ.GlassCase", (0.97, 0.99, 0.98), roughness=0.0, ior=1.5, reflect=P("case_reflect", 0.35))


@_reg("SHJ.NightBackdrop")
def night_backdrop():
    """Night courtyard seen through the lattice windows: dark blue sky
    glow (emissive, like the world) with soft vertical falloff."""
    def build(t: Tree):
        z = t.sep(_obj(t))[2]
        k = t.map_range(z, P("backdrop_z0", 0.0), P("backdrop_height", 4.0), 0.0, 1.0)
        col = S.mix_rgb(t, k, P("night_low", (0.08, 0.14, 0.32, 1.0)),
                        P("night_high", (0.02, 0.04, 0.12, 1.0)))
        return t.n("ShaderNodeEmission", Color=col, Strength=P("backdrop_strength", 1.0))["Emission"]
    return S.material("SHJ.NightBackdrop", build)


@_reg("SHJ.NightBackdropBay")
def night_backdrop_bay():
    """The brighter garden seen through the big lattice window of the left
    bay (same night gradient, its own strength)."""
    def build(t: Tree):
        z = t.sep(_obj(t))[2]
        k = t.map_range(z, 0.0, P("bay_backdrop_height", 4.0), 0.0, 1.0)
        col = S.mix_rgb(t, k, P("bay_low", (0.08, 0.14, 0.32, 1.0)),
                        P("bay_high", (0.02, 0.04, 0.12, 1.0)))
        return t.n("ShaderNodeEmission", Color=col, Strength=P("bay_backdrop_strength", 1.5))["Emission"]
    return S.material("SHJ.NightBackdropBay", build)


@_reg("SHJ.Downlight")
def downlight():
    return S.emission_mat("SHJ.Downlight", (1.0, 0.86, 0.66), P("downlight_emission", 40.0))


@_reg("SHJ.DownlightTrim")
def downlight_trim():
    return S.principled("SHJ.DownlightTrim", (0.5, 0.45, 0.38), roughness=0.35, metallic=0.7)


# --------------------------------------------------------------- furniture
@_reg("SHJ.Rosewood")
def rosewood():
    """Dark reddish-brown hardwood (tables, chairs)."""
    return wood("SHJ.Rosewood", C("rosewood"),
                tuple(c * 0.5 for c in C("rosewood")[:3]) + (1.0,), rough=0.32,
                coat=P("rosewood_coat", 0.6), coat_rough=0.12, scale=(1.0, 18.0, 18.0), strength=0.3,
                spec=0.5)


@_reg("SHJ.TableTop")
def table_top():
    """Light golden lacquered tabletop panel (with a faint grain)."""
    return wood("SHJ.TableTop", C("table_inlay"),
                tuple(c * 0.78 for c in C("table_inlay")[:3]) + (1.0,), rough=0.22,
                coat=P("table_coat", 0.9), coat_rough=P("table_coat_roughness", 0.06),
                scale=(0.6, 9.0, 9.0), strength=0.25, spec=0.5)


@_reg("SHJ.TableTopDark")
def table_top_dark():
    """Dark olive-black stone top under a glossy coat (the tables in the middle
    of the hall): faint cloudy mottling, crisp reflections of the lamps."""
    def build(t: Tree):
        P3 = _obj(t)
        n = S.noise(t, P3, scale=6.0, detail=5.0, rough=0.6)["Fac"]
        base = P("table_dark", (0.035, 0.033, 0.026))
        col = S.mix_rgb(t, t.map_range(n, 0.35, 0.7, 0.0, 1.0), tuple(c * 0.7 for c in base[:3]) + (1.0,),
                        tuple(c * 1.5 for c in base[:3]) + (1.0,))
        return S.bsdf(t, Base_Color=col, Roughness=0.35, Specular_IOR_Level=0.5,
                      Coat_Weight=P("table_dark_coat", 1.0), Coat_Roughness=P("table_dark_coat_roughness", 0.05))["BSDF"]
    return S.material("SHJ.TableTopDark", build)


@_reg("SHJ.Inlay")
def inlay():
    """Pale gold inlay lines (tabletop border)."""
    return S.principled("SHJ.Inlay", P("inlay", (0.95, 0.82, 0.55)), roughness=0.25, metallic=0.5, specular=0.6)


@_reg("SHJ.CushionRed")
def cushion_red():
    def build(t: Tree):
        return S.bsdf(t, Base_Color=C("cushion_red"), Roughness=0.55,
                      Sheen_Weight=0.6, Sheen_Tint=(1.0, 0.5, 0.45, 1.0),
                      Specular_IOR_Level=0.4)["BSDF"]
    return S.material("SHJ.CushionRed", build)


@_reg("SHJ.Stud")
def stud():
    """Copper-brass decorative studs on legs and posts."""
    return S.principled("SHJ.Stud", (0.85, 0.55, 0.42), roughness=0.25, metallic=0.95, specular=0.6)


@_reg("SHJ.Brass")
def brass():
    """Hammered brass (kettles, trays, stretchers): small overlapping dimples
    (Voronoi bump) and a satin finish, so it glows golden instead of
    mirroring the dark room."""
    def build(t: Tree):
        P3 = _obj(t)
        v = t.n("ShaderNodeTexVoronoi", P3, Scale=P("hammer_scale", 90.0),
                props={"voronoi_dimensions": "3D", "feature": "F1"})["Distance"]
        bump = t.n("ShaderNodeBump", Strength=P("hammer_strength", 0.35), Distance=0.002, Height=v)["Normal"]
        n = S.noise(t, P3, scale=25.0, detail=3.0)["Fac"]
        col = S.mix_rgb(t, t.map_range(n, 0.35, 0.7, 0.0, 1.0), C("brass"),
                        tuple(c * 0.75 for c in C("brass")[:3]) + (1.0,))
        return S.bsdf(t, Base_Color=col, Metallic=1.0, Roughness=P("brass_roughness", 0.38),
                      Specular_IOR_Level=0.6, Normal=bump)["BSDF"]
    return S.material("SHJ.Brass", build)


# -------------------------------------------------------------------- props
def _porcelain(name, density=1.0, seed=0.0, blue_share=0.5, pigment="porcelain_blue", glaze="porcelain_white"):
    """Blue-and-white porcelain: glossy white glaze with cobalt decoration
    -- horizontal bands near rim/foot plus scrolling floral blobs between.
    Decoration lives in object space (Z up, angle around the axis)."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        ang = t.math("ARCTAN2", py, px)
        uv = t.vec(ang * 2.0 * density + seed, pz * 14.0 * density, seed)
        n = S.noise(t, uv, scale=1.6, detail=4.0, rough=0.55, distortion=1.2)["Fac"]
        flor = t.map_range(n, 0.5 - blue_share * 0.12, 0.56 - blue_share * 0.1, 0.0, 1.0)
        bands = t.n("ShaderNodeTexWave", t.vec(0.0, 0.0, pz * 3.0 * density + seed), Scale=1.0,
                    Distortion=0.0, props={"wave_type": "BANDS", "bands_direction": "Z",
                                           "wave_profile": "SIN"})["Fac"]
        band = t.map_range(bands, 0.9, 0.95, 0.0, 1.0)
        m = t.clamp01(flor + band)
        col = S.mix_rgb(t, m, C(glaze), C(pigment))
        return S.bsdf(t, Base_Color=col, Roughness=0.12, Specular_IOR_Level=0.55,
                      Coat_Weight=0.6, Coat_Roughness=0.05, Subsurface_Weight=0.05)["BSDF"]
    return S.material(name, build)


@_reg("SHJ.PorcelainBW")
def porcelain_bw():
    return _porcelain("SHJ.PorcelainBW", 1.0, 0.0, 0.3)


@_reg("SHJ.PorcelainBW2")
def porcelain_bw2():
    return _porcelain("SHJ.PorcelainBW2", 1.6, 3.7, 0.5)


@_reg("SHJ.PorcelainGreen")
def porcelain_green():
    """Pale celadon glaze with dark green decoration (the shelf-top planters)."""
    return _porcelain("SHJ.PorcelainGreen", 1.3, 1.9, 0.25, pigment="planter_green", glaze="celadon")


@_reg("SHJ.PorcelainWhite")
def porcelain_white():
    return S.principled("SHJ.PorcelainWhite", C("porcelain_white"), roughness=0.12, specular=0.55,
                        coat=0.6, coat_roughness=0.05)


@_reg("SHJ.PorcelainLilac")
def porcelain_lilac():
    """White floor vase with pale lilac scroll decoration."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        ang = t.math("ARCTAN2", py, px)
        n = S.noise(t, t.vec(ang * 1.5, pz * 5.0, 0.0), scale=1.4, detail=3.0,
                    distortion=1.5)["Fac"]
        m = t.map_range(n, 0.52, 0.58, 0.0, 1.0)
        col = S.mix_rgb(t, m, C("porcelain_white"), (0.55, 0.45, 0.7, 1.0))
        return S.bsdf(t, Base_Color=col, Roughness=0.15, Specular_IOR_Level=0.55,
                      Coat_Weight=0.5, Coat_Roughness=0.05)["BSDF"]
    return S.material("SHJ.PorcelainLilac", build)


@_reg("SHJ.Celadon")
def celadon():
    return S.principled("SHJ.Celadon", C("celadon"), roughness=0.15, specular=0.55, coat=0.5)


@_reg("SHJ.Bamboo")
def bamboo_stalk():
    """Glossy pale yellow-green bamboo stalks."""
    return S.principled("SHJ.Bamboo", P("bamboo", (0.42, 0.52, 0.16, 1.0)), roughness=0.3, specular=0.5,
                        coat=0.3)


@_reg("SHJ.CaddyLime")
def caddy_lime():
    """Glossy yellow-green glaze (tea caddies in the cabinet)."""
    return S.principled("SHJ.CaddyLime", (0.62, 0.72, 0.2), roughness=0.15, specular=0.55, coat=0.5)


@_reg("SHJ.PinkGlass")
def pink_glass():
    return S.principled("SHJ.PinkGlass", (0.75, 0.2, 0.4), roughness=0.1, specular=0.6, coat=0.6)


@_reg("SHJ.Stone")
def stone():
    """Pale carved stone (guardian lions)."""
    def build(t: Tree):
        n = S.noise(t, _obj(t), scale=18.0, detail=4.0, rough=0.6)["Fac"]
        col = S.mix_rgb(t, t.map_range(n, 0.35, 0.7, 0.0, 1.0), C("stone_lion"),
                        tuple(c * 0.78 for c in C("stone_lion")[:3]) + (1.0,))
        return S.bsdf(t, Base_Color=col, Roughness=0.6, Specular_IOR_Level=0.4)["BSDF"]
    return S.material("SHJ.Stone", build)


@_reg("SHJ.Leaf")
def leaf():
    def build(t: Tree):
        n = S.noise(t, _obj(t), scale=9.0, detail=2.0)["Fac"]
        col = S.mix_rgb(t, n, C("leaf_green"), (0.25, 0.5, 0.12, 1.0))
        return S.bsdf(t, Base_Color=col, Roughness=0.45, Specular_IOR_Level=0.45,
                      Subsurface_Weight=0.15, Transmission_Weight=0.1)["BSDF"]
    return S.material("SHJ.Leaf", build)


@_reg("SHJ.Grass")
def grass():
    return S.principled("SHJ.Grass", (0.18, 0.45, 0.1), roughness=0.5, specular=0.4)


@_reg("SHJ.Soil")
def soil():
    return S.principled("SHJ.Soil", (0.05, 0.035, 0.025), roughness=0.95)


@_reg("SHJ.LanternPaper")
def lantern_paper():
    """Glowing red silk lantern: lit from inside, with darker rib lines."""
    def build(t: Tree):
        P3 = _obj(t)
        px, py, pz = t.sep(P3)
        ang = t.math("ARCTAN2", py, px)
        rib = t.map_range(t.abs(t.math("FRACT", ang * (P("lantern_ribs", 14.0) / 6.2832)) - 0.5),
                          0.44, 0.49, 0.0, 1.0)
        col = S.mix_rgb(t, rib, C("lantern_red"), (0.7, 0.04, 0.03, 1.0))
        glow = t.mix(rib, P("lantern_emission", 6.0), P("lantern_emission", 6.0) * 0.8)
        return S.bsdf(t, Base_Color=col, Roughness=0.6, Specular_IOR_Level=0.3,
                      Emission_Color=C("lantern_red"), Emission_Strength=glow)["BSDF"]
    return S.material("SHJ.LanternPaper", build)


@_reg("SHJ.LanternGold")
def lantern_gold():
    """Gold caps and characters of the lanterns (slightly self-lit by the
    lantern)."""
    return S.principled("SHJ.LanternGold", P("lantern_gold", (0.95, 0.72, 0.22, 1.0)), roughness=0.4, metallic=0.3,
                        specular=0.6, emission=P("lantern_gold", (0.95, 0.72, 0.22, 1.0)),
                        emission_strength=P("lantern_gold_emission", 0.6))


@_reg("SHJ.Tassel")
def tassel():
    return S.principled("SHJ.Tassel", (0.7, 0.45, 0.12), roughness=0.6)


@_reg("SHJ.TeaBoxRed")
def teabox_red():
    return S.principled("SHJ.TeaBoxRed", (0.45, 0.05, 0.04), roughness=0.4, specular=0.5)


@_reg("SHJ.TeaBoxGreen")
def teabox_green():
    return S.principled("SHJ.TeaBoxGreen", (0.35, 0.42, 0.2), roughness=0.45, specular=0.5)


@_reg("SHJ.TeaBoxSage")
def teabox_sage():
    return S.principled("SHJ.TeaBoxSage", (0.5, 0.55, 0.38), roughness=0.5, specular=0.4)


@_reg("SHJ.TeaBoxCream")
def teabox_cream():
    return S.principled("SHJ.TeaBoxCream", (0.75, 0.68, 0.5), roughness=0.5, specular=0.4)


@_reg("SHJ.GiftBlue")
def gift_blue():
    return S.principled("SHJ.GiftBlue", (0.02, 0.35, 0.65), roughness=0.3, specular=0.5,
                        emission=(0.05, 0.45, 0.8), emission_strength=P("gift_glow", 0.4))


@_reg("SHJ.PandaWhite")
def panda_white():
    return S.principled("SHJ.PandaWhite", (0.88, 0.88, 0.86), roughness=0.2, specular=0.5, coat=0.5)


@_reg("SHJ.PandaBlack")
def panda_black():
    return S.principled("SHJ.PandaBlack", P("panda_blue", (0.1, 0.16, 0.3)), roughness=0.2, specular=0.5, coat=0.5)


@_reg("SHJ.Snack")
def snack():
    return S.principled("SHJ.Snack", (0.75, 0.35, 0.3), roughness=0.6, specular=0.3)


@_reg("SHJ.Plate")
def plate():
    return S.principled("SHJ.Plate", (0.85, 0.82, 0.8), roughness=0.15, specular=0.5, coat=0.4)


@_reg("SHJ.Tea")
def tea():
    return S.principled("SHJ.Tea", (0.35, 0.18, 0.04), roughness=0.05, specular=0.5)
