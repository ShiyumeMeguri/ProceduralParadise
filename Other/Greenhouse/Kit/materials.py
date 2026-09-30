"""
Greenhouse material library (``GH.*``), made for Cycles.

All glass is one dielectric (IOR 1.5) with Beer-Lambert absorption inside
towards ``jade`` (a Volume Absorption shader): seen face on, a pane or a
bottle wall is nearly clear; seen through its edge, where light crosses
decimetres of glass, it turns the deep blue-green of jade -- the colour the
painting gives every glass edge.  Near the camera the floor is transparent,
far off it mirrors the windows, because that is what Fresnel reflection of
IOR 1.5 does at grazing angles.  Shadow rays see tinted transparency, so
sunlight reaches the garden under the glass floor instead of being lost to
caustics.

Organic surfaces read colours the kit stores on the geometry:
``leaf_color`` (per leaf), ``leaf_u`` (0 at the base, 1 at the tip) and
``leaf_v`` (-1..1 across) on every blade the flora kit grows.  A leaf's
margin is inked (``leaf_outline`` of its half width in ``ink``), the
painting's line art carried by the material, so it shows through glass.

Base colours come from the palette (``Greenhouse.json``); a scene may
override parameters and palette colours (``"color:<key>"``) through
``PARAMS`` before anything is built.
"""
from __future__ import annotations

import math

import bpy

from Core import shaders as S
from Core.nodes import Sock, Tree
from Core.render import INK_SKIP
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


def light_clear(tree: Tree, shader, tint):
    """``shader`` for camera and glossy rays; for the rays that carry light
    to a surface -- shadow rays and rays scattered off a diffuse surface --
    a tinted transparent surface.  Light reaches the garden through glass;
    refracted, it would be a caustic path, which the render does not trace,
    and the sky would light the conservatory only through its sampled
    shadow rays, a fraction of its light."""
    path = tree.n("ShaderNodeLightPath")
    carries_light = tree.math("MAXIMUM", path["Is Shadow Ray"], path["Is Diffuse Ray"])
    transparent = tree.n("ShaderNodeBsdfTransparent", Color=tint)["BSDF"]
    return mix_shader(tree, carries_light, shader, transparent)


def scaled(rgba, factor):
    return tuple(channel * factor for channel in rgba[:3]) + (1.0,)


def glazed(graph, geometry, material, see_through=True):
    """``geometry`` in ``material``, marked as glass for the ink pass
    (``Core.render.INK_SKIP``): lines of what lies behind it are drawn
    through it.  ``see_through`` is a constant or an asset's switch."""
    skip = graph.switch(see_through, 0.0, 1.0, "FLOAT") if isinstance(see_through, Sock) else float(see_through)
    return graph.mat(graph.store(geometry, INK_SKIP, skip, "FLOAT", "FACE"), material)


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


FRESNEL_LOSS = 0.96


def dielectric(tree: Tree, density_key, density, wall, ior=1.5):
    """Surface and volume of jade glass: a dielectric of ``ior`` filled with
    absorption towards ``jade`` at ``density_key``.  A ray carrying light
    crosses a surface and half a ``wall`` of glass per surface it meets, so
    it is tinted by the Fresnel loss and the Beer-Lambert transmittance of
    half a wall -- the light a pane really lets through."""
    density = param(density_key, density)
    surface = tree.n("ShaderNodeBsdfGlass", Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=ior)["BSDF"]
    volume = tree.n("ShaderNodeVolumeAbsorption", Color=color("jade"), Density=density)["Volume"]
    half_wall = tuple(FRESNEL_LOSS * math.exp(-(1.0 - channel) * density * wall * 0.5) for channel in color("jade")[:3])
    return {"Surface": light_clear(tree, surface, (*half_wall, 1.0)), "Volume": volume}


@register("GH.Glass")
def glass():
    """Architectural glass: floor panes, stair treads, balustrade infill,
    curtain wall and roof (``pane_density``).  The panes are anti-reflection
    coated: the coating's reflectance curve -- about 0.2 % face on, rising
    to a mirror at grazing angles -- is that of an uncoated dielectric of
    ``pane_ior`` (1.1), so the garden seen down through the floor is not
    veiled by the bright sky it mirrors, and the floor mirrors the windows
    only far off."""
    def build(tree: Tree):
        return dielectric(tree, "pane_density", 10.0, 0.02, param("pane_ior", 1.1))
    return S.material("GH.Glass", build)


@register("GH.Jade")
def jade():
    """Polished jade of the frame -- beams, posts, mullions, rails, table
    columns: a translucent stone (light scatters a few millimetres into it
    and comes back ``jade_stone``) under a clear polish, so a bar is a dark
    green body with a bright edge where it catches the light."""
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("jade_stone"), Roughness=0.35, Subsurface_Weight=0.4,
                      Subsurface_Radius=(0.05, 0.15, 0.12), Coat_Weight=1.0, Coat_Roughness=0.04)["BSDF"]
    return S.material("GH.Jade", build)


@register("GH.GlassJade")
def glass_jade():
    """Thick jade glass of the glassware and glass furniture
    (``glassware_density``): pale where a wall is crossed face on, deep
    blue-green along edges and in solid rods."""
    def build(tree: Tree):
        return dielectric(tree, "glassware_density", 60.0, 0.012)
    return S.material("GH.GlassJade", build)


@register("GH.GlassBottle")
def glass_bottle():
    """Green bottle glass of the tall bottle and the flask: absorbs red and
    blue (``bottle_glass``, ``bottle_density``)."""
    def build(tree: Tree):
        density = param("bottle_density", 30.0)
        surface = tree.n("ShaderNodeBsdfGlass", Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=1.5)["BSDF"]
        volume = tree.n("ShaderNodeVolumeAbsorption", Color=color("bottle_glass"), Density=density)["Volume"]
        half_wall = tuple(FRESNEL_LOSS * math.exp(-(1.0 - channel) * density * 0.006) for channel in color("bottle_glass")[:3])
        return {"Surface": light_clear(tree, surface, (*half_wall, 1.0)), "Volume": volume}
    return S.material("GH.GlassBottle", build)


@register("GH.Water")
def water():
    """Water: an IOR 1.333 dielectric absorbing towards ``water_tint``
    (``water_density``), faintly turbid (``water_turbidity``): the sunlight
    it scatters lights the whole body of water teal."""
    def build(tree: Tree):
        density = param("water_density", 8.0)
        surface = tree.n("ShaderNodeBsdfGlass", Color=(1.0, 1.0, 1.0, 1.0), Roughness=0.0, IOR=1.333)["BSDF"]
        absorption = tree.n("ShaderNodeVolumeAbsorption", Color=color("water_tint"), Density=density)["Volume"]
        scatter = tree.n("ShaderNodeVolumeScatter", Color=color("water_tint"), Density=param("water_turbidity", 2.0), Anisotropy=0.3)["Volume"]
        volume = tree.n("ShaderNodeAddShader", absorption, scatter)["Shader"]
        half = tuple(FRESNEL_LOSS * math.exp(-(1.0 - channel) * density * 0.1) for channel in color("water_tint")[:3])
        return {"Surface": light_clear(tree, surface, (*half, 1.0)), "Volume": volume}
    return S.material("GH.Water", build)


@register("GH.MilkGlass")
def milk_glass():
    """Opal (milk) glass: a pale, softly glossy top that lets light through
    diffusely (``milk``)."""
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("milk"), Roughness=0.3, Transmission_Weight=0.35, IOR=1.5,
                      Subsurface_Weight=0.4, Subsurface_Radius=(0.05, 0.05, 0.05), Coat_Weight=0.5, Coat_Roughness=0.05)["BSDF"]
    return S.material("GH.MilkGlass", build)


@register("GH.GlassClear")
def glass_clear():
    """Thin clear glassware -- terrarium orbs, the flask, the ball
    (``clear_glass_density``)."""
    def build(tree: Tree):
        return dielectric(tree, "clear_glass_density", 3.0, 0.003)
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


@register("GH.Lawn")
def lawn():
    """Mown grass seen from afar: mottled greens with a fine blade bump."""
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        mottle = S.noise(tree, coordinates, 0.4, 6.0, 0.6)["Fac"]
        blades = S.noise(tree, coordinates, 300.0, 2.0)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(mottle, 0.3, 0.7, 0.0, 1.0), color("leaf"), color("leaf_light"))
        return S.bsdf(tree, Base_Color=base, Roughness=0.9, Normal=bump(tree, blades, 0.3))["BSDF"]
    return S.material("GH.Lawn", build)


@register("GH.Planter")
def planter():
    """Glazed stoneware planter."""
    def build(tree: Tree):
        speckle = S.noise(tree, S.tex_coord(tree), 80.0, 3.0)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(speckle, 0.4, 0.7, 0.0, 1.0), color("planter"), scaled(color("planter"), 0.8))
        return S.bsdf(tree, Base_Color=base, Roughness=0.25, Coat_Weight=0.3)["BSDF"]
    return S.material("GH.Planter", build)


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
        return S.bsdf(tree, Base_Color=color("brass"), Metallic=1.0, Roughness=0.35)["BSDF"]
    return S.material("GH.Brass", build)


@register("GH.Bronze")
def bronze():
    """Dark patinated bronze."""
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("bronze"), Metallic=1.0, Roughness=0.45)["BSDF"]
    return S.material("GH.Bronze", build)


@register("GH.PhoneBody")
def phone_body():
    """Glossy phone case."""
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("phone"), Roughness=0.25, Coat_Weight=0.6, Coat_Roughness=0.05)["BSDF"]
    return S.material("GH.PhoneBody", build)


def screen(tree: Tree, base):
    """A lit screen under cover glass: ``base`` glowing at
    ``screen_glow`` under a clear coat that mirrors the room."""
    lit = S.bsdf(tree, Base_Color=base, Roughness=0.4, Emission_Color=base, Emission_Strength=param("screen_glow", 0.6),
                 Coat_Weight=1.0, Coat_Roughness=0.02, Coat_IOR=1.5)["BSDF"]
    return lit


@register("GH.PhoneScreen")
def phone_screen():
    """The white page the phone shows."""
    def build(tree: Tree):
        return screen(tree, color("screen"))
    return S.material("GH.PhoneScreen", build)


@register("GH.PhonePhoto")
def phone_photo():
    """A photo of greenery on the screen: leaf-sized cells of dark teal and
    fresh green."""
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        cells = tree.n("ShaderNodeTexVoronoi", coordinates, Scale=90.0, props={"voronoi_dimensions": "3D", "feature": "F1"})["Color"]
        shade = tree.sep(cells)[0]
        base = S.mix_rgb(tree, tree.map_range(shade, 0.2, 0.9, 0.0, 1.0), scaled(color("leaf_deep"), 0.8), color("leaf_light"))
        return screen(tree, base)
    return S.material("GH.PhonePhoto", build)


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
    surface = S.bsdf(tree, Base_Color=shaded, Roughness=roughness, Specular_IOR_Level=sheen)["BSDF"]
    backlit = tree.n("ShaderNodeBsdfTranslucent", Color=tree.vmath("MULTIPLY", shaded, (1.2, 1.15, 0.7)))["BSDF"]
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


# ------------------------------------------------------------------ air
@register("GH.Air")
def air():
    """Sunlit air of the conservatory: a thin forward-scattering volume
    (``air_density``, ``air_anisotropy``) that turns the sun into shafts
    between the glazing bars.  Only volume, no surface."""
    def build(tree: Tree):
        volume = tree.n("ShaderNodeVolumePrincipled", Color=color("air"), Density=param("air_density", 0.02),
                        Anisotropy=param("air_anisotropy", 0.6))["Volume"]
        return {"Volume": volume}
    return S.material("GH.Air", build)


@register("GH.Smog")
def smog():
    """The city haze below the tower: an absorbing medium that glows with
    the skylight it scatters in, so along a path of transmittance T the view
    becomes L * T + smog * brightness * (1 - T) -- single-scattered skylight
    in closed form.  It thins with height, exp(-(z - ``smog_ground``) /
    ``smog_scale``) from ``smog_density`` at the ground: the streets far
    below vanish into pink while a neighbouring tower at the conservatory's
    height stays clear.  The glow is skylight the haze sends towards the
    eye, seen directly, in reflections and through glass; diffuse rays do
    not see it -- the sky already lights the scene."""
    def build(tree: Tree):
        _, _, z = tree.sep(tree.n("ShaderNodeNewGeometry")["Position"])
        falloff = tree.math("EXPONENT", (z - param("smog_ground", -120.0)) * (-1.0 / param("smog_scale", 30.0)))
        density = tree.math("MULTIPLY", falloff, param("smog_density", 0.05))
        absorb = tree.n("ShaderNodeVolumeAbsorption", Color=(0.0, 0.0, 0.0, 1.0), Density=density)["Volume"]
        seen = tree.math("SUBTRACT", 1.0, tree.n("ShaderNodeLightPath")["Is Diffuse Ray"])
        glow = tree.n("ShaderNodeEmission", Color=color("smog"),
                      Strength=tree.math("MULTIPLY", tree.math("MULTIPLY", density, param("smog_brightness", 1.0)), seen))["Emission"]
        return {"Volume": tree.n("ShaderNodeAddShader", absorb, glow)["Shader"]}
    return S.material("GH.Smog", build)


# ------------------------------------------------------------------ backdrop
@register("GH.TowerGlass")
def tower_glass():
    """Curtain-wall glass of a distant tower: cyan-tinted panes, each pane
    (``pane_shade``) catching the sky a little differently."""
    def build(tree: Tree):
        shade = attribute(tree, "pane_shade")
        base = S.mix_rgb(tree, shade, scaled(color("tower_glass"), 0.8), scaled(color("tower_glass"), 1.2))
        return S.bsdf(tree, Base_Color=base, Metallic=0.3, Roughness=0.12)["BSDF"]
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
