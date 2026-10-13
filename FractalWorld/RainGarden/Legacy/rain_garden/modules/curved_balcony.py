from rain_garden.shapes import rectangle_profile, sweep

GROUP_NAME = "Curved Balcony"
CATEGORY = "Architecture"
DESCRIPTION = "Half-elliptic balcony projecting toward local -Y from a wall on the XZ plane: crescent slab around a glass-bottomed pool, curved glass railing, fascia band and a hanging glass basin beneath."


def half_ellipse(b, radius_x, radius_y, height, resolution):
    line = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=resolution).out
    t = b.math("DIVIDE", b.index(), resolution - 1)
    angle = b.math("MULTIPLY", t, 3.14159265)
    position = b.combine(b.math("MULTIPLY", b.math("COSINE", angle), radius_x), b.math("MULTIPLY", b.math("SINE", angle), b.math("MULTIPLY", radius_y, -1.0)), height)
    return b.node("GeometryNodeMeshToCurve", Mesh=b.set_position(line, position=position)).out


def build(b, context):
    radius_x = b.input("Width Radius", "FLOAT", 6.0, 0.2, 100.0, "DISTANCE")
    radius_y = b.input("Depth Radius", "FLOAT", 4.0, 0.2, 100.0, "DISTANCE")
    ring_width = b.input("Ring Width", "FLOAT", 1.4, 0.1, 50.0, "DISTANCE")
    thickness = b.input("Slab Thickness", "FLOAT", 0.45, 0.05, 5.0, "DISTANCE")
    railing_height = b.input("Railing Height", "FLOAT", 1.1, 0.0, 3.0, "DISTANCE")
    basin_depth = b.input("Basin Depth", "FLOAT", 1.3, 0.05, 20.0, "DISTANCE")
    stone = b.input("Stone", "MATERIAL", context.material("White Stone"))
    frame = b.input("Railing Frame", "MATERIAL", context.material("Dark Steel"))
    glass = b.input("Railing Glass", "MATERIAL", context.material("Panel Glass"))

    resolution = 64
    outer = half_ellipse(b, radius_x, radius_y, 0.0, resolution)
    inner = half_ellipse(b, b.math("SUBTRACT", radius_x, ring_width), b.math("SUBTRACT", radius_y, ring_width), 0.0, resolution)
    crescent = b.node("GeometryNodeFillCurve", Curve=b.join(b.node("GeometryNodeSetSplineCyclic", Curve=outer, Cyclic=True).out, b.node("GeometryNodeSetSplineCyclic", Curve=inner, Cyclic=True).out), Mode="Triangles").out
    crescent = b.node("GeometryNodeFlipFaces", Mesh=crescent, Selection=b.compare(b.normal().z, 0.0, "LESS_THAN")).out
    lowered = b.transform(crescent, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", thickness, -1.0)))
    slab = b.node("GeometryNodeExtrudeMesh", props={"mode": "FACES"}, Mesh=lowered, Offset=b.combine(0.0, 0.0, thickness), Individual=False).out
    slab = b.join(slab, b.node("GeometryNodeFlipFaces", Mesh=lowered).out)
    fascia = sweep(b, b.transform(outer, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", thickness, -0.5))), rectangle_profile(b, b.math("MULTIPLY", thickness, 1.3), 0.12), up=(0.0, 0.0, 1.0))

    railing_path = half_ellipse(b, b.math("SUBTRACT", radius_x, 0.12), b.math("SUBTRACT", radius_y, 0.12), 0.0, resolution)
    railing = b.group(context.require("Glass Railing"), Curve=railing_path, Height=railing_height, Frame_Material=frame, Glass_Material=glass).out

    basin_radius_y = b.math("MULTIPLY", b.math("SUBTRACT", radius_y, ring_width), 0.98)
    basin = b.group(context.require("Floating Disc Basin"), Radius=basin_radius_y, Length_Ratio=b.math("DIVIDE", b.math("SUBTRACT", radius_x, ring_width), b.math("SUBTRACT", radius_y, ring_width)), Taper=0.0, Depth=basin_depth, Water_Level=0.12, Rim_Radius=0.04, Rim_Gap=0.08, Foam_Density=300.0, Glitter_Density=40.0).out
    basin = b.transform(basin, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", thickness, -0.3)))
    half_mask = b.compare(b.position().y, 0.0, "GREATER_THAN")
    basin = b.node("GeometryNodeDeleteGeometry", props={"domain": "FACE"}, Geometry=basin, Selection=half_mask).out

    b.output("Geometry", "GEOMETRY", b.join(b.set_material(b.join(slab, fascia), stone), railing, basin))
