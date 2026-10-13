from rain_garden.shapes import circle_profile, rectangle_profile, sweep, vertical_ribbon

GROUP_NAME = "Glass Railing"
CATEGORY = "Architecture"
DESCRIPTION = "Frameless glass balustrade following the input curve: base shoe, vertical thin-wall glass ribbon, plumb posts at even spacing and a round handrail."


def build(b, context):
    curve = b.input("Curve", "GEOMETRY")
    height = b.input("Height", "FLOAT", 1.1, 0.1, 5.0, "DISTANCE")
    post_spacing = b.input("Post Spacing", "FLOAT", 1.6, 0.1, 20.0, "DISTANCE")
    post_size = b.input("Post Size", "FLOAT", 0.055, 0.0, 1.0, "DISTANCE")
    rail_radius = b.input("Handrail Radius", "FLOAT", 0.03, 0.005, 0.5, "DISTANCE")
    shoe_height = b.input("Shoe Height", "FLOAT", 0.1, 0.0, 1.0, "DISTANCE")
    shoe_width = b.input("Shoe Width", "FLOAT", 0.07, 0.0, 1.0, "DISTANCE")
    frame = b.input("Frame Material", "MATERIAL", context.material("Dark Steel"))
    glass = b.input("Glass Material", "MATERIAL", context.material("Panel Glass"))

    length = b.node("GeometryNodeCurveLength", Curve=curve).out
    segments = b.math("MAXIMUM", b.math("CEIL", b.math("DIVIDE", length, post_spacing)), 1.0)
    even = b.node("GeometryNodeResampleCurve", Curve=curve, Mode="Count", Count=segments + 1.0).out

    handrail = b.curve_to_mesh(b.transform(even, translation=b.combine(0.0, 0.0, height)), circle_profile(b, rail_radius, 10), fill_caps=True)
    shoe = sweep(b, b.transform(even, translation=b.combine(0.0, 0.0, shoe_height * 0.5)), rectangle_profile(b, shoe_height, shoe_width))
    panel = vertical_ribbon(b, even, shoe_height, height - rail_radius)

    points = b.node("GeometryNodeCurveToPoints", props={"mode": "EVALUATED"}, Curve=even)
    tangent = points["Tangent"]
    heading = b.align_z(b.combine(tangent.x, tangent.y, 0.0), axis="X")
    post = b.node("GeometryNodeMeshCube", Size=b.combine(post_size, post_size, height)).out
    post = b.transform(post, translation=b.combine(0.0, 0.0, height * 0.5))
    posts = b.realize(b.instance(points["Points"], post, rotation=heading))

    metal = b.set_material(b.join(b.smooth(handrail), shoe, posts), frame)
    b.output("Geometry", "GEOMETRY", b.join(metal, b.set_material(panel, glass)))
