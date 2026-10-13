from rain_garden.shapes import box

GROUP_NAME = "Plinth Planter"
CATEGORY = "Decorative"
DESCRIPTION = "Stone pedestal with a moulded cap and an inset medallion, crowned by a small branching tree."


def build(b, context):
    width = b.input("Width", "FLOAT", 2.4, 0.2, 30.0, "DISTANCE")
    height = b.input("Height", "FLOAT", 2.6, 0.2, 30.0, "DISTANCE")
    tree_height = b.input("Tree Height", "FLOAT", 2.4, 0.1, 30.0, "DISTANCE")
    seed = b.input("Seed", "INT", 5, 0, 100000)
    stone = b.input("Stone", "MATERIAL", context.material("White Stone"))
    medallion_material = b.input("Medallion", "MATERIAL", context.material("Inlay Blue"))

    body = box(b, b.combine(width, width, height), b.combine(0.0, 0.0, b.math("MULTIPLY", height, 0.5)))
    cap = box(b, b.combine(b.math("ADD", width, 0.25), b.math("ADD", width, 0.25), 0.22), b.combine(0.0, 0.0, b.math("ADD", height, 0.11)))
    skirt = box(b, b.combine(b.math("ADD", width, 0.18), b.math("ADD", width, 0.18), 0.3), b.combine(0.0, 0.0, 0.15))
    medallion = b.node("GeometryNodeMeshCylinder", Vertices=32, Radius=b.math("MULTIPLY", width, 0.22), Depth=0.06)["Mesh"]
    medallion = b.transform(medallion, translation=b.combine(0.0, b.math("MULTIPLY", width, -0.5), b.math("MULTIPLY", height, 0.45)), rotation=(1.5708, 0.0, 0.0))
    tree = b.group(context.require("Branching Tree"), Height=tree_height, Trunk_Radius=b.math("MULTIPLY", tree_height, 0.03), Trunk_Bend=0.15, Limb_Count=7, Limb_Start=0.35, Limb_Length=b.math("MULTIPLY", tree_height, 0.3), Limb_Rise=0.35, Twig_Count=3, Twig_Length=b.math("MULTIPLY", tree_height, 0.14), Pad_Width=b.math("MULTIPLY", tree_height, 0.14), Pad_Height=b.math("MULTIPLY", tree_height, 0.1), Pad_Density=70.0, Clump_Size=0.06, Crown_Pad_Scale=1.8, Seed=seed, Foliage=context.material("Foliage Bright")).out
    tree = b.transform(tree, translation=b.combine(0.0, 0.0, b.math("ADD", height, 0.22)))
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(b.join(body, cap, skirt), stone), b.set_material(medallion, medallion_material), tree))
