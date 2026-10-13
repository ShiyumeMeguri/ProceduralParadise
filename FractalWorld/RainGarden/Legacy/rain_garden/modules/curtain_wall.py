from rain_garden.shapes import box_between, row_points

GROUP_NAME = "Curtain Wall"
CATEGORY = "Architecture"
DESCRIPTION = "Glazed curtain wall in the local XZ plane facing -Y: a glass skin behind a grid of vertical mullions and horizontal transoms."


def build(b, context):
    width = b.input("Width", "FLOAT", 6.0, 0.1, 500.0, "DISTANCE")
    height = b.input("Height", "FLOAT", 30.0, 0.1, 500.0, "DISTANCE")
    mullion_spacing = b.input("Mullion Spacing", "FLOAT", 1.5, 0.05, 50.0, "DISTANCE")
    transom_spacing = b.input("Transom Spacing", "FLOAT", 4.0, 0.05, 100.0, "DISTANCE")
    member = b.input("Member Size", "FLOAT", 0.1, 0.005, 2.0, "DISTANCE")
    depth = b.input("Member Depth", "FLOAT", 0.25, 0.005, 5.0, "DISTANCE")
    glass = b.input("Glass", "MATERIAL", context.material("Dark Glass Curtain"))
    metal = b.input("Frame", "MATERIAL", context.material("Dark Steel"))

    skin = box_between(b, b.combine(0.0, 0.0, 0.0), b.combine(width, 0.04, height))
    mullion = box_between(b, b.combine(b.math("MULTIPLY", member, -0.5), b.math("MULTIPLY", depth, -1.0), 0.0), b.combine(b.math("MULTIPLY", member, 0.5), 0.0, height))
    transom = box_between(b, b.combine(0.0, b.math("MULTIPLY", depth, -1.0), b.math("MULTIPLY", member, -0.5)), b.combine(width, 0.0, b.math("MULTIPLY", member, 0.5)))
    mullions = b.instance(row_points(b, b.math("ADD", b.math("FLOOR", b.math("DIVIDE", width, mullion_spacing)), 1.0), b.combine(mullion_spacing, 0.0, 0.0)), mullion)
    transoms = b.instance(row_points(b, b.math("ADD", b.math("FLOOR", b.math("DIVIDE", height, transom_spacing)), 1.0), b.combine(0.0, 0.0, transom_spacing)), transom)
    frame = b.realize(b.join(mullions, transoms))
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(skin, glass), b.set_material(frame, metal)))
