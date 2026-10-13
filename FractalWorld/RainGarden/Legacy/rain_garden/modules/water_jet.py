GROUP_NAME = "Water Jet"
CATEGORY = "Water"
DESCRIPTION = "Fountain jet erupting upward from the origin: a flared central column ringed by splash spikes and a halo of spray droplets."


def build(b, context):
    height = b.input("Height", "FLOAT", 6.0, 0.1, 200.0, "DISTANCE")
    base_radius = b.input("Base Radius", "FLOAT", 0.35, 0.01, 20.0, "DISTANCE")
    top_radius = b.input("Top Radius", "FLOAT", 0.9, 0.01, 30.0, "DISTANCE")
    spikes = b.input("Spikes", "INT", 14, 0, 500)
    spike_spread = b.input("Spike Spread", "FLOAT", 0.35, 0.0, 1.5, "ANGLE")
    droplets = b.input("Droplets", "INT", 220, 0, 20000)
    seed = b.input("Seed", "INT", 2, 0, 100000)
    material = b.input("Material", "MATERIAL", context.material("Waterfall"))
    spray_material = b.input("Spray Material", "MATERIAL", context.material("Spray"))

    column = b.group(context.require("Waterfall Curtain"), Width=b.math("MULTIPLY", top_radius, 6.2832), Spread=b.math("DIVIDE", base_radius, top_radius), Length=height, Throw=0.0, Curl=1.0, Turbulence=b.math("MULTIPLY", top_radius, 0.25), Ripple_Scale=1.1, Columns=32, Rows=80, Seed=seed, Material=material).out
    column = b.transform(column, translation=b.combine(0.0, 0.0, height))

    ring = b.node("GeometryNodeMeshCircle", Vertices=spikes, Radius=base_radius).out
    ring_points = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=ring).out
    identifier = b.index()
    spike_height = b.math("MULTIPLY", height, b.random(0.3, 0.85, seed, identifier=identifier))
    spike = b.node("GeometryNodeMeshCone", Vertices=6, Side_Segments=6, Radius_Bottom=1.0, Radius_Top=0.0, Depth=1.0)["Mesh"]
    spike = b.transform(spike, translation=(0.0, 0.0, 0.5))
    outward = b.math("ARCTAN2", b.position().y, b.position().x)
    tilt = b.math("MULTIPLY", spike_spread, b.random(0.4, 1.0, b.math("ADD", seed, 3), identifier=identifier))
    spike_rotation = b.node("FunctionNodeRotateRotation", props={"rotation_space": "GLOBAL"}, Rotation=b.euler(b.combine(0.0, tilt, 0.0)), Rotate_By=b.euler(b.combine(0.0, 0.0, outward))).out
    spike_width = b.math("MULTIPLY", base_radius, b.random(0.18, 0.4, b.math("ADD", seed, 5), identifier=identifier))
    spike_instances = b.instance(ring_points, spike, rotation=spike_rotation, scale=b.combine(spike_width, spike_width, spike_height))
    spike_instances = b.store(spike_instances, "fall_uv", b.combine(0.0, b.random(0.0, 50.0, b.math("ADD", seed, 7), identifier=identifier), 0.0), data_type="FLOAT_VECTOR", domain="INSTANCE")
    spike_mesh = b.realize(spike_instances)
    spike_mesh = b.store(spike_mesh, "fall_uv", b.vmath("ADD", b.named("fall_uv", "FLOAT_VECTOR"), b.combine(b.position().x, b.position().z, 0.0)), data_type="FLOAT_VECTOR", domain="POINT")

    cloud = b.node("GeometryNodeMeshUVSphere", Segments=16, Rings=8, Radius=1.0).out
    cloud = b.transform(cloud, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", height, 0.8)), scale=b.combine(top_radius, top_radius, b.math("MULTIPLY", height, 0.35)))
    spray_points = b.node("GeometryNodeDistributePointsInVolume", Volume=b.node("GeometryNodeMeshToVolume", Mesh=cloud, Interior_Band_Width=0.2).out, Mode="Random", Density=b.math("DIVIDE", droplets, b.math("MULTIPLY", b.math("MULTIPLY", top_radius, top_radius), b.math("MULTIPLY", height, 1.5))), Seed=seed).out
    droplet = b.node("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=1).out
    spray = b.realize(b.instance(spray_points, droplet, scale=b.math("MULTIPLY", base_radius, b.random(0.02, 0.07, b.math("ADD", seed, 9), identifier=b.node("GeometryNodeInputID").out))))

    b.output("Geometry", "GEOMETRY", b.join(column, b.set_material(b.smooth(spike_mesh), material), b.set_material(spray, spray_material)))
