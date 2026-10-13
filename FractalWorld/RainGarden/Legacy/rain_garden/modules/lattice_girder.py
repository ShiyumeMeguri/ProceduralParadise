from rain_garden.shapes import line_curve, rectangle_profile, sweep

GROUP_NAME = "Lattice Girder"
CATEGORY = "Architecture"
DESCRIPTION = "Straight square box truss along local +X: four corner chords with Warren lacing on all four faces."


def zigzag(b, length, bays, start_a, start_b):
    count = b.math("ADD", b.math("MULTIPLY", bays, 2.0), 1.0)
    line = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=count).out
    index = b.index()
    x = b.math("MULTIPLY", length, b.math("DIVIDE", index, b.math("SUBTRACT", count, 1.0)))
    odd = b.math("MODULO", index, 2.0)
    offset = b.mix(odd, start_a, start_b, data_type="VECTOR")
    placed = b.set_position(line, position=b.vmath("ADD", b.combine(x, 0.0, 0.0), offset))
    return b.node("GeometryNodeMeshToCurve", Mesh=placed).out


def build(b, context):
    length = b.input("Length", "FLOAT", 30.0, 0.5, 500.0, "DISTANCE")
    width = b.input("Width", "FLOAT", 1.4, 0.05, 20.0, "DISTANCE")
    depth = b.input("Depth", "FLOAT", 1.4, 0.05, 20.0, "DISTANCE")
    bays = b.input("Bays", "INT", 24, 1, 1000)
    chord = b.input("Chord Size", "FLOAT", 0.14, 0.01, 2.0, "DISTANCE")
    web = b.input("Web Size", "FLOAT", 0.07, 0.005, 1.0, "DISTANCE")
    steel = b.input("Steel", "MATERIAL", context.material("White Steel"))

    half_width = width * 0.5
    half_depth = depth * 0.5
    parts = []
    for y_sign in (-1.0, 1.0):
        for z_sign in (-1.0, 1.0):
            start = b.combine(0.0, half_width * y_sign, half_depth * z_sign)
            end = b.combine(length, half_width * y_sign, half_depth * z_sign)
            parts.append(sweep(b, line_curve(b, start, end), rectangle_profile(b, chord, chord), up=(0.0, 0.0, 1.0)))
    web_profile = rectangle_profile(b, web, web)
    for y_sign in (-1.0, 1.0):
        lace = zigzag(b, length, bays, b.combine(0.0, half_width * y_sign, half_depth), b.combine(0.0, half_width * y_sign, half_depth * -1.0))
        parts.append(sweep(b, lace, web_profile, up=(0.0, 1.0, 0.0)))
    for z_sign in (-1.0, 1.0):
        lace = zigzag(b, length, bays, b.combine(0.0, half_width, half_depth * z_sign), b.combine(0.0, half_width * -1.0, half_depth * z_sign))
        parts.append(sweep(b, lace, web_profile, up=(0.0, 0.0, 1.0)))
    b.output("Geometry", "GEOMETRY", b.set_material(b.join(*parts), steel))
