GROUP_NAME = "Manta Ray"
CATEGORY = "Creatures"
DESCRIPTION = "Gliding manta ray along local +X: swept-back pointed wings over a lens-shaped body, flexing wing tips, cephalic fins and a whip tail; back and belly take separate materials."


def wing_surface(b, span, length, thickness, sweep, flap, upper, columns=48, rows=20):
    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=columns, Vertices_Y=rows).out
    position = b.position()
    signed = b.math("MULTIPLY", position.x, 2.0)
    u = b.math("ABSOLUTE", signed)
    v = b.math("ADD", position.y, 0.5)
    lead = b.math("SUBTRACT", b.math("MULTIPLY", length, 0.5), b.math("MULTIPLY", b.math("MULTIPLY", sweep, length), b.math("POWER", u, 1.6)))
    chord = b.math("MULTIPLY", length, b.math("MULTIPLY", b.math("POWER", b.math("MAXIMUM", b.math("SUBTRACT", 1.0, u), 0.0), 0.75), b.math("ADD", 0.25, b.math("MULTIPLY", b.math("SUBTRACT", 1.0, u), 0.75))))
    x = b.math("SUBTRACT", lead, b.math("MULTIPLY", v, chord))
    y = b.math("MULTIPLY", signed, b.math("MULTIPLY", span, 0.5))
    body = b.math("MULTIPLY", thickness, b.math("POWER", b.math("MAXIMUM", b.math("SUBTRACT", 1.0, b.math("MULTIPLY", u, 1.6)), 0.0), 1.4))
    body = b.math("MULTIPLY", body, b.math("POWER", b.math("SINE", b.math("MULTIPLY", v, 3.14159)), 0.7))
    skin = b.math("MULTIPLY", thickness, b.math("MULTIPLY", 0.12, b.math("SINE", b.math("MULTIPLY", v, 3.14159))))
    bend = b.math("MULTIPLY", flap, b.math("MULTIPLY", b.math("POWER", u, 2.2), b.math("MULTIPLY", span, 0.22)))
    half = b.math("ADD", body, skin)
    z = b.math("ADD", bend, half if upper else b.math("MULTIPLY", half, -0.6))
    surface = b.set_position(grid, position=b.combine(x, y, z))
    return surface if upper else b.node("GeometryNodeFlipFaces", Mesh=surface).out


def build(b, context):
    span = b.input("Wingspan", "FLOAT", 4.0, 0.05, 50.0, "DISTANCE")
    length = b.input("Length", "FLOAT", 2.2, 0.05, 50.0, "DISTANCE")
    thickness = b.input("Thickness", "FLOAT", 0.22, 0.005, 5.0, "DISTANCE")
    sweep = b.input("Sweep", "FLOAT", 0.55, 0.0, 2.0)
    flap = b.input("Flap", "FLOAT", 0.35, -2.0, 2.0)
    tail = b.input("Tail Length", "FLOAT", 1.6, 0.0, 30.0, "DISTANCE")
    back = b.input("Back", "MATERIAL", context.material("Manta Back"))
    belly = b.input("Belly", "MATERIAL", context.material("Manta Belly"))

    upper = wing_surface(b, span, length, thickness, sweep, flap, True)
    lower = wing_surface(b, span, length, thickness, sweep, flap, False)
    horn = b.node("GeometryNodeMeshCone", Vertices=6, Radius_Bottom=b.math("MULTIPLY", thickness, 0.45), Radius_Top=b.math("MULTIPLY", thickness, 0.1), Depth=b.math("MULTIPLY", length, 0.3))["Mesh"]
    horn = b.transform(horn, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", length, 0.15)))
    horn_left = b.transform(horn, translation=b.combine(b.math("MULTIPLY", length, 0.42), b.math("MULTIPLY", span, 0.06), 0.0), rotation=(0.0, 1.35, 0.25))
    horn_right = b.transform(horn, translation=b.combine(b.math("MULTIPLY", length, 0.42), b.math("MULTIPLY", span, -0.06), 0.0), rotation=(0.0, 1.35, -0.25))
    whip = b.node("GeometryNodeMeshCone", Vertices=6, Radius_Bottom=b.math("MULTIPLY", thickness, 0.16), Radius_Top=0.0, Depth=tail)["Mesh"]
    whip = b.transform(whip, translation=b.combine(b.math("SUBTRACT", b.math("MULTIPLY", length, -0.45), b.math("MULTIPLY", tail, 0.5)), 0.0, 0.0), rotation=(0.0, -1.5708, 0.0))
    result = b.join(b.set_material(b.smooth(b.join(upper, horn_left, horn_right, whip)), back), b.set_material(b.smooth(lower), belly))
    b.output("Geometry", "GEOMETRY", result)
