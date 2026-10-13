from rain_garden.shapes import fill_at_height

GROUP_NAME = "Outline Slab"
CATEGORY = "Architecture"
DESCRIPTION = "Closed outline curve filled and extruded downward into a solid floor slab; the curve height is the top surface."


def build(b, context):
    outline = b.input("Outline", "OBJECT")
    thickness = b.input("Thickness", "FLOAT", 0.4, 0.0, 200.0, "DISTANCE")
    material = b.input("Material", "MATERIAL", context.material("White Stone"))
    info = b.node("GeometryNodeObjectInfo", props={"transform_space": "RELATIVE"}, Object=outline)
    top = fill_at_height(b, info["Geometry"])
    lowered = b.transform(top, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", thickness, -1.0)))
    walls = b.node("GeometryNodeExtrudeMesh", props={"mode": "FACES"}, Mesh=lowered, Offset=b.combine(0.0, 0.0, thickness), Individual=False).out
    bottom = b.node("GeometryNodeFlipFaces", Mesh=lowered).out
    solid = b.node("GeometryNodeMergeByDistance", Geometry=b.join(walls, bottom), Distance=0.0005).out
    solid = b.smooth(solid, False)
    b.output("Geometry", "GEOMETRY", b.set_material(solid, material))
