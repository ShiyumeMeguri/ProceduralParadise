import math

from rain_garden.shapes import box_between, index_switch, rectangle_profile, row_points, sweep

GROUP_NAME = "Tower Pier"
CATEGORY = "Architecture"
DESCRIPTION = "Stone tower pier: front face on the local XZ plane facing -Y with a deep lancet window, corner pilaster with gold-inlaid panels, a dark mullioned glass curtain on the -X side and string courses."


def lancet_points(width, spring, samples):
    points = [(-width / 2, 0.0), (-width / 2, spring)]
    apex_angle = math.radians(60.0)
    for index in range(1, samples):
        angle = apex_angle * index / samples
        points.append((width / 2 - width * math.cos(angle), spring + width * math.sin(angle)))
    points.append((0.0, spring + width * math.sin(apex_angle)))
    for index in range(samples - 1, 0, -1):
        angle = apex_angle * index / samples
        points.append((-width / 2 + width * math.cos(angle), spring + width * math.sin(angle)))
    points.append((width / 2, spring))
    points.append((width / 2, 0.0))
    return points


def build(b, context):
    width = b.input("Width", "FLOAT", 14.0, 1.0, 200.0, "DISTANCE")
    depth = b.input("Depth", "FLOAT", 13.0, 1.0, 200.0, "DISTANCE")
    height = b.input("Height", "FLOAT", 48.0, 1.0, 500.0, "DISTANCE")
    window_offset = b.input("Window Offset", "FLOAT", 3.2, 0.0, 200.0, "DISTANCE")
    window_sill = b.input("Window Sill", "FLOAT", 7.5, 0.0, 200.0, "DISTANCE")
    window_width = b.input("Window Width", "FLOAT", 2.8, 0.2, 50.0, "DISTANCE")
    window_height = b.input("Window Height", "FLOAT", 6.9, 0.2, 100.0, "DISTANCE")
    pilaster = b.input("Pilaster Width", "FLOAT", 2.2, 0.1, 30.0, "DISTANCE")
    course_spacing = b.input("Course Spacing", "FLOAT", 6.0, 0.5, 100.0, "DISTANCE")
    curtain_mullion = b.input("Curtain Mullion Spacing", "FLOAT", 1.6, 0.1, 50.0, "DISTANCE")
    inlay_bottom = b.input("Inlay Bottom", "FLOAT", 6.0, 0.0, 500.0, "DISTANCE")
    inlay_top = b.input("Inlay Top", "FLOAT", 13.5, 0.0, 500.0, "DISTANCE")
    inlay_text = b.input("Inlay Text", "STRING", "LAYRE")
    band_bottom = b.input("Upper Band Bottom", "FLOAT", 22.0, 0.0, 500.0, "DISTANCE")
    band_text = b.input("Upper Band Text", "STRING", "AZURE")
    looks = b.panel("Materials")
    stone = b.input("Stone", "MATERIAL", context.material("White Stone"), panel=looks)
    curtain = b.input("Curtain Glass", "MATERIAL", context.material("Dark Glass Curtain"), panel=looks)
    metal = b.input("Mullion", "MATERIAL", context.material("Dark Steel"), panel=looks)
    window_light = b.input("Window Light", "MATERIAL", context.material("Window Light"), panel=looks)
    gold = b.input("Gold", "MATERIAL", context.material("Gold Trim"), panel=looks)
    inlay = b.input("Inlay Panel", "MATERIAL", context.material("Inlay Blue"), panel=looks)

    core = box_between(b, b.combine(0.0, 0.0, 0.0), b.combine(width, depth, height))
    pilaster_block = box_between(b, b.combine(-0.6, -0.6, 0.0), b.combine(pilaster, pilaster, b.math("ADD", height, 1.5)))
    courses = b.realize(b.instance(row_points(b, b.math("CEIL", b.math("DIVIDE", height, course_spacing)), b.combine(0.0, 0.0, course_spacing), b.combine(0.0, 0.0, course_spacing)), box_between(b, b.combine(-0.25, -0.25, -0.2), b.combine(width, depth, 0.2))))

    curtain_panel = box_between(b, b.combine(-0.08, pilaster, 0.0), b.combine(-0.02, depth, height))
    mullion = box_between(b, b.combine(-0.2, 0.0, 0.0), b.combine(-0.02, 0.12, height))
    mullion_count = b.math("CEIL", b.math("DIVIDE", b.math("SUBTRACT", depth, pilaster), curtain_mullion))
    mullions = b.realize(b.instance(row_points(b, mullion_count, b.combine(0.0, curtain_mullion, 0.0), b.combine(0.0, pilaster, 0.0)), mullion))

    outline = lancet_points(2.8, 4.5, 8)
    line = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=len(outline)).out
    line = b.set_position(line, position=index_switch(b, b.index(), [(x, 0.0, z) for x, z in outline]))
    lancet = b.node("GeometryNodeMeshToCurve", Mesh=line).out
    frame = sweep(b, lancet, rectangle_profile(b, 0.9, 0.55), up=(0.0, -1.0, 0.0))
    closed = b.node("GeometryNodeSetSplineCyclic", Curve=lancet, Cyclic=True).out
    pane = b.node("GeometryNodeFillCurve", Curve=b.transform(closed, rotation=(-1.5708, 0.0, 0.0)), Mode="N-gons").out
    pane = b.transform(pane, rotation=(1.5708, 0.0, 0.0), translation=(0.0, 0.9, 0.0))
    reveal = b.node("GeometryNodeExtrudeMesh", props={"mode": "EDGES"}, Mesh=b.curve_to_mesh(closed), Offset=(0.0, 0.9, 0.0)).out
    mullion_bar = box_between(b, b.combine(-0.09, 0.3, 0.0), b.combine(0.09, 0.45, 7.0))
    transom = box_between(b, b.combine(-1.4, 0.3, 4.4), b.combine(1.4, 0.45, 4.6))
    window_stone = b.join(frame, reveal, mullion_bar, transom)
    window = b.join(b.set_material(window_stone, stone), b.set_material(pane, window_light))
    window_scale = b.combine(b.math("DIVIDE", window_width, 2.8), 1.0, b.math("DIVIDE", window_height, 4.5 + 2.8 * math.sin(math.radians(60.0))))
    window = b.transform(window, translation=b.combine(window_offset, -0.2, window_sill), scale=window_scale)

    inlay_height = b.math("SUBTRACT", inlay_top, inlay_bottom)
    inlay_middle = b.math("MULTIPLY", b.math("ADD", inlay_top, inlay_bottom), 0.5)
    inlay_panel = box_between(b, b.combine(0.25, -0.75, inlay_bottom), b.combine(b.math("SUBTRACT", pilaster, 0.25), -0.62, inlay_top))
    inlay_frame = sweep(b, b.node("GeometryNodeCurvePrimitiveQuadrilateral", props={"mode": "RECTANGLE"}, Width=b.math("SUBTRACT", pilaster, 0.4), Height=inlay_height).out, rectangle_profile(b, 0.08, 0.08), up=(0.0, 0.0, 1.0))
    inlay_frame = b.transform(inlay_frame, rotation=(1.5708, 0.0, 0.0), translation=b.combine(b.math("MULTIPLY", pilaster, 0.5), -0.78, inlay_middle))
    ornament = b.node("GeometryNodeStringToCurves", String=inlay_text, Size=b.math("MULTIPLY", pilaster, 0.32), Align_X="Center", Align_Y="Middle")["Curve Instances"]
    ornament = b.curve_to_mesh(b.realize(ornament), b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=6, Radius=0.03)["Curve"])
    ornament = b.transform(ornament, rotation=(1.5708, 1.5708, 0.0), translation=b.combine(b.math("MULTIPLY", pilaster, 0.5), -0.8, inlay_middle))

    band_panel = box_between(b, b.combine(pilaster, -0.7, band_bottom), b.combine(width, -0.05, height))
    band_middle = b.math("MULTIPLY", b.math("ADD", band_bottom, height), 0.5)
    band_glyphs = b.node("GeometryNodeStringToCurves", String=band_text, Size=b.math("MULTIPLY", b.math("SUBTRACT", height, band_bottom), 0.35), Align_X="Center", Align_Y="Middle")["Curve Instances"]
    band_glyphs = b.curve_to_mesh(b.realize(band_glyphs), b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=6, Radius=0.06)["Curve"])
    band_glyphs = b.transform(band_glyphs, rotation=(1.5708, 0.0, 0.0), translation=b.combine(b.math("MULTIPLY", b.math("ADD", width, pilaster), 0.5), -0.75, band_middle))

    result = b.join(
        b.set_material(b.join(core, pilaster_block, courses), stone),
        b.set_material(curtain_panel, curtain),
        b.set_material(mullions, metal),
        window,
        b.set_material(b.join(inlay_panel, band_panel), inlay),
        b.set_material(b.join(inlay_frame, ornament, band_glyphs), gold),
    )
    b.output("Geometry", "GEOMETRY", result)
