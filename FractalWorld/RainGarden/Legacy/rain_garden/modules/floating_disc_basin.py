from rain_garden.shapes import circle_profile, fill_at_height

GROUP_NAME = "Floating Disc Basin"
CATEGORY = "Water"
DESCRIPTION = "Floating teardrop glass basin: iridescent double-walled bowl, twin gold rims with a foam band, and a water body that stays level in world space however the basin is tilted. Origin at the rim centre, pointed tip toward local +X."


def outline_position(b, u, radius, length_ratio, taper, scale):
    angle = b.math("MULTIPLY", u, 6.283185307)
    cosine = b.math("COSINE", angle)
    narrowing = b.math("POWER", b.math("MAXIMUM", b.math("MULTIPLY", b.math("SUBTRACT", 1.0, cosine), 0.5), 0.0), taper)
    x = b.math("MULTIPLY", b.math("MULTIPLY", cosine, b.math("MULTIPLY", radius, length_ratio)), scale)
    y = b.math("MULTIPLY", b.math("MULTIPLY", b.math("SINE", angle), b.math("MULTIPLY", radius, narrowing)), scale)
    return x, y


def bowl_surface(b, segments, rings, radius, length_ratio, taper, depth, scale):
    grid = b.node("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=segments + 1, Vertices_Y=rings).out
    position = b.position()
    u = b.math("ADD", position.x, 0.5)
    v = b.math("ADD", position.y, 0.5)
    x, y = outline_position(b, u, radius, length_ratio, taper, b.math("MULTIPLY", v, scale))
    fall = b.math("POWER", b.math("MAXIMUM", b.math("SUBTRACT", 1.0, b.math("MULTIPLY", v, v)), 0.0), 0.55)
    z = b.math("MULTIPLY", b.math("MULTIPLY", depth, scale), b.math("MULTIPLY", fall, -1.0))
    placed = b.set_position(grid, position=b.combine(x, y, z))
    return b.node("GeometryNodeMergeByDistance", Geometry=placed, Distance=0.00001).out


def outline_curve(b, segments, radius, length_ratio, taper, scale, height):
    circle = b.node("GeometryNodeCurvePrimitiveCircle", props={"mode": "RADIUS"}, Resolution=segments, Radius=1.0)["Curve"]
    parameter = b.node("GeometryNodeSplineParameter")["Factor"]
    x, y = outline_position(b, parameter, radius, length_ratio, taper, scale)
    return b.set_position(circle, position=b.combine(x, y, height))


def build(b, context):
    shape = b.panel("Shape")
    radius = b.input("Radius", "FLOAT", 3.0, 0.05, 100.0, "DISTANCE", panel=shape)
    length_ratio = b.input("Length Ratio", "FLOAT", 1.6, 0.2, 10.0, panel=shape)
    taper = b.input("Taper", "FLOAT", 0.6, 0.0, 4.0, panel=shape)
    depth = b.input("Depth", "FLOAT", 1.6, 0.02, 50.0, "DISTANCE", panel=shape)
    wall = b.input("Wall Thickness", "FLOAT", 0.05, 0.001, 2.0, "DISTANCE", panel=shape)
    water_level = b.input("Water Level", "FLOAT", 0.25, -50.0, 50.0, "DISTANCE", panel=shape)
    rim_radius = b.input("Rim Radius", "FLOAT", 0.05, 0.0, 2.0, "DISTANCE", panel=shape)
    rim_gap = b.input("Rim Gap", "FLOAT", 0.14, 0.0, 5.0, "DISTANCE", panel=shape)
    foam_density = b.input("Foam Density", "FLOAT", 900.0, 0.0, 20000.0, panel=shape)
    glitter_density = b.input("Glitter Density", "FLOAT", 140.0, 0.0, 20000.0, panel=shape)
    glitter_size = b.input("Glitter Size", "FLOAT", 0.012, 0.001, 1.0, "DISTANCE", panel=shape)
    seed = b.input("Seed", "INT", 3, 0, 100000, panel=shape)
    looks = b.panel("Materials")
    shell_material = b.input("Shell", "MATERIAL", context.material("Iridescent Glass"), panel=looks)
    rim_material = b.input("Rim", "MATERIAL", context.material("Gold Trim"), panel=looks)
    water_material = b.input("Water", "MATERIAL", context.material("Basin Water"), panel=looks)
    glitter_material = b.input("Glitter", "MATERIAL", context.material("Glitter"), panel=looks)

    segments = 128
    rings = 28
    outer = bowl_surface(b, segments, rings, radius, length_ratio, taper, depth, 1.0)
    inner_scale = b.math("SUBTRACT", 1.0, b.math("DIVIDE", wall, radius))
    inner = b.node("GeometryNodeFlipFaces", Mesh=bowl_surface(b, segments, rings, radius, length_ratio, taper, depth, inner_scale)).out
    shell = b.smooth(b.join(outer, inner))

    cavity_scale = b.math("MULTIPLY", inner_scale, 0.996)
    cavity_floor = bowl_surface(b, segments, rings, radius, length_ratio, taper, depth, cavity_scale)
    cavity_cap = b.node("GeometryNodeFlipFaces", Mesh=bowl_surface(b, segments, rings, radius, length_ratio, taper, 0.0, cavity_scale)).out
    cavity = b.node("GeometryNodeMergeByDistance", Geometry=b.join(cavity_floor, cavity_cap), Distance=0.00001).out

    self_rotation = b.node("GeometryNodeObjectInfo", Object=b.node("GeometryNodeSelfObject").out)["Rotation"]
    local_up = b.node("FunctionNodeRotateVector", Vector=(0.0, 0.0, 1.0), Rotation=b.node("FunctionNodeInvertRotation", Rotation=self_rotation).out).out
    extent = b.math("MULTIPLY", b.math("ADD", b.math("MULTIPLY", radius, length_ratio), depth), 4.0)
    slab = b.node("GeometryNodeMeshCube", Size=b.combine(extent, extent, extent)).out
    slab = b.transform(slab, translation=b.combine(0.0, 0.0, b.math("MULTIPLY", extent, -0.5)))
    slab = b.transform(slab, rotation=b.align_z(local_up, axis="Z"))
    slab = b.transform(slab, translation=b.vmath("SCALE", local_up, b.math("MULTIPLY", water_level, -1.0)))
    water = b.node("GeometryNodeMeshBoolean", props={"operation": "INTERSECT", "solver": "MANIFOLD"})
    b.link(slab, water.node.inputs["Mesh 2"])
    b.link(cavity, water.node.inputs["Mesh 2"])
    water_body = b.smooth(water.out)

    rim = b.smooth(b.curve_to_mesh(outline_curve(b, segments, radius, length_ratio, taper, 1.0, 0.0), circle_profile(b, rim_radius, 12)))
    inner_rim_scale = b.math("SUBTRACT", 1.0, b.math("DIVIDE", rim_gap, radius))
    inner_rim = b.smooth(b.curve_to_mesh(outline_curve(b, segments, radius, length_ratio, taper, inner_rim_scale, b.math("MULTIPLY", rim_radius, -0.5)), circle_profile(b, b.math("MULTIPLY", rim_radius, 0.7), 10)))

    band_outer = outline_curve(b, segments, radius, length_ratio, taper, b.math("MULTIPLY", inner_scale, 0.99), b.math("MULTIPLY", rim_radius, -0.4))
    band_inner = outline_curve(b, segments, radius, length_ratio, taper, inner_rim_scale, b.math("MULTIPLY", rim_radius, -0.4))
    band = fill_at_height(b, b.join(band_outer, band_inner), mode="Triangles")
    identifier = b.node("GeometryNodeInputID").out
    foam_points = b.node("GeometryNodeDistributePointsOnFaces", Mesh=band, Density=foam_density, Seed=seed)["Points"]
    glitter_points = b.node("GeometryNodeDistributePointsOnFaces", Mesh=b.node("GeometryNodeFlipFaces", Mesh=cavity_floor).out, Density=glitter_density, Seed=b.math("ADD", seed, 5))["Points"]
    bottom_glitter = b.node("GeometryNodeDeleteGeometry", props={"domain": "POINT"}, Geometry=glitter_points, Selection=b.compare(b.vmath("DOT_PRODUCT", b.position(), local_up), b.math("MULTIPLY", water_level, -1.0), "GREATER_THAN")).out
    grain = b.node("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=1).out
    foam = b.instance(foam_points, grain, scale=b.math("MULTIPLY", glitter_size, b.random(0.6, 1.6, seed, identifier=identifier)))
    sparkles = b.instance(bottom_glitter, grain, scale=b.math("MULTIPLY", glitter_size, b.random(0.5, 1.2, b.math("ADD", seed, 9), identifier=identifier)))
    glitter = b.realize(b.join(foam, sparkles))

    result = b.join(
        b.set_material(shell, shell_material),
        b.set_material(b.join(rim, inner_rim), rim_material),
        b.set_material(water_body, water_material),
        b.set_material(glitter, glitter_material),
    )
    b.output("Geometry", "GEOMETRY", result)
