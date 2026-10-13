GROUP_NAME = "Fan Coral"
CATEGORY = "Plants"
DESCRIPTION = "Branching sea-fan coral grown by recursive forking in the local XZ plane with slight depth jitter; branches thin toward glowing polyp tips."


def fork(b, child, length, spread, depth_jitter, seed, count):
    stem = b.node("GeometryNodeCurvePrimitiveLine", props={"mode": "POINTS"}, Start=(0.0, 0.0, 0.0), End=b.combine(0.0, 0.0, length)).out
    stem = b.node("GeometryNodeResampleCurve", Curve=stem, Mode="Count", Count=6).out
    wobble = b.node("ShaderNodeTexNoise", props={"noise_dimensions": "4D"}, Vector=b.position(), W=b.math("MULTIPLY", seed, 2.3), Scale=1.2, Detail=1.0)["Color"]
    stem = b.set_position(stem, offset=b.vmath("MULTIPLY", b.vmath("SUBTRACT", wobble, (0.5, 0.5, 0.5)), b.combine(b.math("MULTIPLY", length, 0.25), b.math("MULTIPLY", length, depth_jitter), 0.0)))
    tips = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=count).out
    tips = b.set_position(tips, position=b.combine(0.0, 0.0, length))
    index = b.index()
    fan = b.map_range(index, 0.0, b.math("MAXIMUM", b.math("SUBTRACT", count, 1.0), 1.0), b.math("MULTIPLY", spread, -1.0), spread)
    jitter = b.random(-0.15, 0.15, seed, identifier=index)
    rotation = b.euler(b.combine(b.random(-0.25, 0.25, b.math("ADD", seed, 3), identifier=index), b.math("ADD", fan, jitter), 0.0))
    children = b.instance(tips, child, rotation=rotation, scale=b.random(0.62, 0.8, b.math("ADD", seed, 5), identifier=index))
    return stem, children


def build(b, context):
    height = b.input("Height", "FLOAT", 2.0, 0.05, 50.0, "DISTANCE")
    spread = b.input("Spread", "FLOAT", 0.55, 0.0, 1.5, "ANGLE")
    thickness = b.input("Thickness", "FLOAT", 0.045, 0.001, 2.0, "DISTANCE")
    depth_jitter = b.input("Depth Jitter", "FLOAT", 0.25, 0.0, 2.0)
    seed = b.input("Seed", "INT", 2, 0, 100000)
    body = b.input("Coral", "MATERIAL", context.material("Coral Violet"))
    polyp = b.input("Polyps", "MATERIAL", context.material("Coral Glow"))

    section = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=6, Radius=1.0)["Curve"]
    bead = b.set_material(b.node("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=1).out, polyp)

    level_length = b.math("MULTIPLY", height, 0.36)
    element = b.transform(bead, scale=b.math("MULTIPLY", thickness, 1.8))
    for level in range(4):
        stem, children = fork(b, element, level_length, spread, depth_jitter, b.math("ADD", seed, level * 17), 3 if level < 3 else 2)
        radius = b.math("MULTIPLY", thickness, 1.0 + level * 0.45)
        shaped = b.node("GeometryNodeSetCurveRadius", Curve=stem, Radius=radius).out
        stem_mesh = b.set_material(b.curve_to_mesh_by_radius(shaped, section, fill_caps=True), body)
        element = b.realize(b.join(stem_mesh, children))
    b.output("Geometry", "GEOMETRY", element)
