GROUP_NAME = "Fish School"
CATEGORY = "Creatures"
DESCRIPTION = "Scatters a mixed school of reef fish, small mantas and jellyfish through a box volume above the origin, heading along local +X with jitter."


def build(b, context):
    size = b.input("Box Size", "VECTOR", (20.0, 4.0, 12.0), subtype="XYZ")
    count = b.input("Count", "INT", 60, 0, 10000)
    min_scale = b.input("Min Scale", "FLOAT", 0.6, 0.01, 50.0)
    max_scale = b.input("Max Scale", "FLOAT", 1.4, 0.01, 50.0)
    heading_jitter = b.input("Heading Jitter", "FLOAT", 0.6, 0.0, 3.14159, "ANGLE")
    manta_ratio = b.input("Manta Ratio", "FLOAT", 0.25, 0.0, 1.0, "FACTOR")
    jelly_ratio = b.input("Jelly Ratio", "FLOAT", 0.15, 0.0, 1.0, "FACTOR")
    seed = b.input("Seed", "INT", 8, 0, 100000)

    fish_group = context.require("Reef Fish")
    variants = [
        b.group(fish_group, Length=0.55, Material=context.material("Fish Cyan")).out,
        b.group(fish_group, Length=0.45, Height_Ratio=0.45, Material=context.material("Fish Gold")).out,
        b.group(fish_group, Length=0.5, Height_Ratio=0.5, Material=context.material("Fish Pink")).out,
        b.group(context.require("Manta Ray"), Wingspan=1.4, Length=0.8, Thickness=0.08, Tail_Length=0.6, Back=context.material("Fish Cyan"), Belly=context.material("Manta Belly")).out,
        b.group(context.require("Jellyfish"), Size=0.35, Tentacle_Length=1.0, Tentacles=8).out,
    ]
    library = b.join(*[b.node("GeometryNodeGeometryToInstance", Geometry=variant).out for variant in variants])

    points = b.node("GeometryNodePoints", Count=count).out
    index = b.index()
    unit = b.random((-0.5, -0.5, 0.0), (0.5, 0.5, 1.0), seed, data_type="FLOAT_VECTOR", identifier=index)
    points = b.set_position(points, position=b.vmath("MULTIPLY", unit, size))
    roll = b.random(0.0, 1.0, b.math("ADD", seed, 1), identifier=index)
    pick_fish = b.node("FunctionNodeFloatToInt", props={"rounding_mode": "FLOOR"}, Float=b.random(0.0, 2.999, b.math("ADD", seed, 2), identifier=index)).out
    is_manta = b.compare(roll, manta_ratio, "LESS_THAN")
    is_jelly = b.boolean("AND", b.compare(roll, b.math("ADD", manta_ratio, jelly_ratio), "LESS_THAN"), b.boolean("NOT", is_manta))
    choice = b.switch(is_manta, pick_fish, 3, input_type="INT")
    choice = b.switch(is_jelly, choice, 4, input_type="INT")
    yaw = b.random(b.math("MULTIPLY", heading_jitter, -1.0), heading_jitter, b.math("ADD", seed, 3), identifier=index)
    pitch = b.random(-0.25, 0.25, b.math("ADD", seed, 4), identifier=index)
    bank = b.random(-0.3, 0.3, b.math("ADD", seed, 5), identifier=index)
    scale = b.random(min_scale, max_scale, b.math("ADD", seed, 6), identifier=index)
    school = b.instance(points, library, rotation=b.euler(b.combine(bank, pitch, yaw)), scale=scale, pick=True, instance_index=choice)
    b.output("Geometry", "GEOMETRY", school)
