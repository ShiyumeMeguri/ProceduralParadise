from rain_garden.shapes import circle_profile, index_switch

GROUP_NAME = "Glass Whale Lens"
CATEGORY = "Water"
DESCRIPTION = "Closed biconvex glass lens shaped like a gliding whale: water-filled body, swept dorsal blade, pointed tail spike and a gold keel line. Long axis along local X, head toward -X."


def lens_outline(b, u, radius, length_ratio, taper, scale):
    angle = b.math("MULTIPLY", u, 6.283185307)
    cosine = b.math("COSINE", angle)
    narrowing = b.math("POWER", b.math("MAXIMUM", b.math("MULTIPLY", b.math("SUBTRACT", 1.0, cosine), 0.5), 0.0), taper)
    x = b.math("MULTIPLY", b.math("MULTIPLY", cosine, b.math("MULTIPLY", radius, length_ratio)), scale)
    y = b.math("MULTIPLY", b.math("MULTIPLY", b.math("SINE", angle), b.math("MULTIPLY", radius, narrowing)), scale)
    return x, y


def lens_surface(b, segments, rings, radius, length_ratio, taper, thickness, exponent, scale, downward):
    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=segments + 1, Vertices_Y=rings).out
    position = b.position()
    u = b.math("ADD", position.x, 0.5)
    v = b.math("ADD", position.y, 0.5)
    x, y = lens_outline(b, u, radius, length_ratio, taper, b.math("MULTIPLY", v, scale))
    bulge = b.math("POWER", b.math("MAXIMUM", b.math("SUBTRACT", 1.0, b.math("MULTIPLY", v, v)), 0.0), exponent)
    z = b.math("MULTIPLY", b.math("MULTIPLY", thickness, scale), bulge)
    if downward:
        z = b.math("MULTIPLY", z, -1.0)
    placed = b.set_position(grid, position=b.combine(x, y, z))
    surface = b.node("GeometryNodeMergeByDistance", Geometry=placed, Distance=0.00001).out
    return surface if downward else b.node("GeometryNodeFlipFaces", Mesh=surface).out


def closed_lens(b, radius, length_ratio, taper, top, bottom, scale):
    upper = lens_surface(b, 128, 20, radius, length_ratio, taper, top, 0.5, scale, False)
    lower = lens_surface(b, 128, 20, radius, length_ratio, taper, bottom, 0.65, scale, True)
    return b.smooth(b.node("GeometryNodeMergeByDistance", Geometry=b.join(upper, lower), Distance=0.00001).out)


def build(b, context):
    shape = b.panel("Shape")
    radius = b.input("Radius", "FLOAT", 2.0, 0.05, 100.0, "DISTANCE", panel=shape)
    length_ratio = b.input("Length Ratio", "FLOAT", 2.2, 0.3, 10.0, panel=shape)
    taper = b.input("Taper", "FLOAT", 1.1, 0.0, 4.0, panel=shape)
    top = b.input("Top Thickness", "FLOAT", 0.55, 0.01, 20.0, "DISTANCE", panel=shape)
    bottom = b.input("Bottom Thickness", "FLOAT", 0.4, 0.01, 20.0, "DISTANCE", panel=shape)
    fin_size = b.input("Fin Size", "FLOAT", 1.2, 0.0, 30.0, "DISTANCE", panel=shape)
    fin_position = b.input("Fin Position", "FLOAT", -0.15, -1.0, 1.0, "FACTOR", panel=shape)
    fin_thickness = b.input("Fin Thickness", "FLOAT", 0.06, 0.001, 2.0, "DISTANCE", panel=shape)
    tail_length = b.input("Tail Length", "FLOAT", 0.9, 0.0, 30.0, "DISTANCE", panel=shape)
    keel_radius = b.input("Keel Radius", "FLOAT", 0.03, 0.0, 1.0, "DISTANCE", panel=shape)
    looks = b.panel("Materials")
    glass = b.input("Glass", "MATERIAL", context.material("Iridescent Glass"), panel=looks)
    water = b.input("Water", "MATERIAL", context.material("Water"), panel=looks)
    keel_material = b.input("Keel", "MATERIAL", context.material("Gold Trim"), panel=looks)

    body = closed_lens(b, radius, length_ratio, taper, top, bottom, 1.0)
    core = closed_lens(b, radius, length_ratio, taper, top, bottom, 0.965)

    half_length = b.math("MULTIPLY", radius, length_ratio)
    fin_points = [
        (0.0, 0.0, 0.0), (0.45, 0.2, 0.0), (0.95, 0.52, 0.0), (1.4, 0.86, 0.0), (1.75, 1.08, 0.0), (1.42, 0.62, 0.0), (1.12, 0.26, 0.0), (0.9, 0.04, 0.0),
    ]
    fin_line = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=len(fin_points)).out
    fin_line = b.set_position(fin_line, position=b.vmath("SCALE", index_switch(b, b.index(), fin_points), fin_size))
    fin_curve = b.node("GeometryNodeSetSplineCyclic", Curve=b.node("GeometryNodeMeshToCurve", Mesh=fin_line).out, Cyclic=True).out
    fin_curve = b.node("GeometryNodeCurveSplineType", props={"spline_type": "CATMULL_ROM"}, Curve=fin_curve).out
    fin_curve = b.node("GeometryNodeResampleCurve", Curve=fin_curve, Mode="Count", Count=48).out
    fin_face = b.node("GeometryNodeFillCurve", Curve=fin_curve, Mode="N-gons").out
    fin_face = b.node("GeometryNodeFlipFaces", Mesh=fin_face, Selection=b.compare(b.normal().z, 0.0, "LESS_THAN")).out
    fin_solid = b.node("GeometryNodeExtrudeMesh", props={"mode": "FACES"}, Mesh=fin_face, Offset=b.combine(0.0, 0.0, fin_thickness), Individual=False).out
    fin_solid = b.join(fin_solid, b.node("GeometryNodeFlipFaces", Mesh=fin_face).out)
    fin_solid = b.transform(fin_solid, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", fin_thickness, -0.5)))
    fin_anchor = b.combine(b.math("MULTIPLY", fin_position, half_length), 0.0, b.math("MULTIPLY", top, 0.8))
    fin = b.transform(fin_solid, translation=fin_anchor, rotation=(1.5708, 0.0, 0.0))

    tail = b.node("GeometryNodeMeshCone", Vertices=16, Radius_Bottom=b.math("MULTIPLY", radius, 0.08), Radius_Top=0.0, Depth=tail_length)["Mesh"]
    tail = b.transform(tail, translation=b.combine(b.math("ADD", b.math("MULTIPLY", half_length, 0.82), b.math("MULTIPLY", tail_length, 0.5)), 0.0, 0.0), rotation=(0.0, 1.5708, 0.0))

    rim = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=128, Radius=1.0)["Curve"]
    parameter = b.node("GeometryNodeSplineParameter")["Factor"]
    rim_x, rim_y = lens_outline(b, parameter, radius, length_ratio, taper, 1.003)
    rim = b.set_position(rim, position=b.combine(rim_x, rim_y, b.math("MULTIPLY", keel_radius, -0.5)))
    keel = b.smooth(b.curve_to_mesh(rim, circle_profile(b, keel_radius, 8)))

    result = b.join(
        b.set_material(b.join(body, b.smooth(fin), b.smooth(tail)), glass),
        b.set_material(core, water),
        b.set_material(keel, keel_material),
    )
    b.output("Geometry", "GEOMETRY", result)
