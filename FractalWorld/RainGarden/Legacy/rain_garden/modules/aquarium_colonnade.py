from rain_garden.shapes import box, box_between, count_for, row_points

GROUP_NAME = "Aquarium Colonnade"
CATEGORY = "Architecture"
DESCRIPTION = "Colonnaded aquarium facade: square piers in front of a mullioned aquarium curtain wall, a dropped parapet beam, a recessed soffit with warm downlights and a deep tank behind. Runs along local +X, faces local -Y."


def build(b, context):
    shape = b.panel("Shape")
    length = b.input("Length", "FLOAT", 40.0, 1.0, 500.0, "DISTANCE", panel=shape)
    height = b.input("Height", "FLOAT", 14.15, 1.0, 200.0, "DISTANCE", panel=shape)
    spacing = b.input("Column Spacing", "FLOAT", 5.2, 0.5, 50.0, "DISTANCE", panel=shape)
    column_width = b.input("Column Width", "FLOAT", 1.3, 0.1, 10.0, "DISTANCE", panel=shape)
    column_depth = b.input("Column Depth", "FLOAT", 1.3, 0.1, 10.0, "DISTANCE", panel=shape)
    plinth_height = b.input("Plinth Height", "FLOAT", 0.5, 0.0, 5.0, "DISTANCE", panel=shape)
    capital_height = b.input("Capital Height", "FLOAT", 0.7, 0.0, 5.0, "DISTANCE", panel=shape)
    flare = b.input("Moulding Flare", "FLOAT", 0.14, 0.0, 2.0, "DISTANCE", panel=shape)
    setback = b.input("Glass Setback", "FLOAT", 1.8, 0.1, 20.0, "DISTANCE", panel=shape)
    mullion_spacing = b.input("Mullion Spacing", "FLOAT", 1.3, 0.1, 20.0, "DISTANCE", panel=shape)
    mullion_width = b.input("Mullion Width", "FLOAT", 0.12, 0.01, 2.0, "DISTANCE", panel=shape)
    band_height = b.input("Beam Height", "FLOAT", 2.0, 0.1, 20.0, "DISTANCE", panel=shape)
    band_projection = b.input("Beam Projection", "FLOAT", 0.45, 0.0, 10.0, "DISTANCE", panel=shape)
    band_depth = b.input("Beam Depth", "FLOAT", 1.2, 0.1, 10.0, "DISTANCE", panel=shape)
    soffit_rise = b.input("Soffit Rise", "FLOAT", 0.7, 0.0, 10.0, "DISTANCE", panel=shape)
    tank_depth = b.input("Tank Depth", "FLOAT", 7.0, 0.5, 50.0, "DISTANCE", panel=shape)
    light_spacing = b.input("Light Spacing", "FLOAT", 2.6, 0.2, 20.0, "DISTANCE", panel=shape)
    light_size = b.input("Light Size", "FLOAT", 0.55, 0.01, 5.0, "DISTANCE", panel=shape)
    looks = b.panel("Materials")
    stone = b.input("Stone", "MATERIAL", context.material("White Stone"), panel=looks)
    glass = b.input("Aquarium Glass", "MATERIAL", context.material("Aquarium Glass"), panel=looks)
    metal = b.input("Mullion Metal", "MATERIAL", context.material("Dark Steel"), panel=looks)
    lamp = b.input("Downlight", "MATERIAL", context.material("Warm Downlight"), panel=looks)
    tank = b.input("Tank Interior", "MATERIAL", context.material("Aquarium Depth"), panel=looks)

    shaft_height = height - plinth_height - capital_height
    shaft = box(b, b.combine(column_width, column_depth, shaft_height), b.combine(0.0, column_depth * 0.5, plinth_height + shaft_height * 0.5))
    plinth = box(b, b.combine(column_width + flare * 2.0, column_depth + flare * 2.0, plinth_height), b.combine(0.0, column_depth * 0.5, plinth_height * 0.5))
    necking = box(b, b.combine(column_width + flare * 0.8, column_depth + flare * 0.8, capital_height * 0.35), b.combine(0.0, column_depth * 0.5, height - capital_height + capital_height * 0.175))
    abacus = box(b, b.combine(column_width + flare * 2.0, column_depth + flare * 2.0, capital_height * 0.65), b.combine(0.0, column_depth * 0.5, height - capital_height * 0.325))
    column = b.join(shaft, plinth, necking, abacus)
    column_count = count_for(b, length, spacing)
    columns = b.realize(b.instance(row_points(b, column_count, b.combine(spacing, 0.0, 0.0)), column))

    glass_pane = box(b, b.combine(length, 0.06, height), b.combine(length * 0.5, setback, height * 0.5))
    mullion = box(b, b.combine(mullion_width, 0.22, height), b.combine(0.0, setback - 0.11, height * 0.5))
    mullion_count = count_for(b, length, mullion_spacing)
    mullions = b.realize(b.instance(row_points(b, mullion_count, b.combine(mullion_spacing, 0.0, 0.0)), mullion))
    sill = box(b, b.combine(length, setback + 0.2, 0.25), b.combine(length * 0.5, setback * 0.5, 0.125))

    beam = box_between(b, b.combine(-column_width, -band_projection, height), b.combine(length + column_width, band_depth - band_projection, height + band_height))
    beam_lip = box_between(b, b.combine(-column_width, -band_projection - 0.12, height + band_height - 0.22), b.combine(length + column_width, band_depth - band_projection, height + band_height))
    soffit = box_between(b, b.combine(-column_width, band_depth - band_projection - 0.01, height + soffit_rise), b.combine(length + column_width, setback + tank_depth, height + band_height))

    tank_back = box_between(b, b.combine(0.0, setback + tank_depth, 0.0), b.combine(length, setback + tank_depth + 0.3, height + soffit_rise))
    tank_floor = box_between(b, b.combine(0.0, setback, -0.3), b.combine(length, setback + tank_depth, 0.0))
    tank_end_start = box_between(b, b.combine(-0.3, setback, 0.0), b.combine(0.0, setback + tank_depth, height + soffit_rise))
    tank_end_finish = box_between(b, b.combine(length, setback, 0.0), b.combine(length + 0.3, setback + tank_depth, height + soffit_rise))
    tank_shell = b.node("GeometryNodeFlipFaces", Mesh=b.join(tank_back, tank_floor, tank_end_start, tank_end_finish)).out

    light_count = count_for(b, length, light_spacing)
    light = box(b, b.combine(light_size, light_size, 0.04), b.combine(light_spacing * 0.5, band_depth - band_projection + (setback - band_depth + band_projection) * 0.5, height + soffit_rise - 0.02))
    lights = b.realize(b.instance(row_points(b, light_count, b.combine(light_spacing, 0.0, 0.0)), light))

    stonework = b.set_material(b.join(columns, sill, beam, beam_lip, soffit), stone)
    result = b.join(
        stonework,
        b.set_material(glass_pane, glass),
        b.set_material(mullions, metal),
        b.set_material(tank_shell, tank),
        b.set_material(lights, lamp),
    )
    b.output("Geometry", "GEOMETRY", result)
