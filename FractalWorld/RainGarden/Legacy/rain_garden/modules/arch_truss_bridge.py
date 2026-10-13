import math

from rain_garden.shapes import rectangle_profile, sweep

GROUP_NAME = "Arch Truss Bridge"
CATEGORY = "Architecture"
DESCRIPTION = "Circular arch footbridge spanning local X with its crown on +Z: curved deck, twin Warren side trusses hanging below it and glass railings on the deck edges."


def arc_polyline(b, count, center_z, start_angle, sweep_angle, y, radius_even, radius_odd):
    line = b.node("GeometryNodeMeshLine", props={"mode": "OFFSET"}, Count=count).out
    index = b.index()
    t = b.math("DIVIDE", index, b.math("SUBTRACT", count, 1.0))
    angle = b.math("ADD", start_angle, b.math("MULTIPLY", sweep_angle, t))
    odd = b.math("MODULO", index, 2.0)
    radius = b.mix(odd, radius_even, radius_odd)
    position = b.combine(b.math("MULTIPLY", b.math("COSINE", angle), radius), y, b.math("ADD", center_z, b.math("MULTIPLY", b.math("SINE", angle), radius)))
    placed = b.set_position(line, position=position)
    return b.node("GeometryNodeMeshToCurve", Mesh=placed).out


def build(b, context):
    span = b.input("Span", "FLOAT", 40.0, 1.0, 500.0, "DISTANCE")
    rise = b.input("Rise", "FLOAT", 18.0, 0.1, 300.0, "DISTANCE")
    deck_width = b.input("Deck Width", "FLOAT", 2.6, 0.3, 30.0, "DISTANCE")
    deck_thickness = b.input("Deck Thickness", "FLOAT", 0.45, 0.05, 5.0, "DISTANCE")
    truss_depth = b.input("Truss Depth", "FLOAT", 1.3, 0.1, 10.0, "DISTANCE")
    bays = b.input("Truss Bays", "INT", 48, 2, 1000)
    chord = b.input("Chord Size", "FLOAT", 0.16, 0.01, 2.0, "DISTANCE")
    web = b.input("Web Size", "FLOAT", 0.08, 0.005, 1.0, "DISTANCE")
    railing_height = b.input("Railing Height", "FLOAT", 1.05, 0.0, 3.0, "DISTANCE")
    steel = b.input("Steel", "MATERIAL", context.material("White Steel"))
    glass = b.input("Railing Glass", "MATERIAL", context.material("Panel Glass"))

    half = span * 0.5
    center_z = b.math("DIVIDE", b.math("SUBTRACT", b.math("MULTIPLY", rise, rise), b.math("MULTIPLY", half, half)), b.math("MULTIPLY", rise, 2.0))
    radius = b.math("SUBTRACT", rise, center_z)
    start_angle = b.math("ARCTAN2", b.math("MULTIPLY", center_z, -1.0), half)
    sweep_angle = b.math("SUBTRACT", math.pi, b.math("MULTIPLY", start_angle, 2.0))
    resolution = b.math("ADD", b.math("MULTIPLY", bays, 2.0), 1.0)

    deck_arc = arc_polyline(b, resolution, center_z, start_angle, sweep_angle, 0.0, radius, radius)
    deck = sweep(b, deck_arc, rectangle_profile(b, deck_width, deck_thickness), up=(0.0, 1.0, 0.0))

    top_radius = b.math("SUBTRACT", radius, b.math("MULTIPLY", deck_thickness, 0.5))
    bottom_radius = b.math("SUBTRACT", radius, truss_depth)
    parts = [deck]
    for side in (-1.0, 1.0):
        y = b.math("MULTIPLY", b.math("SUBTRACT", b.math("MULTIPLY", deck_width, 0.5), b.math("MULTIPLY", chord, 0.5)), side)
        bottom = arc_polyline(b, resolution, center_z, start_angle, sweep_angle, y, bottom_radius, bottom_radius)
        parts.append(sweep(b, bottom, rectangle_profile(b, chord, chord), up=(0.0, 1.0, 0.0)))
        zigzag = arc_polyline(b, resolution, center_z, start_angle, sweep_angle, y, top_radius, bottom_radius)
        parts.append(sweep(b, zigzag, rectangle_profile(b, web, web), up=(0.0, 1.0, 0.0)))

    steelwork = b.set_material(b.join(*parts), steel)
    railing_group = context.require("Glass Railing")
    rail_radius = b.math("ADD", radius, b.math("MULTIPLY", deck_thickness, 0.5))
    railings = []
    for side in (-1.0, 1.0):
        y = b.math("MULTIPLY", b.math("SUBTRACT", b.math("MULTIPLY", deck_width, 0.5), 0.08), side)
        path = arc_polyline(b, resolution, center_z, start_angle, sweep_angle, y, rail_radius, rail_radius)
        railings.append(b.group(railing_group, Curve=path, Height=railing_height, Post_Spacing=1.8, Frame_Material=steel, Glass_Material=glass).out)
    b.output("Geometry", "GEOMETRY", b.join(steelwork, *railings))
