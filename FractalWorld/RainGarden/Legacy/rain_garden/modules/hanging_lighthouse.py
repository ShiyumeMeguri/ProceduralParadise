from rain_garden.shapes import lathe

GROUP_NAME = "Hanging Lighthouse"
CATEGORY = "Lights"
DESCRIPTION = "Suspended lighthouse fountain hung from a stem: bronze spire and roof, glazed lantern room, railed stone gallery with finial statues, water-filled glass drum, funnel bowl, dripping strands and a falling water column. Origin at the gallery deck."

SPIRE = [(0.0, 7.6), (0.05, 7.4), (0.09, 6.6), (0.16, 6.55), (0.16, 6.35), (0.1, 6.3), (0.14, 5.2), (0.28, 4.9), (0.28, 4.7), (0.2, 4.6)]
ROOF = [(0.2, 4.6), (0.6, 3.9), (1.2, 3.0), (1.75, 2.2), (2.0, 1.85), (2.05, 1.7), (1.9, 1.62)]
LANTERN_ROOM = [(1.5, 1.62), (1.5, 0.35)]
GALLERY = [(1.5, 0.35), (2.95, 0.3), (3.0, 0.15), (2.95, 0.0), (2.75, -0.15), (2.7, -0.4)]
TOP_RING = [(2.7, -0.4), (2.72, -0.55), (2.64, -0.62)]
DRUM = [(2.6, -0.62), (2.6, -3.3)]
BOTTOM_RING = [(2.64, -3.3), (2.75, -3.38), (2.72, -3.5), (2.55, -3.55)]
FUNNEL = [(2.55, -3.55), (2.2, -3.9), (1.65, -4.4), (1.15, -4.95), (0.95, -5.3), (0.9, -5.6)]
NOZZLE = [(0.95, -5.6), (0.95, -5.75), (0.7, -5.8)]
DRUM_WATER = [(0.0, -0.75), (2.52, -0.75), (2.52, -3.5), (2.45, -3.6), (2.1, -3.95), (1.58, -4.42), (1.08, -4.97), (0.86, -5.55), (0.0, -5.55)]


def build(b, context):
    scale = b.input("Scale", "FLOAT", 1.0, 0.05, 20.0)
    stem_length = b.input("Stem Length", "FLOAT", 20.0, 0.0, 500.0, "DISTANCE")
    column_length = b.input("Column Length", "FLOAT", 15.0, 0.0, 500.0, "DISTANCE")
    drips = b.input("Drips", "INT", 28, 0, 400)
    statues = b.input("Statues", "INT", 8, 0, 64)
    seed = b.input("Seed", "INT", 5, 0, 100000)
    looks = b.panel("Materials")
    bronze = b.input("Bronze", "MATERIAL", context.material("Bronze"), panel=looks)
    roof_material = b.input("Roof", "MATERIAL", context.material("Lighthouse Roof"), panel=looks)
    stone = b.input("Stone", "MATERIAL", context.material("White Stone"), panel=looks)
    gold = b.input("Gold", "MATERIAL", context.material("Gold Trim"), panel=looks)
    glass = b.input("Glass", "MATERIAL", context.material("Clear Glass"), panel=looks)
    water = b.input("Water", "MATERIAL", context.material("Water"), panel=looks)
    falling = b.input("Falling Water", "MATERIAL", context.material("Waterfall"), panel=looks)

    def part(points, segments=64):
        mesh = lathe(b, [b.vmath("SCALE", point, scale) for point in [(radius, 0.0, height) for radius, height in points]], segments)
        return b.smooth(mesh)

    spire = part(SPIRE, 32)
    roof = part(ROOF)
    room = part(LANTERN_ROOM)
    gallery = part(GALLERY)
    rings = b.join(part(TOP_RING), part(BOTTOM_RING), part(NOZZLE, 48))
    drum = b.join(part(DRUM), part(FUNNEL))
    drum_water = part(DRUM_WATER)

    tip_height = b.math("MULTIPLY", 7.6, scale)
    stem = b.node("GeometryNodeMeshCylinder", Vertices=12, Radius=b.math("MULTIPLY", 0.05, scale), Depth=stem_length)["Mesh"]
    stem = b.transform(stem, translation=b.combine(0.0, 0.0, b.math("ADD", tip_height, b.math("MULTIPLY", stem_length, 0.5))))

    railing_curve = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=64, Radius=b.math("MULTIPLY", 2.85, scale))["Curve"]
    railing_curve = b.transform(railing_curve, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", 0.3, scale)))
    railing = b.group(context.require("Glass Railing"), Curve=railing_curve, Height=b.math("MULTIPLY", 0.9, scale), Post_Spacing=b.math("MULTIPLY", 0.7, scale), Post_Size=b.math("MULTIPLY", 0.05, scale), Handrail_Radius=b.math("MULTIPLY", 0.035, scale), Frame_Material=bronze, Glass_Material=glass).out

    statue_ring = b.node("GeometryNodeMeshCircle", Vertices=statues, Radius=b.math("MULTIPLY", 2.85, scale)).out
    statue_points = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=statue_ring).out
    statue_points = b.set_position(statue_points, offset=b.combine(0.0, 0.0, b.math("MULTIPLY", 0.3, scale)))
    statue = b.smooth(lathe(b, [(0.0, 0.0, 1.35), (0.07, 0.0, 1.3), (0.09, 0.0, 1.18), (0.06, 0.0, 1.08), (0.12, 0.0, 0.95), (0.16, 0.0, 0.6), (0.13, 0.0, 0.3), (0.2, 0.0, 0.12), (0.2, 0.0, 0.0)], 12))
    statues_mesh = b.realize(b.instance(statue_points, statue, scale=scale))

    drip_ring = b.node("GeometryNodeMeshCircle", Vertices=drips, Radius=b.math("MULTIPLY", 2.62, scale)).out
    drip_points = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=drip_ring).out
    drip_points = b.set_position(drip_points, offset=b.combine(0.0, 0.0, b.math("MULTIPLY", -3.5, scale)))
    identifier = b.index()
    drip_length = b.math("MULTIPLY", scale, b.random(0.4, 3.2, seed, identifier=identifier))
    drip_width = b.math("MULTIPLY", scale, b.random(0.03, 0.09, b.math("ADD", seed, 1), identifier=identifier))
    drip = b.node("GeometryNodeMeshCone", Vertices=8, Side_Segments=8, Radius_Top=1.0, Radius_Bottom=0.25, Depth=1.0)["Mesh"]
    drip = b.transform(drip, translation=(0.0, 0.0, -0.5))
    drip_instances = b.instance(drip_points, drip, scale=b.combine(drip_width, drip_width, drip_length))
    drip_mesh = b.realize(drip_instances)
    drip_mesh = b.store(drip_mesh, "fall_uv", b.combine(b.position().x, b.math("MULTIPLY", b.position().z, -1.0), 0.0), data_type="FLOAT_VECTOR", domain="POINT")

    nozzle_radius = b.math("MULTIPLY", 0.9, scale)
    column = b.group(context.require("Waterfall Curtain"), Width=b.math("MULTIPLY", nozzle_radius, 6.2832), Spread=1.35, Length=column_length, Throw=0.0, Curl=1.0, Turbulence=b.math("MULTIPLY", nozzle_radius, 0.12), Ripple_Scale=0.8, Columns=40, Rows=160, Seed=seed, Material=falling).out
    column = b.transform(column, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", -5.75, scale)))
    has_column = b.compare(column_length, 0.01, "GREATER_THAN")
    column = b.switch(has_column, None, column)

    result = b.join(
        b.set_material(b.join(spire, stem, statues_mesh), bronze),
        b.set_material(roof, roof_material),
        b.set_material(b.join(room, drum), glass),
        b.set_material(gallery, stone),
        b.set_material(rings, gold),
        b.set_material(drum_water, water),
        b.set_material(b.smooth(drip_mesh), falling),
        railing,
        column,
    )
    b.output("Geometry", "GEOMETRY", result)
