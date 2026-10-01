"""
Greenhouse material library (``GH.*``), made for EEVEE.

Every glass -- the panes, the jade glass of the frame, the crystal of the
glassware, the water in the flask and in the pools -- is one row of the
design system's ``glasses`` (``Greenhouse.json``) built by one builder
(:func:`dielectric`): a smooth dielectric of its ``ior`` -- a thin pane
seen through straight, a thick body refracted by EEVEE's ray tracing --
tinted by Beer-Lambert absorption towards a palette ``tint`` over the path
light takes inside it: the ``thickness`` every glazed body carries
(:func:`glazed`), stretched by the slant of the refracted ray.  Seen face
on, a thin wall is nearly clear; along an edge or through a rod, where
light crosses centimetres to decimetres of glass, it turns the deep
blue-green of jade -- the colour the painting gives every glass edge and
every bar of the frame.  Shadows see the glass as
transparent as its mean transmittance, so sunlight reaches the garden under
the glass floor.

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
from Core.gn import get_asset
from Core.nodes import Sock, Tree
from Core.render import INK_SKIP
from .. import GLASSES, PALETTE, ROOM

LIBRARY = S.MaterialLibrary(PALETTE, "greenhouse_built")
PARAMS = LIBRARY.params
register = LIBRARY.register
get = LIBRARY.get
color = LIBRARY.color
param = LIBRARY.param
GLAZED_DEPTH = 3.0
BODIES = ("pane", "slab", "sphere", "over")
STRAIGHT_BODIES = ("pane", "over")


def attribute(tree: Tree, name, output="Fac", kind="GEOMETRY"):
    return tree.n("ShaderNodeAttribute", props={"attribute_name": name, "attribute_type": kind})[output]


def bump(tree: Tree, height, strength, distance=0.001):
    return tree.n("ShaderNodeBump", Strength=strength, Distance=distance, Height=height)["Normal"]


def mix_shader(tree: Tree, factor, first, second):
    return tree.n("ShaderNodeMixShader", factor, first, second)["Shader"]


def scaled(rgba, factor):
    return tuple(channel * factor for channel in rgba[:3]) + (1.0,)


def bodied(name, body):
    """Name of the material of the glass ``name`` built for a ``body`` of
    that kind (:data:`BODIES`, :func:`dielectric`): the glass's own name for
    a pane."""
    return name if body == "pane" else f"{name}.{body.title()}"


def glazed(graph, geometry, material, see_through=True, body="pane"):
    """``geometry`` in ``material``, carrying the ``thickness`` its glass
    reads (``Shading.Thickness``: how far light travels through the body
    along the normal, at most ``GLAZED_DEPTH`` -- through the edge of a pane,
    the pane's width) and marked as glass for the ink pass
    (``Core.render.INK_SKIP``): lines of what lies behind it are drawn
    through it.  ``see_through`` is a constant or an asset's switch.  The
    geometry says what ``body`` of glass it is -- a ``pane`` of a few
    millimetres, a solid ``slab`` (a bar, a plate, a block), a solid
    ``sphere`` (a ball, a body of water), or a flat solid standing ``over``
    other glass (a block on a glass table) -- and a glass of ``GLASSES`` is
    made that body (:func:`bodied`); any other material is kept."""
    skip = graph.switch(see_through, 0.0, 1.0, "FLOAT") if isinstance(see_through, Sock) else float(see_through)
    measured = graph.group(get_asset("Shading.Thickness"), Mesh=geometry, Max_Thickness=GLAZED_DEPTH).o
    result = graph.mat(graph.store(measured, INK_SKIP, skip, "FLOAT", "FACE"), material)
    if body != "pane":
        for name in GLASSES:
            result = graph.n("GeometryNodeReplaceMaterial", Geometry=result, Old=get(name), New=get(bodied(name, body))).o
    return result


# ------------------------------------------------------------------ structure
def enamel(name, key):
    """Painted steel ``name``: a satin enamel of the palette colour ``key``
    over the metal, mottled up to a quarter lighter."""
    def build(tree: Tree):
        grain = S.noise(tree, S.tex_coord(tree), 60.0, 4.0)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(grain, 0.35, 0.65, 0.0, 1.0), color(key), scaled(color(key), 1.25))
        return S.bsdf(tree, Base_Color=base, Roughness=param("steel_roughness", 0.32), Coat_Weight=0.4,
                      Coat_Roughness=0.08, Specular_IOR_Level=0.5)["BSDF"]
    return S.material(name, build)


@register("GH.Steel")
def steel():
    """Green-painted steel of the atrium's fittings (``steel``)."""
    return enamel("GH.Steel", "steel")


@register("GH.FrameSteel")
def frame_steel():
    """Teal-painted steel of the conservatory's frame (``frame``), a lighter,
    bluer green than the atrium's fittings."""
    return enamel("GH.FrameSteel", "frame")


def reflection_room(tree: Tree):
    """The panes of the conservatory a reflected ray looks into -- a
    reflection probe of the room in closed form (``ROOM``), the same from
    every camera: ``bays`` bays round the horizon, each split by a mullion
    taking the share ``gap`` of it, and ``rows`` of panes (the elevations,
    degrees, of the sill, the transoms and the eaves) with transoms
    ``transom`` degrees deep; a pane shows the ``sky`` (the haze beyond the
    glass) unless it is one of the share ``screened`` of the panes, picked
    at random pane by pane, that the vines and the plants outside screen;
    everything else -- frame, screened panes, garden, roof -- shows nothing,
    so the glass shows its own clear body there."""
    x, y, z = tree.sep(tree.vmath("NORMALIZE", tree.n("ShaderNodeTexCoord")["Reflection"]))
    soft = math.radians(0.5)
    bay = math.tau / ROOM["bays"]
    bays_round = tree.math("DIVIDE", tree.math("ARCTAN2", y, x), bay)
    turn = tree.math("FRACT", bays_round)
    from_mullion = tree.math("MULTIPLY", tree.math("MINIMUM", turn, tree.math("SUBTRACT", 1.0, turn)), bay)
    half_mullion = bay * ROOM["gap"] * 0.5
    between_mullions = tree.map_range(from_mullion, half_mullion - soft, half_mullion + soft, 0.0, 1.0)
    elevation = tree.math("ARCSINE", z)
    half_transom = math.radians(ROOM["transom"]) * 0.5
    in_row = None
    row = None
    for low, high in zip(ROOM["rows"][:-1], ROOM["rows"][1:]):
        above = tree.map_range(elevation, math.radians(low) + half_transom - soft, math.radians(low) + half_transom + soft, 0.0, 1.0)
        below = tree.map_range(elevation, math.radians(high) - half_transom - soft, math.radians(high) - half_transom + soft, 1.0, 0.0)
        band = tree.math("MULTIPLY", above, below)
        numbered = tree.math("GREATER_THAN", elevation, math.radians(low))
        in_row = band if in_row is None else tree.math("ADD", in_row, band)
        row = numbered if row is None else tree.math("ADD", row, numbered)
    pane = tree.n("ShaderNodeCombineXYZ", tree.math("FLOOR", bays_round), row, 0.0).o
    draw = tree.n("ShaderNodeTexWhiteNoise", tree.vmath("ADD", pane, (0.5, 0.5, 0.5)), props={"noise_dimensions": "3D"})["Value"]
    lit = tree.math("GREATER_THAN", draw, ROOM["screened"])
    inside = tree.math("MULTIPLY", between_mullions, in_row)
    return tree.vmath("SCALE", color(ROOM["sky"])[:3], scale=tree.math("MULTIPLY", inside, lit))


def slant_path(tree: Tree, thickness, ior):
    """Path light refracted into a body ``thickness`` thick along its normal
    takes across it: ``thickness`` / cos(theta_t), the ray bent from the line
    of sight by Snell's law at ``ior``."""
    geometry = tree.n("ShaderNodeNewGeometry")
    facing = tree.math("ABSOLUTE", tree.vmath("DOT_PRODUCT", geometry["Normal"], geometry["Incoming"]))
    bent = tree.math("DIVIDE", tree.math("SUBTRACT", 1.0, tree.math("MULTIPLY", facing, facing)), ior * ior)
    return tree.math("DIVIDE", thickness, tree.math("SQRT", tree.math("SUBTRACT", 1.0, bent)))


def dielectric(name, spec, body):
    """Builder of the glass ``name`` (a row ``spec`` of ``GLASSES``) for a
    ``body`` of that kind (:func:`glazed`): a smooth dielectric of ``ior``
    absorbing towards the palette colour ``tint`` at ``density`` per metre
    over the slanted path through it (:func:`slant_path`).  The body says
    how light crosses it.  A ``slab`` (a bar, a table top, a body of water)
    and a ``sphere`` (a ball, the water in a flask) are refracted by EEVEE's
    ray tracing as that shape.  A ``pane`` of a few millimetres does not
    bend what is seen through it, so it lets the scene behind through
    straight, tinted by half its path at each of its two faces, and mirrors
    the room by its Fresnel reflectance (the sun's shadow sees only the
    tint: it has no eye to take a Fresnel angle from); it is dithered, part
    of the scene the other glass refracts.  EEVEE refracts through one layer
    of glass only: a solid standing in front of other refracting glass -- a
    block on a glass table -- refracted, shows the bare floor beyond both,
    pale where the accepted render shows it jade.  Such a solid is ``over``
    the other glass: between parallel faces it only shifts what it shows
    aside, so it is drawn like a pane but blended over the finished scene,
    the glass behind it showing through it, its back faces its inner
    reflections.
    Painted glassware mirrors the room far more than real glass does, and
    mirrors it as the painter sees it -- bright panes over a clear body,
    not the even glare the room really sheds on a sphere -- so a
    ``reflection`` gain above 1 adds that many times the glass's own
    reflectance more (never past a mirror) of the room
    (:func:`reflection_room`, a probe of the conservatory that holds for
    every camera) at ``ROOM["brightness"]``: the reflections only ever
    brighten what is seen through the glass.  A scene overrides a field as
    ``"<name>.<field>"``."""
    def field(key, default=None):
        return param(f"{name}.{key}", spec.get(key, default))

    def build(tree: Tree):
        ior, density, tint = field("ior"), field("density"), color(field("tint"))
        thickness = attribute(tree, S.THICKNESS_ATTRIBUTE)
        straight = body in STRAIGHT_BODIES
        path = slant_path(tree, thickness, ior)
        transmittance = S.beer_lambert(tree, tint[:3], density, tree.math("MULTIPLY", path, 0.5) if straight else path)
        if straight:
            clear = tree.n("ShaderNodeBsdfTransparent", Color=transmittance)["BSDF"]
            mirror = tree.n("ShaderNodeBsdfGlossy", Color=(1.0, 1.0, 1.0, 1.0), Roughness=field("roughness", 0.0))["BSDF"]
            surface = mix_shader(tree, tree.n("ShaderNodeFresnel", IOR=ior)["Fac"], clear, mirror)
        else:
            surface = S.bsdf(tree, Base_Color=transmittance, Roughness=field("roughness", 0.0), IOR=ior, Transmission_Weight=1.0)["BSDF"]
        gain = field("reflection", 1.0)
        if gain > 1.0:
            facing = tree.n("ShaderNodeFresnel", IOR=ior)["Fac"]
            share = tree.math("MULTIPLY", facing, gain - 1.0, clamp=True)
            glint = tree.n("ShaderNodeEmission", reflection_room(tree), tree.math("MULTIPLY", share, ROOM["brightness"]))["Emission"]
            surface = tree.n("ShaderNodeAddShader", surface, glint)["Shader"]
        if straight:
            return mix_shader(tree, tree.n("ShaderNodeLightPath")["Is Shadow Ray"], surface, clear)
        return S.eevee_refraction(tree, surface, transmittance, thickness)

    if body == "pane":
        settings = {"surface_render_method": "DITHERED", "use_transparent_shadow": True}
    elif body == "over":
        settings = {"surface_render_method": "BLENDED", "use_transparent_shadow": True, "show_transparent_back": True,
                    "use_transparency_overlap": True}
    else:
        settings = {**S.EEVEE_REFRACTION, "thickness_mode": body.upper()}
    return lambda: S.material(bodied(name, body), build, settings=settings)


for glass_name, glass_spec in GLASSES.items():
    for glass_body in BODIES:
        register(bodied(glass_name, glass_body))(dielectric(glass_name, glass_spec, glass_body))


@register("GH.MilkGlass")
def milk_glass():
    """Opal (milk) glass: a pale, softly glossy top that lets light through
    diffusely (``milk``)."""
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("milk"), Roughness=0.3, Transmission_Weight=0.35, IOR=1.5,
                      Subsurface_Weight=0.4, Subsurface_Radius=(0.05, 0.05, 0.05), Coat_Weight=0.5, Coat_Roughness=0.05)["BSDF"]
    return S.material("GH.MilkGlass", build)



@register("GH.Tread")
def tread():
    """Honed limestone of the stair treads."""
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        cloud = S.noise(tree, coordinates, 6.0, 6.0, 0.6)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(cloud, 0.3, 0.7, 0.0, 1.0), scaled(color("tread"), 0.9), scaled(color("tread"), 1.08))
        return S.bsdf(tree, Base_Color=base, Roughness=0.45)["BSDF"]
    return S.material("GH.Tread", build)


@register("GH.Stone")
def stone():
    """Honed pale stone of the copings, the steps and the retaining walls'
    caps: ``stone`` clouded a little lighter and darker."""
    def build(tree: Tree):
        cloud = S.noise(tree, S.tex_coord(tree), 3.0, 6.0, 0.6)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(cloud, 0.35, 0.65, 0.0, 1.0), scaled(color("stone"), 0.9), scaled(color("stone"), 1.06))
        return S.bsdf(tree, Base_Color=base, Roughness=0.55)["BSDF"]
    return S.material("GH.Stone", build)


@register("GH.Cliff")
def cliff():
    """The faces of the hill's terraces: dressed stone (``stone_dark``)
    overgrown in patches by moss and ivy (``moss``), thickest towards the
    top where the terrace above drips water down it."""
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        _, _, height = tree.sep(coordinates)
        patches = S.noise(tree, tree.vmath("MULTIPLY", coordinates, (1.0, 1.0, 0.35)), 0.25, 5.0, 0.65)["Fac"]
        grit = S.noise(tree, coordinates, 30.0, 4.0)["Fac"]
        overgrown = tree.map_range(patches, 0.42, 0.58, 0.0, 1.0)
        base = S.mix_rgb(tree, overgrown, S.mix_rgb(tree, grit, scaled(color("stone_dark"), 0.85), scaled(color("stone_dark"), 1.1)), color("moss"))
        return S.bsdf(tree, Base_Color=base, Roughness=0.9, Normal=bump(tree, grit, 0.3))["BSDF"]
    return S.material("GH.Cliff", build)


@register("GH.PoolTile")
def pool_tile():
    """Glazed tile lining a pool's basin (``pool_tile``), seen through the
    water."""
    def build(tree: Tree):
        speckle = S.noise(tree, S.tex_coord(tree), 12.0, 3.0)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(speckle, 0.35, 0.65, 0.0, 1.0), scaled(color("pool_tile"), 0.85), scaled(color("pool_tile"), 1.1))
        return S.bsdf(tree, Base_Color=base, Roughness=0.3)["BSDF"]
    return S.material("GH.PoolTile", build)


def flagstones(name, dark, light):
    """Stone paving ``name``: the flags carry ``flag_shade`` (0..1, one value
    per flag), so every flag has its own tone between the palette colours
    ``dark`` and ``light``."""
    def build(tree: Tree):
        shade = attribute(tree, "flag_shade")
        base = S.mix_rgb(tree, shade, color(dark), color(light))
        grit = S.noise(tree, S.tex_coord(tree), 40.0, 5.0)["Fac"]
        return S.bsdf(tree, Base_Color=base, Roughness=tree.map_range(grit, 0.3, 0.7, 0.55, 0.8),
                      Normal=bump(tree, grit, 0.15))["BSDF"]
    return S.material(name, build)


@register("GH.Paving")
def paving():
    """Stone paving of the garden floor under the glass (``paving``)."""
    return flagstones("GH.Paving", "paving", "paving_light")


@register("GH.PlazaPaving")
def plaza_paving():
    """Granite paving out in the sun, the conservatory's plaza and roof
    terraces (``plaza``): a darker stone than the polished floor under the
    glass."""
    return flagstones("GH.PlazaPaving", "plaza", "plaza_light")


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
    """Mown grass in the open sun: mottled between ``grass`` and
    ``grass_light`` -- the albedo of real turf, a tenth to a third of the
    light, not the painted colours of the leaves under glass -- with a fine
    blade bump."""
    def build(tree: Tree):
        coordinates = S.tex_coord(tree)
        mottle = S.noise(tree, coordinates, 0.4, 6.0, 0.6)["Fac"]
        blades = S.noise(tree, coordinates, 300.0, 2.0)["Fac"]
        base = S.mix_rgb(tree, tree.map_range(mottle, 0.3, 0.7, 0.0, 1.0), color("grass"), color("grass_light"))
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


def sheet(tree: Tree):
    """Thickness output of a sheet -- a leaf, a blade -- for EEVEE: none, so
    the light through it crosses the blade instead of a body as deep as the
    object is wide (with ``thickness_mode`` "SLAB")."""
    zero = tree.n("ShaderNodeValue")
    zero.n.outputs[0].default_value = 0.0
    return zero.o


@register("GH.Leaf")
def leaf():
    def build(tree: Tree):
        return {"Surface": leaf_shader(tree, param("leaf_sheen", 0.45), param("leaf_translucency", 0.3), 0.42), "Thickness": sheet(tree)}
    return S.material("GH.Leaf", build, settings={"thickness_mode": "SLAB"})


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
    """Humid air of the conservatory: a thin scattering volume of
    ``air_density`` whose ``air_anisotropy`` runs from 0 (light scattered
    evenly) towards 1 (onwards), lit by the sun between the leaves above and
    the glazing bars.  Only volume, no surface."""
    def build(tree: Tree):
        volume = tree.n("ShaderNodeVolumePrincipled", Color=color("air"), Density=param("air_density", 0.01),
                        Anisotropy=param("air_anisotropy", 0.0))["Volume"]
        return {"Volume": volume}
    return S.material("GH.Air", build)


@register("GH.Smog")
def smog():
    """The city haze in the valley below the conservatory: an absorbing
    medium that glows with the skylight it scatters in, so along a path of
    transmittance T the view becomes L * T + smog * brightness * (1 - T) --
    single-scattered skylight in closed form.  It thins with height,
    exp(-(z - ``smog_ground``) / ``smog_scale``) from ``smog_density`` at
    the ground: the streets far below vanish into pink while a neighbouring
    tower at the conservatory's height stays clear.  An inversion holds it
    in the valley: above ``smog_top`` it fades over ``smog_top_fade`` to the
    share ``smog_above`` of itself, so a view down from the hill dissolves
    into pink while the sky above the hill stays blue; and the hilltop
    itself, the box from ``smog_clear_min`` to ``smog_clear_max``, is clear
    air.  What is left above the inversion is the clean air's own haze: it
    glows with the blue skylight it scatters (``clear_air``), turning from
    the smog's pink over ``smog_air_fade`` above the inversion's top.  It is
    seen, it lights nothing."""
    def build(tree: Tree):
        x, y, z = tree.sep(tree.n("ShaderNodeNewGeometry")["Position"])
        falloff = tree.math("EXPONENT", (z - param("smog_ground", -120.0)) * (-1.0 / param("smog_scale", 30.0)))
        top = param("smog_top", 0.0)
        clean = top + param("smog_top_fade", 1.0)
        inversion = tree.map_range(z, top, clean, 1.0, param("smog_above", 1.0))
        tint = S.mix_rgb(tree, tree.map_range(z, clean, clean + param("smog_air_fade", 1.0), 0.0, 1.0), color("smog"), color("clear_air"))
        inside = None
        for axis, low, high in zip((x, y, z), param("smog_clear_min", (0.0, 0.0, 0.0)), param("smog_clear_max", (0.0, 0.0, 0.0))):
            within = tree.math("MULTIPLY", tree.math("GREATER_THAN", axis, low), tree.math("LESS_THAN", axis, high))
            inside = within if inside is None else tree.math("MULTIPLY", inside, within)
        outside = tree.math("SUBTRACT", 1.0, inside)
        density = tree.math("MULTIPLY", tree.math("MULTIPLY", tree.math("MULTIPLY", falloff, inversion), outside), param("smog_density", 0.05))
        absorb = tree.n("ShaderNodeVolumeAbsorption", Color=(0.0, 0.0, 0.0, 1.0), Density=density)["Volume"]
        glow = tree.n("ShaderNodeEmission", Color=tint, Strength=tree.math("MULTIPLY", density, param("smog_brightness", 1.0)))["Emission"]
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


def haze_transmittance(tree: Tree, direction, origin):
    """Share of the light coming from ``direction`` that reaches ``origin``
    through the city haze (:func:`smog`, without its inversion: the light
    crosses the whole column): clear air out to the face of the box
    ``smog_clear_min`` -- ``smog_clear_max`` the light enters it by, beyond
    it the exponential column of ``smog_density`` at ``smog_ground`` thinning
    over ``smog_scale``, whose optical depth along the rest of the way up is
    density * scale / sin(elevation) * exp(-(z_exit - ground) / scale).  No
    sky light comes from below the horizon: it crosses the whole valley."""
    scale, ground = param("smog_scale", 30.0), param("smog_ground", -120.0)
    exits = []
    for axis, start, low, high in zip(tree.sep(direction), origin, param("smog_clear_min", (0.0,) * 3), param("smog_clear_max", (0.0,) * 3)):
        face = tree.mix(tree.math("GREATER_THAN", axis, 0.0), low - start, high - start)
        exits.append(tree.math("DIVIDE", tree.math("ABSOLUTE", face), tree.math("MAXIMUM", tree.math("ABSOLUTE", axis), 1e-6)))
    _, _, rise = tree.sep(direction)
    leave = tree.math("MINIMUM", tree.math("MINIMUM", exits[0], exits[1]), exits[2])
    exit_height = tree.math("ADD", tree.math("MULTIPLY", leave, rise), origin[2])
    column = tree.math("EXPONENT", tree.math("MULTIPLY", tree.math("SUBTRACT", exit_height, ground), -1.0 / scale))
    depth = tree.math("MULTIPLY", tree.math("DIVIDE", param("smog_density", 0.05) * scale, tree.math("MAXIMUM", rise, 1e-3)), column)
    return tree.math("MULTIPLY", tree.math("EXPONENT", tree.math("MULTIPLY", depth, -1.0)), tree.math("GREATER_THAN", rise, 0.0))


def sky_colour(tree: Tree, direction, height, haze_top, zenith_height, clouds):
    """The sky's colour towards ``direction`` (``height`` its up component):
    the gradient from the haze below ``haze_top`` through ``sky_horizon``
    to ``sky_zenith`` at ``zenith_height``, under the ``clouds`` -- banks of
    their ``color`` covering the share ``cover`` of the sky, ``scale`` of
    them across it, flattened ``flatten`` times, edges ``softness`` soft,
    fading in over the heights ``band[0]..band[1]`` and out over
    ``band[2]..band[3]``."""
    sky = S.ramp(tree, tree.map_range(height, haze_top, zenith_height, 0.0, 1.0),
                 [(0.0, color("haze")), (0.35, color("sky_horizon")), (1.0, color("sky_zenith"))])["Color"]
    flattened = tree.vmath("MULTIPLY", direction, (1.0, 1.0, clouds["flatten"]))
    billows = S.noise(tree, flattened, clouds["scale"], 6.0, 0.55)["Fac"]
    threshold = 1.0 - clouds["cover"]
    cover = tree.map_range(billows, threshold, threshold + clouds["softness"], 0.0, 1.0)
    rising, full, thinning, gone = clouds["band"]
    band = tree.math("MULTIPLY", tree.map_range(height, rising, full, 0.0, 1.0), tree.map_range(height, thinning, gone, 1.0, 0.0))
    return S.mix_rgb(tree, tree.math("MULTIPLY", cover, band), sky, color(clouds["color"]))


def world(config):
    """Hazy daylight sky: a gradient from the pink-white haze at and below
    the horizon to a pale blue zenith, under clouds (:func:`sky_colour`).
    The sky sheds ``light_strength`` (the light fit's), and every ray
    reaches it the way it does through the city haze from ``light_origin``
    (:func:`haze_transmittance`, T): the light falling on a surface is the
    sky dimmed to T; a reflection sees the sky dimmed to T and the haze's
    own glow, smog * ``smog_brightness`` * (1 - T) -- both the sky the light
    fit was made with, its blue reaching down to ``zenith_height`` under the
    ``clouds``.  The camera sees the sky at ``seen_strength`` -- the eye
    adapted to a sunlit park, where the sky is bright but not blinding --
    with the haze between drawn by the haze's own volume, its blue reaching
    down to ``seen_zenith_height`` under the ``seen_clouds`` (below
    ``haze_top`` both are the haze)."""
    world_block = S.new_world("GH.Sky")
    tree = Tree.wrap(world_block.node_tree, clear=True)
    out = tree.n("ShaderNodeOutputWorld")
    direction = tree.vmath("NORMALIZE", tree.n("ShaderNodeTexCoord")["Generated"])
    _, _, height = tree.sep(direction)
    sky = sky_colour(tree, direction, height, config["haze_top"], config["zenith_height"], config["clouds"])
    seen_sky = sky_colour(tree, direction, height, config["haze_top"], config["seen_zenith_height"], config["seen_clouds"])
    path = tree.n("ShaderNodeLightPath")
    through = haze_transmittance(tree, direction, config["light_origin"])
    lit = tree.vmath("SCALE", sky, scale=tree.math("MULTIPLY", through, config["light_strength"]))
    glow = tree.vmath("SCALE", color("smog")[:3], scale=tree.math("MULTIPLY", tree.math("SUBTRACT", 1.0, through), param("smog_brightness", 1.0)))
    reflected = tree.mix(path["Is Glossy Ray"], lit, tree.vmath("ADD", lit, glow), data_type="RGBA")
    seen = tree.vmath("SCALE", seen_sky, scale=config["seen_strength"])
    radiance = tree.mix(path["Is Camera Ray"], reflected, seen, data_type="RGBA")
    tree.link(tree.n("ShaderNodeBackground", radiance, 1.0)["Background"], out.n.inputs["Surface"])
    tree.layout()
    bpy.context.scene.world = world_block
    return world_block
