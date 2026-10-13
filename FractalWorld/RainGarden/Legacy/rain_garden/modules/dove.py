GROUP_NAME = "Dove"
CATEGORY = "Creatures"
DESCRIPTION = "White dove in flight along local +X: plump body, small head and beak, broad feathered wings with adjustable beat angle and a fanned tail."


def wing(b, span, chord, beat, side):
    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=12, Vertices_Y=6).out
    position = b.position()
    s = b.math("ADD", position.x, 0.5)
    c = b.math("ADD", position.y, 0.5)
    local_chord = b.math("MULTIPLY", chord, b.math("SUBTRACT", 1.0, b.math("MULTIPLY", s, 0.55)))
    feather = b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", s, 25.0)), b.math("MULTIPLY", b.math("MULTIPLY", c, c), b.math("MULTIPLY", chord, 0.08)))
    x = b.math("ADD", b.math("MULTIPLY", b.math("SUBTRACT", 0.3, c), local_chord), b.math("MULTIPLY", s, b.math("MULTIPLY", chord, -0.35)))
    y = b.math("MULTIPLY", b.math("MULTIPLY", s, span), side)
    lift = b.math("MULTIPLY", b.math("SINE", beat), b.math("MULTIPLY", s, span))
    arch = b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", s, 3.14159)), b.math("MULTIPLY", chord, 0.12))
    z = b.math("ADD", b.math("ADD", lift, arch), feather)
    y = b.math("MULTIPLY", y, b.math("COSINE", beat))
    return b.set_position(grid, position=b.combine(x, y, z))


def build(b, context):
    size = b.input("Size", "FLOAT", 0.35, 0.01, 10.0, "DISTANCE")
    beat = b.input("Wing Beat", "FLOAT", 0.45, -1.5, 1.5, "ANGLE")
    material = b.input("Plumage", "MATERIAL", context.material("Feather White"))
    beak_material = b.input("Beak", "MATERIAL", context.material("Beak"))

    body = b.node("GeometryNodeMeshUVSphere", Segments=16, Rings=10, Radius=0.5).out
    body = b.transform(body, scale=(1.0, 0.42, 0.42))
    head = b.node("GeometryNodeMeshUVSphere", Segments=12, Rings=8, Radius=0.16).out
    head = b.transform(head, translation=(0.5, 0.0, 0.1))
    beak = b.node("GeometryNodeMeshCone", Vertices=6, Radius_Bottom=0.035, Radius_Top=0.0, Depth=0.1)["Mesh"]
    beak = b.transform(beak, translation=(0.68, 0.0, 0.09), rotation=(0.0, 1.5708, 0.0))
    tail_grid = b.node("GeometryNodeMeshGrid", Size_X=0.5, Size_Y=0.3, Vertices_X=4, Vertices_Y=6).out
    spread = b.math("ADD", 1.0, b.math("MULTIPLY", b.math("SUBTRACT", 0.25, b.position().x), 1.6))
    tail = b.set_position(tail_grid, position=b.combine(b.math("SUBTRACT", b.position().x, 0.72), b.math("MULTIPLY", b.position().y, spread), -0.02))
    left = wing(b, 1.25, 0.55, beat, 1.0)
    right = b.node("GeometryNodeFlipFaces", Mesh=wing(b, 1.25, 0.55, beat, -1.0)).out
    dove = b.join(b.smooth(b.join(body, head)), left, right, tail)
    dove = b.transform(dove, scale=size)
    beak = b.transform(beak, scale=size)
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(dove, material), b.set_material(beak, beak_material)))
