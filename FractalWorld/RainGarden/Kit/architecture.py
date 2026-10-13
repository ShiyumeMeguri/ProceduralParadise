"""
Architecture kit -- geometry-node groups (``RainGarden.Architecture.*``):
the stone, steel and glass of the garden's halls.

Local frames: facades run along local +X and face local -Y; things that
stand rest on z = 0; curve-driven pieces (railings, galleries) follow the
``Curve`` they are given, slabs the outline curve object they read.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, set_menu
from . import materials as M
from .shapes import box, count_for, euler, fill_at_height, framed_sweep, hanging_ribbon, held_normal

QUARTER = math.pi * 0.5


def mesh_to_curve(graph, mesh):
    return graph.n("GeometryNodeMeshToCurve", mesh).o


def cyclic(graph, curve):
    return graph.n("GeometryNodeSetSplineCyclic", curve, Cyclic=True).o


def flip_down_faces(graph, mesh):
    return graph.n("GeometryNodeFlipFaces", mesh, Selection=graph.compare(graph.normal().z, 0.0, "LESS_THAN")).o


def row(graph, count, step, start=(0.0, 0.0, 0.0)):
    return graph.mesh_line(count, start, step)


def text_tube(graph, text, size, radius):
    """Glyph outlines of ``text`` (centred on the origin in XY) as thin
    tubes of ``radius``."""
    node = graph.n("GeometryNodeStringToCurves", String=text, Size=size)
    set_menu(graph._in_socket(node.n, "Align X"), "Center")
    set_menu(graph._in_socket(node.n, "Align Y"), "Middle")
    return graph.sweep(graph.realize(node["Curve Instances"]), graph.circle(radius, 6), False)


@asset("RainGarden.Architecture.Block", "Architecture")
def block():
    """Axis-aligned box whose origin sits at the centre of its bottom face."""
    graph = GN("RainGarden.Architecture.Block", block.__doc__)
    size = graph.inp("Size", "VECTOR", (2.0, 2.0, 2.0), subtype="XYZ")
    material = graph.inp("Material", "MATERIAL", default=M.get("RainGarden.WhiteStone"))
    graph.result(graph.mat(box(graph, size, graph.vec(0.0, 0.0, size.z * 0.5)), material))
    return graph


@asset("RainGarden.Architecture.OutlineSlab", "Architecture")
def outline_slab():
    """Closed outline curve (an object) filled and extruded downward into a
    solid floor slab; the curve's height is the top surface."""
    graph = GN("RainGarden.Architecture.OutlineSlab", outline_slab.__doc__)
    outline = graph.inp("Outline", "OBJECT")
    thickness = graph.inp("Thickness", "FLOAT", 0.4, 0.0, 200.0, "DISTANCE")
    material = graph.inp("Material", "MATERIAL", default=M.get("RainGarden.WhiteStone"))
    top = fill_at_height(graph, graph.object_info(outline, relative=True)["Geometry"])
    solid = graph.solid(graph.move(top, z=-thickness), thickness)
    graph.result(graph.mat(graph.smooth(solid, False), material))
    return graph


@asset("RainGarden.Architecture.CurtainWall", "Architecture")
def curtain_wall():
    """Glazed curtain wall in the local XZ plane facing -Y: a glass skin
    behind a grid of vertical mullions and horizontal transoms."""
    graph = GN("RainGarden.Architecture.CurtainWall", curtain_wall.__doc__)
    width = graph.inp("Width", "FLOAT", 6.0, 0.1, 500.0, "DISTANCE")
    height = graph.inp("Height", "FLOAT", 30.0, 0.1, 500.0, "DISTANCE")
    mullion_spacing = graph.inp("Mullion Spacing", "FLOAT", 1.5, 0.05, 50.0, "DISTANCE")
    transom_spacing = graph.inp("Transom Spacing", "FLOAT", 4.0, 0.05, 100.0, "DISTANCE")
    member = graph.inp("Member Size", "FLOAT", 0.1, 0.005, 2.0, "DISTANCE")
    depth = graph.inp("Member Depth", "FLOAT", 0.25, 0.005, 5.0, "DISTANCE")
    glass = graph.inp("Glass", "MATERIAL", default=M.get("RainGarden.DarkGlassCurtain"))
    metal = graph.inp("Frame", "MATERIAL", default=M.get("RainGarden.DarkSteel"))
    skin = graph.box(0.0, 0.0, 0.0, width, 0.04, height)
    mullion = graph.box(member * -0.5, -depth, 0.0, member * 0.5, 0.0, height)
    transom = graph.box(0.0, -depth, member * -0.5, width, 0.0, member * 0.5)
    mullions = graph.iop(row(graph, count_for(graph, width, mullion_spacing), graph.vec(mullion_spacing, 0.0, 0.0)), mullion)
    transoms = graph.iop(row(graph, count_for(graph, height, transom_spacing), graph.vec(0.0, 0.0, transom_spacing)), transom)
    graph.result(graph.join(graph.mat(skin, glass), graph.mat(graph.realize(graph.join(mullions, transoms)), metal)))
    return graph


@asset("RainGarden.Architecture.GlassRailing", "Architecture")
def glass_railing():
    """Frameless glass balustrade following the input curve: base shoe,
    vertical glass ribbon, plumb posts at even spacing and a round
    handrail."""
    graph = GN("RainGarden.Architecture.GlassRailing", glass_railing.__doc__)
    curve = graph.inp("Curve", "GEOMETRY")
    height = graph.inp("Height", "FLOAT", 1.1, 0.1, 5.0, "DISTANCE")
    post_spacing = graph.inp("Post Spacing", "FLOAT", 1.6, 0.1, 20.0, "DISTANCE")
    post_size = graph.inp("Post Size", "FLOAT", 0.055, 0.0, 1.0, "DISTANCE")
    rail_radius = graph.inp("Handrail Radius", "FLOAT", 0.03, 0.005, 0.5, "DISTANCE")
    shoe_height = graph.inp("Shoe Height", "FLOAT", 0.1, 0.0, 1.0, "DISTANCE")
    shoe_width = graph.inp("Shoe Width", "FLOAT", 0.07, 0.0, 1.0, "DISTANCE")
    frame = graph.inp("Frame Material", "MATERIAL", default=M.get("RainGarden.DarkSteel"))
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("RainGarden.PanelGlass"))
    length = graph.n("GeometryNodeCurveLength", curve).o
    even = graph.resample(curve, graph.max(graph.math("CEIL", length / post_spacing), 1.0) + 1.0)
    handrail = graph.smooth(graph.sweep(graph.move(even, z=height), graph.circle(rail_radius, 10), True))
    shoe = framed_sweep(graph, graph.move(even, z=shoe_height * 0.5), graph.rect(shoe_height, shoe_width))
    panel = hanging_ribbon(graph, even, shoe_height, height - rail_radius)
    points = graph.n("GeometryNodeCurveToPoints", even, props={"mode": "EVALUATED"})
    tangent = points["Tangent"]
    heading = graph.align_rotation(graph.vec(tangent.x, tangent.y, 0.0), axis="X")
    post = box(graph, graph.vec(post_size, post_size, height), graph.vec(0.0, 0.0, height * 0.5))
    posts = graph.realize(graph.iop(points["Points"], post, rot=heading))
    graph.result(graph.join(graph.mat(graph.join(handrail, shoe, posts), frame), graph.mat(panel, glass)))
    return graph


@asset("RainGarden.Architecture.GlassVault", "Architecture")
def glass_vault():
    """Glazed barrel vault along local +X: a circular section of ``Radius``
    springing at the origin height, a glass skin on a grid of steel ribs and
    purlins, clipped below ``Minimum Height``."""
    graph = GN("RainGarden.Architecture.GlassVault", glass_vault.__doc__)
    length = graph.inp("Length", "FLOAT", 60.0, 1.0, 1000.0, "DISTANCE")
    radius = graph.inp("Radius", "FLOAT", 20.0, 0.5, 500.0, "DISTANCE")
    sweep = graph.inp("Sweep", "FLOAT", math.pi, 0.1, math.tau, "ANGLE")
    rib_spacing = graph.inp("Rib Spacing", "FLOAT", 3.6, 0.2, 50.0, "DISTANCE")
    purlins = graph.inp("Purlins", "INT", 28, 2, 400)
    member = graph.inp("Member Size", "FLOAT", 0.14, 0.01, 2.0, "DISTANCE")
    minimum_height = graph.inp("Minimum Height", "FLOAT", -1000.0, -10000.0, 10000.0, "DISTANCE")
    glass = graph.inp("Glass", "MATERIAL", default=M.get("RainGarden.RoofGlass"))
    steel = graph.inp("Steel", "MATERIAL", default=M.get("RainGarden.WhiteSteel"))
    grid = graph.grid(1.0, 1.0, graph.math("CEIL", length / rib_spacing) + 1.0, purlins + 1.0)
    position = graph.position()
    angle = (math.pi - sweep) * 0.5 + (position.y + 0.5) * sweep
    skin = graph.set_pos(grid, pos=graph.vec((position.x + 0.5) * length, graph.cos(angle) * radius, graph.sin(angle) * radius))
    frame = graph.sweep(mesh_to_curve(graph, skin), graph.rect(member, member), False)
    low = graph.compare(position.z, minimum_height, "LESS_THAN")
    graph.result(graph.join(graph.mat(graph.delete(skin, low), glass), graph.mat(graph.delete(frame, low), steel)))
    return graph


def zigzag(graph, length, bays, start_a, start_b):
    """Poly curve of ``2 bays + 1`` points along +X alternating between the
    offsets ``start_a`` and ``start_b``: the line of a Warren lacing."""
    count = bays * 2.0 + 1.0
    index = graph.index()
    offset = graph.mix(graph.math("MODULO", index, 2.0), start_a, start_b, data_type="VECTOR")
    placed = graph.set_pos(row(graph, count, (1.0, 0.0, 0.0)), pos=graph.vec(length * (index / (count - 1.0)), 0.0, 0.0) + offset)
    return mesh_to_curve(graph, placed)


@asset("RainGarden.Architecture.LatticeGirder", "Architecture")
def lattice_girder():
    """Straight square box truss along local +X: four corner chords with
    Warren lacing on all four faces."""
    graph = GN("RainGarden.Architecture.LatticeGirder", lattice_girder.__doc__)
    length = graph.inp("Length", "FLOAT", 30.0, 0.5, 500.0, "DISTANCE")
    width = graph.inp("Width", "FLOAT", 1.4, 0.05, 20.0, "DISTANCE")
    depth = graph.inp("Depth", "FLOAT", 1.4, 0.05, 20.0, "DISTANCE")
    bays = graph.inp("Bays", "INT", 24, 1, 1000)
    chord = graph.inp("Chord Size", "FLOAT", 0.14, 0.01, 2.0, "DISTANCE")
    web = graph.inp("Web Size", "FLOAT", 0.07, 0.005, 1.0, "DISTANCE")
    steel = graph.inp("Steel", "MATERIAL", default=M.get("RainGarden.WhiteSteel"))
    half_width = width * 0.5
    half_depth = depth * 0.5
    parts = []
    for y_sign in (-1.0, 1.0):
        for z_sign in (-1.0, 1.0):
            line = graph.curve_line(graph.vec(0.0, half_width * y_sign, half_depth * z_sign), graph.vec(length, half_width * y_sign, half_depth * z_sign))
            parts.append(framed_sweep(graph, line, graph.rect(chord, chord)))
    web_profile = graph.rect(web, web)
    for y_sign in (-1.0, 1.0):
        lace = zigzag(graph, length, bays, graph.vec(0.0, half_width * y_sign, half_depth), graph.vec(0.0, half_width * y_sign, -half_depth))
        parts.append(framed_sweep(graph, lace, web_profile, up=(0.0, 1.0, 0.0)))
    for z_sign in (-1.0, 1.0):
        lace = zigzag(graph, length, bays, graph.vec(0.0, half_width, half_depth * z_sign), graph.vec(0.0, -half_width, half_depth * z_sign))
        parts.append(framed_sweep(graph, lace, web_profile))
    graph.result(graph.mat(graph.join(*parts), steel))
    return graph


@asset("RainGarden.Architecture.Staircase", "Architecture")
def staircase():
    """Straight flight rising along local +X from the origin: a floating
    stepped soffit, solid stringer parapets on both sides and glass railings
    on top."""
    graph = GN("RainGarden.Architecture.Staircase", staircase.__doc__)
    steps = graph.inp("Step Count", "INT", 20, 1, 400)
    rise = graph.inp("Rise", "FLOAT", 0.16, 0.05, 1.0, "DISTANCE")
    run = graph.inp("Run", "FLOAT", 0.32, 0.1, 2.0, "DISTANCE")
    width = graph.inp("Width", "FLOAT", 3.0, 0.3, 50.0, "DISTANCE")
    soffit = graph.inp("Soffit Thickness", "FLOAT", 0.35, 0.05, 5.0, "DISTANCE")
    wall_thickness = graph.inp("Parapet Thickness", "FLOAT", 0.28, 0.0, 3.0, "DISTANCE")
    wall_height = graph.inp("Parapet Height", "FLOAT", 0.45, 0.0, 3.0, "DISTANCE")
    railing_height = graph.inp("Railing Height", "FLOAT", 0.95, 0.0, 3.0, "DISTANCE")
    stone = graph.inp("Stone", "MATERIAL", default=M.get("RainGarden.WhiteStone"))
    frame = graph.inp("Railing Frame", "MATERIAL", default=M.get("RainGarden.DarkSteel"))
    glass = graph.inp("Railing Glass", "MATERIAL", default=M.get("RainGarden.PanelGlass"))
    total_run = run * steps
    total_rise = rise * steps
    slope = rise / run
    step_block = box(graph, graph.vec(run, width, rise), graph.vec(run * 0.5, 0.0, rise * 0.5))
    step_row = graph.realize(graph.iop(row(graph, steps, graph.vec(run, 0.0, rise)), step_block))
    underside = box(graph, graph.vec(total_run, width, soffit), graph.vec(total_run * 0.5, 0.0, soffit * -0.5))
    stonework = [step_row, graph.set_pos(underside, offset=graph.vec(0.0, 0.0, graph.position().x * slope))]
    wall_total = wall_height + soffit + rise
    top = rise + wall_height
    railings = []
    for side in (-1.0, 1.0):
        offset_y = (width * 0.5 + wall_thickness * 0.5) * side
        wall = box(graph, graph.vec(total_run, wall_thickness, wall_total), graph.vec(total_run * 0.5, offset_y, wall_total * 0.5 - soffit))
        stonework.append(graph.set_pos(wall, offset=graph.vec(0.0, 0.0, graph.position().x * slope)))
        path = graph.curve_line(graph.vec(0.0, offset_y, top), graph.vec(total_run, offset_y, total_rise + top))
        railings.append(graph.group(get_asset("RainGarden.Architecture.GlassRailing"), Curve=path, Height=railing_height,
                                    Frame_Material=frame, Glass_Material=glass).o)
    graph.result(graph.join(graph.mat(graph.join(*stonework), stone), *railings))
    return graph


def half_ellipse(graph, radius_x, radius_y, resolution=64):
    """Poly curve of the half ellipse from +X round through -Y to -X."""
    angle = graph.index() / (resolution - 1) * math.pi
    position = graph.vec(graph.cos(angle) * radius_x, graph.sin(angle) * (radius_y * -1.0), 0.0)
    return mesh_to_curve(graph, graph.set_pos(row(graph, resolution, (1.0, 0.0, 0.0)), pos=position))


@asset("RainGarden.Architecture.CurvedBalcony", "Architecture")
def curved_balcony():
    """Half-elliptic balcony projecting toward local -Y from a wall on the XZ
    plane: a crescent slab round a glass-bottomed pool, a curved glass
    railing, a fascia band and a hanging glass basin beneath."""
    graph = GN("RainGarden.Architecture.CurvedBalcony", curved_balcony.__doc__)
    radius_x = graph.inp("Width Radius", "FLOAT", 6.0, 0.2, 100.0, "DISTANCE")
    radius_y = graph.inp("Depth Radius", "FLOAT", 4.0, 0.2, 100.0, "DISTANCE")
    ring_width = graph.inp("Ring Width", "FLOAT", 1.4, 0.1, 50.0, "DISTANCE")
    thickness = graph.inp("Slab Thickness", "FLOAT", 0.45, 0.05, 5.0, "DISTANCE")
    railing_height = graph.inp("Railing Height", "FLOAT", 1.1, 0.0, 3.0, "DISTANCE")
    basin_depth = graph.inp("Basin Depth", "FLOAT", 1.3, 0.05, 20.0, "DISTANCE")
    stone = graph.inp("Stone", "MATERIAL", default=M.get("RainGarden.WhiteStone"))
    frame = graph.inp("Railing Frame", "MATERIAL", default=M.get("RainGarden.DarkSteel"))
    glass = graph.inp("Railing Glass", "MATERIAL", default=M.get("RainGarden.PanelGlass"))
    outer = half_ellipse(graph, radius_x, radius_y)
    inner_x = radius_x - ring_width
    inner_y = radius_y - ring_width
    crescent = flip_down_faces(graph, graph.fill(graph.join(cyclic(graph, outer), cyclic(graph, half_ellipse(graph, inner_x, inner_y))), "TRIANGLES"))
    slab = graph.solid(graph.move(crescent, z=-thickness), thickness)
    fascia = framed_sweep(graph, graph.move(outer, z=thickness * -0.5), graph.rect(thickness * 1.3, 0.12))
    railing = graph.group(get_asset("RainGarden.Architecture.GlassRailing"), Curve=half_ellipse(graph, radius_x - 0.12, radius_y - 0.12),
                          Height=railing_height, Frame_Material=frame, Glass_Material=glass).o
    basin = graph.group(get_asset("RainGarden.Water.FloatingDiscBasin"), Radius=inner_y * 0.98, Length_Ratio=inner_x / inner_y, Taper=0.0,
                        Depth=basin_depth, Water_Level=0.12, Rim_Radius=0.04, Rim_Gap=0.08, Foam_Density=300.0, Glitter_Density=40.0).o
    basin = graph.delete(graph.move(basin, z=thickness * -0.3), graph.compare(graph.position().y, 0.0, "GREATER_THAN"), "FACE")
    graph.result(graph.join(graph.mat(graph.join(slab, fascia), stone), railing, basin))
    return graph


@asset("RainGarden.Architecture.AquariumColonnade", "Architecture")
def aquarium_colonnade():
    """Colonnaded aquarium facade along local +X facing -Y: square piers in
    front of a mullioned aquarium curtain wall, a dropped parapet beam, a
    recessed soffit with warm downlights and a deep tank behind."""
    graph = GN("RainGarden.Architecture.AquariumColonnade", aquarium_colonnade.__doc__)
    length = graph.inp("Length", "FLOAT", 40.0, 1.0, 500.0, "DISTANCE", panel="Shape")
    height = graph.inp("Height", "FLOAT", 14.15, 1.0, 200.0, "DISTANCE", panel="Shape")
    spacing = graph.inp("Column Spacing", "FLOAT", 5.2, 0.5, 50.0, "DISTANCE", panel="Shape")
    column_width = graph.inp("Column Width", "FLOAT", 1.3, 0.1, 10.0, "DISTANCE", panel="Shape")
    column_depth = graph.inp("Column Depth", "FLOAT", 1.3, 0.1, 10.0, "DISTANCE", panel="Shape")
    plinth_height = graph.inp("Plinth Height", "FLOAT", 0.5, 0.0, 5.0, "DISTANCE", panel="Shape")
    capital_height = graph.inp("Capital Height", "FLOAT", 0.7, 0.0, 5.0, "DISTANCE", panel="Shape")
    flare = graph.inp("Moulding Flare", "FLOAT", 0.14, 0.0, 2.0, "DISTANCE", panel="Shape")
    setback = graph.inp("Glass Setback", "FLOAT", 1.8, 0.1, 20.0, "DISTANCE", panel="Shape")
    mullion_spacing = graph.inp("Mullion Spacing", "FLOAT", 1.3, 0.1, 20.0, "DISTANCE", panel="Shape")
    mullion_width = graph.inp("Mullion Width", "FLOAT", 0.12, 0.01, 2.0, "DISTANCE", panel="Shape")
    beam_height = graph.inp("Beam Height", "FLOAT", 2.0, 0.1, 20.0, "DISTANCE", panel="Shape")
    beam_projection = graph.inp("Beam Projection", "FLOAT", 0.45, 0.0, 10.0, "DISTANCE", panel="Shape")
    beam_depth = graph.inp("Beam Depth", "FLOAT", 1.2, 0.1, 10.0, "DISTANCE", panel="Shape")
    soffit_rise = graph.inp("Soffit Rise", "FLOAT", 0.7, 0.0, 10.0, "DISTANCE", panel="Shape")
    tank_depth = graph.inp("Tank Depth", "FLOAT", 7.0, 0.5, 50.0, "DISTANCE", panel="Shape")
    light_spacing = graph.inp("Light Spacing", "FLOAT", 2.6, 0.2, 20.0, "DISTANCE", panel="Shape")
    light_size = graph.inp("Light Size", "FLOAT", 0.55, 0.01, 5.0, "DISTANCE", panel="Shape")
    stone = graph.inp("Stone", "MATERIAL", default=M.get("RainGarden.WhiteStone"), panel="Materials")
    glass = graph.inp("Aquarium Glass", "MATERIAL", default=M.get("RainGarden.AquariumGlass"), panel="Materials")
    metal = graph.inp("Mullion Metal", "MATERIAL", default=M.get("RainGarden.DarkSteel"), panel="Materials")
    lamp = graph.inp("Downlight", "MATERIAL", default=M.get("RainGarden.WarmDownlight"), panel="Materials")
    tank = graph.inp("Tank Interior", "MATERIAL", default=M.get("RainGarden.AquariumDepth"), panel="Materials")

    shaft_height = height - plinth_height - capital_height
    middle = column_depth * 0.5
    column = graph.join(
        box(graph, graph.vec(column_width, column_depth, shaft_height), graph.vec(0.0, middle, plinth_height + shaft_height * 0.5)),
        box(graph, graph.vec(column_width + flare * 2.0, column_depth + flare * 2.0, plinth_height), graph.vec(0.0, middle, plinth_height * 0.5)),
        box(graph, graph.vec(column_width + flare * 0.8, column_depth + flare * 0.8, capital_height * 0.35),
            graph.vec(0.0, middle, height - capital_height + capital_height * 0.175)),
        box(graph, graph.vec(column_width + flare * 2.0, column_depth + flare * 2.0, capital_height * 0.65), graph.vec(0.0, middle, height - capital_height * 0.325)))
    columns = graph.realize(graph.iop(row(graph, count_for(graph, length, spacing), graph.vec(spacing, 0.0, 0.0)), column))
    pane = box(graph, graph.vec(length, 0.06, height), graph.vec(length * 0.5, setback, height * 0.5))
    mullion = box(graph, graph.vec(mullion_width, 0.22, height), graph.vec(0.0, setback - 0.11, height * 0.5))
    mullions = graph.realize(graph.iop(row(graph, count_for(graph, length, mullion_spacing), graph.vec(mullion_spacing, 0.0, 0.0)), mullion))
    sill = box(graph, graph.vec(length, setback + 0.2, 0.25), graph.vec(length * 0.5, setback * 0.5, 0.125))
    beam_back = beam_depth - beam_projection
    top = height + beam_height
    beam = graph.box(-column_width, -beam_projection, height, length + column_width, beam_back, top)
    beam_lip = graph.box(-column_width, -beam_projection - 0.12, top - 0.22, length + column_width, beam_back, top)
    soffit = graph.box(-column_width, beam_back - 0.01, height + soffit_rise, length + column_width, setback + tank_depth, top)
    back = setback + tank_depth
    ceiling = height + soffit_rise
    tank_shell = graph.n("GeometryNodeFlipFaces", graph.join(
        graph.box(0.0, back, 0.0, length, back + 0.3, ceiling),
        graph.box(0.0, setback, -0.3, length, back, 0.0),
        graph.box(-0.3, setback, 0.0, 0.0, back, ceiling),
        graph.box(length, setback, 0.0, length + 0.3, back, ceiling))).o
    light = box(graph, graph.vec(light_size, light_size, 0.04),
                graph.vec(light_spacing * 0.5, beam_back + (setback - beam_back) * 0.5, ceiling - 0.02))
    lights = graph.realize(graph.iop(row(graph, count_for(graph, length, light_spacing), graph.vec(light_spacing, 0.0, 0.0)), light))
    graph.result(graph.join(graph.mat(graph.join(columns, sill, beam, beam_lip, soffit), stone), graph.mat(pane, glass),
                            graph.mat(mullions, metal), graph.mat(tank_shell, tank), graph.mat(lights, lamp)))
    return graph


def arc_polyline(graph, count, center_z, start_angle, sweep, y, radius_even, radius_odd):
    """Poly curve of ``count`` points on a circular arc in the XZ plane at
    ``y`` about (0, centre z), alternating between two radii."""
    index = graph.index()
    angle = start_angle + sweep * (index / (count - 1.0))
    radius = graph.mix(graph.math("MODULO", index, 2.0), radius_even, radius_odd)
    position = graph.vec(graph.cos(angle) * radius, y, center_z + graph.sin(angle) * radius)
    return mesh_to_curve(graph, graph.set_pos(row(graph, count, (1.0, 0.0, 0.0)), pos=position))


@asset("RainGarden.Architecture.ArchTrussBridge", "Architecture")
def arch_truss_bridge():
    """Circular arch footbridge spanning local X with its crown on +Z: a
    curved deck, twin Warren side trusses hanging below it and glass
    railings on the deck edges."""
    graph = GN("RainGarden.Architecture.ArchTrussBridge", arch_truss_bridge.__doc__)
    span = graph.inp("Span", "FLOAT", 40.0, 1.0, 500.0, "DISTANCE")
    rise = graph.inp("Rise", "FLOAT", 18.0, 0.1, 300.0, "DISTANCE")
    deck_width = graph.inp("Deck Width", "FLOAT", 2.6, 0.3, 30.0, "DISTANCE")
    deck_thickness = graph.inp("Deck Thickness", "FLOAT", 0.45, 0.05, 5.0, "DISTANCE")
    truss_depth = graph.inp("Truss Depth", "FLOAT", 1.3, 0.1, 10.0, "DISTANCE")
    bays = graph.inp("Truss Bays", "INT", 48, 2, 1000)
    chord = graph.inp("Chord Size", "FLOAT", 0.16, 0.01, 2.0, "DISTANCE")
    web = graph.inp("Web Size", "FLOAT", 0.08, 0.005, 1.0, "DISTANCE")
    railing_height = graph.inp("Railing Height", "FLOAT", 1.05, 0.0, 3.0, "DISTANCE")
    steel = graph.inp("Steel", "MATERIAL", default=M.get("RainGarden.WhiteSteel"))
    glass = graph.inp("Railing Glass", "MATERIAL", default=M.get("RainGarden.PanelGlass"))
    half = span * 0.5
    center_z = (rise * rise - half * half) / (rise * 2.0)
    radius = rise - center_z
    start_angle = graph.math("ARCTAN2", center_z * -1.0, half)
    sweep = math.pi - start_angle * 2.0
    count = bays * 2.0 + 1.0
    top_radius = radius - deck_thickness * 0.5
    bottom_radius = radius - truss_depth
    rail_radius = radius + deck_thickness * 0.5
    sideways = (0.0, 1.0, 0.0)
    parts = [framed_sweep(graph, arc_polyline(graph, count, center_z, start_angle, sweep, 0.0, radius, radius), graph.rect(deck_width, deck_thickness), sideways)]
    railings = []
    for side in (-1.0, 1.0):
        y = (deck_width * 0.5 - chord * 0.5) * side
        parts.append(framed_sweep(graph, arc_polyline(graph, count, center_z, start_angle, sweep, y, bottom_radius, bottom_radius), graph.rect(chord, chord), sideways))
        parts.append(framed_sweep(graph, arc_polyline(graph, count, center_z, start_angle, sweep, y, top_radius, bottom_radius), graph.rect(web, web), sideways))
        path = arc_polyline(graph, count, center_z, start_angle, sweep, (deck_width * 0.5 - 0.08) * side, rail_radius, rail_radius)
        railings.append(graph.group(get_asset("RainGarden.Architecture.GlassRailing"), Curve=path, Height=railing_height, Post_Spacing=1.8,
                                    Frame_Material=steel, Glass_Material=glass).o)
    graph.result(graph.join(graph.mat(graph.join(*parts), steel), *railings))
    return graph


@asset("RainGarden.Architecture.LeaningFrame", "Architecture")
def leaning_frame():
    """Row of tapered square piers along local +X leaning toward local +Y
    (``Lean``) and sideways (``Rake``), carrying an overhanging sloped roof
    whose underside is a coffered steel grid."""
    graph = GN("RainGarden.Architecture.LeaningFrame", leaning_frame.__doc__)
    count = graph.inp("Count", "INT", 6, 1, 200)
    spacing = graph.inp("Spacing", "FLOAT", 4.4, 0.2, 100.0, "DISTANCE")
    height = graph.inp("Height", "FLOAT", 15.0, 0.5, 200.0, "DISTANCE")
    lean = graph.inp("Lean", "FLOAT", 0.18, -1.2, 1.2, "ANGLE")
    rake = graph.inp("Rake", "FLOAT", 0.0, -1.3, 1.3, "ANGLE")
    base_width = graph.inp("Base Width", "FLOAT", 1.25, 0.05, 20.0, "DISTANCE")
    top_width = graph.inp("Top Width", "FLOAT", 0.85, 0.05, 20.0, "DISTANCE")
    roof_back = graph.inp("Roof Back", "FLOAT", 6.0, 0.0, 100.0, "DISTANCE")
    roof_front = graph.inp("Roof Front", "FLOAT", 5.0, 0.0, 100.0, "DISTANCE")
    roof_thickness = graph.inp("Roof Thickness", "FLOAT", 1.6, 0.05, 20.0, "DISTANCE")
    roof_slope = graph.inp("Roof Slope", "FLOAT", 0.22, -1.2, 1.2, "ANGLE")
    coffer = graph.inp("Coffer Size", "FLOAT", 2.2, 0.2, 20.0, "DISTANCE")
    rib = graph.inp("Rib Width", "FLOAT", 0.28, 0.01, 5.0, "DISTANCE")
    stone = graph.inp("Pier Material", "MATERIAL", default=M.get("RainGarden.WhiteStone"))
    steel = graph.inp("Roof Material", "MATERIAL", default=M.get("RainGarden.DarkSteel"))
    diagonal = math.sqrt(0.5)
    pier = graph.n("GeometryNodeMeshCone", Vertices=4, Side_Segments=1, Radius_Top=top_width * diagonal,
                   Radius_Bottom=base_width * diagonal, Depth=height)["Mesh"]
    tilt = euler(graph, graph.vec(lean * -1.0, rake, 0.0))
    pier = graph.transform(graph.transform(pier, t=graph.vec(0.0, 0.0, height * 0.5), r=(0.0, 0.0, math.pi * 0.25)), r=tilt)
    piers = graph.realize(graph.iop(row(graph, count, graph.vec(spacing, 0.0, 0.0)), pier))
    total = spacing * (count - 1.0)
    top = graph.rotate_vector(graph.vec(0.0, 0.0, height), tilt)
    roof_length = total + spacing
    roof_depth = roof_back + roof_front
    rib_height = roof_thickness * 0.45
    rib_center = graph.vec(0.0, 0.0, roof_thickness * -0.225)
    slab = box(graph, graph.vec(roof_length, roof_depth, roof_thickness), graph.vec(0.0, 0.0, roof_thickness * 0.5))
    along = graph.iop(row(graph, graph.math("CEIL", roof_depth / coffer) + 1.0, graph.vec(0.0, coffer, 0.0), graph.vec(0.0, roof_depth * -0.5, 0.0)),
                      box(graph, graph.vec(roof_length, rib, rib_height), rib_center))
    across = graph.iop(row(graph, graph.math("CEIL", roof_length / coffer) + 1.0, graph.vec(coffer, 0.0, 0.0), graph.vec(roof_length * -0.5, 0.0, 0.0)),
                       box(graph, graph.vec(rib, roof_depth, rib_height), rib_center))
    roof = graph.transform(graph.join(slab, graph.realize(graph.join(along, across))), r=euler(graph, graph.vec(roof_slope * -1.0, 0.0, 0.0)))
    roof = graph.transform(roof, t=graph.vec(total * 0.5 + top.x, top.y + (roof_front - roof_back) * 0.5, top.z))
    graph.result(graph.join(graph.mat(piers, stone), graph.mat(roof, steel)))
    return graph


@asset("RainGarden.Architecture.MallGallery", "Architecture")
def mall_gallery():
    """Stack of gallery floors whose front edge follows the input curve:
    slabs of constant depth behind the curve, glass balustrades, lit
    storefront glazing set back from the edge, planters with shrubs and
    blossoms, and slender columns."""
    graph = GN("RainGarden.Architecture.MallGallery", mall_gallery.__doc__)
    curve = graph.inp("Curve", "GEOMETRY")
    levels = graph.inp("Levels", "INT", 4, 1, 50)
    level_height = graph.inp("Level Height", "FLOAT", 4.5, 1.0, 50.0, "DISTANCE")
    first_level = graph.inp("First Level", "FLOAT", 4.5, -50.0, 200.0, "DISTANCE")
    depth = graph.inp("Depth", "FLOAT", 5.0, 0.2, 100.0, "DISTANCE")
    thickness = graph.inp("Slab Thickness", "FLOAT", 0.55, 0.05, 5.0, "DISTANCE")
    setback = graph.inp("Storefront Setback", "FLOAT", 2.6, 0.0, 50.0, "DISTANCE")
    railing_height = graph.inp("Railing Height", "FLOAT", 1.1, 0.0, 3.0, "DISTANCE")
    planter_spacing = graph.inp("Planter Spacing", "FLOAT", 3.2, 0.2, 100.0, "DISTANCE")
    column_spacing = graph.inp("Column Spacing", "FLOAT", 7.0, 0.5, 100.0, "DISTANCE")
    seed = graph.inp("Seed", "INT", 9, 0, 100000)
    stone = graph.inp("Slab", "MATERIAL", default=M.get("RainGarden.WhiteStone"), panel="Materials")
    frame = graph.inp("Railing Frame", "MATERIAL", default=M.get("RainGarden.DarkSteel"), panel="Materials")
    glass = graph.inp("Railing Glass", "MATERIAL", default=M.get("RainGarden.PanelGlass"), panel="Materials")
    storefront = graph.inp("Storefront", "MATERIAL", default=M.get("RainGarden.StorefrontGlass"), panel="Materials")
    foliage = graph.inp("Foliage", "MATERIAL", default=M.get("RainGarden.Foliage"), panel="Materials")
    flowers = graph.inp("Flowers", "MATERIAL", default=M.get("RainGarden.Flowers"), panel="Materials")

    level = held_normal(graph, curve)
    slab_profile = graph.transform(graph.rect(thickness, depth), t=graph.vec(thickness * -0.5, depth * -0.5, 0.0))
    slab = graph.sweep(level, slab_profile, True)
    railing = graph.group(get_asset("RainGarden.Architecture.GlassRailing"), Curve=curve, Height=railing_height,
                          Frame_Material=frame, Glass_Material=glass).o
    inward = graph.n("GeometryNodeInputTangent").o.cross((0.0, 0.0, 1.0))
    glazing_line = graph.set_pos(level, offset=inward * (setback * -1.0))
    glazing = hanging_ribbon(graph, glazing_line, 0.0, level_height - thickness)
    planter_spots = graph.n("GeometryNodeCurveToPoints", graph.set_pos(level, offset=inward * -0.45), props={"mode": "LENGTH"}, Length=planter_spacing)
    planter = box(graph, (1.4, 0.45, 0.45), (0.0, 0.0, 0.225))
    planters = graph.realize(graph.iop(planter_spots["Points"], planter, rot=planter_spots["Rotation"]))
    soil = graph.delete(planters, graph.compare(graph.normal().z, 0.5, "LESS_THAN"), "FACE")
    shrub_points = graph.n("GeometryNodeDistributePointsOnFaces", Mesh=soil, Density=14.0, Seed=seed)["Points"]
    shrub_scale = graph.random(0.12, 0.28, seed, ID=graph.id())
    blob = graph.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=2)["Mesh"]
    shrubs = graph.realize(graph.iop(shrub_points, blob, scale=graph.vec(shrub_scale, shrub_scale, shrub_scale * 0.8)))
    shrubs = graph.store(shrubs, "leaf_variation", graph.random(0.0, 1.0, seed + 3, ID=graph.index()))
    flower_points = graph.n("GeometryNodeDistributePointsOnFaces", Mesh=shrubs, Density=22.0, Seed=seed + 5)["Points"]
    blossoms = graph.realize(graph.iop(flower_points, graph.n("GeometryNodeMeshIcoSphere", Radius=0.05, Subdivisions=1)["Mesh"]))
    storey = level_height - thickness
    column_points = graph.n("GeometryNodeCurveToPoints", glazing_line, props={"mode": "LENGTH"}, Length=column_spacing)["Points"]
    columns = graph.realize(graph.iop(column_points, graph.transform(graph.cylinder(0.3, storey, 24), t=graph.vec(0.0, 0.0, storey * 0.5))))
    floor = graph.join(graph.mat(graph.join(slab, planters, columns), stone), railing, graph.mat(glazing, storefront),
                       graph.mat(graph.smooth(shrubs), foliage), graph.mat(blossoms, flowers))
    graph.result(graph.realize(graph.iop(row(graph, levels, graph.vec(0.0, 0.0, level_height), graph.vec(0.0, 0.0, first_level)), floor)))
    return graph


def lancet_points(width, spring, samples):
    """Outline (x, z) of an equilateral lancet window ``width`` wide whose
    arch springs at ``spring``: up the left jamb, over the pointed arch and
    down the right jamb."""
    apex = math.radians(60.0)
    points = [(-width / 2, 0.0), (-width / 2, spring)]
    for index in range(1, samples):
        angle = apex * index / samples
        points.append((width / 2 - width * math.cos(angle), spring + width * math.sin(angle)))
    points.append((0.0, spring + width * math.sin(apex)))
    for index in range(samples - 1, 0, -1):
        angle = apex * index / samples
        points.append((-width / 2 + width * math.cos(angle), spring + width * math.sin(angle)))
    points.append((width / 2, spring))
    points.append((width / 2, 0.0))
    return points


LANCET_WIDTH = 2.8
LANCET_SPRING = 4.5


@asset("RainGarden.Architecture.TowerPier", "Architecture")
def tower_pier():
    """Stone tower pier with its front face on the local XZ plane facing -Y:
    a deep lancet window, a corner pilaster with gold-framed inlay panels and
    lettering, a dark mullioned glass curtain on the -X side and string
    courses."""
    graph = GN("RainGarden.Architecture.TowerPier", tower_pier.__doc__)
    width = graph.inp("Width", "FLOAT", 14.0, 1.0, 200.0, "DISTANCE")
    depth = graph.inp("Depth", "FLOAT", 13.0, 1.0, 200.0, "DISTANCE")
    height = graph.inp("Height", "FLOAT", 48.0, 1.0, 500.0, "DISTANCE")
    window_offset = graph.inp("Window Offset", "FLOAT", 3.2, 0.0, 200.0, "DISTANCE")
    window_sill = graph.inp("Window Sill", "FLOAT", 7.5, 0.0, 200.0, "DISTANCE")
    window_width = graph.inp("Window Width", "FLOAT", 2.8, 0.2, 50.0, "DISTANCE")
    window_height = graph.inp("Window Height", "FLOAT", 6.9, 0.2, 100.0, "DISTANCE")
    pilaster = graph.inp("Pilaster Width", "FLOAT", 2.2, 0.1, 30.0, "DISTANCE")
    course_spacing = graph.inp("Course Spacing", "FLOAT", 6.0, 0.5, 100.0, "DISTANCE")
    curtain_mullion = graph.inp("Curtain Mullion Spacing", "FLOAT", 1.6, 0.1, 50.0, "DISTANCE")
    inlay_bottom = graph.inp("Inlay Bottom", "FLOAT", 6.0, 0.0, 500.0, "DISTANCE")
    inlay_top = graph.inp("Inlay Top", "FLOAT", 13.5, 0.0, 500.0, "DISTANCE")
    inlay_text = graph.inp("Inlay Text", "STRING", "")
    band_bottom = graph.inp("Upper Band Bottom", "FLOAT", 22.0, 0.0, 500.0, "DISTANCE")
    band_text = graph.inp("Upper Band Text", "STRING", "")
    stone = graph.inp("Stone", "MATERIAL", default=M.get("RainGarden.WhiteStone"), panel="Materials")
    curtain = graph.inp("Curtain Glass", "MATERIAL", default=M.get("RainGarden.DarkGlassCurtain"), panel="Materials")
    metal = graph.inp("Mullion", "MATERIAL", default=M.get("RainGarden.DarkSteel"), panel="Materials")
    window_light = graph.inp("Window Light", "MATERIAL", default=M.get("RainGarden.WindowLight"), panel="Materials")
    gold = graph.inp("Gold", "MATERIAL", default=M.get("RainGarden.GoldTrim"), panel="Materials")
    inlay = graph.inp("Inlay Panel", "MATERIAL", default=M.get("RainGarden.InlayBlue"), panel="Materials")

    core = graph.box(0.0, 0.0, 0.0, width, depth, height)
    pilaster_block = graph.box(-0.6, -0.6, 0.0, pilaster, pilaster, height + 1.5)
    course_step = graph.vec(0.0, 0.0, course_spacing)
    courses = graph.realize(graph.iop(row(graph, graph.math("CEIL", height / course_spacing), course_step, course_step),
                                      graph.box(-0.25, -0.25, -0.2, width, depth, 0.2)))
    curtain_panel = graph.box(-0.08, pilaster, 0.0, -0.02, depth, height)
    mullion_count = graph.math("CEIL", (depth - pilaster) / curtain_mullion)
    mullions = graph.realize(graph.iop(row(graph, mullion_count, graph.vec(0.0, curtain_mullion, 0.0), graph.vec(0.0, pilaster, 0.0)),
                                       graph.box(-0.2, 0.0, 0.0, -0.02, 0.12, height)))

    lancet = graph.polyline([(x, 0.0, z) for x, z in lancet_points(LANCET_WIDTH, LANCET_SPRING, 8)])
    frame = framed_sweep(graph, lancet, graph.rect(0.9, 0.55), up=(0.0, -1.0, 0.0))
    closed = cyclic(graph, lancet)
    pane = graph.fill(graph.transform(closed, r=(-QUARTER, 0.0, 0.0)), "NGONS")
    pane = graph.transform(pane, t=(0.0, 0.9, 0.0), r=(QUARTER, 0.0, 0.0))
    reveal = graph.n("GeometryNodeExtrudeMesh", props={"mode": "EDGES"}, Mesh=graph.sweep(closed, None, False), Offset=(0.0, 0.9, 0.0)).o
    window_stone = graph.join(frame, reveal, graph.box(-0.09, 0.3, 0.0, 0.09, 0.45, 7.0), graph.box(-1.4, 0.3, 4.4, 1.4, 0.45, 4.6))
    window = graph.join(graph.mat(window_stone, stone), graph.mat(pane, window_light))
    lancet_height = LANCET_SPRING + LANCET_WIDTH * math.sin(math.radians(60.0))
    window = graph.transform(window, t=graph.vec(window_offset, -0.2, window_sill),
                             s=graph.vec(window_width / LANCET_WIDTH, 1.0, window_height / lancet_height))

    inlay_middle = (inlay_top + inlay_bottom) * 0.5
    inlay_panel = graph.box(0.25, -0.75, inlay_bottom, pilaster - 0.25, -0.62, inlay_top)
    inlay_frame = framed_sweep(graph, graph.rect(pilaster - 0.4, inlay_top - inlay_bottom), graph.rect(0.08, 0.08))
    inlay_frame = graph.transform(inlay_frame, t=graph.vec(pilaster * 0.5, -0.78, inlay_middle), r=(QUARTER, 0.0, 0.0))
    ornament = graph.transform(text_tube(graph, inlay_text, pilaster * 0.32, 0.03), t=graph.vec(pilaster * 0.5, -0.8, inlay_middle),
                               r=(QUARTER, QUARTER, 0.0))
    band_panel = graph.box(pilaster, -0.7, band_bottom, width, -0.05, height)
    band_glyphs = graph.transform(text_tube(graph, band_text, (height - band_bottom) * 0.35, 0.06),
                                  t=graph.vec((width + pilaster) * 0.5, -0.75, (band_bottom + height) * 0.5), r=(QUARTER, 0.0, 0.0))
    graph.result(graph.join(graph.mat(graph.join(core, pilaster_block, courses), stone), graph.mat(curtain_panel, curtain),
                            graph.mat(mullions, metal), window, graph.mat(graph.join(inlay_panel, band_panel), inlay),
                            graph.mat(graph.join(inlay_frame, ornament, band_glyphs), gold)))
    return graph
