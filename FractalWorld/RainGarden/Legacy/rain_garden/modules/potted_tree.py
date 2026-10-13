from rain_garden.shapes import lathe

GROUP_NAME = "Potted Tree"
CATEGORY = "Plants"
DESCRIPTION = "Tapered planter with a rolled rim and soil, holding a small self-similar branching tree."


def build(b, context):
    pot_radius = b.input("Pot Radius", "FLOAT", 0.55, 0.05, 10.0, "DISTANCE")
    pot_height = b.input("Pot Height", "FLOAT", 0.7, 0.05, 10.0, "DISTANCE")
    tree_height = b.input("Tree Height", "FLOAT", 1.8, 0.1, 30.0, "DISTANCE")
    spread = b.input("Spread", "FLOAT", 0.7, 0.05, 20.0, "DISTANCE")
    limb_count = b.input("Limb Count", "INT", 7, 0, 100)
    limb_rise = b.input("Limb Rise", "FLOAT", 0.35, -2.0, 2.0)
    pad_density = b.input("Pad Density", "FLOAT", 60.0, 0.1, 5000.0)
    clump = b.input("Clump Size", "FLOAT", 0.07, 0.005, 5.0, "DISTANCE")
    seed = b.input("Seed", "INT", 1, 0, 100000)
    looks = b.panel("Materials")
    pot_material = b.input("Pot", "MATERIAL", context.material("Pot Charcoal"), panel=looks)
    soil_material = b.input("Soil", "MATERIAL", context.material("Soil"), panel=looks)
    bark = b.input("Bark", "MATERIAL", context.material("Bark"), panel=looks)
    foliage = b.input("Foliage", "MATERIAL", context.material("Foliage"), panel=looks)

    profile = [(0.0, 0.0, 0.0), (0.72, 0.0, 0.0), (0.78, 0.0, 0.08), (0.9, 0.0, 0.62), (0.97, 0.0, 0.9), (1.0, 0.0, 0.95), (1.0, 0.0, 1.0), (0.93, 0.0, 1.0), (0.92, 0.0, 0.94)]
    shaped = [b.combine(b.math("MULTIPLY", point[0], pot_radius), 0.0, b.math("MULTIPLY", point[2], pot_height)) for point in profile]
    pot = b.smooth(lathe(b, shaped, 48))
    soil = b.node("GeometryNodeMeshCircle", props={"fill_type": "NGON"}, Vertices=48, Radius=b.math("MULTIPLY", pot_radius, 0.9)).out
    soil = b.transform(soil, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", pot_height, 0.93)))
    tree = b.group(
        context.require("Branching Tree"),
        Height=tree_height,
        Trunk_Radius=b.math("MULTIPLY", tree_height, 0.035),
        Trunk_Bend=0.12,
        Limb_Count=limb_count,
        Limb_Start=0.3,
        Limb_Length=b.math("MULTIPLY", spread, 0.8),
        Limb_Rise=limb_rise,
        Limb_Droop=0.05,
        Twig_Count=3,
        Twig_Length=b.math("MULTIPLY", spread, 0.35),
        Pad_Width=b.math("MULTIPLY", spread, 0.32),
        Pad_Height=b.math("MULTIPLY", spread, 0.22),
        Pad_Density=pad_density,
        Clump_Size=clump,
        Crown_Pad_Scale=1.6,
        Seed=seed,
        Bark=bark,
        Foliage=foliage,
    ).out
    tree = b.transform(tree, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", pot_height, 0.93)))
    b.output("Geometry", "GEOMETRY", b.join(b.set_material(pot, pot_material), b.set_material(soil, soil_material), tree))
