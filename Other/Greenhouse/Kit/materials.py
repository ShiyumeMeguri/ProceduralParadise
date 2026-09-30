"""
Greenhouse material library (``GH.*``), made for Cycles.

Architectural glass (floor panes, balustrades, the curtain wall) is a real
dielectric for camera, reflection and refraction rays but lets shadow rays
through tinted, so sunlight reaches the garden under a glass floor instead
of being lost to caustics.  Glassware is thick glass with Beer-Lambert
absorption inside (a Volume Absorption shader), so a bottle is deep green
where the light crosses much glass and clear where it crosses little.

Organic surfaces read colours the kit stores on the geometry:
``leaf_color`` (per leaf), ``leaf_u`` (0 at the base, 1 at the tip) and
``leaf_v`` (-1..1 across) on every blade the flora kit grows.

Base colours come from the palette (``Greenhouse.json``); a scene may
override parameters and palette colours (``"color:<key>"``) through
``PARAMS`` before anything is built.
"""
from __future__ import annotations

import bpy

from Core import shaders as S
from Core.nodes import Tree
from .. import PALETTE

LIBRARY = S.MaterialLibrary(PALETTE, "greenhouse_built")
PARAMS = LIBRARY.params
register = LIBRARY.register
get = LIBRARY.get
color = LIBRARY.color
param = LIBRARY.param


def attribute(tree: Tree, name, output="Fac", kind="GEOMETRY"):
    return tree.n("ShaderNodeAttribute", props={"attribute_name": name, "attribute_type": kind})[output]


def bump(tree: Tree, height, strength, distance=0.001):
    return tree.n("ShaderNodeBump", Strength=strength, Distance=distance, Height=height)["Normal"]


def mix_shader(tree: Tree, factor, first, second):
    return tree.n("ShaderNodeMixShader", factor, first, second)["Shader"]


def shadow_clear(tree: Tree, shader, tint):
    """``shader`` for camera and indirect rays, a tinted transparent surface
    for shadow rays."""
    shadow = tree.n("ShaderNodeLightPath")["Is Shadow Ray"]
    transparent = tree.n("ShaderNodeBsdfTransparent", Color=tint)["BSDF"]
    return mix_shader(tree, shadow, shader, transparent)


def scaled(rgba, factor):
    return tuple(channel * factor for channel in rgba[:3]) + (1.0,)


# ------------------------------------------------------------------ structure
@register("GH.Steel")
def steel():
    """Green-painted steel: a satin enamel over the metal."""
    def build(tree: Tree):
        grain = S.noise(tree, S.tex_coord(tree), 60.0, 4.0)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(grain, 0.35, 0.65, 0.0, 1.0), color("steel"), scaled(color("steel"), 1.25))
        return S.bsdf(tree, Base_Color=base, Roughness=param("steel_roughness", 0.32), Coat_Weight=0.4,
                      Coat_Roughness=0.08, Specular_IOR_Level=0.5)["BSDF"]
    return S.material("GH.Steel", build)


@register("GH.Glass")
def glass():
    """Architectural glass: clear with the faint green of float glass, a real
    dielectric for camera rays, tinted transparency for shadow rays.
    ``glass_ior`` below 1.5 stands for an anti-reflective coating.  Inside,
    the float glass absorbs towards ``glass_green`` (``pane_density``), so a
    pane seen through its edge is deep teal and face on almost clear."""
    def build(tree: Tree):
        tint = color("glass")
        shader = tree.n("ShaderNodeBsdfGlass", Color=tint, Roughness=0.0, IOR=param("glass_ior", 1.5))["BSDF"]
        volume = tree.n("ShaderNodeVolumeAbsorption", Color=color("glass_green"), Density=param("pane_density", 6.0))["Volume"]
        return {"Surface": shadow_clear(tree, shader, scaled(tint, param("glass_shadow", 0.92))), "Volume": volume}
    return S.material("GH.Glass", build)


@register("GH.GlassFrosted")
def glass_frosted():
    """Sand-blasted floor glass: a rough dielectric that turns what lies
    below into a pale glow."""
    def build(tree: Tree):
        tint = color("glass")
        shader = tree.n("ShaderNodeBsdfGlass", Color=tint, Roughness=param("frosted_roughness", 0.45), IOR=1.5)["BSDF"]
        return shadow_clear(tree, shader, scaled(tint, param("frosted_shadow", 0.6)))
    return S.material("GH.GlassFrosted", build)


@register("GH.GlassGreen")
def glass_green():
    """Thick green glass of glassware and glass furniture: clear surfaces,
    colour from absorption inside the body (deep where the glass is thick).
    Shadow rays see a pale tinted transparency."""
    def build(tree: Tree):
        surface = tree.n("ShaderNodeBsdfGlass", Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=1.5)["BSDF"]
        volume = tree.n("ShaderNodeVolumeAbsorption", Color=color("glass_green"), Density=param("glassware_density", 6.0))["Volume"]
        return {"Surface": shadow_clear(tree, surface, scaled(color("glass_green"), 0.9)), "Volume": volume}
    return S.material("GH.GlassGreen", build)


@register("GH.GlassClear")
def glass_clear():
    """Clear thin-walled glassware (terrarium orbs, the flask): a dielectric
    with a whisper of absorption."""
    def build(tree: Tree):
        surface = tree.n("ShaderNodeBsdfGlass", Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=1.5)["BSDF"]
        volume = tree.n("ShaderNodeVolumeAbsorption", Color=color("glass_green"), Density=param("clear_glass_density", 1.5))["Volume"]
        return {"Surface": shadow_clear(tree, surface, scaled(color("glass"), 0.95)), "Volume": volume}
    return S.material("GH.GlassClear", build)


@register("GH.Tread")
def tread():
    """Honed limestone of the stair treads."""
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        cloud = S.noise(tree, coordinates, 6.0, 6.0, 0.6)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(cloud, 0.3, 0.7, 0.0, 1.0), scaled(color("tread"), 0.9), scaled(color("tread"), 1.08))
        return S.bsdf(tree, Base_Color=base, Roughness=0.45)["BSDF"]
    return S.material("GH.Tread", build)


@register("GH.Paving")
def paving():
    """Stone paving of the garden floor; the flags carry ``flag_shade``
    (0..1, one value per flag) so every flag has its own tone."""
    def build(tree: Tree):
        shade = attribute(tree, "flag_shade")
        base = S.mix_rgb(tree, shade, color("paving"), color("paving_light"))
        grit = S.noise(tree, S.tex_coord(tree), 40.0, 5.0)["Fac"]
        return S.bsdf(tree, Base_Color=base, Roughness=tree.map_range(grit, 0.3, 0.7, 0.55, 0.8),
                      Normal=bump(tree, grit, 0.15))["BSDF"]
    return S.material("GH.Paving", build)


@register("GH.Deck")
def deck():
    """Weathered hardwood decking; boards carry ``board_shade``."""
    def build(tree: Tree):
        shade = attribute(tree, "board_shade")
        coordinates = S.tex_coord(tree)
        grain = S.noise(tree, tree.vmath("MULTIPLY", coordinates, (1.0, 18.0, 1.0)), 4.0, 6.0)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(shade + grain * 0.4, 0.2, 1.2, 0.0, 1.0), scaled(color("deck"), 0.85), scaled(color("deck"), 1.2))
        return S.bsdf(tree, Base_Color=base, Roughness=0.6, Normal=bump(tree, grain, 0.1))["BSDF"]
    return S.material("GH.Deck", build)


@register("GH.Soil")
def soil():
    def build(tree: Tree):
        grit = S.noise(tree, S.tex_coord(tree), 120.0, 6.0)["Fac"]
        base = S.mix_rgb(tree, grit, scaled(color("soil"), 0.7), scaled(color("soil"), 1.5))
        return S.bsdf(tree, Base_Color=base, Roughness=0.95, Normal=bump(tree, grit, 0.4))["BSDF"]
    return S.material("GH.Soil", build)


@register("GH.Pebble")
def pebble():
    """White decorative pebbles; each stone carries ``pebble_shade``."""
    def build(tree: Tree):
        shade = attribute(tree, "pebble_shade")
        base = S.mix_rgb(tree, shade, scaled(color("pebble"), 0.82), scaled(color("pebble"), 1.08))
        return S.bsdf(tree, Base_Color=base, Roughness=0.5, Subsurface_Weight=0.1, Subsurface_Radius=(0.02, 0.02, 0.02))["BSDF"]
    return S.material("GH.Pebble", build)


@register("GH.Bark")
def bark():
    def build(tree: Tree):
        grain = S.noise(tree, tree.vmath("MULTIPLY", S.tex_coord(tree), (8.0, 8.0, 1.0)), 30.0, 5.0)["Fac"]
        base = S.mix_rgb(tree, grain, scaled(color("bark"), 0.7), scaled(color("bark"), 1.4))
        return S.bsdf(tree, Base_Color=base, Roughness=0.85, Normal=bump(tree, grain, 0.3))["BSDF"]
    return S.material("GH.Bark", build)


@register("GH.Brass")
def brass():
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("brass"), Metallic=1.0, Roughness=0.28)["BSDF"]
    return S.material("GH.Brass", build)


@register("GH.Paper")
def paper():
    """Page edges of a book."""
    def build(tree: Tree):
        lines = S.noise(tree, tree.vmath("MULTIPLY", S.tex_coord(tree), (1.0, 1.0, 900.0)), 3.0, 1.0)["Fac"]
        base = S.mix_rgb(tree, lines, scaled(color("paper"), 0.9), color("paper"))
        return S.bsdf(tree, Base_Color=base, Roughness=0.8)["BSDF"]
    return S.material("GH.Paper", build)


@register("GH.Cover")
def cover():
    """Cloth book cover."""
    def build(tree: Tree):
        weave = S.noise(tree, S.tex_coord(tree), 400.0, 2.0)["Fac"]
        return S.bsdf(tree, Base_Color=color("cover"), Roughness=0.7, Normal=bump(tree, weave, 0.1))["BSDF"]
    return S.material("GH.Cover", build)


@register("GH.Ink")
def ink():
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("cover_ink"), Roughness=0.5)["BSDF"]
    return S.material("GH.Ink", build)


# ------------------------------------------------------------------ plants
def leaf_shader(tree: Tree, sheen, translucency, roughness):
    """Two-sided leaf: the per-leaf ``leaf_color`` darkened along the midrib
    and towards the base, a waxy sheen on top, light through the blade."""
    tint = attribute(tree, "leaf_color", "Color")
    across = tree.abs(attribute(tree, "leaf_v"))
    along = attribute(tree, "leaf_u")
    rib = tree.map_range(across, 0.0, 0.08, 0.72, 1.0)
    base_shade = tree.map_range(along, 0.0, 0.35, 0.7, 1.0)
    shaded = tree.vmath("SCALE", tint, scale=rib * base_shade)
    surface = S.bsdf(tree, Base_Color=shaded, Roughness=roughness, Specular_IOR_Level=sheen, Coat_Weight=sheen * 0.6,
                     Coat_Roughness=0.25)["BSDF"]
    backlit = tree.n("ShaderNodeBsdfTranslucent", Color=tree.vmath("MULTIPLY", shaded, (1.3, 1.5, 0.6)))["BSDF"]
    return mix_shader(tree, translucency, surface, backlit)


@register("GH.Leaf")
def leaf():
    def build(tree: Tree):
        return leaf_shader(tree, param("leaf_sheen", 0.45), param("leaf_translucency", 0.3), 0.42)
    return S.material("GH.Leaf", build)


@register("GH.Succulent")
def succulent():
    """Glaucous succulent leaves: the per-leaf colour blushing to the
    palette's edge tint towards the tips and the margins."""
    def build(tree: Tree):
        tint = attribute(tree, "leaf_color", "Color")
        across = tree.abs(attribute(tree, "leaf_v"))
        along = attribute(tree, "leaf_u")
        blush = tree.map_range(tree.max(across, along * 0.9), 0.75, 1.0, 0.0, 1.0)
        base = S.mix_rgb(tree, blush, tint, color("succulent_edge"))
        return S.bsdf(tree, Base_Color=base, Roughness=0.38, Subsurface_Weight=0.25, Subsurface_Radius=(0.01, 0.02, 0.008),
                      Coat_Weight=0.3, Coat_Roughness=0.3)["BSDF"]
    return S.material("GH.Succulent", build)


# ------------------------------------------------------------------ backdrop
@register("GH.TowerGlass")
def tower_glass():
    """Curtain-wall glass of a distant tower: reflective blue-grey panes,
    each pane (``pane_shade``) catching the sky a little differently."""
    def build(tree: Tree):
        shade = attribute(tree, "pane_shade")
        base = S.mix_rgb(tree, shade, scaled(color("tower_glass"), 0.7), scaled(color("tower_glass"), 1.3))
        return S.bsdf(tree, Base_Color=base, Metallic=0.6, Roughness=0.08)["BSDF"]
    return S.material("GH.TowerGlass", build)


@register("GH.TowerFrame")
def tower_frame():
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("tower_frame"), Roughness=0.4, Metallic=0.3)["BSDF"]
    return S.material("GH.TowerFrame", build)


def names():
    return LIBRARY.names()


def world(config):
    """Hazy daylight sky: a gradient from the pink-white haze at and below
    the horizon to a pale blue zenith.  Camera rays may see the sky at a
    different strength than the light it sheds."""
    world_block = S.new_world("GH.Sky")
    tree = Tree.wrap(world_block.node_tree, clear=True)
    out = tree.n("ShaderNodeOutputWorld")
    direction = tree.vmath("NORMALIZE", tree.n("ShaderNodeTexCoord")["Generated"])
    _, _, height = tree.sep(direction)
    sky = S.ramp(tree, tree.map_range(height, config.get("haze_top", -0.1), config.get("zenith_height", 0.6), 0.0, 1.0),
                 [(0.0, color("haze")), (0.35, color("sky_horizon")), (1.0, color("sky_zenith"))])["Color"]
    camera = tree.n("ShaderNodeLightPath")["Is Camera Ray"]
    strength = config["light_strength"] + (config["camera_strength"] - config["light_strength"]) * camera
    tree.link(tree.n("ShaderNodeBackground", sky, strength)["Background"], out.n.inputs["Surface"])
    tree.layout()
    bpy.context.scene.world = world_block
    return world_block
