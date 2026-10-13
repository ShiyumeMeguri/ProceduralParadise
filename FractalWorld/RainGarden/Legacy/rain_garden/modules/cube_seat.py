GROUP_NAME = "Cube Seat"
CATEGORY = "Decorative"
DESCRIPTION = "Soft-edged cube stool."


def build(b, context):
    size = b.input("Size", "FLOAT", 0.55, 0.05, 10.0, "DISTANCE")
    material = b.input("Material", "MATERIAL", context.material("Seat Blue"))
    cube = b.node("GeometryNodeMeshCube", Size=b.combine(size, size, size), Vertices_X=3, Vertices_Y=3, Vertices_Z=3).out
    rounded = b.node("GeometryNodeSubdivisionSurface", Mesh=cube, Level=2, Edge_Crease=0.75).out
    rounded = b.transform(rounded, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", size, 0.5)))
    b.output("Geometry", "GEOMETRY", b.set_material(b.smooth(rounded), material))
