from rain_garden.shapes import box, line_curve, row_points

GROUP_NAME = "Staircase"
CATEGORY = "Architecture"
DESCRIPTION = "Straight flight rising along local +X from the origin: floating stepped soffit, solid stringer parapets on both sides and glass railings on top."


def build(b, context):
    steps = b.input("Step Count", "INT", 20, 1, 400)
    rise = b.input("Rise", "FLOAT", 0.16, 0.05, 1.0, "DISTANCE")
    run = b.input("Run", "FLOAT", 0.32, 0.1, 2.0, "DISTANCE")
    width = b.input("Width", "FLOAT", 3.0, 0.3, 50.0, "DISTANCE")
    soffit = b.input("Soffit Thickness", "FLOAT", 0.35, 0.05, 5.0, "DISTANCE")
    wall_thickness = b.input("Parapet Thickness", "FLOAT", 0.28, 0.0, 3.0, "DISTANCE")
    wall_height = b.input("Parapet Height", "FLOAT", 0.45, 0.0, 3.0, "DISTANCE")
    railing_height = b.input("Railing Height", "FLOAT", 0.95, 0.0, 3.0, "DISTANCE")
    stone = b.input("Stone", "MATERIAL", context.material("White Stone"))
    frame = b.input("Railing Frame", "MATERIAL", context.material("Dark Steel"))
    glass = b.input("Railing Glass", "MATERIAL", context.material("Panel Glass"))

    total_run = run * steps
    total_rise = rise * steps
    slope = rise / run
    step_block = box(b, b.combine(run, width, rise), b.combine(run * 0.5, 0.0, rise * 0.5))
    step_row = b.realize(b.instance(row_points(b, steps, b.combine(run, 0.0, rise)), step_block))

    underside = box(b, b.combine(total_run, width, soffit), b.combine(total_run * 0.5, 0.0, -soffit * 0.5))
    sheared = b.set_position(underside, offset=b.combine(0.0, 0.0, b.position().x * slope))

    wall_total = wall_height + soffit + rise
    walls = []
    railing_group = context.require("Glass Railing")
    railings = []
    for side in (-1.0, 1.0):
        offset_y = (width * 0.5 + wall_thickness * 0.5) * side
        wall = box(b, b.combine(total_run, wall_thickness, wall_total), b.combine(total_run * 0.5, offset_y, wall_total * 0.5 - soffit))
        walls.append(b.set_position(wall, offset=b.combine(0.0, 0.0, b.position().x * slope)))
        top = rise + wall_height
        path = line_curve(b, b.combine(0.0, offset_y, top), b.combine(total_run, offset_y, total_rise + top))
        railings.append(b.group(railing_group, Curve=path, Height=railing_height, Frame_Material=frame, Glass_Material=glass).out)

    stonework = b.set_material(b.join(step_row, sheared, *walls), stone)
    b.output("Geometry", "GEOMETRY", b.join(stonework, *railings))
