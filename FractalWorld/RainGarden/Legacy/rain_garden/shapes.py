def box(b, size, center=None):
    cube = b.node("GeometryNodeMeshCube", Size=size).out
    if center is None:
        return cube
    return b.transform(cube, translation=center)


def box_between(b, minimum, maximum):
    size = maximum - minimum
    center = (minimum + maximum) * 0.5
    return box(b, size, center)


def row_points(b, count, step, start=None):
    return b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=count, Start_Location=start, Offset=step).out


def count_for(b, length, spacing):
    return b.node("FunctionNodeFloatToInt", props={"rounding_mode": "FLOOR"}, Float=b.math("DIVIDE", length, spacing)).out + 1


def grid_points(b, size_x, size_y, count_x, count_y):
    grid = b.node("GeometryNodeMeshGrid", Size_X=size_x, Size_Y=size_y, Vertices_X=count_x, Vertices_Y=count_y).out
    return b.node("GeometryNodeMeshToPoints", props={"mode": "VERTICES"}, Mesh=grid).out


def rectangle_profile(b, width, height):
    return b.node("GeometryNodeCurvePrimitiveQuadrilateral", props={"mode": "RECTANGLE"}, Width=width, Height=height).out


def circle_profile(b, radius, resolution=12):
    return b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=resolution, Radius=radius)["Curve"]


def line_curve(b, start, end):
    return b.node("GeometryNodeCurvePrimitiveLine", props={"mode": "POINTS"}, Start=start, End=end).out


def sweep(b, curve, profile, up=(0.0, 0.0, 1.0), caps=True):
    framed = b.node("GeometryNodeSetCurveNormal", Curve=curve, Mode="Free", Normal=up).out
    return b.curve_to_mesh(framed, profile, fill_caps=caps)


def vertical_ribbon(b, curve, bottom, top):
    edges = b.curve_to_mesh(b.transform(curve, translation=b.combine(0.0, 0.0, bottom)))
    return b.node("GeometryNodeExtrudeMesh", props={"mode": "EDGES"}, Mesh=edges, Offset=b.combine(0.0, 0.0, top - bottom)).out


def index_switch(b, index, values, data_type="VECTOR"):
    handle = b.node("GeometryNodeIndexSwitch", props={"data_type": data_type})
    node = handle.node
    while len(node.index_switch_items) < len(values):
        node.index_switch_items.new()
    b.link(index, node.inputs[0])
    for position, value in enumerate(values):
        b.link(value, node.inputs[position + 1])
    return handle.out


def lathe(b, profile, segments=48, seam_distance=0.0005):
    count = len(profile)
    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=segments + 1, Vertices_Y=count).out
    position = b.position()
    u = b.math("ADD", position.x, 0.5)
    row = b.node("FunctionNodeFloatToInt", props={"rounding_mode": "ROUND"}, Float=b.math("MULTIPLY", b.math("ADD", position.y, 0.5), count - 1)).out
    point = index_switch(b, row, profile)
    radius = point.x
    angle = b.math("MULTIPLY", u, 6.283185307)
    placed = b.set_position(grid, position=b.combine(b.math("MULTIPLY", b.math("COSINE", angle), radius), b.math("MULTIPLY", b.math("SINE", angle), radius), point.z))
    return b.node("GeometryNodeMergeByDistance", Geometry=placed, Distance=seam_distance).out


def polyline(b, points):
    line = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=len(points)).out
    placed = b.set_position(line, position=index_switch(b, b.index(), points))
    return b.node("GeometryNodeMeshToCurve", Mesh=placed).out


def fill_at_height(b, curve, mode="N-gons", facing_up=True):
    filled = b.node("GeometryNodeFillCurve", Curve=curve, Mode=mode).out
    if facing_up:
        filled = b.node("GeometryNodeFlipFaces", Mesh=filled, Selection=b.compare(b.normal().z, 0.0, "LESS_THAN")).out
    height = b.node("GeometryNodeBoundBox", Geometry=curve)["Min"]
    return b.transform(filled, translation=b.combine(0.0, 0.0, height.z))


def object_geometry(b, obj):
    return b.node("GeometryNodeObjectInfo", props={"transform_space": "RELATIVE"}, Object=obj)["Geometry"]


def resample_length(b, curve, length):
    return b.node("GeometryNodeResampleCurve", Curve=curve, Mode="Length", Length=length).out


def points_along(b, curve, spacing):
    handle = b.node("GeometryNodeCurveToPoints", props={"mode": "LENGTH"}, Curve=curve, Length=spacing)
    return handle["Points"], handle["Rotation"], handle["Tangent"]
