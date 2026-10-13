from rain_garden.shapes import lathe

GROUP_NAME = "Ornate Lantern"
CATEGORY = "Lights"
DESCRIPTION = "Hanging bronze lantern on a chain: finial, onion cap, gold rings, glowing octagonal glass body with frame bars, pointed base and strands of glass drops below. Origin at the chain's anchor."

FINIAL = [(0.0, 3.05), (0.04, 2.95), (0.03, 2.85), (0.09, 2.78), (0.1, 2.7), (0.06, 2.62), (0.05, 2.55)]
CAP = [(0.05, 2.55), (0.2, 2.45), (0.38, 2.3), (0.52, 2.12), (0.6, 1.98), (0.64, 1.9), (0.58, 1.86)]
TOP_RING = [(0.58, 1.86), (0.62, 1.82), (0.6, 1.76), (0.52, 1.74)]
BODY = [(0.5, 1.74), (0.55, 1.4), (0.5, 0.95)]
BOTTOM_RING = [(0.52, 0.95), (0.62, 0.9), (0.6, 0.82), (0.45, 0.78)]
BASE = [(0.45, 0.78), (0.3, 0.6), (0.15, 0.4), (0.06, 0.2), (0.04, 0.1), (0.0, 0.0)]


def build(b, context):
    scale = b.input("Scale", "FLOAT", 1.0, 0.05, 20.0)
    chain_length = b.input("Chain Length", "FLOAT", 12.0, 0.0, 500.0, "DISTANCE")
    strands = b.input("Drop Strands", "INT", 8, 0, 64)
    strand_length = b.input("Strand Length", "FLOAT", 1.2, 0.0, 20.0, "DISTANCE")
    seed = b.input("Seed", "INT", 6, 0, 100000)
    looks = b.panel("Materials")
    bronze = b.input("Bronze", "MATERIAL", context.material("Bronze"), panel=looks)
    gold = b.input("Gold", "MATERIAL", context.material("Gold Trim"), panel=looks)
    glow = b.input("Glass", "MATERIAL", context.material("Lantern Glass"), panel=looks)
    drops = b.input("Drops", "MATERIAL", context.material("Crystal Cyan"), panel=looks)

    def part(points, segments=48):
        return b.smooth(lathe(b, [(radius, 0.0, height) for radius, height in points], segments))

    lantern_height = 3.05
    finial = part(FINIAL, 24)
    cap = part(CAP)
    rings = b.join(part(TOP_RING), part(BOTTOM_RING))
    body = lathe(b, [(radius, 0.0, height) for radius, height in BODY], 8)
    base = part(BASE)
    bar = b.node("GeometryNodeMeshCube", Size=(0.035, 0.035, 0.82)).out
    bar = b.transform(bar, translation=(0.0, 0.0, 1.345))
    bar_ring = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=b.node("GeometryNodeMeshCircle", Vertices=8, Radius=0.53).out).out
    bars = b.realize(b.instance(bar_ring, bar))

    strand_ring = b.node("GeometryNodeMeshCircle", Vertices=strands, Radius=0.5).out
    strand_points = b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=strand_ring).out
    strand_points = b.set_position(strand_points, offset=(0.0, 0.0, 0.85))
    pendant_group = context.require("Crystal Pendant")
    identifier = b.index()
    strand = b.group(pendant_group, Length=strand_length, Beads=4, Bead_Size=0.06, Bell_Size=0.0, Seed=seed, Glass=drops, Thread=bronze).out
    strand_scale = b.random(0.6, 1.3, seed, identifier=identifier)
    strands_mesh = b.realize(b.instance(strand_points, strand, scale=b.combine(1.0, 1.0, strand_scale)))
    central = b.group(pendant_group, Length=b.math("MULTIPLY", strand_length, 1.6), Beads=5, Bead_Size=0.08, Bell_Size=0.22, Tendrils=6, Seed=b.math("ADD", seed, 1), Glass=drops, Thread=bronze).out

    lantern = b.join(
        b.set_material(b.join(finial, cap, base, bars), bronze),
        b.set_material(rings, gold),
        b.set_material(body, glow),
        strands_mesh,
        central,
    )
    lantern = b.transform(lantern, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", lantern_height, -1.0)), scale=scale)
    lantern = b.transform(lantern, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", chain_length, -1.0)))
    chain = b.group(context.require("Hanging Chain"), Length=chain_length, Link_Length=b.math("MULTIPLY", 0.2, scale), Link_Width=b.math("MULTIPLY", 0.1, scale), Wire_Radius=b.math("MULTIPLY", 0.014, scale), Material=bronze).out
    b.output("Geometry", "GEOMETRY", b.join(chain, lantern))
