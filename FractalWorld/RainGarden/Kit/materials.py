"""
Rain Garden material library (``RainGarden.*``), made for EEVEE.

Every material is data: ``Realm.json`` gives each one a ``shader`` type and
its parameters, and :data:`SHADERS` turns a type into a node tree.  A scene
overrides any parameter of any material through ``scene.json``
``"materials": {material: {parameter: value}}`` (``PARAMS``), read before the
kit is built.

EEVEE refracts through one layer, so the kit follows :mod:`Core.shaders`:

* ``thin_glass`` -- panes, railings, the vault: transparent and glossy mixed
  by Fresnel, so what is behind shows through undistorted;
* ``refractive`` and ``crystal`` -- bodies of water and crystal refract with
  the ``thickness`` that ``Shading.Thickness`` stores on their geometry and
  absorb along it by Beer-Lambert (``absorption_color``,
  ``absorption_density`` per metre); shadow rays see their mean
  transmittance;
* ``iridescent_glass`` -- a thin glass shell with a rainbow sheen running
  along noise bands and the viewing angle (the thin-film look of the
  basins);
* ``waterfall`` -- a streaked, dithered transparent sheet that glows where the
  water runs thick (``fall_uv`` from the falling-water assets).
"""
from __future__ import annotations

from Core import shaders as S
from Core.nodes import Tree
from .. import MATERIALS, PALETTE

LIBRARY = S.MaterialLibrary(PALETTE, "rain_garden_built")
PARAMS = LIBRARY.params
register = LIBRARY.register
get = LIBRARY.get

DITHERED_SHADOWED = {"surface_render_method": "DITHERED", "use_transparent_shadow": True}


def rgba(value):
    value = tuple(value)
    return value if len(value) == 4 else (*value, 1.0)


def attribute(tree: Tree, name, output="Fac"):
    return tree.n("ShaderNodeAttribute", props={"attribute_name": name, "attribute_type": "GEOMETRY"})[output]


def ramp(tree: Tree, factor, stops, interpolation="LINEAR"):
    node = S.ramp(tree, factor, [(position, rgba(color)) for position, color in stops])
    node.n.color_ramp.interpolation = interpolation
    return node["Color"]


def emission(tree: Tree, color, strength):
    return tree.n("ShaderNodeEmission", Color=color, Strength=strength)["Emission"]


def add(tree: Tree, first, second):
    return tree.n("ShaderNodeAddShader", first, second)["Shader"]


def principled(tree: Tree, p, **overrides):
    inputs = dict(Base_Color=rgba(p.get("base_color", (0.8, 0.8, 0.8))), Metallic=p.get("metallic", 0.0),
                  Roughness=p.get("roughness", 0.5), IOR=p.get("ior", 1.5), Alpha=p.get("alpha", 1.0),
                  Transmission_Weight=p.get("transmission", 0.0), Coat_Weight=p.get("coat", 0.0),
                  Coat_Roughness=p.get("coat_roughness", 0.03), Specular_IOR_Level=p.get("specular", 0.5),
                  Emission_Color=rgba(p.get("emission_color", (1.0, 1.0, 1.0))),
                  Emission_Strength=p.get("emission_strength", 0.0), Subsurface_Weight=p.get("subsurface", 0.0),
                  Sheen_Weight=p.get("sheen", 0.0))
    inputs.update(overrides)
    return S.bsdf(tree, **inputs)["BSDF"]


def shadow_clear(tree: Tree, shader, tint):
    """``shader`` for camera and indirect rays, a tinted transparent surface
    for shadow rays."""
    shadow = tree.n("ShaderNodeLightPath")["Is Shadow Ray"]
    clear = tree.n("ShaderNodeBsdfTransparent", Color=rgba(tint))["BSDF"]
    return tree.n("ShaderNodeMixShader", shadow, shader, clear)["Shader"]


def ripples(tree: Tree, p):
    if not p.get("ripple_strength"):
        return None
    stretched = tree.n("ShaderNodeMapping", Vector=S.tex_coord(tree), Scale=tuple(p.get("ripple_stretch", (1.0, 1.0, 1.0)))).o
    height = S.noise(tree, stretched, p.get("ripple_scale", 1.6), p.get("ripple_detail", 6.0), 0.55)["Fac"]
    return tree.n("ShaderNodeBump", Strength=p["ripple_strength"], Distance=0.02, Height=height)["Normal"]


def refractive_body(tree: Tree, p, tint=None, glow=None):
    """Clear body refracting with the stored ``thickness``: absorbs along it
    (Beer-Lambert) and glows ``glow_strength`` per metre of it (what a
    self-luminous medium adds up along the path), plus any surface ``glow``."""
    thickness = attribute(tree, S.THICKNESS_ATTRIBUTE)
    transmittance = S.beer_lambert(tree, tuple(p.get("absorption_color", (1.0, 1.0, 1.0))[:3]), p.get("absorption_density", 0.0), thickness)
    color = transmittance if tint is None else tree.vmath("MULTIPLY", transmittance, tint)
    body = principled(tree, p, Base_Color=color, Transmission_Weight=p.get("transmission", 1.0), IOR=p.get("ior", 1.333),
                      Roughness=p.get("roughness", 0.0), Normal=ripples(tree, p), Specular_Tint=rgba(p.get("reflection_tint", (1.0, 1.0, 1.0))))
    if p.get("glow_strength"):
        body = add(tree, body, emission(tree, rgba(p.get("glow_color", (0.2, 0.8, 1.0))), thickness * p["glow_strength"]))
    if glow is not None:
        body = add(tree, body, glow)
    return S.eevee_refraction(tree, body, transmittance, thickness), dict(S.EEVEE_REFRACTION)


# ------------------------------------------------------------------ shader types
def principled_surface(tree: Tree, p):
    surface = principled(tree, p)
    if p.get("shadow_transparent"):
        return shadow_clear(tree, surface, p.get("shadow_tint", (1.0, 1.0, 1.0))), dict(DITHERED_SHADOWED)
    return surface, {}


def emission_surface(tree: Tree, p):
    return emission(tree, rgba(p["color"]), p.get("strength", 1.0)), {}


def thin_glass_surface(tree: Tree, p):
    pane = S.thin_glass(tree, tuple(p.get("color", (0.95, 0.99, 1.0))[:3]), p.get("roughness", 0.0), p.get("ior", 1.5), p.get("reflect", 1.0))
    return pane, dict(DITHERED_SHADOWED)


def refractive_surface(tree: Tree, p):
    glow = emission(tree, rgba(p.get("glow_color", (0.2, 0.8, 1.0))), p["surface_glow"]) if p.get("surface_glow") else None
    tint = tuple(p["base_color"][:3]) if "base_color" in p else None
    return refractive_body(tree, p, tint, glow)


def crystal_surface(tree: Tree, p):
    tint = ramp(tree, attribute(tree, p.get("tint_attribute", "tint")), p["tint_stops"])
    facing = tree.n("ShaderNodeLayerWeight", Blend=0.4)["Facing"]
    return refractive_body(tree, p, tint, emission(tree, tint, facing * p.get("inner_glow", 0.35)))


def iridescent_glass_surface(tree: Tree, p):
    bands = S.noise(tree, S.tex_coord(tree), p.get("film_scale", 0.35), 2.0, 0.5, distortion=0.8)["Fac"]
    facing = tree.n("ShaderNodeLayerWeight", Blend=p.get("sheen_blend", 0.45))["Facing"]
    hue = tree.math("FRACT", bands * p.get("sheen_band_scale", 1.6) + facing * p.get("sheen_facing_scale", 0.9))
    sheen = emission(tree, ramp(tree, hue, p["sheen_stops"]), facing * p.get("sheen_strength", 0.5))
    pane = S.thin_glass(tree, tuple(p.get("color", (0.9, 0.97, 1.0))[:3]), p.get("roughness", 0.03), p.get("ior", 1.45), p.get("reflect", 1.0))
    return add(tree, pane, sheen), dict(DITHERED_SHADOWED)


def waterfall_surface(tree: Tree, p):
    flow = tree.n("ShaderNodeMapping", Vector=attribute(tree, p.get("uv_attribute", "fall_uv"), "Vector"),
                  Scale=tuple(p.get("streak_scale", (18.0, 0.6, 1.0)))).o
    streaks = S.noise(tree, flow, 1.0, 8.0, 0.62, distortion=0.3)["Fac"]
    streaks = tree.map_range(streaks, p.get("streak_low", 0.35), p.get("streak_high", 0.75), 0.0, 1.0)
    edge = tree.n("ShaderNodeLayerWeight", Blend=p.get("edge_blend", 0.35))["Facing"]
    opacity = tree.clamp01((streaks * p.get("streak_opacity", 0.75) + edge * p.get("edge_opacity", 0.45)) * p.get("opacity", 1.0))
    glow = emission(tree, rgba(p.get("glow_color", (0.75, 0.95, 1.0))), streaks * p.get("glow_strength", 1.2))
    body = principled(tree, p, Base_Color=rgba(p.get("base_color", (0.85, 0.97, 1.0))), Roughness=p.get("roughness", 0.08),
                      Transmission_Weight=p.get("transmission", 0.35))
    clear = tree.n("ShaderNodeBsdfTransparent")["BSDF"]
    return tree.n("ShaderNodeMixShader", opacity, clear, add(tree, body, glow))["Shader"], dict(DITHERED_SHADOWED)


def aquarium_depth_surface(tree: Tree, p):
    position = S.tex_coord(tree)
    factor = tree.map_range(tree.sep(position)[2], p.get("bottom", 0.0), p.get("top", 14.0), 0.0, 1.0)
    color = tree.mix(factor, rgba(p["bottom_color"]), rgba(p["top_color"]), data_type="RGBA")
    cells = tree.n("ShaderNodeTexVoronoi", props={"feature": "SMOOTH_F1", "voronoi_dimensions": "3D"}, Vector=position,
                   Scale=p.get("caustic_scale", 0.9), Smoothness=0.6)["Distance"]
    caustic = tree.map_range(cells, 0.0, 0.35, p.get("caustic_strength", 0.6), 0.0)
    return emission(tree, color, caustic + p.get("strength", 1.0)), {}


def tiled_stone_surface(tree: Tree, p):
    position = S.tex_coord(tree)
    tiles = tree.n("ShaderNodeMapping", Vector=position, Scale=(1.0 / p.get("tile_size", 1.2),) * 3).o
    grid = tree.n("ShaderNodeTexBrick", Vector=tiles, Scale=1.0, Mortar_Size=p.get("grout", 0.012), Mortar_Smooth=0.1,
                  Brick_Width=1.0, Row_Height=1.0, Color1=rgba(p["base_color"]), Color2=rgba(p["alternate_color"]),
                  Mortar=rgba(p["grout_color"]), props={"offset": 0.0, "squash": 1.0})
    variation = S.noise(tree, position, p.get("variation_scale", 0.35), 3.0)["Fac"]
    color = tree.mix(variation * p.get("variation", 0.25), grid["Color"], rgba(p["variation_color"]), data_type="RGBA")
    roughness = tree.map_range(grid["Fac"], 0.0, 1.0, p.get("roughness", 0.25), p.get("grout_roughness", 0.6))
    relief = tree.n("ShaderNodeBump", Strength=0.25, Distance=0.004, Height=1.0 - grid["Fac"])["Normal"]
    return principled(tree, p, Base_Color=color, Roughness=roughness, Normal=relief), {}


def foliage_surface(tree: Tree, p):
    variation = tree.math("FRACT", tree.n("ShaderNodeObjectInfo")["Random"] + attribute(tree, "leaf_variation"))
    color = tree.mix(variation, rgba(p["base_color"]), rgba(p["alternate_color"]), data_type="RGBA")
    surface = principled(tree, p, Base_Color=color, Roughness=p.get("roughness", 0.55))
    glow = tree.n("ShaderNodeBsdfTranslucent", Color=tree.mix(0.5, color, rgba(p["translucent_color"]), data_type="RGBA"))["BSDF"]
    return tree.n("ShaderNodeMixShader", p.get("translucency", 0.3), surface, glow)["Shader"], {}


def caustic_floor_surface(tree: Tree, p):
    position = S.tex_coord(tree)
    warped = position + S.noise(tree, position, 0.4, 2.0)["Color"] * p.get("warp", 0.6)
    cells = tree.n("ShaderNodeTexVoronoi", props={"feature": "DISTANCE_TO_EDGE", "voronoi_dimensions": "3D"}, Vector=warped,
                   Scale=p.get("caustic_scale", 0.7))["Distance"]
    lines = tree.map_range(cells, 0.0, p.get("line_width", 0.06), 1.0, 0.0)
    color = tree.mix(lines, rgba(p["base_color"]), rgba(p["caustic_color"]), data_type="RGBA")
    glow = lines * p.get("caustic_emission", 1.5) + p.get("base_glow", 0.0)
    return principled(tree, p, Base_Color=color, Emission_Color=color, Emission_Strength=glow), {}


def storefront_surface(tree: Tree, p):
    cells = tree.n("ShaderNodeMapping", Vector=S.tex_coord(tree), Scale=tuple(p.get("cell_stretch", (0.35, 0.35, 0.12)))).o
    cells = tree.n("ShaderNodeTexVoronoi", props={"feature": "F1", "voronoi_dimensions": "3D"}, Vector=cells, Scale=1.0, Randomness=1.0)["Color"]
    pick = tree.n("ShaderNodeSeparateColor", Color=cells)["Red"]
    interior = emission(tree, ramp(tree, pick, p["interior_stops"], "CONSTANT"), p.get("interior_strength", 1.5))
    pane = tree.n("ShaderNodeBsdfGlossy", Color=(1.0, 1.0, 1.0, 1.0), Roughness=p.get("roughness", 0.04))["BSDF"]
    fresnel = tree.n("ShaderNodeFresnel", IOR=p.get("ior", 1.5))["Fac"]
    return tree.n("ShaderNodeMixShader", fresnel, interior, pane)["Shader"], {}


SHADERS = {
    "principled": principled_surface,
    "emission": emission_surface,
    "thin_glass": thin_glass_surface,
    "refractive": refractive_surface,
    "crystal": crystal_surface,
    "iridescent_glass": iridescent_glass_surface,
    "waterfall": waterfall_surface,
    "aquarium_depth": aquarium_depth_surface,
    "tiled_stone": tiled_stone_surface,
    "foliage": foliage_surface,
    "caustic_floor": caustic_floor_surface,
    "storefront": storefront_surface,
}


def build(name):
    definition = {**MATERIALS[name], **PARAMS.get(name, {})}
    shader = SHADERS[definition["shader"]]
    settings = {}

    def tree_builder(tree: Tree):
        outputs, wanted = shader(tree, definition)
        settings.update(wanted)
        return outputs
    material = S.material(name, tree_builder)
    for key, value in settings.items():
        setattr(material, key, value)
    material.diffuse_color = rgba(definition.get("viewport_color", definition.get("base_color", definition.get("color", (0.8, 0.8, 0.8)))))
    return material


for _name in MATERIALS:
    register(_name)(lambda name=_name: build(name))
