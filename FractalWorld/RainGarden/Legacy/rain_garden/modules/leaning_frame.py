from rain_garden.shapes import box, row_points

GROUP_NAME = "Leaning Frame"
CATEGORY = "Architecture"
DESCRIPTION = "Row of tapered piers along local +X leaning toward local +Y, carrying an overhanging sloped roof whose underside is a coffered steel grid."


def build(b, context):
    count = b.input("Count", "INT", 6, 1, 200)
    spacing = b.input("Spacing", "FLOAT", 4.4, 0.2, 100.0, "DISTANCE")
    height = b.input("Height", "FLOAT", 15.0, 0.5, 200.0, "DISTANCE")
    lean = b.input("Lean", "FLOAT", 0.18, -1.2, 1.2, "ANGLE")
    rake = b.input("Rake", "FLOAT", 0.0, -1.3, 1.3, "ANGLE")
    base_width = b.input("Base Width", "FLOAT", 1.25, 0.05, 20.0, "DISTANCE")
    top_width = b.input("Top Width", "FLOAT", 0.85, 0.05, 20.0, "DISTANCE")
    roof_back = b.input("Roof Back", "FLOAT", 6.0, 0.0, 100.0, "DISTANCE")
    roof_front = b.input("Roof Front", "FLOAT", 5.0, 0.0, 100.0, "DISTANCE")
    roof_thickness = b.input("Roof Thickness", "FLOAT", 1.6, 0.05, 20.0, "DISTANCE")
    roof_slope = b.input("Roof Slope", "FLOAT", 0.22, -1.2, 1.2, "ANGLE")
    coffer = b.input("Coffer Size", "FLOAT", 2.2, 0.2, 20.0, "DISTANCE")
    rib = b.input("Rib Width", "FLOAT", 0.28, 0.01, 5.0, "DISTANCE")
    stone = b.input("Pier Material", "MATERIAL", context.material("White Stone"))
    steel = b.input("Roof Material", "MATERIAL", context.material("Dark Steel"))

    pier = b.node("GeometryNodeMeshCone", Vertices=4, Side_Segments=1, Radius_Top=b.math("MULTIPLY", top_width, 0.7071), Radius_Bottom=b.math("MULTIPLY", base_width, 0.7071), Depth=height)["Mesh"]
    pier = b.transform(pier, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", height, 0.5)), rotation=(0.0, 0.0, 0.7854))
    tilt = b.euler(b.combine(b.math("MULTIPLY", lean, -1.0), rake, 0.0))
    pier = b.transform(pier, rotation=tilt)
    total = b.math("MULTIPLY", spacing, b.math("SUBTRACT", count, 1.0))
    piers = b.realize(b.instance(row_points(b, count, b.combine(spacing, 0.0, 0.0)), pier))

    top = b.node("FunctionNodeRotateVector", Vector=b.combine(0.0, 0.0, height), Rotation=tilt).out
    top_z = top.z
    roof_length = b.math("ADD", total, b.math("MULTIPLY", spacing, 1.0))
    roof_depth = b.math("ADD", roof_back, roof_front)
    roof_center = b.combine(b.math("ADD", b.math("MULTIPLY", total, 0.5), top.x), b.math("ADD", top.y, b.math("MULTIPLY", b.math("SUBTRACT", roof_front, roof_back), 0.5)), 0.0)
    slab = box(b, b.combine(roof_length, roof_depth, roof_thickness), b.combine(0.0, 0.0, b.math("MULTIPLY", roof_thickness, 0.5)))
    ribs_x = b.math("CEIL", b.math("DIVIDE", roof_length, coffer))
    ribs_y = b.math("CEIL", b.math("DIVIDE", roof_depth, coffer))
    rib_along = box(b, b.combine(roof_length, rib, b.math("MULTIPLY", roof_thickness, 0.45)), b.combine(0.0, 0.0, b.math("MULTIPLY", roof_thickness, -0.225)))
    rib_across = box(b, b.combine(rib, roof_depth, b.math("MULTIPLY", roof_thickness, 0.45)), b.combine(0.0, 0.0, b.math("MULTIPLY", roof_thickness, -0.225)))
    along_points = row_points(b, b.math("ADD", ribs_y, 1.0), b.combine(0.0, coffer, 0.0), b.combine(0.0, b.math("MULTIPLY", roof_depth, -0.5), 0.0))
    across_points = row_points(b, b.math("ADD", ribs_x, 1.0), b.combine(coffer, 0.0, 0.0), b.combine(b.math("MULTIPLY", roof_length, -0.5), 0.0, 0.0))
    grid = b.realize(b.join(b.instance(along_points, rib_along), b.instance(across_points, rib_across)))
    roof = b.join(slab, grid)
    roof = b.transform(roof, rotation=b.combine(b.math("MULTIPLY", roof_slope, -1.0), 0.0, 0.0))
    roof = b.transform(roof, translation=b.vmath("ADD", roof_center, b.combine(0.0, 0.0, top_z)))

    b.output("Geometry", "GEOMETRY", b.join(b.set_material(piers, stone), b.set_material(roof, steel)))
