GROUP_NAME = "Waterfall Curtain"
CATEGORY = "Water"
DESCRIPTION = "Falling water sheet hanging from a lip at the origin: widens as it falls, drifts forward along +Y, can curl into a tube, and carries a fall_uv attribute that drives streaked water shading."


def build(b, context):
    width = b.input("Width", "FLOAT", 2.0, 0.01, 100.0, "DISTANCE")
    spread = b.input("Spread", "FLOAT", 1.6, 0.1, 20.0)
    length = b.input("Length", "FLOAT", 12.0, 0.05, 500.0, "DISTANCE")
    throw = b.input("Throw", "FLOAT", 0.4, -50.0, 50.0, "DISTANCE")
    curl = b.input("Curl", "FLOAT", 0.25, 0.0, 1.0, "FACTOR")
    twist = b.input("Twist", "FLOAT", 0.0, -50.0, 50.0, "ANGLE")
    turbulence = b.input("Turbulence", "FLOAT", 0.18, 0.0, 10.0, "DISTANCE")
    ripple_scale = b.input("Ripple Scale", "FLOAT", 0.6, 0.0, 50.0)
    columns = b.input("Columns", "INT", 48, 3, 1000)
    rows = b.input("Rows", "INT", 96, 3, 4000)
    seed = b.input("Seed", "INT", 1, 0, 100000)
    material = b.input("Material", "MATERIAL", context.material("Waterfall"))

    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=columns, Vertices_Y=rows).out
    position = b.position()
    u = position.x
    v = b.math("SUBTRACT", 0.5, position.y)
    local_width = b.math("MULTIPLY", width, b.math("ADD", 1.0, b.math("MULTIPLY", b.math("SUBTRACT", spread, 1.0), b.math("POWER", v, 0.7))))
    bend = b.math("MAXIMUM", curl, 0.001)
    angle = b.math("MULTIPLY", u, b.math("MULTIPLY", bend, 6.283185307))
    bend_radius = b.math("DIVIDE", local_width, b.math("MULTIPLY", bend, 6.283185307))
    x = b.math("MULTIPLY", b.math("SINE", angle), bend_radius)
    y = b.math("SUBTRACT", b.math("MULTIPLY", bend_radius, b.math("SUBTRACT", 1.0, curl)), b.math("MULTIPLY", b.math("COSINE", angle), bend_radius))
    spin = b.math("MULTIPLY", twist, v)
    twisted_x = b.math("SUBTRACT", b.math("MULTIPLY", x, b.math("COSINE", spin)), b.math("MULTIPLY", y, b.math("SINE", spin)))
    twisted_y = b.math("ADD", b.math("MULTIPLY", x, b.math("SINE", spin)), b.math("MULTIPLY", y, b.math("COSINE", spin)))
    y = b.math("ADD", twisted_y, b.math("MULTIPLY", throw, b.math("SQRT", v)))
    z = b.math("MULTIPLY", length, b.math("MULTIPLY", v, -1.0))
    base = b.combine(twisted_x, y, z)
    noise_coordinates = b.combine(b.math("MULTIPLY", u, 3.0), b.math("MULTIPLY", b.math("MULTIPLY", v, length), ripple_scale), b.math("MULTIPLY", seed, 1.37))
    wobble = b.node("ShaderNodeTexNoise", props={"noise_dimensions": "3D"}, Vector=noise_coordinates, Scale=1.0, Detail=3.0, Roughness=0.5)["Color"]
    wobble = b.vmath("SUBTRACT", wobble, (0.5, 0.5, 0.5))
    amplitude = b.math("MULTIPLY", turbulence, b.math("ADD", 0.25, v))
    displaced = b.vmath("ADD", base, b.vmath("SCALE", wobble, amplitude))
    sheet = b.set_position(grid, position=displaced)
    fall_uv = b.combine(b.math("MULTIPLY", u, local_width), b.math("MULTIPLY", v, length), 0.0)
    sheet = b.store(sheet, "fall_uv", fall_uv, data_type="FLOAT_VECTOR", domain="POINT")
    sheet = b.node("GeometryNodeMergeByDistance", Geometry=sheet, Distance=0.00001).out
    b.output("Geometry", "GEOMETRY", b.set_material(b.smooth(sheet), material))
