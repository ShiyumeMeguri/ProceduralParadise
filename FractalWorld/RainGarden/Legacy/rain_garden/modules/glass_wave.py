GROUP_NAME = "Glass Wave"
CATEGORY = "Decorative"
DESCRIPTION = "Curling glass sail shaped like a breaking wave: a cresting profile in the local XZ plane swept across local Y, thickened into a cast glass blade."


def build(b, context):
    height = b.input("Height", "FLOAT", 3.2, 0.1, 50.0, "DISTANCE")
    width = b.input("Width", "FLOAT", 1.6, 0.05, 50.0, "DISTANCE")
    curl = b.input("Curl", "FLOAT", 1.1, 0.0, 3.0)
    reach = b.input("Reach", "FLOAT", 1.4, 0.0, 20.0, "DISTANCE")
    thickness = b.input("Thickness", "FLOAT", 0.08, 0.005, 2.0, "DISTANCE")
    material = b.input("Material", "MATERIAL", context.material("Wave Glass"))

    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=40, Vertices_Y=12).out
    position = b.position()
    t = b.math("ADD", position.x, 0.5)
    s = position.y
    rise = b.math("MULTIPLY", height, b.math("POWER", t, 0.85))
    lean = b.math("MULTIPLY", reach, b.math("POWER", t, 2.4))
    hook = b.math("MULTIPLY", b.math("MULTIPLY", curl, b.math("POWER", b.math("MAXIMUM", b.math("SUBTRACT", t, 0.7), 0.0), 2.0)), b.math("MULTIPLY", height, 1.6))
    taper = b.math("SUBTRACT", 1.0, b.math("MULTIPLY", t, 0.35))
    flare = b.math("MULTIPLY", b.math("MULTIPLY", s, width), taper)
    placed = b.combine(b.math("ADD", lean, b.math("MULTIPLY", hook, 0.3)), flare, b.math("SUBTRACT", rise, hook))
    sheet = b.set_position(grid, position=placed)
    solid = b.node("GeometryNodeExtrudeMesh", props={"mode": "FACES"}, Mesh=sheet, Offset_Scale=thickness, Individual=False).out
    solid = b.join(solid, b.node("GeometryNodeFlipFaces", Mesh=sheet).out)
    b.output("Geometry", "GEOMETRY", b.set_material(b.smooth(solid), material))
