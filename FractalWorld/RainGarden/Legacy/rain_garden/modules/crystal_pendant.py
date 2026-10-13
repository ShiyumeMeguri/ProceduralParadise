from rain_garden.shapes import lathe

GROUP_NAME = "Crystal Pendant"
CATEGORY = "Lights"
DESCRIPTION = "Strand of glowing glass drops hanging from the origin on a fine thread; drops swell toward the bottom and end in a jellyfish bell with trailing tendrils."


def build(b, context):
    length = b.input("Length", "FLOAT", 4.0, 0.05, 200.0, "DISTANCE")
    beads = b.input("Beads", "INT", 7, 1, 200)
    bead_size = b.input("Bead Size", "FLOAT", 0.12, 0.005, 5.0, "DISTANCE")
    bell_size = b.input("Bell Size", "FLOAT", 0.35, 0.0, 10.0, "DISTANCE")
    tendrils = b.input("Tendrils", "INT", 7, 0, 64)
    seed = b.input("Seed", "INT", 4, 0, 100000)
    glass = b.input("Glass", "MATERIAL", context.material("Crystal Cyan"))
    thread_material = b.input("Thread", "MATERIAL", context.material("Bronze"))

    thread = b.node("GeometryNodeMeshCylinder", Vertices=6, Radius=0.006, Depth=length)["Mesh"]
    thread = b.transform(thread, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", length, -0.5)))

    drop = b.smooth(lathe(b, [(0.0, 0.0, 1.0), (0.18, 0.0, 0.7), (0.42, 0.0, 0.35), (0.5, 0.0, 0.0), (0.42, 0.0, -0.3), (0.2, 0.0, -0.5), (0.0, 0.0, -0.55)], 16))
    spacing = b.math("DIVIDE", b.math("MULTIPLY", length, 0.9), beads)
    points = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=beads, Start_Location=b.combine(0.0, 0.0, b.math("MULTIPLY", spacing, -0.6)), Offset=b.combine(0.0, 0.0, b.math("MULTIPLY", spacing, -1.0))).out
    identifier = b.index()
    growth = b.map_range(identifier, 0.0, b.math("MAXIMUM", b.math("SUBTRACT", beads, 1.0), 1.0), 0.6, 1.3)
    size = b.math("MULTIPLY", b.math("MULTIPLY", bead_size, growth), b.random(0.75, 1.25, seed, identifier=identifier))
    beads_mesh = b.realize(b.instance(points, drop, scale=b.combine(size, size, b.math("MULTIPLY", size, 1.6))))

    bell = b.smooth(lathe(b, [(0.0, 0.0, 0.62), (0.3, 0.0, 0.58), (0.52, 0.0, 0.42), (0.62, 0.0, 0.15), (0.64, 0.0, 0.0), (0.5, 0.0, 0.04), (0.3, 0.0, 0.12), (0.0, 0.0, 0.15)], 24))
    bell = b.transform(bell, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", length, -1.0)), scale=bell_size)
    tendril_ring = b.node("GeometryNodeMeshCircle", Vertices=tendrils, Radius=b.math("MULTIPLY", bell_size, 0.45)).out
    tendril_points = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=tendril_ring).out
    tendril_points = b.set_position(tendril_points, offset=b.combine(0.0, 0.0, b.math("MULTIPLY", length, -1.0)))
    tendril = b.node("GeometryNodeMeshCone", Vertices=6, Side_Segments=4, Radius_Top=1.0, Radius_Bottom=0.0, Depth=1.0)["Mesh"]
    tendril = b.transform(tendril, translation=(0.0, 0.0, -0.5))
    tendril_length = b.math("MULTIPLY", bell_size, b.random(1.5, 4.0, b.math("ADD", seed, 2), identifier=identifier))
    tendril_width = b.math("MULTIPLY", bell_size, 0.05)
    tendrils_mesh = b.realize(b.instance(tendril_points, tendril, scale=b.combine(tendril_width, tendril_width, tendril_length)))

    has_bell = b.compare(bell_size, 0.001, "GREATER_THAN")
    jelly = b.switch(has_bell, None, b.join(bell, b.smooth(tendrils_mesh)))
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(b.join(beads_mesh, jelly), glass), b.set_material(thread, thread_material)))
