GROUP_NAME = "Branching Tree"
CATEGORY = "Plants"
DESCRIPTION = "Self-similar tree grown by nested instancing: foliage pads on twigs, twigs along limbs, limbs along a curving trunk. Pads are flattened clouds of small leaf clumps; limbs can spread level (cloud-pruned) or rise (round crown)."


def tapered_tube(b, curve, base_radius, tip_radius, resolution=8):
    parameter = b.node("GeometryNodeSplineParameter")["Factor"]
    radius = b.map_range(parameter, 0.0, 1.0, base_radius, tip_radius)
    shaped = b.node("GeometryNodeSetCurveRadius", Curve=curve, Radius=radius).out
    section = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=resolution, Radius=1.0)["Curve"]
    return b.curve_to_mesh_by_radius(shaped, section, fill_caps=True)


def bent_limb(b, length, rise, droop, curl, seed):
    bezier = b.node("GeometryNodeCurveQuadraticBezier", Resolution=10, Start=(0.0, 0.0, 0.0), Middle=b.combine(b.math("MULTIPLY", length, 0.5), b.math("MULTIPLY", curl, length), b.math("MULTIPLY", rise, length)), End=b.combine(length, 0.0, b.math("MULTIPLY", b.math("SUBTRACT", rise, droop), length))).out
    wobble = b.node("ShaderNodeTexNoise", props={"noise_dimensions": "4D"}, Vector=b.position(), W=b.math("MULTIPLY", seed, 3.1), Scale=0.8, Detail=1.0)["Color"]
    offset = b.vmath("SCALE", b.vmath("SUBTRACT", wobble, (0.5, 0.5, 0.5)), b.math("MULTIPLY", length, 0.12))
    return b.set_position(bezier, offset=offset)


def foliage_pad(b, width, height, density, clump, seed, material):
    shell = b.node("GeometryNodeMeshUVSphere", Segments=24, Rings=12, Radius=1.0).out
    shell = b.transform(shell, scale=b.combine(width, width, height))
    lumps = b.node("ShaderNodeTexNoise", props={"noise_dimensions": "4D"}, Vector=b.position(), W=b.math("MULTIPLY", seed, 1.7), Scale=b.math("DIVIDE", 1.4, width), Detail=2.0)["Factor"]
    shell = b.set_position(shell, offset=b.vmath("SCALE", b.normal(), b.math("MULTIPLY", b.math("SUBTRACT", lumps, 0.5), b.math("MULTIPLY", width, 0.55))))
    points = b.node("GeometryNodeDistributePointsOnFaces", Mesh=shell, Density=density, Seed=seed)
    leaf = b.node("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=1).out
    leaf = b.set_material(b.transform(leaf, scale=(1.0, 1.0, 0.55)), material)
    identifier = b.node("GeometryNodeInputID").out
    size = b.math("MULTIPLY", clump, b.random(0.55, 1.35, seed, identifier=identifier))
    tilt = b.random((0.0, 0.0, 0.0), (0.8, 0.8, 6.28), b.math("ADD", seed, 1), data_type="FLOAT_VECTOR", identifier=identifier)
    return b.instance(points["Points"], leaf, rotation=b.euler(tilt), scale=size)


def build(b, context):
    trunk = b.panel("Trunk")
    height = b.input("Height", "FLOAT", 6.0, 0.2, 100.0, "DISTANCE", panel=trunk)
    trunk_radius = b.input("Trunk Radius", "FLOAT", 0.22, 0.01, 5.0, "DISTANCE", panel=trunk)
    trunk_bend = b.input("Trunk Bend", "FLOAT", 0.25, -2.0, 2.0, panel=trunk)
    limbs = b.panel("Limbs")
    limb_count = b.input("Limb Count", "INT", 9, 0, 200, panel=limbs)
    limb_start = b.input("Limb Start", "FLOAT", 0.35, 0.0, 1.0, "FACTOR", panel=limbs)
    limb_length = b.input("Limb Length", "FLOAT", 2.2, 0.05, 50.0, "DISTANCE", panel=limbs)
    limb_rise = b.input("Limb Rise", "FLOAT", 0.15, -2.0, 2.0, panel=limbs)
    limb_droop = b.input("Limb Droop", "FLOAT", 0.1, -2.0, 2.0, panel=limbs)
    twig_count = b.input("Twig Count", "INT", 4, 0, 100, panel=limbs)
    twig_length = b.input("Twig Length", "FLOAT", 0.8, 0.02, 20.0, "DISTANCE", panel=limbs)
    leaves = b.panel("Foliage")
    pad_width = b.input("Pad Width", "FLOAT", 0.75, 0.02, 20.0, "DISTANCE", panel=leaves)
    pad_height = b.input("Pad Height", "FLOAT", 0.38, 0.02, 20.0, "DISTANCE", panel=leaves)
    pad_density = b.input("Pad Density", "FLOAT", 40.0, 0.1, 5000.0, panel=leaves)
    clump = b.input("Clump Size", "FLOAT", 0.1, 0.005, 5.0, "DISTANCE", panel=leaves)
    crown_pad = b.input("Crown Pad Scale", "FLOAT", 1.5, 0.0, 20.0, panel=leaves)
    seed = b.input("Seed", "INT", 1, 0, 100000)
    looks = b.panel("Materials")
    bark = b.input("Bark", "MATERIAL", context.material("Bark"), panel=looks)
    foliage = b.input("Foliage", "MATERIAL", context.material("Foliage"), panel=looks)

    pad = foliage_pad(b, pad_width, pad_height, pad_density, clump, seed, foliage)

    twig_curve = bent_limb(b, twig_length, 0.35, 0.0, 0.1, b.math("ADD", seed, 7))
    twig_mesh = tapered_tube(b, twig_curve, b.math("MULTIPLY", trunk_radius, 0.12), b.math("MULTIPLY", trunk_radius, 0.05), 6)
    twig_tip = b.combine(twig_length, 0.0, b.math("MULTIPLY", twig_length, 0.35))
    twig = b.join(b.set_material(twig_mesh, bark), b.transform(pad, translation=twig_tip))

    limb_curve = bent_limb(b, limb_length, limb_rise, limb_droop, 0.12, b.math("ADD", seed, 11))
    limb_mesh = tapered_tube(b, limb_curve, b.math("MULTIPLY", trunk_radius, 0.42), b.math("MULTIPLY", trunk_radius, 0.12), 8)
    twig_spots = b.node("GeometryNodeCurveToPoints", props={"mode": "COUNT"}, Curve=b.node("GeometryNodeTrimCurve", Curve=limb_curve, Start=0.35, End=1.0).out, Count=twig_count)
    twig_identifier = b.index()
    twig_yaw = b.math("MULTIPLY", b.math("SUBTRACT", b.math("MODULO", twig_identifier, 2.0), 0.5), b.random(1.6, 2.6, b.math("ADD", seed, 13), identifier=twig_identifier))
    twig_rotation = b.node("FunctionNodeRotateRotation", props={"rotation_space": "LOCAL"}, Rotation=twig_spots["Rotation"], Rotate_By=b.euler(b.combine(0.0, -0.25, twig_yaw))).out
    twigs = b.instance(twig_spots["Points"], twig, rotation=twig_rotation, scale=b.random(0.7, 1.15, b.math("ADD", seed, 17), identifier=twig_identifier))
    limb_tip = b.node("GeometryNodeSampleCurve", props={"mode": "FACTOR"}, Curves=limb_curve, Factor=1.0)["Position"]
    limb_pad = b.transform(pad, translation=limb_tip, scale=1.2)
    limb = b.join(b.set_material(limb_mesh, bark), twigs, limb_pad)

    trunk_curve = b.node("GeometryNodeCurveQuadraticBezier", Resolution=16, Start=(0.0, 0.0, 0.0), Middle=b.combine(b.math("MULTIPLY", height, trunk_bend), 0.0, b.math("MULTIPLY", height, 0.5)), End=b.combine(b.math("MULTIPLY", height, b.math("MULTIPLY", trunk_bend, -0.4)), b.math("MULTIPLY", height, b.math("MULTIPLY", trunk_bend, 0.3)), height)).out
    trunk_mesh = tapered_tube(b, trunk_curve, trunk_radius, b.math("MULTIPLY", trunk_radius, 0.35), 12)
    limb_spots = b.node("GeometryNodeCurveToPoints", props={"mode": "COUNT"}, Curve=b.node("GeometryNodeTrimCurve", Curve=trunk_curve, Start=limb_start, End=0.96).out, Count=limb_count)
    identifier = b.index()
    golden = b.math("MULTIPLY", identifier, 2.39996)
    limb_rotation = b.euler(b.combine(0.0, b.random(-0.25, 0.15, b.math("ADD", seed, 19), identifier=identifier), golden))
    along = b.map_range(identifier, 0.0, b.math("MAXIMUM", b.math("SUBTRACT", limb_count, 1.0), 1.0), 1.0, 0.55)
    limbs_instances = b.instance(limb_spots["Points"], limb, rotation=limb_rotation, scale=b.math("MULTIPLY", along, b.random(0.8, 1.15, b.math("ADD", seed, 23), identifier=identifier)))
    crown_tip = b.node("GeometryNodeSampleCurve", props={"mode": "FACTOR"}, Curves=trunk_curve, Factor=1.0)["Position"]
    crown = b.transform(pad, translation=crown_tip, scale=crown_pad)
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(trunk_mesh, bark), limbs_instances, crown))
