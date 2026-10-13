GROUP_NAME = "Glass Vault"
CATEGORY = "Architecture"
DESCRIPTION = "Glazed barrel vault along local +X: circular cross-section of the given radius springing at the origin height, glass skin on a grid of steel ribs and purlins, clipped below a minimum height."


def build(b, context):
    length = b.input("Length", "FLOAT", 60.0, 1.0, 1000.0, "DISTANCE")
    radius = b.input("Radius", "FLOAT", 20.0, 0.5, 500.0, "DISTANCE")
    sweep_angle = b.input("Sweep", "FLOAT", 3.14159, 0.1, 6.28318, "ANGLE")
    rib_spacing = b.input("Rib Spacing", "FLOAT", 3.6, 0.2, 50.0, "DISTANCE")
    purlins = b.input("Purlins", "INT", 28, 2, 400)
    member = b.input("Member Size", "FLOAT", 0.14, 0.01, 2.0, "DISTANCE")
    minimum_height = b.input("Minimum Height", "FLOAT", -1000.0, -10000.0, 10000.0, "DISTANCE")
    glass = b.input("Glass", "MATERIAL", context.material("Roof Glass"))
    steel = b.input("Steel", "MATERIAL", context.material("White Steel"))

    columns = b.math("ADD", b.math("CEIL", b.math("DIVIDE", length, rib_spacing)), 1.0)
    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=columns, Vertices_Y=b.math("ADD", purlins, 1.0)).out
    position = b.position()
    along = b.math("MULTIPLY", b.math("ADD", position.x, 0.5), length)
    start = b.math("MULTIPLY", b.math("SUBTRACT", 3.14159265, sweep_angle), 0.5)
    angle = b.math("ADD", start, b.math("MULTIPLY", b.math("ADD", position.y, 0.5), sweep_angle))
    placed = b.combine(along, b.math("MULTIPLY", b.math("COSINE", angle), radius), b.math("MULTIPLY", b.math("SINE", angle), radius))
    skin = b.set_position(grid, position=placed)
    frame_edges = b.node("GeometryNodeMeshToCurve", Mesh=skin).out
    frame = b.curve_to_mesh(frame_edges, b.node("GeometryNodeCurvePrimitiveQuadrilateral", props={"mode": "RECTANGLE"}, Width=member, Height=member).out)
    low_faces = b.compare(b.position().z, minimum_height, "LESS_THAN")
    skin = b.node("GeometryNodeDeleteGeometry", props={"domain": "POINT"}, Geometry=skin, Selection=low_faces).out
    frame = b.node("GeometryNodeDeleteGeometry", props={"domain": "POINT"}, Geometry=frame, Selection=b.compare(b.position().z, minimum_height, "LESS_THAN")).out
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(skin, glass), b.set_material(frame, steel)))
