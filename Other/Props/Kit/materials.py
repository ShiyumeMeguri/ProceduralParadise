"""
Props material library (``Props.*``), made for EEVEE.

Refractive bodies (water, goo, slime, the water balloon) read the per-vertex
``thickness`` that ``Shading.Thickness`` stores on their geometry: it drives
EEVEE's refraction and a Beer-Lambert tint exp(-(1 - colour) density d), the
same law as a Volume Absorption shader (EEVEE applies object volumes along
the camera ray, not the refracted one, so absorption lives in the surface).
Wood and bamboo read coordinates stored by their shapes (``wood_coordinate``,
``bamboo_coordinate``) so the grain follows the part however it moves.

Base colours come from the palette (``Props.json``); a scene may override
parameters and palette colours (``"color:<key>"``) through ``PARAMS``.
"""
from __future__ import annotations

from Core import shaders as S
from Core.nodes import Tree
from .. import PALETTE

LIBRARY = S.MaterialLibrary(PALETTE, "props_built")
PARAMS = LIBRARY.params
register = LIBRARY.register
get = LIBRARY.get
color = LIBRARY.color
param = LIBRARY.param

DITHERED_REFRACTION = {"surface_render_method": "DITHERED", "use_raytrace_refraction": True}


def attribute(tree: Tree, name, output="Fac", kind="GEOMETRY"):
    return tree.n("ShaderNodeAttribute", props={"attribute_name": name, "attribute_type": kind})[output]


def bump(tree: Tree, height, strength, distance=0.001):
    return tree.n("ShaderNodeBump", Strength=strength, Distance=distance, Height=height)["Normal"]


def rgb(rgba):
    return tuple(rgba[:3])


# ------------------------------------------------------------------ rubber & water
@register("Props.Latex")
def latex():
    """Thick rubber of a balloon's knot: translucent where stretched thin
    (``stretch`` attribute), deep and opaque where thick."""
    tint = rgb(color("rubber_red"))

    def build(tree: Tree):
        stretch = tree.max(attribute(tree, "stretch"), 1.0)
        thinness = tree.map_range(stretch, 1.0, 2.2, 0.0, 1.0)
        transmission = tree.mix(thinness, 0.12, 0.9)
        base = tree.mix(thinness, tuple(channel * channel * 0.7 for channel in tint), tint, "RGBA")
        grain = S.noise(tree, S.tex_coord(tree), 180.0, 3.0)["Fac"]
        return S.bsdf(tree, Base_Color=base, Roughness=tree.map_range(grain, 0.3, 0.7, 0.14, 0.24), IOR=1.45, Thin_Wall=True,
                      Transmission_Weight=transmission, Coat_Weight=0.35, Coat_Roughness=0.04, Specular_IOR_Level=0.5)["BSDF"]
    return S.material("Props.Latex", build, settings={**DITHERED_REFRACTION, "thickness_mode": "SLAB"})


@register("Props.WaterBalloon")
def water_balloon():
    """A water balloon as one surface: the water's refraction under a tinted
    rubber coat that pales where the rubber is stretched thin."""
    tint = rgb(color("rubber_red"))

    def build(tree: Tree):
        stretch = tree.max(attribute(tree, "stretch"), 1.0)
        thinness = tree.map_range(stretch, 1.0, 2.0, 0.0, 1.0)
        coat_tint = tree.mix(thinness, tuple(max(channel * channel, 0.02) for channel in tint), tint, "RGBA")
        coordinates = S.tex_coord(tree)
        grain = S.noise(tree, coordinates, 220.0, 3.0)["Fac"]
        texture = bump(tree, S.noise(tree, coordinates, 900.0, 2.0)["Fac"], 0.04, 0.0003)
        thickness = attribute(tree, S.THICKNESS_ATTRIBUTE)
        transmittance = S.beer_lambert(tree, color("balloon_absorption")[:3], param("balloon_absorption", 3.0), thickness)
        shader = S.bsdf(tree, Base_Color=transmittance, Roughness=0.0, IOR=1.333, Transmission_Weight=1.0, Coat_Weight=1.0, Coat_IOR=1.52,
                        Coat_Roughness=tree.map_range(grain, 0.3, 0.7, 0.14, 0.24), Coat_Tint=coat_tint, Coat_Normal=texture,
                        Specular_IOR_Level=0.5)["BSDF"]
        return S.eevee_refraction(tree, shader, tree.vmath("MULTIPLY", transmittance, coat_tint), thickness)
    return S.material("Props.WaterBalloon", build, settings=S.EEVEE_REFRACTION)


@register("Props.Water")
def water():
    """Clear water with a faint blue absorption."""
    def build(tree: Tree):
        thickness = attribute(tree, S.THICKNESS_ATTRIBUTE)
        transmittance = S.beer_lambert(tree, color("water_absorption")[:3], param("water_absorption", 6.0), thickness)
        shader = S.bsdf(tree, Base_Color=transmittance, Roughness=0.0, IOR=1.333, Transmission_Weight=1.0, Specular_IOR_Level=0.5)["BSDF"]
        return S.eevee_refraction(tree, shader, transmittance, thickness)
    return S.material("Props.Water", build, settings=S.EEVEE_REFRACTION)


def jelly(name):
    """Slime jelly: green through its thickness, a clear coat, flashes on a
    hit (``flash``) and shows a ragged wound (``wound``)."""
    tint = rgb(color("slime_green"))

    def build(tree: Tree):
        flash_amount = tree.clamp01(attribute(tree, "flash"))
        coordinates = S.tex_coord(tree)
        wobble = S.noise(tree, coordinates, 14.0, 3.0)["Fac"]
        ragged = S.noise(tree, coordinates, 90.0, 4.0)["Fac"]
        tear = attribute(tree, "wound") + (ragged - 0.5) * 0.4
        torn = tree.map_range(tear, 0.35, 0.55, 0.0, 1.0, interp="SMOOTHSTEP")
        rim = torn * (1.0 - torn) * 4.0
        roughness = tree.mix(torn, tree.map_range(wobble, 0.35, 0.65, 0.03, 0.09), 0.3)
        thickness = attribute(tree, S.THICKNESS_ATTRIBUTE)
        body = tree.mix(torn, tint, tuple(channel * 0.45 for channel in tint), "RGBA")
        transmittance = tree.vmath("MULTIPLY", body, S.beer_lambert(tree, color("slime_absorption")[:3], param("slime_absorption", 28.0), thickness))
        height = S.noise(tree, coordinates, 55.0, 2.0)["Fac"] + rim * 1.5
        shader = S.bsdf(tree, Base_Color=transmittance, Roughness=roughness, IOR=1.36, Transmission_Weight=1.0, Coat_Weight=(1.0 - torn) * 0.6,
                        Coat_Roughness=0.02, Specular_IOR_Level=0.55, Normal=bump(tree, height, 0.06, 0.002),
                        Emission_Color=color("flash"), Emission_Strength=flash_amount * 6.0)["BSDF"]
        return S.eevee_refraction(tree, shader, transmittance, thickness)
    return S.material(name, build, settings=S.EEVEE_REFRACTION)


@register("Props.Slime")
def slime():
    return jelly("Props.Slime")


@register("Props.Goo")
def goo():
    return jelly("Props.Goo")


# ------------------------------------------------------------------ face
@register("Props.EyeBlack")
def eye_black():
    return S.material("Props.EyeBlack", lambda tree: S.bsdf(tree, Base_Color=color("eye_black"), Roughness=0.08, Coat_Weight=1.0,
                                                             Coat_Roughness=0.02, Specular_IOR_Level=0.6)["BSDF"])


@register("Props.EyeShine")
def eye_shine():
    return S.emission_mat("Props.EyeShine", (1.0, 1.0, 1.0), 6.0)


@register("Props.Mouth")
def mouth():
    return S.material("Props.Mouth", lambda tree: S.bsdf(tree, Base_Color=color("lips"), Roughness=0.35, Subsurface_Weight=0.3,
                                                          Subsurface_Radius=(0.02, 0.005, 0.004), Subsurface_Scale=0.01)["BSDF"])


# ------------------------------------------------------------------ wood, metal, bamboo, stone
@register("Props.Wood")
def wood():
    """A whittled stick: grey-brown bark with cracks, pale fresh wood where
    ``whittled`` is 1.  Grain along ``wood_coordinate`` z."""
    def build(tree: Tree):
        coordinates = attribute(tree, "wood_coordinate", "Vector")
        fibres = S.noise(tree, tree.vmath("MULTIPLY", coordinates, (40.0, 40.0, 1.5)), 6.0, 8.0, 0.6)["Fac"]
        bark_noise = S.noise(tree, coordinates, 90.0, 6.0, 0.65)["Fac"]
        cracks = tree.n("ShaderNodeTexVoronoi", Vector=tree.vmath("MULTIPLY", coordinates, (120.0, 120.0, 18.0)),
                        props={"feature": "DISTANCE_TO_EDGE"})["Distance"]
        bark_mask = tree.map_range(cracks, 0.0, 0.08, 0.0, 1.0)
        bark_color = S.ramp(tree, bark_noise * bark_mask, [(0.0, (0.035, 0.022, 0.013)), (0.35, (0.12, 0.075, 0.042)),
                                                          (0.7, (0.21, 0.14, 0.085)), (1.0, (0.3, 0.22, 0.14))])["Color"]
        fresh = S.ramp(tree, fibres, [(0.0, (0.45, 0.3, 0.16)), (0.5, (0.62, 0.45, 0.26)), (1.0, (0.78, 0.62, 0.4))])["Color"]
        whittled = attribute(tree, "whittled")
        base = tree.mix(whittled, bark_color, fresh, "RGBA")
        roughness = tree.mix(whittled, tree.map_range(bark_noise, 0.2, 0.8, 0.62, 0.9), 0.55)
        height = tree.mix(whittled, (bark_noise + (1.0 - bark_mask) * -0.6) * 1.0, fibres * 0.3)
        return S.bsdf(tree, Base_Color=base, Roughness=roughness, Normal=bump(tree, height, 0.8, 0.0015), Specular_IOR_Level=0.4)["BSDF"]
    return S.material("Props.Wood", build)


@register("Props.Brass")
def brass():
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        brushed = S.noise(tree, tree.vmath("MULTIPLY", coordinates, (1.0, 1.0, 60.0)), 30.0, 4.0)["Fac"]
        return S.bsdf(tree, Base_Color=color("brass"), Metallic=1.0, Roughness=tree.map_range(brushed, 0.3, 0.7, 0.16, 0.3), Anisotropic=0.4)["BSDF"]
    return S.material("Props.Brass", build)


@register("Props.Bamboo")
def bamboo():
    """Green bamboo culm with a waxy sheen: fine streaks along the culm,
    darker rings at the nodes (``bamboo_node``), pale dry fibre on cut faces
    and inside the bore (``bamboo_cut``).  ``bamboo_coordinate`` is (around,
    along, radius) in the culm's own frame."""
    def build(tree: Tree):
        coordinates = attribute(tree, "bamboo_coordinate", "Vector")
        streaks = S.noise(tree, tree.vmath("MULTIPLY", coordinates, (60.0, 1.2, 1.0)), 8.0, 6.0, 0.55)["Fac"]
        blotch = S.noise(tree, coordinates, 9.0, 3.0)["Fac"]
        skin = tree.mix(tree.map_range(streaks + blotch * 0.5, 0.45, 1.05, 0.0, 1.0), color("bamboo"), color("bamboo_dry"), "RGBA")
        ringed = tree.mix(attribute(tree, "bamboo_node"), skin, color("bamboo_node"), "RGBA")
        cut = attribute(tree, "bamboo_cut")
        fibre = tree.mix(streaks, color("bamboo_dry"), tuple(channel * 0.8 for channel in color("bamboo_dry")[:3]), "RGBA")
        base = tree.mix(cut, ringed, fibre, "RGBA")
        return S.bsdf(tree, Base_Color=base, Roughness=tree.mix(cut, 0.28, 0.7), Coat_Weight=tree.mix(cut, 0.35, 0.0), Coat_Roughness=0.12,
                      Specular_IOR_Level=0.5, Normal=bump(tree, streaks, 0.15, 0.0005))["BSDF"]
    return S.material("Props.Bamboo", build)


@register("Props.Stone")
def stone():
    """Weathered granite: speckled grey, rough, with a little moss in hollows."""
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        speckle = S.noise(tree, coordinates, 180.0, 4.0, 0.7)["Fac"]
        mottle = S.noise(tree, coordinates, 12.0, 5.0, 0.6)["Fac"]
        grey = tree.mix(tree.map_range(speckle + mottle * 0.6, 0.55, 1.1, 0.0, 1.0), color("granite"), color("granite_light"), "RGBA")
        base = tree.mix(tree.map_range(mottle, 0.62, 0.72, 0.0, 0.6), grey, color("moss"), "RGBA")
        return S.bsdf(tree, Base_Color=base, Roughness=tree.map_range(speckle, 0.3, 0.7, 0.55, 0.85), Specular_IOR_Level=0.45,
                      Normal=bump(tree, speckle + mottle * 0.5, 0.35, 0.002))["BSDF"]
    return S.material("Props.Stone", build)


def studio_surface(name, key):
    def build(tree: Tree):
        speckle = S.noise(tree, S.tex_coord(tree), 300.0, 2.0)["Fac"]
        return S.bsdf(tree, Base_Color=color(key), Roughness=tree.map_range(speckle, 0.3, 0.7, 0.42, 0.55), Specular_IOR_Level=0.45,
                      Coat_Weight=0.15, Coat_Roughness=0.2)["BSDF"]
    return S.material(name, build)


@register("Props.Table")
def table():
    return studio_surface("Props.Table", "table")


@register("Props.Backdrop")
def backdrop():
    return studio_surface("Props.Backdrop", "backdrop")
