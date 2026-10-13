from rain_garden.shapes import fill_at_height, rectangle_profile, sweep, vertical_ribbon

GROUP_NAME = "Pool Basin"
CATEGORY = "Water"
DESCRIPTION = "Pool built from a closed outline curve at rim height: water volume filled to just below the rim, caustic floor, lined walls and a flat coping band on top."


def upward_fill(b, curve):
    return fill_at_height(b, curve)


def build(b, context):
    outline = b.input("Outline", "OBJECT")
    depth = b.input("Depth", "FLOAT", 1.2, 0.05, 50.0, "DISTANCE")
    water_gap = b.input("Water Gap", "FLOAT", 0.05, 0.0, 5.0, "DISTANCE")
    coping_width = b.input("Coping Width", "FLOAT", 0.35, 0.0, 5.0, "DISTANCE")
    coping_height = b.input("Coping Height", "FLOAT", 0.06, 0.0, 2.0, "DISTANCE")
    lined = b.input("Lined", "BOOL", True)
    water_material = b.input("Water", "MATERIAL", context.material("Water"))
    floor_material = b.input("Floor", "MATERIAL", context.material("Pool Floor Caustics"))
    wall_material = b.input("Wall", "MATERIAL", context.material("Pool Tile"))
    coping_material = b.input("Coping", "MATERIAL", context.material("White Stone"))

    curve = b.node("GeometryNodeObjectInfo", props={"transform_space": "RELATIVE"}, Object=outline)["Geometry"]
    top = upward_fill(b, b.transform(curve, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", water_gap, -1.0))))
    body_height = b.math("SUBTRACT", b.math("SUBTRACT", depth, water_gap), 0.01)
    lowered = b.transform(top, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", body_height, -1.0)))
    walls = b.node("GeometryNodeExtrudeMesh", props={"mode": "FACES"}, Mesh=lowered, Offset=b.combine(0.0, 0.0, body_height), Individual=False).out
    water = b.node("GeometryNodeMergeByDistance", Geometry=b.join(walls, b.node("GeometryNodeFlipFaces", Mesh=lowered).out), Distance=0.00001).out

    floor = b.transform(upward_fill(b, curve), translation=b.combine(0.0, 0.0, b.math("MULTIPLY", depth, -1.0)))
    lining = b.node("GeometryNodeFlipFaces", Mesh=vertical_ribbon(b, curve, b.math("MULTIPLY", depth, -1.0), 0.0)).out
    lining = b.switch(lined, None, lining)
    coping = sweep(b, b.transform(curve, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", coping_height, 0.5))), rectangle_profile(b, coping_height, coping_width))

    b.output("Geometry", "GEOMETRY", b.join(
        b.set_material(water, water_material),
        b.set_material(floor, floor_material),
        b.set_material(lining, wall_material),
        b.set_material(coping, coping_material),
    ))
