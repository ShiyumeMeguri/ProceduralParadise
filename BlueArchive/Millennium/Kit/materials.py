"""
Millennium material library (``MIL.*``).

Every material is procedural (no bitmaps) and takes its base colours from the
academy palette so all Millennium rooms share one look.  ``get(name)`` builds a
material on first use.
"""
from __future__ import annotations

import math

import bpy

from Core.nodes import Tree
from Core import shaders as S
from .. import PALETTE, MOD

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
    if m is not None and m.get("mil_built"):
        return m
    m = _BUILDERS[name]()
    m["mil_built"] = True
    return m


def all_names():
    return sorted(_BUILDERS)


def C(key, a=1.0):
    r, g, b = PALETTE[key]
    return (r, g, b, a)


# ------------------------------------------------------------------ floor
@_reg("MIL.Marble")
def marble():
    """Polished white/blue marble in 1.2 m tiles with thin grout joints.

    Tiles are laid in the object's local XY (room frame) starting at the
    origin, so the room builder controls alignment with the facade grid.
    Each tile receives an independent random offset of the vein pattern.
    """
    tile = MOD["floor_tile"]

    def build(t: Tree):
        P = t.n("ShaderNodeTexCoord")["Object"]
        g = P / tile
        cell = t.vmath("FLOOR", g)
        frac = t.vmath("FRACTION", g)
        fx, fy, _ = t.sep(frac)
        ex = t.min(fx, 1.0 - fx)
        ey = t.min(fy, 1.0 - fy)
        edge = t.min(ex, ey) * tile                  # distance to joint (m)
        grout = t.map_range(edge, 0.004, 0.0075, 1.0, 0.0)
        rnd = t.n("ShaderNodeTexWhiteNoise", cell, props={"noise_dimensions": "3D"})["Color"]
        # per-tile pattern offset + slight rotation of the vein direction
        Pm = P * PARAMS.get("marble_scale", 0.55) + rnd * 37.0
        dist = S.noise(t, Pm, scale=1.6, detail=6.0, rough=0.62)["Fac"]
        wave = t.n("ShaderNodeTexWave", Pm, Scale=0.9, Distortion=9.5, Detail=6.0,
                   Detail_Scale=1.4, Detail_Roughness=0.62,
                   props={"wave_type": "BANDS", "bands_direction": "DIAGONAL",
                          "wave_profile": "SIN"})["Fac"]
        veins = S.ramp(t, wave, [(0.0, (1, 1, 1, 1)), (0.035, (0.25, 0.25, 0.25, 1)),
                                 (0.11, (0, 0, 0, 1)), (1.0, (0, 0, 0, 1))])["Color"]
        fine = t.n("ShaderNodeTexWave", Pm * 2.3, Scale=1.7, Distortion=14.0, Detail=8.0,
                   props={"wave_type": "BANDS", "bands_direction": "DIAGONAL"})["Fac"]
        fine_v = S.ramp(t, fine, [(0.0, (0.55, 0.55, 0.55, 1)), (0.03, (0, 0, 0, 1)),
                                  (1.0, (0, 0, 0, 1))])["Color"]
        cloud = S.ramp(t, dist, [(0.3, (0, 0, 0, 1)), (0.75, (0.35, 0.35, 0.35, 1))])["Color"]
        v = t.n("ShaderNodeRGBToBW", veins).o * 0.8 + t.n("ShaderNodeRGBToBW", fine_v).o * 0.35 \
            + t.n("ShaderNodeRGBToBW", cloud).o * 0.5
        base = S.mix_rgb(t, t.clamp01(v), C("marble_base"), C("marble_vein"))
        col = S.mix_rgb(t, grout, base, C("grout"))
        rough = t.mix(grout, PARAMS.get("marble_roughness", 0.045), 0.55)
        b = S.bsdf(t, Base_Color=col, Roughness=rough, Specular_IOR_Level=0.28,
                   Coat_Weight=PARAMS.get("marble_coat", 0.1), Coat_Roughness=0.03)
        return b["BSDF"]
    return S.material("MIL.Marble", build)


# ------------------------------------------------------------ architecture
@_reg("MIL.WallPaint")
def wall_paint():
    return S.principled("MIL.WallPaint", C("wall_white"), roughness=0.55, specular=0.35)


@_reg("MIL.TrimWhite")
def trim_white():
    return S.principled("MIL.TrimWhite", C("trim_white"), roughness=0.28, specular=0.5)


@_reg("MIL.CeilingPanel")
def ceiling_panel():
    """Satin metal ceiling panels in a 1.2 x 1.5 m module (tile x facade)
    with thin dark shadow-gap joints; slightly reflective so window light and
    fixtures streak across them, as in the reference.  The joint grid is in
    object space, i.e. aligned with the room frame / building grid."""
    jx, jy, jw = MOD["floor_tile"], MOD["facade"], 0.012

    def build(t: Tree):
        P = t.n("ShaderNodeTexCoord")["Object"]
        px, py, pz = t.sep(P)
        fx = t.math("FRACT", px / jx)
        fy = t.math("FRACT", py / jy)
        dx = t.min(fx, 1.0 - fx) * jx
        dy = t.min(fy, 1.0 - fy) * jy
        joint = t.map_range(t.min(dx, dy), jw * 0.5, jw * 0.5 + 0.004, 1.0, 0.0)
        col = S.mix_rgb(t, joint, C("ceiling_panel"), C("ceiling_joint"))
        b = S.bsdf(t, Base_Color=col, Roughness=t.mix(joint, 0.22, 0.7),
                   Metallic=t.mix(joint, 0.35, 0.0), Specular_IOR_Level=0.6)
        return b["BSDF"]
    return S.material("MIL.CeilingPanel", build)


@_reg("MIL.CeilingJoint")
def ceiling_joint():
    return S.principled("MIL.CeilingJoint", C("ceiling_joint"), roughness=0.6)


@_reg("MIL.Soffit")
def soffit():
    return S.principled("MIL.Soffit", C("ceiling_panel"), roughness=0.4, metallic=0.2)


@_reg("MIL.Mullion")
def mullion():
    return S.principled("MIL.Mullion", C("mullion"), roughness=0.28, metallic=0.55,
                        specular=0.6)


@_reg("MIL.Glass")
def glass():
    return S.glass_mat("MIL.Glass", C("glass_tint"), roughness=0.0, ior=1.5, reflect=0.45,
                       camera_boost=PARAMS.get("glass_camera_boost", 1.0),
                       coating={"reflect": 0.3, "tint": C("glass_coating")[:3]})


@_reg("MIL.FacadeSpandrel")
def spandrel():
    return S.principled("MIL.FacadeSpandrel", C("facade_spandrel"), roughness=0.25,
                        metallic=0.6, specular=0.6)


@_reg("MIL.MetalFrame")
def metal_frame():
    return S.principled("MIL.MetalFrame", C("metal_frame"), roughness=0.35, metallic=0.6)


# --------------------------------------------------------------- furniture
@_reg("MIL.DeskTop")
def desk_top():
    return S.principled("MIL.DeskTop", C("desk_top"), roughness=PARAMS.get("desk_roughness", 0.22),
                        specular=0.5, coat=PARAMS.get("desk_coat", 0.25), coat_roughness=0.08)


@_reg("MIL.DeskEdge")
def desk_edge():
    return S.principled("MIL.DeskEdge", C("desk_edge"), roughness=0.35, metallic=0.3)


@_reg("MIL.ChairWhite")
def chair_white():
    return S.principled("MIL.ChairWhite", C("chair_white"), roughness=0.32, specular=0.5,
                        coat=0.15)


@_reg("MIL.ChairBlue")
def chair_blue():
    """Translucent blue polypropylene: a little of the light passing through
    the thin shell is modelled as a faint glow of the base colour."""
    return S.principled("MIL.ChairBlue", C("chair_blue"), roughness=0.55, specular=0.08,
                        emission=C("chair_blue"), emission_strength=PARAMS.get("chair_glow", 0.0))


@_reg("MIL.CushionBlue")
def cushion_blue():
    def build(t: Tree):
        return S.bsdf(t, Base_Color=C("cushion_blue"), Roughness=0.75,
                      Sheen_Weight=0.4, Sheen_Tint=(0.6, 0.8, 1.0, 1.0))["BSDF"]
    return S.material("MIL.CushionBlue", build)


@_reg("MIL.Aluminium")
def aluminium():
    return S.principled("MIL.Aluminium", (0.78, 0.8, 0.83), roughness=0.3, metallic=0.9)


@_reg("MIL.Screen")
def screen():
    return S.principled("MIL.Screen", (0.02, 0.03, 0.05), roughness=0.08, specular=0.6)


@_reg("MIL.Paper")
def paper():
    return S.principled("MIL.Paper", (0.85, 0.88, 0.9), roughness=0.7)


@_reg("MIL.BookBlue")
def book_blue():
    return S.principled("MIL.BookBlue", (0.02, 0.2, 0.7), roughness=0.5)


@_reg("MIL.BookTeal")
def book_teal():
    return S.principled("MIL.BookTeal", (0.05, 0.45, 0.55), roughness=0.5)


@_reg("MIL.BookGreen")
def book_green():
    return S.principled("MIL.BookGreen", (0.25, 0.5, 0.2), roughness=0.5)


# ---------------------------------------------------------------- lighting
@_reg("MIL.LED")
def led():
    """Linear pendant diffuser."""
    return S.emission_mat("MIL.LED", (0.92, 0.97, 1.0), 22.0)


@_reg("MIL.HoloEdge")
def holo_edge():
    return S.emission_mat("MIL.HoloEdge", C("holo_cyan"), PARAMS.get("holo_edge_strength", 9.0))


@_reg("MIL.HoloPanel")
def holo_panel():
    """Frosted, faintly self-lit acrylic sign panel."""
    def build(t: Tree):
        # lighter header band across the top ~15 % of the panel (object Z)
        z = t.sep(t.n("ShaderNodeTexCoord")["Object"])[2]
        zmax = PARAMS.get("holo_panel_height", 2.84)
        band = t.map_range(z, zmax * 0.80, zmax * 0.86, 0.0, 1.0)
        col = S.mix_rgb(t, band, (0.58, 0.7, 0.9, 1), (0.8, 0.9, 1.0, 1))
        b = S.bsdf(t, Base_Color=col, Roughness=0.18, Specular_IOR_Level=0.6,
                   Emission_Color=col, Emission_Strength=t.mix(band, 0.12, 0.3))["BSDF"]
        return b
    return S.material("MIL.HoloPanel", build)


@_reg("MIL.LogoBlue")
def logo_blue():
    return S.principled("MIL.LogoBlue", C("millennium_blue"), roughness=0.35,
                        emission=C("millennium_blue"), emission_strength=0.6)


@_reg("MIL.DoorGlass")
def door_glass():
    return S.principled("MIL.DoorGlass", (0.1, 0.45, 0.85), roughness=0.05, specular=0.7,
                        transmission=0.6, ior=1.5)
