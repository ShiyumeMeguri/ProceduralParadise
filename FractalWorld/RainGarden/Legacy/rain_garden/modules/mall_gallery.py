from rain_garden.shapes import rectangle_profile, sweep, vertical_ribbon

GROUP_NAME = "Mall Gallery"
CATEGORY = "Architecture"
DESCRIPTION = "Stack of gallery floors whose front edge follows the input curve: slabs of constant depth behind the curve, glass balustrades, lit storefront glazing set back from the edge, planters with shrubs and slender columns."


def build(b, context):
    curve = b.input("Curve", "GEOMETRY")
    levels = b.input("Levels", "INT", 4, 1, 50)
    level_height = b.input("Level Height", "FLOAT", 4.5, 1.0, 50.0, "DISTANCE")
    first_level = b.input("First Level", "FLOAT", 4.5, -50.0, 200.0, "DISTANCE")
    depth = b.input("Depth", "FLOAT", 5.0, 0.2, 100.0, "DISTANCE")
    thickness = b.input("Slab Thickness", "FLOAT", 0.55, 0.05, 5.0, "DISTANCE")
    setback = b.input("Storefront Setback", "FLOAT", 2.6, 0.0, 50.0, "DISTANCE")
    railing_height = b.input("Railing Height", "FLOAT", 1.1, 0.0, 3.0, "DISTANCE")
    planter_spacing = b.input("Planter Spacing", "FLOAT", 3.2, 0.2, 100.0, "DISTANCE")
    column_spacing = b.input("Column Spacing", "FLOAT", 7.0, 0.5, 100.0, "DISTANCE")
    seed = b.input("Seed", "INT", 9, 0, 100000)
    looks = b.panel("Materials")
    stone = b.input("Slab", "MATERIAL", context.material("White Stone"), panel=looks)
    frame = b.input("Railing Frame", "MATERIAL", context.material("Dark Steel"), panel=looks)
    glass = b.input("Railing Glass", "MATERIAL", context.material("Panel Glass"), panel=looks)
    storefront = b.input("Storefront", "MATERIAL", context.material("Storefront Glass"), panel=looks)
    foliage = b.input("Foliage", "MATERIAL", context.material("Foliage"), panel=looks)
    flowers = b.input("Flowers", "MATERIAL", context.material("Flowers"), panel=looks)

    normal_curve = b.node("GeometryNodeSetCurveNormal", Curve=curve, Mode="Free", Normal=(0.0, 0.0, 1.0)).out
    slab_profile = b.transform(rectangle_profile(b, thickness, depth), translation=b.combine(b.math("MULTIPLY", thickness, -0.5), b.math("MULTIPLY", depth, -0.5), 0.0))
    slab = b.curve_to_mesh(normal_curve, slab_profile, fill_caps=True)
    railing = b.group(context.require("Glass Railing"), Curve=curve, Height=railing_height, Frame_Material=frame, Glass_Material=glass).out

    offset_curve = b.node("GeometryNodeSetPosition", Geometry=normal_curve, Offset=b.vmath("SCALE", b.vmath("CROSS_PRODUCT", b.node("GeometryNodeInputTangent").out, (0.0, 0.0, 1.0)), b.math("MULTIPLY", setback, -1.0))).out
    glazing = vertical_ribbon(b, offset_curve, 0.0, b.math("SUBTRACT", level_height, thickness))

    planter_points = b.node("GeometryNodeCurveToPoints", props={"mode": "LENGTH"}, Curve=b.node("GeometryNodeSetPosition", Geometry=normal_curve, Offset=b.vmath("SCALE", b.vmath("CROSS_PRODUCT", b.node("GeometryNodeInputTangent").out, (0.0, 0.0, 1.0)), -0.45)).out, Length=planter_spacing)
    planter_box = b.node("GeometryNodeMeshCube", Size=(1.4, 0.45, 0.45)).out
    planter_box = b.transform(planter_box, translation=(0.0, 0.0, 0.225))
    planters = b.realize(b.instance(planter_points["Points"], planter_box, rotation=planter_points["Rotation"]))
    shrub_points = b.node("GeometryNodeDistributePointsOnFaces", Mesh=b.node("GeometryNodeDeleteGeometry", props={"domain": "FACE"}, Geometry=planters, Selection=b.compare(b.normal().z, 0.5, "LESS_THAN")).out, Density=14.0, Seed=seed)["Points"]
    blob = b.node("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=2).out
    identifier = b.node("GeometryNodeInputID").out
    shrub_scale = b.random(0.12, 0.28, seed, identifier=identifier)
    shrubs = b.realize(b.instance(shrub_points, blob, scale=b.combine(shrub_scale, shrub_scale, b.math("MULTIPLY", shrub_scale, 0.8))))
    shrubs = b.store(shrubs, "leaf_variation", b.random(0.0, 1.0, b.math("ADD", seed, 3), identifier=b.index()), domain="POINT")
    flower_points = b.node("GeometryNodeDistributePointsOnFaces", Mesh=shrubs, Density=22.0, Seed=b.math("ADD", seed, 5))["Points"]
    blossom = b.node("GeometryNodeMeshIcoSphere", Radius=0.05, Subdivisions=1).out
    blossoms = b.realize(b.instance(flower_points, blossom))

    column_points = b.node("GeometryNodeCurveToPoints", props={"mode": "LENGTH"}, Curve=offset_curve, Length=column_spacing)["Points"]
    column = b.node("GeometryNodeMeshCylinder", Vertices=24, Radius=0.3, Depth=b.math("SUBTRACT", level_height, thickness))["Mesh"]
    column = b.transform(column, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", b.math("SUBTRACT", level_height, thickness), 0.5)))
    columns = b.realize(b.instance(column_points, column))

    floor = b.join(
        b.set_material(b.join(slab, planters, columns), stone),
        railing,
        b.set_material(glazing, storefront),
        b.set_material(b.smooth(shrubs), foliage),
        b.set_material(blossoms, flowers),
    )
    level_points = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=levels, Start_Location=b.combine(0.0, 0.0, first_level), Offset=b.combine(0.0, 0.0, level_height)).out
    stacked = b.realize(b.instance(level_points, floor))
    b.output("Geometry", "GEOMETRY", stacked)
