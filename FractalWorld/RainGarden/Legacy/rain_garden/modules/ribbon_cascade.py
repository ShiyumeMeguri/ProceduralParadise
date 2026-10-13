GROUP_NAME = "Ribbon Cascade"
CATEGORY = "Water"
DESCRIPTION = "Row of twisted water ribbons spilling from an edge along local +X, each with its own width, drop length and turn."


def build(b, context):
    length = b.input("Length", "FLOAT", 20.0, 0.1, 500.0, "DISTANCE")
    count = b.input("Count", "INT", 14, 1, 500)
    width = b.input("Ribbon Width", "FLOAT", 0.35, 0.01, 10.0, "DISTANCE")
    drop = b.input("Drop", "FLOAT", 3.0, 0.05, 100.0, "DISTANCE")
    twist = b.input("Twist", "FLOAT", 3.2, -50.0, 50.0, "ANGLE")
    seed = b.input("Seed", "INT", 12, 0, 100000)
    material = b.input("Material", "MATERIAL", context.material("Water Ribbon"))

    ribbon = b.group(context.require("Waterfall Curtain"), Width=1.0, Spread=1.25, Length=1.0, Throw=0.0, Curl=0.35, Twist=twist, Turbulence=0.02, Ripple_Scale=4.0, Columns=10, Rows=48, Seed=seed, Material=material).out
    points = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=count, Offset=b.combine(b.math("DIVIDE", length, b.math("MAXIMUM", b.math("SUBTRACT", count, 1.0), 1.0)), 0.0, 0.0)).out
    index = b.index()
    jitter = b.random(-0.35, 0.35, seed, identifier=index)
    spacing = b.math("DIVIDE", length, b.math("MAXIMUM", count, 1.0))
    points = b.set_position(points, offset=b.combine(b.math("MULTIPLY", jitter, spacing), 0.0, 0.0))
    ribbon_width = b.math("MULTIPLY", width, b.random(0.6, 1.5, b.math("ADD", seed, 1), identifier=index))
    ribbon_drop = b.math("MULTIPLY", drop, b.random(0.55, 1.1, b.math("ADD", seed, 2), identifier=index))
    turn = b.random(-0.6, 0.6, b.math("ADD", seed, 3), identifier=index)
    ribbons = b.instance(points, ribbon, rotation=b.euler(b.combine(0.0, 0.0, turn)), scale=b.combine(ribbon_width, ribbon_width, ribbon_drop))
    b.output("Geometry", "GEOMETRY", b.realize(ribbons))
