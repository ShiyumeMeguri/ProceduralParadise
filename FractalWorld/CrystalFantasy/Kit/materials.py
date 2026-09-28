"""
Crystal Fantasy material library (``CF.*``).

Everything is procedural and lives in object or world space, so any camera
sees the same surfaces.  Transparent media -- glass, crystal, water -- are
real refractive dielectrics for camera and reflection rays, but let shadow
rays through tinted: the conservatory is a house of glass, and blocking the
light at every pane (or chasing it as caustics) would leave it dark or
noisy.  Organic surfaces read their colours from attributes the kit stores
on the geometry (``petal_inner`` / ``petal_outer``, ``leaf_color``,
``star_color`` ...), so one material serves every flower, leaf or star.

Base colours come from the realm palette (``Realm.json``); a shot may
override look parameters through ``PARAMS`` before the materials are built.
"""
from __future__ import annotations

import bpy

from Core import anim as ANIM, shaders as S
from Core.nodes import Tree
from .. import PALETTE

LIBRARY = S.MaterialLibrary(PALETTE, "crystal_fantasy_built")
PARAMS = LIBRARY.params
register = LIBRARY.register
get = LIBRARY.get
color = LIBRARY.color
param = LIBRARY.param


# ------------------------------------------------------------------ helpers
def attribute(tree: Tree, name, output="Factor", kind="GEOMETRY"):
    return tree.n("ShaderNodeAttribute", props={"attribute_name": name, "attribute_type": kind})[output]


def shadow_clear(tree: Tree, shader, tint):
    """``shader`` for camera and indirect rays, a tinted transparent surface
    for shadow rays."""
    shadow = tree.n("ShaderNodeLightPath")["Is Shadow Ray"]
    transparent = tree.n("ShaderNodeBsdfTransparent", Color=tint)["BSDF"]
    return tree.n("ShaderNodeMixShader", shadow, shader, transparent)["Shader"]


def emission(tree: Tree, tint, strength):
    return tree.n("ShaderNodeEmission", Color=tint, Strength=strength)["Emission"]


def add(tree: Tree, first, second):
    return tree.n("ShaderNodeAddShader", first, second)["Shader"]


def mix(tree: Tree, factor, first, second):
    return tree.n("ShaderNodeMixShader", factor, first, second)["Shader"]


def scaled(rgba, factor):
    return tuple(channel * factor for channel in rgba[:3]) + (1.0,)


def scene_seconds(tree: Tree, material):
    """Shader-side clock: a Value node keyed to the scene time in seconds,
    the same clock the geometry nodes read."""
    node = tree.n("ShaderNodeValue", name="Seconds", label="Seconds")
    ANIM.key_seconds(node.n.outputs[0], "default_value", material.node_tree, bpy.context.scene.render.fps)
    return node.o


def dielectric(name, tint, ior, roughness=0.0, film=0.0, film_ior=1.38, dispersion=0.0, abbe=30.0,
               absorption=None, density=0.0, glow=None, glow_strength=0.0):
    """Clear refractive solid: surface tint, optional thin film (iridescent
    reflections), dispersion, and a volume that absorbs towards
    ``absorption`` with ``density`` per metre and may glow from within."""
    def build(tree: Tree):
        inputs = dict(Base_Color=tint, Roughness=roughness, IOR=ior, Transmission_Weight=1.0)
        if film:
            inputs.update(Thin_Film_Thickness=film, Thin_Film_IOR=film_ior)
        if dispersion:
            inputs.update(Transmission_Dispersion_Scale=dispersion, Transmission_Dispersion_Abbe_Number=abbe)
        surface = shadow_clear(tree, S.bsdf(tree, **inputs)["BSDF"], tint)
        volume = None
        if absorption is not None and density:
            volume = tree.n("ShaderNodeVolumeAbsorption", Color=absorption, Density=density)["Volume"]
        if glow is not None and glow_strength:
            light = emission(tree, glow, glow_strength)
            volume = light if volume is None else add(tree, volume, light)
        return {"Surface": surface, "Volume": volume}
    return S.material(name, build)


# ------------------------------------------------------------------ glass & crystal
@register("CF.Glass")
def glass():
    """Vessel glass: clear, with a faint iridescent film on reflections."""
    return dielectric("CF.Glass", color("glass"), 1.5, param("glass_roughness", 0.0),
                      film=param("glass_film", 320.0))


@register("CF.GlassPane")
def glass_pane():
    """Architectural panes: thin glass (no refraction offset)."""
    return S.glass_mat("CF.GlassPane", color=color("glass")[:3], roughness=0.0, ior=1.5,
                       reflect=param("pane_reflect", 1.0))


@register("CF.Crystal")
def crystal():
    """Clear crystal: dispersion splits highlights into spectral sparkles,
    a thin film tints the reflections."""
    return dielectric("CF.Crystal", color("ice"), 1.56, film=param("crystal_film", 480.0),
                      dispersion=param("crystal_dispersion", 1.0), abbe=param("crystal_abbe", 28.0),
                      absorption=color("cyan"), density=param("crystal_absorption", 0.6))


@register("CF.CrystalBlue")
def crystal_blue():
    """Blue crystal whose colour deepens with thickness, glowing faintly."""
    return dielectric("CF.CrystalBlue", color("ice"), 1.56, film=param("crystal_film", 480.0),
                      dispersion=param("crystal_dispersion", 1.0), abbe=param("crystal_abbe", 28.0),
                      absorption=color("azure"), density=param("crystal_blue_absorption", 4.0),
                      glow=color("cyan"), glow_strength=param("crystal_blue_glow", 0.6))


@register("CF.CrystalViolet")
def crystal_violet():
    return dielectric("CF.CrystalViolet", color("ice"), 1.56, film=param("crystal_film", 480.0),
                      dispersion=param("crystal_dispersion", 1.0), abbe=param("crystal_abbe", 28.0),
                      absorption=color("lilac"), density=param("crystal_violet_absorption", 4.0),
                      glow=color("violet"), glow_strength=param("crystal_violet_glow", 0.5))


@register("CF.CrystalLight")
def crystal_light():
    """Crystal heart: clear facets around a strong inner light -- the lamps
    at the far ends of the naves."""
    return dielectric("CF.CrystalLight", color("ice"), 1.56, film=param("crystal_film", 480.0),
                      absorption=color("cyan"), density=param("crystal_light_absorption", 0.4),
                      glow=color("ice"), glow_strength=param("crystal_light_glow", 12.0))


@register("CF.CrystalLightViolet")
def crystal_light_violet():
    return dielectric("CF.CrystalLightViolet", color("ice"), 1.56, film=param("crystal_film", 480.0),
                      absorption=color("lilac"), density=param("crystal_light_absorption", 0.4),
                      glow=color("lilac"), glow_strength=param("crystal_light_glow", 12.0))


@register("CF.Water")
def water():
    """Water in the vessels: refractive surface, blue absorption with depth
    and a soft cyan glow from within."""
    return dielectric("CF.Water", color("glass"), 1.333, absorption=color("cyan"),
                      density=param("water_absorption", 2.5), glow=color("cyan"),
                      glow_strength=param("water_glow", 0.8))


@register("CF.OrbGlass")
def orb_glass():
    """Deep cobalt glass of the galaxy orbs."""
    return dielectric("CF.OrbGlass", color("ice"), 1.47, film=param("orb_film", 420.0),
                      absorption=color("azure"), density=param("orb_absorption", 7.0))


@register("CF.OrbMarble")
def orb_marble():
    """Planet-like marbled orb: fractal (fBm) swirls of blues and teal under
    a glassy coat."""
    def build(tree: Tree):
        position = tree.n("ShaderNodeTexCoord")["Object"]
        warp = S.noise(tree, position, scale=2.2, detail=8.0, rough=0.62, distortion=1.4)["Fac"]
        bands = S.noise(tree, position + tree.vec(warp, warp, warp), scale=3.4, detail=10.0, rough=0.58)["Fac"]
        tint = S.ramp(tree, bands, [(0.28, color("cobalt")), (0.45, color("azure")), (0.55, color("leaf_teal")),
                                    (0.64, color("cyan")), (0.72, color("ice"))])["Color"]
        return S.bsdf(tree, Base_Color=tint, Roughness=0.35, Coat_Weight=1.0, Coat_Roughness=0.02,
                      Emission_Color=tint, Emission_Strength=param("marble_glow", 0.15))["BSDF"]
    return S.material("CF.OrbMarble", build)


@register("CF.Star")
def star():
    """Stars of the galaxies inside the orbs (colour per point)."""
    def build(tree: Tree):
        tint = attribute(tree, "star_color", "Color")
        return emission(tree, tint, param("star_strength", 12.0))
    return S.material("CF.Star", build)


# ------------------------------------------------------------------ flora
@register("CF.Petal")
def petal():
    """Petals: inner colour at the base graded to the outer colour at the
    tip, deeper towards the centre of the flower, translucent and faintly
    luminous."""
    def build(tree: Tree):
        along = attribute(tree, "petal_u")
        depth = attribute(tree, "petal_t")
        inner = attribute(tree, "petal_inner", "Color")
        outer = attribute(tree, "petal_outer", "Color")
        grade = tree.map_range(along, 0.05, 0.9, 0.0, 1.0, interp="SMOOTHSTEP")
        tint = S.mix_rgb(tree, grade, inner, outer)
        tint = S.mix_rgb(tree, tree.map_range(depth, 0.0, 0.6, 0.45, 0.0), tint, inner)
        surface = S.bsdf(tree, Base_Color=tint, Roughness=0.42, Sheen_Weight=0.5, Sheen_Tint=(1.0, 1.0, 1.0, 1.0),
                         Specular_IOR_Level=0.45)["BSDF"]
        translucent = tree.n("ShaderNodeBsdfTranslucent", Color=tint)["BSDF"]
        body = mix(tree, param("petal_translucency", 0.45), surface, translucent)
        glow = emission(tree, tint, tree.map_range(along, 0.0, 1.0, 0.3, 1.0) * param("petal_glow", 0.35))
        return add(tree, body, glow)
    return S.material("CF.Petal", build)


@register("CF.FlowerCenter")
def flower_center():
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("blush"), Roughness=0.5, Emission_Color=color("blush"),
                      Emission_Strength=param("center_glow", 0.4))["BSDF"]
    return S.material("CF.FlowerCenter", build)


@register("CF.Leaf")
def leaf():
    """Leaves: colour from ``leaf_color``, lighter midrib and margin,
    glossy, translucent against the light."""
    def build(tree: Tree):
        along = attribute(tree, "leaf_u")
        across = tree.abs(attribute(tree, "leaf_v"))
        base = attribute(tree, "leaf_color", "Color")
        rib = tree.map_range(across, 0.0, 0.07, 1.0, 0.0, interp="SMOOTHSTEP")
        light = S.mix_rgb(tree, 0.55, base, color("ice"))
        tint = S.mix_rgb(tree, rib * 0.6, base, light)
        tint = S.mix_rgb(tree, tree.map_range(along, 0.6, 1.0, 0.0, 0.35), tint, light)
        surface = S.bsdf(tree, Base_Color=tint, Roughness=0.3, Coat_Weight=0.4, Coat_Roughness=0.1)["BSDF"]
        translucent = tree.n("ShaderNodeBsdfTranslucent", Color=tint)["BSDF"]
        body = mix(tree, param("leaf_translucency", 0.35), surface, translucent)
        return add(tree, body, emission(tree, tint, param("leaf_glow", 0.12)))
    return S.material("CF.Leaf", build)


@register("CF.Stem")
def stem():
    return S.principled("CF.Stem", color("stem"), roughness=0.4, coat=0.3,
                        emission=color("stem"), emission_strength=param("stem_glow", 0.05))


# ------------------------------------------------------------------ metal & stone
@register("CF.Iron")
def iron():
    """Dark navy enamelled iron of the glasshouse frame."""
    return S.principled("CF.Iron", color("iron"), roughness=0.32, metallic=0.75, coat=0.5, coat_roughness=0.08)


@register("CF.Silver")
def silver():
    return S.principled("CF.Silver", color("silver"), roughness=0.14, metallic=1.0)


@register("CF.Thread")
def thread():
    return S.principled("CF.Thread", color("silver"), roughness=0.3, metallic=0.6,
                        emission=color("ice"), emission_strength=param("thread_glow", 0.2))


@register("CF.Stone")
def stone():
    """Pale blue-white marble tiles (1.2 m, thin joints) with faint veins."""
    size = param("tile_size", 1.2)

    def build(tree: Tree):
        position = tree.n("ShaderNodeNewGeometry")["Position"]
        x, y, _ = tree.sep(position)
        u = tree.math("FRACT", x / size)
        v = tree.math("FRACT", y / size)
        edge = tree.min(tree.min(u, 1.0 - u), tree.min(v, 1.0 - v)) * size
        joint = tree.map_range(edge, 0.002, 0.005, 1.0, 0.0)
        cell = tree.vec(tree.math("FLOOR", x / size), tree.math("FLOOR", y / size), 0.0)
        tone = tree.n("ShaderNodeTexWhiteNoise", cell, props={"noise_dimensions": "3D"})["Value"]
        vein = S.noise(tree, position * 0.8, scale=1.6, detail=9.0, rough=0.6, distortion=2.2)["Fac"]
        vein = tree.map_range(tree.abs(vein - 0.5), 0.0, 0.03, 1.0, 0.0)
        base = S.mix_rgb(tree, tone * 0.5, color("stone"), color("ice"))
        base = S.mix_rgb(tree, vein * 0.25, base, color("azure"))
        base = S.mix_rgb(tree, joint, base, color("navy"))
        return S.bsdf(tree, Base_Color=base, Roughness=tree.mix(joint, param("stone_roughness", 0.12), 0.6),
                      Coat_Weight=param("stone_coat", 0.35), Coat_Roughness=0.05)["BSDF"]
    return S.material("CF.Stone", build)


@register("CF.Soil")
def soil():
    """Dark blue moss of the planting beds, flecked with light."""
    def build(tree: Tree):
        position = tree.n("ShaderNodeTexCoord")["Object"]
        clumps = S.noise(tree, position, scale=9.0, detail=6.0, rough=0.7)["Fac"]
        tint = S.mix_rgb(tree, clumps, color("navy"), color("leaf_teal"))
        flecks = tree.n("ShaderNodeTexVoronoi", position, Scale=60.0, props={"feature": "F1"})["Distance"]
        spark = tree.map_range(flecks, 0.0, 0.06, 1.0, 0.0)
        return S.bsdf(tree, Base_Color=tint, Roughness=0.85, Emission_Color=color("cyan"),
                      Emission_Strength=spark * param("soil_sparkle", 0.6))["BSDF"]
    return S.material("CF.Soil", build)


@register("CF.PoolWater")
def pool_water():
    """Shallow water over the floor: clear refractive film whose surface is
    stirred by expanding ripple rings (one per Voronoi cell, each on its own
    life cycle, driven by the scene clock)."""
    material = bpy.data.materials.get("CF.PoolWater") or bpy.data.materials.new("CF.PoolWater")

    def build(tree: Tree):
        seconds = scene_seconds(tree, material)
        position = tree.n("ShaderNodeNewGeometry")["Position"]
        x, y, _ = tree.sep(position)
        cells = tree.n("ShaderNodeTexVoronoi", tree.vec(x, y, 0.0), Scale=param("ripple_density", 0.9),
                       Randomness=1.0, props={"voronoi_dimensions": "2D", "feature": "F1", "distance": "EUCLIDEAN"})
        distance = cells["Distance"]
        chance = tree.sep(cells["Color"])
        life = tree.math("FRACT", seconds * param("ripple_rate", 0.18) + chance[0])
        radius = life * 0.45
        offset = distance - radius
        ring = tree.sin(offset * param("ripple_frequency", 70.0))
        envelope = tree.math("EXPONENT", tree.abs(offset) * -18.0) * (1.0 - life) * (1.0 - life)
        height = ring * envelope * param("ripple_height", 0.004)
        bump = tree.n("ShaderNodeBump", Strength=1.0, Distance=1.0, Height=height)["Normal"]
        surface = S.bsdf(tree, Base_Color=color("glass"), Roughness=0.015, IOR=1.333, Transmission_Weight=1.0,
                         Normal=bump)["BSDF"]
        return shadow_clear(tree, surface, color("glass"))
    return S.material("CF.PoolWater", build)


# ------------------------------------------------------------------ light
@register("CF.LightCore")
def light_core():
    def build(tree: Tree):
        return emission(tree, color("ice"), param("core_strength", 25.0))
    return S.material("CF.LightCore", build)


@register("CF.Mote")
def mote():
    """Floating light motes; ``glow`` (0..1) twinkles per mote."""
    def build(tree: Tree):
        twinkle = attribute(tree, "glow")
        tint = S.mix_rgb(tree, attribute(tree, "hue"), color("cyan"), color("ice"))
        return emission(tree, tint, twinkle * param("mote_strength", 18.0))
    return S.material("CF.Mote", build)


# ------------------------------------------------------------------ butterflies
@register("CF.Wing")
def wing():
    """Morpho wing: luminous azure blade from a cobalt base, dark border
    with pale spots, iridescent film on top."""
    def build(tree: Tree):
        span = attribute(tree, "wing_u")
        edge = attribute(tree, "wing_edge")
        base = S.mix_rgb(tree, tree.map_range(span, 0.0, 0.55, 0.0, 1.0, interp="SMOOTHSTEP"),
                         color("cobalt"), color("azure"))
        base = S.mix_rgb(tree, tree.map_range(span, 0.45, 0.9, 0.0, 0.6), base, color("cyan"))
        border = tree.map_range(edge, 0.05, 0.14, 1.0, 0.0, interp="SMOOTHSTEP")
        spots = tree.n("ShaderNodeTexVoronoi", tree.vec(attribute(tree, "wing_u") * 9.0, edge * 30.0, 0.0),
                       Scale=1.0, props={"voronoi_dimensions": "2D"})["Distance"]
        spot = tree.map_range(spots, 0.12, 0.2, 1.0, 0.0) * tree.map_range(edge, 0.02, 0.1, 1.0, 0.0)
        tint = S.mix_rgb(tree, border, base, color("navy"))
        tint = S.mix_rgb(tree, spot * 0.8, tint, color("ice"))
        glow = tree.map_range(border, 0.0, 1.0, 1.0, 0.0)
        surface = S.bsdf(tree, Base_Color=tint, Roughness=0.25, Thin_Film_Thickness=param("wing_film", 380.0),
                         Thin_Film_IOR=1.5, Emission_Color=tint,
                         Emission_Strength=glow * param("wing_glow", 1.2))["BSDF"]
        translucent = tree.n("ShaderNodeBsdfTranslucent", Color=tint)["BSDF"]
        return mix(tree, 0.3, surface, translucent)
    return S.material("CF.Wing", build)


@register("CF.ButterflyBody")
def butterfly_body():
    return S.principled("CF.ButterflyBody", color("navy"), roughness=0.35, coat=0.5)


@register("CF.Haze")
def haze():
    """Luminous air: a thin forward-scattering medium that turns every light
    into a glow and every vista into depth."""
    def build(tree: Tree):
        volume = tree.n("ShaderNodeVolumePrincipled", Color=color("ice"), Density=param("haze_density", 0.02),
                        Anisotropy=param("haze_anisotropy", 0.45))["Volume"]
        return {"Surface": None, "Volume": volume}
    return S.material("CF.Haze", build)


# ------------------------------------------------------------------ exterior
@register("CF.Sea")
def sea():
    """The still sea around the conservatory: a dark mirror."""
    def build(tree: Tree):
        position = tree.n("ShaderNodeNewGeometry")["Position"]
        swell = S.noise(tree, position * 0.05, scale=1.0, detail=4.0, rough=0.5)["Fac"]
        bump = tree.n("ShaderNodeBump", Strength=0.08, Distance=1.0, Height=swell)["Normal"]
        return S.bsdf(tree, Base_Color=color("navy"), Roughness=0.03, IOR=1.333, Specular_IOR_Level=0.6,
                      Normal=bump)["BSDF"]
    return S.material("CF.Sea", build)


@register("CF.CrystalFar")
def crystal_far():
    """Distant crystal spires: glossy facets over a cool inner glow (no
    refraction -- they are hundreds of metres away)."""
    def build(tree: Tree):
        facing = tree.n("ShaderNodeLayerWeight", Blend=0.4)["Facing"]
        glow = S.mix_rgb(tree, facing, color("cyan"), color("cobalt"))
        surface = S.bsdf(tree, Base_Color=color("navy"), Roughness=0.08, Specular_IOR_Level=0.8,
                         Emission_Color=glow, Emission_Strength=param("spire_glow", 1.5))["BSDF"]
        return surface
    return S.material("CF.CrystalFar", build)
