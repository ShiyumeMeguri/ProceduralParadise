from rain_garden.shapes import box

GROUP_NAME = "Lounge Bench"
CATEGORY = "Decorative"
DESCRIPTION = "Plaza lounge bench along local X with a timber frame, soft rounded seat and back cushions."


def soft_block(b, size, center):
    cube = b.node("GeometryNodeMeshCube", Size=size, Vertices_X=3, Vertices_Y=3, Vertices_Z=3).out
    rounded = b.node("GeometryNodeSubdivisionSurface", Mesh=cube, Level=2, Edge_Crease=0.65).out
    return b.transform(rounded, translation=center)


def build(b, context):
    length = b.input("Length", "FLOAT", 2.4, 0.3, 20.0, "DISTANCE")
    depth = b.input("Depth", "FLOAT", 0.9, 0.2, 5.0, "DISTANCE")
    seat_height = b.input("Seat Height", "FLOAT", 0.45, 0.1, 2.0, "DISTANCE")
    back_height = b.input("Back Height", "FLOAT", 0.45, 0.0, 2.0, "DISTANCE")
    frame = b.input("Frame", "MATERIAL", context.material("Timber"))
    cushion = b.input("Cushion", "MATERIAL", context.material("Cushion Cream"))

    base = box(b, b.combine(length, depth, b.math("MULTIPLY", seat_height, 0.6)), b.combine(0.0, 0.0, b.math("MULTIPLY", seat_height, 0.3)))
    seat = soft_block(b, b.combine(b.math("SUBTRACT", length, 0.06), b.math("SUBTRACT", depth, 0.06), b.math("MULTIPLY", seat_height, 0.45)), b.combine(0.0, 0.0, b.math("MULTIPLY", seat_height, 0.8)))
    back = soft_block(b, b.combine(b.math("SUBTRACT", length, 0.06), b.math("MULTIPLY", depth, 0.25), back_height), b.combine(0.0, b.math("MULTIPLY", depth, 0.37), b.math("ADD", seat_height, b.math("MULTIPLY", back_height, 0.45))))
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(base, frame), b.set_material(b.smooth(b.join(seat, back)), cushion)))
