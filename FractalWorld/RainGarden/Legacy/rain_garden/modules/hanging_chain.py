GROUP_NAME = "Hanging Chain"
CATEGORY = "Lights"
DESCRIPTION = "Chain of alternating oval links hanging straight down from the origin."


def build(b, context):
    length = b.input("Length", "FLOAT", 10.0, 0.0, 500.0, "DISTANCE")
    link_length = b.input("Link Length", "FLOAT", 0.2, 0.01, 5.0, "DISTANCE")
    link_width = b.input("Link Width", "FLOAT", 0.1, 0.005, 5.0, "DISTANCE")
    wire = b.input("Wire Radius", "FLOAT", 0.014, 0.001, 1.0, "DISTANCE")
    material = b.input("Material", "MATERIAL", context.material("Bronze"))

    ring = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=16, Radius=0.5)["Curve"]
    section = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=6, Radius=wire)["Curve"]
    link = b.curve_to_mesh(ring, section)
    link = b.transform(link, rotation=(1.5708, 0.0, 0.0), scale=b.combine(link_width, 1.0, link_length))
    pitch = b.math("MULTIPLY", link_length, 0.78)
    count = b.math("MAXIMUM", b.math("FLOOR", b.math("DIVIDE", length, pitch)), 1.0)
    points = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=count, Start_Location=b.combine(0.0, 0.0, b.math("MULTIPLY", link_length, -0.5)), Offset=b.combine(0.0, 0.0, b.math("MULTIPLY", pitch, -1.0))).out
    twist = b.math("MULTIPLY", b.math("MODULO", b.index(), 2.0), 1.5708)
    chain = b.realize(b.instance(points, link, rotation=b.euler(b.combine(0.0, 0.0, twist))))
    b.output("Geometry", "GEOMETRY", b.set_material(b.smooth(chain), material))
