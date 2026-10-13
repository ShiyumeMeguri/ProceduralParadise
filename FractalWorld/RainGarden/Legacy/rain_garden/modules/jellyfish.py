from rain_garden.shapes import lathe

GROUP_NAME = "Jellyfish"
CATEGORY = "Creatures"
DESCRIPTION = "Translucent jellyfish: ribbed bell with a scalloped rim, frilly oral arms and long trailing tentacles drifting downward from the origin."


def build(b, context):
    size = b.input("Size", "FLOAT", 0.6, 0.01, 20.0, "DISTANCE")
    tentacles = b.input("Tentacles", "INT", 12, 0, 200)
    tentacle_length = b.input("Tentacle Length", "FLOAT", 2.2, 0.0, 50.0, "DISTANCE")
    sway = b.input("Sway", "FLOAT", 0.25, 0.0, 5.0)
    seed = b.input("Seed", "INT", 3, 0, 100000)
    material = b.input("Material", "MATERIAL", context.material("Jelly Glow"))

    bell = lathe(b, [(0.0, 0.0, 0.62), (0.3, 0.0, 0.59), (0.52, 0.0, 0.45), (0.64, 0.0, 0.2), (0.68, 0.0, 0.02), (0.6, 0.0, 0.0), (0.4, 0.0, 0.06), (0.0, 0.0, 0.1)], 48)
    angle = b.math("ARCTAN2", b.position().y, b.position().x)
    ribs = b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", angle, 16.0)), 0.025)
    bell = b.set_position(bell, offset=b.vmath("SCALE", b.normal(), ribs))
    bell = b.smooth(b.transform(bell, scale=size))

    ring = b.node("GeometryNodeMeshCircle", Vertices=tentacles, Radius=b.math("MULTIPLY", size, 0.55)).out
    anchors = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=ring).out
    strand = b.node("GeometryNodeCurvePrimitiveLine", props={"mode": "POINTS"}, Start=(0.0, 0.0, 0.0), End=(0.0, 0.0, -1.0)).out
    strand = b.node("GeometryNodeResampleCurve", Curve=strand, Mode="Count", Count=24).out
    wave = b.node("ShaderNodeTexNoise", props={"noise_dimensions": "4D"}, Vector=b.position(), W=b.math("MULTIPLY", seed, 1.9), Scale=2.0, Detail=1.0)["Color"]
    strand = b.set_position(strand, offset=b.vmath("MULTIPLY", b.vmath("SUBTRACT", wave, (0.5, 0.5, 0.5)), b.combine(sway, sway, 0.0)))
    strand = b.node("GeometryNodeSetCurveRadius", Curve=strand, Radius=b.map_range(b.node("GeometryNodeSplineParameter")["Factor"], 0.0, 1.0, 0.012, 0.002)).out
    section = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=4, Radius=1.0)["Curve"]
    strand_mesh = b.curve_to_mesh_by_radius(strand, section)
    identifier = b.index()
    lengths = b.math("MULTIPLY", tentacle_length, b.random(0.6, 1.2, seed, identifier=identifier))
    tendrils = b.realize(b.instance(anchors, strand_mesh, rotation=b.euler(b.combine(0.0, 0.0, b.random(0.0, 6.28, b.math("ADD", seed, 1), identifier=identifier))), scale=b.combine(1.0, 1.0, lengths)))

    arm = b.node("GeometryNodeMeshCone", Vertices=5, Side_Segments=6, Radius_Top=0.0, Radius_Bottom=1.0, Depth=1.0)["Mesh"]
    arm = b.transform(arm, translation=(0.0, 0.0, 0.5))
    arm_ring = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=b.node("GeometryNodeMeshCircle", Vertices=4, Radius=b.math("MULTIPLY", size, 0.12)).out).out
    arm_size = b.math("MULTIPLY", size, 0.09)
    arms = b.realize(b.instance(arm_ring, arm, rotation=(3.14159, 0.0, 0.0), scale=b.combine(arm_size, arm_size, b.math("MULTIPLY", size, 1.4))))
    b.output("Geometry", "GEOMETRY", b.set_material(b.join(bell, tendrils, b.smooth(arms)), material))
