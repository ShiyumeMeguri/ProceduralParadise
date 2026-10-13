GROUP_NAME = "Block"
CATEGORY = "Architecture"
DESCRIPTION = "Axis-aligned box whose origin sits at the centre of its bottom face."


def build(b, context):
    size = b.input("Size", "VECTOR", (2.0, 2.0, 2.0), subtype="XYZ")
    material = b.input("Material", "MATERIAL", context.material("White Stone"))
    cube = b.node("GeometryNodeMeshCube", Size=size).out
    lifted = b.transform(cube, translation=b.combine(0.0, 0.0, size.z * 0.5))
    b.output("Geometry", "GEOMETRY", b.set_material(lifted, material))
