import math

import bpy

from .gn import TreeBuilder


def _color(values):
    values = tuple(values)
    return values if len(values) == 4 else (*values, 1.0)


def sun_direction(settings):
    elevation = math.radians(settings["elevation"])
    azimuth = math.radians(settings["azimuth"])
    return (math.sin(azimuth) * math.cos(elevation), math.cos(azimuth) * math.cos(elevation), math.sin(elevation))


def build_sun(settings, collection):
    data = bpy.data.lights.new("Sun", "SUN")
    data.energy = settings["strength"]
    data.angle = math.radians(settings.get("angle_degrees", 1.5))
    data.color = settings.get("color", (1.0, 0.97, 0.92))
    sun = bpy.data.objects.new("Sun", data)
    tilt = math.radians(90.0 - settings["elevation"])
    sun.rotation_euler = (tilt, 0.0, -math.radians(settings["azimuth"] + 180.0))
    collection.objects.link(sun)
    return sun


def build_world(settings, sun_settings):
    world = bpy.data.worlds.new("Rain Garden Sky")
    world.use_nodes = True
    builder = TreeBuilder.shader(world)
    direction = builder.vmath("NORMALIZE", builder.node("ShaderNodeTexCoord")["Generated"])
    height = builder.separate(direction)[2]
    gradient = builder.map_range(height, settings.get("horizon_height", -0.05), settings.get("zenith_height", 0.75), 0.0, 1.0, interpolation="SMOOTHSTEP")
    sky = builder.mix(gradient, _color(settings["horizon_color"]), _color(settings["zenith_color"]), data_type="RGBA")
    alignment = builder.math("MAXIMUM", builder.vmath("DOT_PRODUCT", direction, sun_direction(sun_settings)), 0.0)
    glow = builder.math("MULTIPLY", builder.math("POWER", alignment, settings.get("sun_glow_power", 12.0)), settings.get("sun_glow_strength", 1.5))
    halo = builder.math("MULTIPLY", builder.math("POWER", alignment, settings.get("sun_halo_power", 2.5)), settings.get("sun_halo_strength", 0.4))
    sky = builder.mix(builder.math("ADD", glow, halo, clamp=True), sky, _color(settings.get("sun_glow_color", (1.0, 0.98, 0.94))), data_type="RGBA")
    separated = builder.separate(direction)
    dome = builder.combine(builder.math("DIVIDE", separated[0], builder.math("ADD", separated[2], 0.12)), builder.math("DIVIDE", separated[1], builder.math("ADD", separated[2], 0.12)), 0.0)
    cloud_noise = builder.node("ShaderNodeTexNoise", props={"noise_dimensions": "3D"}, Vector=dome, Scale=settings.get("cloud_scale", 1.6), Detail=6.0, Roughness=0.55)["Factor"]
    cloud = builder.map_range(cloud_noise, settings.get("cloud_threshold", 0.58), settings.get("cloud_threshold", 0.58) + settings.get("cloud_softness", 0.12), 0.0, settings.get("cloud_opacity", 0.8))
    cloud = builder.math("MULTIPLY", cloud, builder.map_range(height, 0.02, 0.25, 0.0, 1.0))
    sky = builder.mix(cloud, sky, _color(settings.get("cloud_color", (1.0, 1.0, 1.0))), data_type="RGBA")
    below = builder.map_range(height, 0.0, -0.08, 0.0, 1.0)
    sky = builder.mix(below, sky, _color(settings.get("ground_color", (0.55, 0.6, 0.66))), data_type="RGBA")
    camera_ray = builder.node("ShaderNodeLightPath")["Is Camera Ray"]
    strength = builder.mix(camera_ray, settings.get("strength", 1.5), settings.get("camera_strength", settings.get("strength", 1.5)))
    background = builder.node("ShaderNodeBackground", Color=sky, Strength=strength).out
    output = builder.node("ShaderNodeOutputWorld")
    builder.link(background, output.node.inputs["Surface"])
    builder.arrange()
    return world


def build_compositor(settings):
    tree = bpy.data.node_groups.new("Rain Garden Look", "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out="INPUT", socket_type="NodeSocketColor")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    builder = TreeBuilder(tree)
    group_input = tree.nodes.new("NodeGroupInput")
    group_output = tree.nodes.new("NodeGroupOutput")
    builder.group_input = group_input
    builder.group_output = group_output
    image = group_input.outputs[0]
    for step in settings.get("chain", []):
        kind = step["node"]
        handle = builder.node(kind, **{key: (tuple(value) if isinstance(value, list) else value) for key, value in step.get("inputs", {}).items()})
        for key, value in step.get("props", {}).items():
            setattr(handle.node, key, value)
        builder.link(image, handle.node.inputs[0])
        image = handle.node.outputs[step.get("output", 0)]
    builder.link(image, group_output.inputs[0])
    builder.arrange()
    return tree


def apply_look(layout, collection):
    scene = bpy.context.scene
    sun_settings = layout["sun"]
    build_sun(sun_settings, collection)
    scene.world = build_world(layout["sky"], sun_settings)
    color = layout.get("color_management", {})
    scene.view_settings.view_transform = color.get("view_transform", "AgX")
    scene.view_settings.look = color.get("look", "None")
    scene.view_settings.exposure = color.get("exposure", 0.0)
    scene.view_settings.gamma = color.get("gamma", 1.0)
    compositor = layout.get("compositor")
    if compositor:
        effect = scene.compositor_effects.new("Rain Garden Look")
        effect.node_group = build_compositor(compositor)
        effect.enable_for_render = True
        scene.render.use_compositing = True
