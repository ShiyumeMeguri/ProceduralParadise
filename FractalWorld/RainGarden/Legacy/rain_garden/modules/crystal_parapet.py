GROUP_NAME = "Crystal Parapet"
CATEGORY = "Decorative"
DESCRIPTION = "Band of clustered hexagonal crystal shards with pointed tips along local +X, leaning outward toward -Y; per-shard tint attribute drives the crystal colour ramp."


def unit_shard(b):
    prism = b.node("GeometryNodeMeshCylinder", Vertices=6, Radius=1.0, Depth=1.0)["Mesh"]
    prism = b.transform(prism, translation=(0.0, 0.0, 0.5))
    tip = b.node("GeometryNodeMeshCone", Vertices=6, Radius_Bottom=1.0, Radius_Top=0.0, Depth=0.55)["Mesh"]
    tip = b.transform(tip, translation=(0.0, 0.0, 1.275))
    return b.node("GeometryNodeMergeByDistance", Geometry=b.join(prism, tip), Distance=0.001).out


def build(b, context):
    length = b.input("Length", "FLOAT", 40.0, 0.5, 500.0, "DISTANCE")
    depth = b.input("Depth", "FLOAT", 1.4, 0.1, 20.0, "DISTANCE")
    density = b.input("Density", "FLOAT", 2.2, 0.01, 50.0)
    min_height = b.input("Min Height", "FLOAT", 1.0, 0.05, 20.0, "DISTANCE")
    max_height = b.input("Max Height", "FLOAT", 4.0, 0.05, 30.0, "DISTANCE")
    min_radius = b.input("Min Radius", "FLOAT", 0.22, 0.01, 5.0, "DISTANCE")
    max_radius = b.input("Max Radius", "FLOAT", 0.6, 0.01, 5.0, "DISTANCE")
    outward_lean = b.input("Outward Lean", "FLOAT", 0.35, -1.5, 1.5, "ANGLE")
    lean_jitter = b.input("Lean Jitter", "FLOAT", 0.35, 0.0, 1.5, "ANGLE")
    grouping = b.input("Grouping Scale", "FLOAT", 0.35, 0.0, 10.0)
    seed = b.input("Seed", "INT", 7, 0, 100000)
    material = b.input("Material", "MATERIAL", context.material("Crystal"))

    strip = b.node("GeometryNodeMeshGrid", Size_X=length, Size_Y=depth, Vertices_X=2, Vertices_Y=2).out
    strip = b.transform(strip, translation=b.combine(length * 0.5, 0.0, 0.0))
    distributed = b.node("GeometryNodeDistributePointsOnFaces", props={"distribute_method": "POISSON"}, Mesh=strip, Distance_Min=min_radius * 1.1, Density_Max=density, Seed=seed)
    points = distributed["Points"]
    identifier = b.node("GeometryNodeInputID").out
    position = b.position()
    grouping_noise = b.node("ShaderNodeTexNoise", props={"noise_dimensions": "1D"}, W=b.math("MULTIPLY", position.x, grouping), Scale=1.0, Detail=1.0)["Factor"]
    envelope = b.map_range(grouping_noise, 0.3, 0.7, 0.35, 1.0)
    height = b.math("MULTIPLY", b.random(min_height, max_height, seed, identifier=identifier), envelope)
    radius = b.random(min_radius, max_radius, b.math("ADD", seed, 11), identifier=identifier)
    flatten = b.random(0.6, 1.0, b.math("ADD", seed, 23), identifier=identifier)
    lean_x = b.math("ADD", b.math("MULTIPLY", b.random(-1.0, 1.0, b.math("ADD", seed, 31), identifier=identifier), lean_jitter), outward_lean)
    lean_y = b.math("MULTIPLY", b.random(-1.0, 1.0, b.math("ADD", seed, 37), identifier=identifier), lean_jitter)
    spin = b.random(0.0, 6.2832, b.math("ADD", seed, 41), identifier=identifier)
    rotation = b.euler(b.combine(lean_x, lean_y, spin))
    scale = b.combine(radius, b.math("MULTIPLY", radius, flatten), b.math("DIVIDE", height, 1.55))
    shards = b.instance(points, unit_shard(b), rotation=rotation, scale=scale)
    tint = b.random(0.0, 1.0, b.math("ADD", seed, 53), identifier=b.index())
    shards = b.store(shards, "tint", tint, domain="INSTANCE")
    solid = b.realize(shards)
    b.output("Geometry", "GEOMETRY", b.set_material(solid, material))
