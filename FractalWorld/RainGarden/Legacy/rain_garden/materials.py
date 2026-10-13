import bpy

from .gn import TreeBuilder


def _color(values):
    values = tuple(values)
    return values if len(values) == 4 else (*values, 1.0)


def _principled(builder, parameters, **overrides):
    inputs = dict(
        Base_Color=_color(parameters.get("base_color", (0.8, 0.8, 0.8))),
        Metallic=parameters.get("metallic", 0.0),
        Roughness=parameters.get("roughness", 0.5),
        IOR=parameters.get("ior", 1.5),
        Alpha=parameters.get("alpha", 1.0),
        Transmission_Weight=parameters.get("transmission", 0.0),
        Coat_Weight=parameters.get("coat", 0.0),
        Coat_Roughness=parameters.get("coat_roughness", 0.03),
        Specular_IOR_Level=parameters.get("specular", 0.5),
        Emission_Color=_color(parameters.get("emission_color", (1.0, 1.0, 1.0))),
        Emission_Strength=parameters.get("emission_strength", 0.0),
        Subsurface_Weight=parameters.get("subsurface", 0.0),
        Sheen_Weight=parameters.get("sheen", 0.0),
    )
    inputs.update(overrides)
    shader = builder.node("ShaderNodeBsdfPrincipled", **inputs)
    if parameters.get("thin_wall"):
        shader.node.inputs["Thin Wall"].default_value = True
    if "thin_film_thickness" in parameters:
        shader.node.inputs["Thin Film Thickness"].default_value = parameters["thin_film_thickness"]
        shader.node.inputs["Thin Film IOR"].default_value = parameters.get("thin_film_ior", 1.33)
    return shader.out


def _shadow_transparent(builder, surface, parameters):
    if not parameters.get("shadow_transparent"):
        return surface
    path = builder.node("ShaderNodeLightPath")
    transparent = builder.node("ShaderNodeBsdfTransparent", Color=_color(parameters.get("shadow_tint", (1.0, 1.0, 1.0)))).out
    return builder.node("ShaderNodeMixShader", path["Is Shadow Ray"], surface, transparent).out


def _surface_principled(builder, parameters):
    return _shadow_transparent(builder, _principled(builder, parameters), parameters), None


def _surface_glass(builder, parameters):
    glass = builder.node("ShaderNodeBsdfGlass", Color=_color(parameters.get("color", (1.0, 1.0, 1.0))), Roughness=parameters.get("roughness", 0.0), IOR=parameters.get("ior", 1.45)).out
    return _shadow_transparent(builder, glass, parameters), None


def _surface_emission(builder, parameters):
    return builder.node("ShaderNodeEmission", Color=_color(parameters.get("color", (1.0, 1.0, 1.0))), Strength=parameters.get("strength", 1.0)).out, None


def _ripple_normal(builder, parameters):
    coordinates = builder.node("ShaderNodeTexCoord")["Object"]
    stretched = builder.node("ShaderNodeMapping", Vector=coordinates, Scale=tuple(parameters.get("ripple_stretch", (1.0, 1.0, 1.0)))).out
    noise = builder.node("ShaderNodeTexNoise", props={"noise_dimensions": "3D"}, Vector=stretched, Scale=parameters.get("ripple_scale", 1.6), Detail=parameters.get("ripple_detail", 6.0), Roughness=0.55)["Factor"]
    return builder.node("ShaderNodeBump", Strength=parameters.get("ripple_strength", 0.12), Distance=0.02, Height=noise).out


def _surface_water(builder, parameters):
    normal = _ripple_normal(builder, parameters)
    surface = _principled(builder, parameters, Normal=normal, Transmission_Weight=1.0, IOR=parameters.get("ior", 1.333), Roughness=parameters.get("roughness", 0.015), Specular_Tint=_color(parameters.get("reflection_tint", (1.0, 1.0, 1.0))))
    if parameters.get("surface_glow", 0.0) > 0.0:
        sheen = builder.node("ShaderNodeEmission", Color=_color(parameters.get("glow_color", (0.2, 0.8, 1.0))), Strength=parameters["surface_glow"]).out
        surface = builder.node("ShaderNodeAddShader", surface, sheen).out
    surface = _shadow_transparent(builder, surface, parameters)
    volume = builder.node(
        "ShaderNodeVolumePrincipled",
        Color=(0.0, 0.0, 0.0, 1.0),
        Density=parameters.get("absorption_density", 0.12),
        Absorption_Color=_color(parameters.get("absorption_color", (0.25, 0.8, 0.95))),
        Emission_Color=_color(parameters.get("glow_color", (0.2, 0.8, 1.0))),
        Emission_Strength=parameters.get("glow_strength", 0.0),
    ).out
    return surface, volume


def _surface_waterfall(builder, parameters):
    attribute = builder.node("ShaderNodeAttribute", props={"attribute_type": "GEOMETRY", "attribute_name": parameters.get("uv_attribute", "fall_uv")})["Vector"]
    stretched = builder.node("ShaderNodeMapping", Vector=attribute, Scale=tuple(parameters.get("streak_scale", (18.0, 0.6, 1.0)))).out
    streaks = builder.node("ShaderNodeTexNoise", props={"noise_dimensions": "3D"}, Vector=stretched, Scale=1.0, Detail=8.0, Roughness=0.62, Distortion=0.3)["Factor"]
    streaks = builder.map_range(streaks, parameters.get("streak_low", 0.35), parameters.get("streak_high", 0.75), 0.0, 1.0)
    edge = builder.node("ShaderNodeLayerWeight", Blend=parameters.get("edge_blend", 0.35))["Facing"]
    opacity = builder.math("MULTIPLY", builder.math("ADD", builder.math("MULTIPLY", streaks, parameters.get("streak_opacity", 0.75)), builder.math("MULTIPLY", edge, parameters.get("edge_opacity", 0.45))), parameters.get("opacity", 1.0), clamp=True)
    glow = builder.node("ShaderNodeEmission", Color=_color(parameters.get("glow_color", (0.75, 0.95, 1.0))), Strength=builder.math("MULTIPLY", streaks, parameters.get("glow_strength", 1.2))).out
    body = _principled(builder, parameters, Base_Color=_color(parameters.get("base_color", (0.85, 0.97, 1.0))), Roughness=parameters.get("roughness", 0.08), Transmission_Weight=parameters.get("transmission", 0.35))
    lit = builder.node("ShaderNodeAddShader", body, glow).out
    transparent = builder.node("ShaderNodeBsdfTransparent").out
    return builder.node("ShaderNodeMixShader", opacity, transparent, lit).out, None


def _surface_aquarium_depth(builder, parameters):
    position = builder.node("ShaderNodeTexCoord")["Object"]
    height = builder.separate(position)[2]
    factor = builder.map_range(height, parameters.get("bottom", 0.0), parameters.get("top", 14.0), 0.0, 1.0)
    color = builder.mix(factor, _color(parameters.get("bottom_color", (0.01, 0.02, 0.08))), _color(parameters.get("top_color", (0.05, 0.18, 0.45))), data_type="RGBA")
    caustic = builder.node("ShaderNodeTexVoronoi", props={"feature": "SMOOTH_F1", "voronoi_dimensions": "3D"}, Vector=position, Scale=parameters.get("caustic_scale", 0.9), Smoothness=0.6)["Distance"]
    caustic = builder.map_range(caustic, 0.0, 0.35, parameters.get("caustic_strength", 0.6), 0.0)
    strength = builder.math("ADD", parameters.get("strength", 1.0), caustic)
    return builder.node("ShaderNodeEmission", Color=color, Strength=strength).out, None


def _surface_tiled_stone(builder, parameters):
    position = builder.node("ShaderNodeTexCoord")["Object"]
    scaled = builder.node("ShaderNodeMapping", Vector=position, Scale=(1.0 / parameters.get("tile_size", 1.2),) * 3).out
    grid = builder.node("ShaderNodeTexBrick", Vector=scaled, Scale=1.0, Mortar_Size=parameters.get("grout", 0.012), Mortar_Smooth=0.1, Brick_Width=1.0, Row_Height=1.0, Color1=_color(parameters.get("base_color", (0.82, 0.85, 0.9))), Color2=_color(parameters.get("alternate_color", (0.78, 0.82, 0.88))), Mortar=_color(parameters.get("grout_color", (0.55, 0.6, 0.68))))
    grid.node.offset = 0.0
    grid.node.squash = 1.0
    variation = builder.node("ShaderNodeTexNoise", Vector=position, Scale=parameters.get("variation_scale", 0.35), Detail=3.0)["Factor"]
    color = builder.mix(builder.math("MULTIPLY", variation, parameters.get("variation", 0.25)), grid["Color"], _color(parameters.get("variation_color", (0.9, 0.93, 0.98))), data_type="RGBA")
    roughness = builder.map_range(grid["Factor"], 0.0, 1.0, parameters.get("roughness", 0.25), parameters.get("grout_roughness", 0.6))
    bump = builder.node("ShaderNodeBump", Strength=0.25, Distance=0.004, Height=builder.math("SUBTRACT", 1.0, grid["Factor"])).out
    surface = _principled(builder, parameters, Base_Color=color, Roughness=roughness, Normal=bump)
    return surface, None


def _surface_crystal(builder, parameters):
    tint = builder.node("ShaderNodeAttribute", props={"attribute_type": "GEOMETRY", "attribute_name": parameters.get("tint_attribute", "tint")})["Factor"]
    ramp = builder.node("ShaderNodeValToRGB", Factor=tint)
    elements = ramp.node.color_ramp.elements
    stops = parameters.get("tint_stops", [[0.0, [0.7, 0.8, 1.0]], [1.0, [0.85, 0.7, 1.0]]])
    elements[0].position = stops[0][0]
    elements[0].color = _color(stops[0][1])
    elements[1].position = stops[-1][0]
    elements[1].color = _color(stops[-1][1])
    for position, color in stops[1:-1]:
        element = elements.new(position)
        element.color = _color(color)
    facing = builder.node("ShaderNodeLayerWeight", Blend=0.4)["Facing"]
    surface = _principled(builder, parameters, Base_Color=ramp["Color"], Transmission_Weight=parameters.get("transmission", 0.85), Roughness=parameters.get("roughness", 0.04), IOR=parameters.get("ior", 1.5), Emission_Color=ramp["Color"], Emission_Strength=builder.math("MULTIPLY", facing, parameters.get("inner_glow", 0.35)))
    return _shadow_transparent(builder, surface, parameters), None


def _surface_foliage(builder, parameters):
    random = builder.node("ShaderNodeObjectInfo")["Random"]
    variation_attribute = builder.node("ShaderNodeAttribute", props={"attribute_type": "GEOMETRY", "attribute_name": "leaf_variation"})["Factor"]
    variation = builder.math("FRACT", builder.math("ADD", random, variation_attribute))
    color = builder.mix(variation, _color(parameters.get("base_color", (0.08, 0.22, 0.12))), _color(parameters.get("alternate_color", (0.2, 0.38, 0.18))), data_type="RGBA")
    surface = _principled(builder, parameters, Base_Color=color, Roughness=parameters.get("roughness", 0.55), Subsurface_Weight=0.0)
    translucent = builder.node("ShaderNodeBsdfTranslucent", Color=builder.mix(0.5, color, _color(parameters.get("translucent_color", (0.35, 0.6, 0.2))), data_type="RGBA")).out
    mixed = builder.node("ShaderNodeMixShader", parameters.get("translucency", 0.3), surface, translucent).out
    alpha_name = parameters.get("alpha_attribute")
    if alpha_name:
        alpha = builder.node("ShaderNodeAttribute", props={"attribute_type": "GEOMETRY", "attribute_name": alpha_name})["Factor"]
        transparent = builder.node("ShaderNodeBsdfTransparent").out
        mixed = builder.node("ShaderNodeMixShader", alpha, transparent, mixed).out
    return mixed, None


def _surface_caustic_floor(builder, parameters):
    position = builder.node("ShaderNodeTexCoord")["Object"]
    warp = builder.node("ShaderNodeTexNoise", Vector=position, Scale=0.4, Detail=2.0)["Color"]
    warped = builder.vmath("ADD", position, builder.vmath("SCALE", warp, parameters.get("warp", 0.6)))
    cells = builder.node("ShaderNodeTexVoronoi", props={"feature": "DISTANCE_TO_EDGE", "voronoi_dimensions": "3D"}, Vector=warped, Scale=parameters.get("caustic_scale", 0.7))["Distance"]
    lines = builder.map_range(cells, 0.0, parameters.get("line_width", 0.06), 1.0, 0.0)
    color = builder.mix(lines, _color(parameters.get("base_color", (0.05, 0.45, 0.75))), _color(parameters.get("caustic_color", (0.75, 0.97, 1.0))), data_type="RGBA")
    glow = builder.math("ADD", builder.math("MULTIPLY", lines, parameters.get("caustic_emission", 1.5)), parameters.get("base_glow", 0.0))
    surface = _principled(builder, parameters, Base_Color=color, Emission_Color=color, Emission_Strength=glow)
    return surface, None


def _surface_iridescent_glass(builder, parameters):
    position = builder.node("ShaderNodeTexCoord")["Object"]
    bands = builder.node("ShaderNodeTexNoise", props={"noise_dimensions": "3D"}, Vector=position, Scale=parameters.get("film_scale", 0.35), Detail=2.0, Distortion=0.8)["Factor"]
    thickness = builder.map_range(bands, 0.25, 0.75, parameters.get("film_min", 250.0), parameters.get("film_max", 900.0))
    surface = _principled(builder, parameters, Thin_Film_Thickness=thickness, Thin_Film_IOR=parameters.get("thin_film_ior", 1.5))
    facing = builder.node("ShaderNodeLayerWeight", Blend=parameters.get("sheen_blend", 0.45))["Facing"]
    hue = builder.math("FRACT", builder.math("ADD", builder.math("MULTIPLY", bands, parameters.get("sheen_band_scale", 1.6)), builder.math("MULTIPLY", facing, parameters.get("sheen_facing_scale", 0.9))))
    ramp = builder.node("ShaderNodeValToRGB", Factor=hue)
    elements = ramp.node.color_ramp.elements
    stops = parameters.get("sheen_stops", [[0.0, [0.3, 0.9, 1.0]], [0.3, [0.35, 0.45, 1.0]], [0.55, [0.8, 0.4, 1.0]], [0.75, [1.0, 0.55, 0.8]], [1.0, [0.3, 0.9, 1.0]]])
    elements[0].position = stops[0][0]
    elements[0].color = _color(stops[0][1])
    elements[1].position = stops[-1][0]
    elements[1].color = _color(stops[-1][1])
    for position_value, color in stops[1:-1]:
        element = elements.new(position_value)
        element.color = _color(color)
    sheen = builder.node("ShaderNodeEmission", Color=ramp["Color"], Strength=builder.math("MULTIPLY", facing, parameters.get("sheen_strength", 0.5))).out
    surface = builder.node("ShaderNodeAddShader", surface, sheen).out
    return _shadow_transparent(builder, surface, parameters), None


def _surface_storefront(builder, parameters):
    position = builder.node("ShaderNodeTexCoord")["Object"]
    stretched = builder.node("ShaderNodeMapping", Vector=position, Scale=tuple(parameters.get("cell_stretch", (0.35, 0.35, 0.12)))).out
    cells = builder.node("ShaderNodeTexVoronoi", props={"feature": "F1", "voronoi_dimensions": "3D"}, Vector=stretched, Scale=1.0, Randomness=1.0)["Color"]
    ramp = builder.node("ShaderNodeValToRGB", Factor=builder.node("ShaderNodeSeparateColor", Color=cells)["Red"])
    elements = ramp.node.color_ramp.elements
    stops = parameters["interior_stops"]
    elements[0].position = stops[0][0]
    elements[0].color = _color(stops[0][1])
    elements[1].position = stops[-1][0]
    elements[1].color = _color(stops[-1][1])
    for position_value, color in stops[1:-1]:
        element = elements.new(position_value)
        element.color = _color(color)
    ramp.node.color_ramp.interpolation = "CONSTANT"
    glow = builder.node("ShaderNodeEmission", Color=ramp["Color"], Strength=parameters.get("interior_strength", 1.5)).out
    glass = builder.node("ShaderNodeBsdfGlossy", Color=(1.0, 1.0, 1.0, 1.0), Roughness=parameters.get("roughness", 0.04)).out
    fresnel = builder.node("ShaderNodeFresnel", IOR=parameters.get("ior", 1.5)).out
    return builder.node("ShaderNodeMixShader", fresnel, glow, glass).out, None


def _surface_clear_glass(builder, parameters):
    transparent = builder.node("ShaderNodeBsdfTransparent", Color=_color(parameters.get("tint", (0.95, 0.99, 1.0)))).out
    glossy = builder.node("ShaderNodeBsdfAnisotropic", Color=_color(parameters.get("reflection_color", (1.0, 1.0, 1.0))), Roughness=parameters.get("roughness", 0.02)).out
    fresnel = builder.node("ShaderNodeLayerWeight", Blend=parameters.get("reflection_blend", 0.12))["Fresnel"]
    amount = builder.math("ADD", builder.math("MULTIPLY", fresnel, parameters.get("reflectivity", 0.9)), parameters.get("base_reflection", 0.04), clamp=True)
    return builder.node("ShaderNodeMixShader", amount, transparent, glossy).out, None


SHADERS = {
    "clear_glass": _surface_clear_glass,
    "storefront": _surface_storefront,
    "iridescent_glass": _surface_iridescent_glass,
    "principled": _surface_principled,
    "glass": _surface_glass,
    "emission": _surface_emission,
    "water": _surface_water,
    "waterfall": _surface_waterfall,
    "aquarium_depth": _surface_aquarium_depth,
    "tiled_stone": _surface_tiled_stone,
    "crystal": _surface_crystal,
    "foliage": _surface_foliage,
    "caustic_floor": _surface_caustic_floor,
}


def build_material(name, parameters):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    if material.node_tree is None:
        material.use_nodes = True
    builder = TreeBuilder.shader(material)
    surface, volume = SHADERS[parameters["shader"]](builder, parameters)
    output = builder.node("ShaderNodeOutputMaterial")
    builder.link(surface, output.node.inputs["Surface"])
    if volume is not None:
        builder.link(volume, output.node.inputs["Volume"])
    builder.arrange()
    viewport = parameters.get("viewport_color", parameters.get("base_color", parameters.get("color", (0.8, 0.8, 0.8))))
    material.diffuse_color = (*viewport[:3], 1.0)
    return material


class MaterialLibrary:
    def __init__(self, palette):
        self.palette = palette
        self.cache = {}

    def __getitem__(self, name):
        if name not in self.cache:
            self.cache[name] = build_material(name, self.palette[name])
        return self.cache[name]
