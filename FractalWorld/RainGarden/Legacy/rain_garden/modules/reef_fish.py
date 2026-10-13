GROUP_NAME = "Reef Fish"
CATEGORY = "Creatures"
DESCRIPTION = "Streamlined fish swimming along local +X: tapered lens body, forked tail, dorsal and pectoral fins; proportions stretch from a reef fish to a small whale."


def build(b, context):
    length = b.input("Length", "FLOAT", 0.6, 0.01, 50.0, "DISTANCE")
    height_ratio = b.input("Height Ratio", "FLOAT", 0.38, 0.05, 2.0)
    width_ratio = b.input("Width Ratio", "FLOAT", 0.16, 0.02, 2.0)
    tail_ratio = b.input("Tail Ratio", "FLOAT", 0.42, 0.0, 2.0)
    fin_ratio = b.input("Fin Ratio", "FLOAT", 0.3, 0.0, 2.0)
    tail_fork = b.input("Tail Fork", "FLOAT", 0.55, 0.0, 1.5, "ANGLE")
    bend = b.input("Bend", "FLOAT", 0.2, -2.0, 2.0)
    material = b.input("Material", "MATERIAL", context.material("Fish Cyan"))

    body = b.node("GeometryNodeMeshUVSphere", Segments=24, Rings=12, Radius=0.5).out
    position = b.position()
    taper = b.map_range(position.x, -0.5, 0.5, 0.35, 1.0)
    body = b.set_position(body, position=b.combine(position.x, b.math("MULTIPLY", position.y, taper), b.math("MULTIPLY", position.z, taper)))
    body = b.transform(body, scale=b.combine(length, b.math("MULTIPLY", length, width_ratio), b.math("MULTIPLY", length, height_ratio)))
    lobe = b.node("GeometryNodeMeshCone", Vertices=3, Radius_Bottom=1.0, Radius_Top=0.0, Depth=1.0)["Mesh"]
    lobe = b.transform(lobe, translation=(0.0, 0.0, 0.5))
    lobe = b.transform(lobe, scale=b.combine(0.25, 0.04, 1.0))
    tail_size = b.math("MULTIPLY", length, tail_ratio)
    upper_lobe = b.transform(lobe, translation=b.combine(b.math("MULTIPLY", length, -0.5), 0.0, 0.0), rotation=b.combine(0.0, b.math("SUBTRACT", -1.5708, b.math("MULTIPLY", tail_fork, -1.0)), 0.0), scale=tail_size)
    lower_lobe = b.transform(lobe, translation=b.combine(b.math("MULTIPLY", length, -0.5), 0.0, 0.0), rotation=b.combine(0.0, b.math("SUBTRACT", -1.5708, tail_fork), 0.0), scale=tail_size)
    fin_size = b.math("MULTIPLY", length, fin_ratio)
    dorsal = b.transform(lobe, translation=b.combine(b.math("MULTIPLY", length, -0.05), 0.0, b.math("MULTIPLY", length, b.math("MULTIPLY", height_ratio, 0.4))), rotation=(0.0, -0.9, 0.0), scale=fin_size)
    pectoral_left = b.transform(lobe, translation=b.combine(b.math("MULTIPLY", length, 0.12), b.math("MULTIPLY", length, b.math("MULTIPLY", width_ratio, 0.4)), b.math("MULTIPLY", length, -0.05)), rotation=(1.2, -1.9, 0.0), scale=b.math("MULTIPLY", fin_size, 0.6))
    pectoral_right = b.transform(lobe, translation=b.combine(b.math("MULTIPLY", length, 0.12), b.math("MULTIPLY", length, b.math("MULTIPLY", width_ratio, -0.4)), b.math("MULTIPLY", length, -0.05)), rotation=(-1.2, -1.9, 0.0), scale=b.math("MULTIPLY", fin_size, 0.6))
    fish = b.join(b.smooth(body), upper_lobe, lower_lobe, dorsal, pectoral_left, pectoral_right)
    swim = b.math("MULTIPLY", bend, b.math("MULTIPLY", b.position().x, b.position().x))
    fish = b.set_position(fish, offset=b.combine(0.0, b.math("DIVIDE", swim, b.math("MAXIMUM", length, 0.01)), 0.0))
    b.output("Geometry", "GEOMETRY", b.set_material(fish, material))
