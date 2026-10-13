"""
Water kit -- geometry-node groups (``RainGarden.Water.*``): pools, floating
glass basins, the glass whales and every falling or leaping water.

Bodies of water are closed meshes that carry the ``thickness`` EEVEE
refracts and absorbs with (:func:`shapes.measured`); falling water is a thin
sheet whose ``fall_uv`` (across, down the fall) streaks its material.

The floating basins and the whales share one outline: a teardrop of
``Radius`` stretched ``Length Ratio`` times along X and narrowed by
``Taper`` toward +X (:func:`teardrop`).
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset
from . import materials as M
from .shapes import euler, fill_at_height, flip, framed_sweep, hanging_ribbon, measured

TEARDROP_SEGMENTS = 128
FIN_OUTLINE = [(0.0, 0.0, 0.0), (0.45, 0.2, 0.0), (0.95, 0.52, 0.0), (1.4, 0.86, 0.0), (1.75, 1.08, 0.0), (1.42, 0.62, 0.0),
               (1.12, 0.26, 0.0), (0.9, 0.04, 0.0)]


def teardrop(graph, u, radius, length_ratio, taper, scale):
    """(x, y) of the teardrop outline at ``u`` (0..1 round it), scaled by
    ``scale``."""
    angle = u * math.tau
    cosine = graph.cos(angle)
    narrowing = graph.math("POWER", graph.max((1.0 - cosine) * 0.5, 0.0), taper)
    return cosine * (radius * length_ratio) * scale, graph.sin(angle) * (radius * narrowing) * scale


def teardrop_dome(graph, rings, radius, length_ratio, taper, height, exponent, scale, downward):
    """Surface over the teardrop outline (scaled by ``scale``) bulging
    ``height`` * ``scale`` at its centre -- down when ``downward`` -- with
    the profile (1 - r^2)^``exponent``; faces turned away from the bulge."""
    position = graph.position()
    v = position.y + 0.5
    x, y = teardrop(graph, position.x + 0.5, radius, length_ratio, taper, v * scale)
    z = height * scale * graph.math("POWER", graph.max(1.0 - v * v, 0.0), exponent)
    surface = graph.set_pos(graph.grid(1.0, 1.0, TEARDROP_SEGMENTS + 1, rings), pos=graph.vec(x, y, z * -1.0 if downward else z))
    surface = graph.merge(surface, 0.00001)
    return surface if downward else flip(graph, surface)


def teardrop_ring(graph, radius, length_ratio, taper, scale, height):
    """The teardrop outline as a closed curve at ``height``."""
    x, y = teardrop(graph, graph.n("GeometryNodeSplineParameter")["Factor"], radius, length_ratio, taper, scale)
    return graph.set_pos(graph.circle(1.0, TEARDROP_SEGMENTS), pos=graph.vec(x, y, height))


@asset("RainGarden.Water.PoolBasin", "Water")
def pool_basin():
    """Pool cut along a closed outline curve (an object) at rim height: a
    water body filled to just below the rim, a caustic floor, lined walls
    and a flat coping band on top."""
    graph = GN("RainGarden.Water.PoolBasin", pool_basin.__doc__)
    outline = graph.inp("Outline", "OBJECT")
    depth = graph.inp("Depth", "FLOAT", 1.2, 0.05, 50.0, "DISTANCE")
    water_gap = graph.inp("Water Gap", "FLOAT", 0.05, 0.0, 5.0, "DISTANCE")
    coping_width = graph.inp("Coping Width", "FLOAT", 0.35, 0.0, 5.0, "DISTANCE")
    coping_height = graph.inp("Coping Height", "FLOAT", 0.06, 0.0, 2.0, "DISTANCE")
    lined = graph.inp("Lined", "BOOL", True)
    water_material = graph.inp("Water", "MATERIAL", default=M.get("RainGarden.Water"))
    floor_material = graph.inp("Floor", "MATERIAL", default=M.get("RainGarden.PoolFloorCaustics"))
    wall_material = graph.inp("Wall", "MATERIAL", default=M.get("RainGarden.PoolTile"))
    coping_material = graph.inp("Coping", "MATERIAL", default=M.get("RainGarden.WhiteStone"))
    curve = graph.object_info(outline, relative=True)["Geometry"]
    body_height = depth - water_gap - 0.01
    surface = fill_at_height(graph, graph.move(curve, z=-water_gap))
    water = measured(graph, graph.solid(graph.move(surface, z=-body_height), body_height), depth)
    floor = graph.move(fill_at_height(graph, curve), z=-depth)
    lining = graph.switch(lined, None, flip(graph, hanging_ribbon(graph, curve, -depth, 0.0)))
    coping = framed_sweep(graph, graph.move(curve, z=coping_height * 0.5), graph.rect(coping_height, coping_width))
    graph.result(graph.join(graph.mat(water, water_material), graph.mat(floor, floor_material),
                            graph.mat(lining, wall_material), graph.mat(coping, coping_material)))
    return graph


@asset("RainGarden.Water.FloatingDiscBasin", "Water")
def floating_disc_basin():
    """Floating teardrop glass basin: an iridescent double-walled bowl, twin
    gold rims with a band of foam, glitter on the floor and a body of water
    that stays level in world space however the basin is tilted.  Origin at
    the rim centre, the pointed tip toward local +X."""
    graph = GN("RainGarden.Water.FloatingDiscBasin", floating_disc_basin.__doc__)
    radius = graph.inp("Radius", "FLOAT", 3.0, 0.05, 100.0, "DISTANCE", panel="Shape")
    length_ratio = graph.inp("Length Ratio", "FLOAT", 1.6, 0.2, 10.0, panel="Shape")
    taper = graph.inp("Taper", "FLOAT", 0.6, 0.0, 4.0, panel="Shape")
    depth = graph.inp("Depth", "FLOAT", 1.6, 0.02, 50.0, "DISTANCE", panel="Shape")
    wall = graph.inp("Wall Thickness", "FLOAT", 0.05, 0.001, 2.0, "DISTANCE", panel="Shape")
    water_level = graph.inp("Water Level", "FLOAT", 0.25, -50.0, 50.0, "DISTANCE", panel="Shape")
    rim_radius = graph.inp("Rim Radius", "FLOAT", 0.05, 0.0, 2.0, "DISTANCE", panel="Shape")
    rim_gap = graph.inp("Rim Gap", "FLOAT", 0.14, 0.0, 5.0, "DISTANCE", panel="Shape")
    foam_density = graph.inp("Foam Density", "FLOAT", 900.0, 0.0, 20000.0, panel="Shape")
    glitter_density = graph.inp("Glitter Density", "FLOAT", 140.0, 0.0, 20000.0, panel="Shape")
    glitter_size = graph.inp("Glitter Size", "FLOAT", 0.012, 0.001, 1.0, "DISTANCE", panel="Shape")
    seed = graph.inp("Seed", "INT", 3, 0, 100000, panel="Shape")
    shell_material = graph.inp("Shell", "MATERIAL", default=M.get("RainGarden.IridescentGlass"), panel="Materials")
    rim_material = graph.inp("Rim", "MATERIAL", default=M.get("RainGarden.GoldTrim"), panel="Materials")
    water_material = graph.inp("Water", "MATERIAL", default=M.get("RainGarden.BasinWater"), panel="Materials")
    glitter_material = graph.inp("Glitter", "MATERIAL", default=M.get("RainGarden.Glitter"), panel="Materials")

    shape = (radius, length_ratio, taper)
    inner_scale = 1.0 - wall / radius
    shell = graph.smooth(graph.join(teardrop_dome(graph, 28, *shape, depth, 0.55, 1.0, True),
                                    flip(graph, teardrop_dome(graph, 28, *shape, depth, 0.55, inner_scale, True))))
    cavity_scale = inner_scale * 0.996
    cavity_floor = teardrop_dome(graph, 28, *shape, depth, 0.55, cavity_scale, True)
    cavity = graph.merge(graph.join(cavity_floor, flip(graph, teardrop_dome(graph, 28, *shape, 0.0, 0.55, cavity_scale, True))), 0.00001)
    rotation = graph.object_info(graph.self_object())["Rotation"]
    local_up = graph.rotate_vector((0.0, 0.0, 1.0), graph.n("FunctionNodeInvertRotation", Rotation=rotation).o)
    extent = (radius * length_ratio + depth) * 4.0
    below = graph.transform(graph.cube(graph.vec(extent, extent, extent)), t=graph.vec(0.0, 0.0, extent * -0.5))
    below = graph.transform(graph.transform(below, r=graph.align_rotation(local_up, axis="Z")), t=local_up * (water_level * -1.0))
    intersect = graph.n("GeometryNodeMeshBoolean", props={"operation": "INTERSECT", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(intersect.n, "Mesh 2"), [below, cavity])
    water = measured(graph, graph.smooth(intersect["Mesh"]), depth)

    rim = graph.sweep(teardrop_ring(graph, *shape, 1.0, 0.0), graph.circle(rim_radius, 12), False)
    inner_rim_scale = 1.0 - rim_gap / radius
    inner_rim = graph.sweep(teardrop_ring(graph, *shape, inner_rim_scale, rim_radius * -0.5), graph.circle(rim_radius * 0.7, 10), False)
    band_height = rim_radius * -0.4
    band = fill_at_height(graph, graph.join(teardrop_ring(graph, *shape, inner_scale * 0.99, band_height),
                                            teardrop_ring(graph, *shape, inner_rim_scale, band_height)), "TRIANGLES")
    foam_points = graph.n("GeometryNodeDistributePointsOnFaces", Mesh=band, Density=foam_density, Seed=seed)["Points"]
    floor_points = graph.n("GeometryNodeDistributePointsOnFaces", Mesh=flip(graph, cavity_floor), Density=glitter_density, Seed=seed + 5)["Points"]
    submerged = graph.delete(floor_points, graph.compare(graph.position().dot(local_up), water_level * -1.0, "GREATER_THAN"))
    grain = graph.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=1)["Mesh"]
    foam = graph.iop(foam_points, grain, scale=glitter_size * graph.random(0.6, 1.6, seed, ID=graph.id()))
    sparkles = graph.iop(submerged, grain, scale=glitter_size * graph.random(0.5, 1.2, seed + 9, ID=graph.id()))
    graph.result(graph.join(graph.mat(shell, shell_material), graph.mat(graph.smooth(graph.join(rim, inner_rim)), rim_material),
                            graph.mat(water, water_material), graph.mat(graph.realize(graph.join(foam, sparkles)), glitter_material)))
    return graph


def closed_lens(graph, radius, length_ratio, taper, top, bottom, scale):
    """Biconvex teardrop lens: a dome of ``top`` over one of ``bottom``."""
    upper = teardrop_dome(graph, 20, radius, length_ratio, taper, top, 0.5, scale, False)
    lower = teardrop_dome(graph, 20, radius, length_ratio, taper, bottom, 0.65, scale, True)
    return graph.smooth(graph.merge(graph.join(upper, lower), 0.00001))


@asset("RainGarden.Water.GlassWhaleLens", "Water")
def glass_whale_lens():
    """Closed biconvex glass lens shaped like a gliding whale: a water-filled
    body, a swept dorsal blade, a pointed tail spike and a gold keel line.
    Long axis along local X, head toward -X."""
    graph = GN("RainGarden.Water.GlassWhaleLens", glass_whale_lens.__doc__)
    radius = graph.inp("Radius", "FLOAT", 2.0, 0.05, 100.0, "DISTANCE", panel="Shape")
    length_ratio = graph.inp("Length Ratio", "FLOAT", 2.2, 0.3, 10.0, panel="Shape")
    taper = graph.inp("Taper", "FLOAT", 1.1, 0.0, 4.0, panel="Shape")
    top = graph.inp("Top Thickness", "FLOAT", 0.55, 0.01, 20.0, "DISTANCE", panel="Shape")
    bottom = graph.inp("Bottom Thickness", "FLOAT", 0.4, 0.01, 20.0, "DISTANCE", panel="Shape")
    fin_size = graph.inp("Fin Size", "FLOAT", 1.2, 0.0, 30.0, "DISTANCE", panel="Shape")
    fin_position = graph.inp("Fin Position", "FLOAT", -0.15, -1.0, 1.0, "FACTOR", panel="Shape")
    fin_thickness = graph.inp("Fin Thickness", "FLOAT", 0.06, 0.001, 2.0, "DISTANCE", panel="Shape")
    tail_length = graph.inp("Tail Length", "FLOAT", 0.9, 0.0, 30.0, "DISTANCE", panel="Shape")
    keel_radius = graph.inp("Keel Radius", "FLOAT", 0.03, 0.0, 1.0, "DISTANCE", panel="Shape")
    glass = graph.inp("Glass", "MATERIAL", default=M.get("RainGarden.IridescentGlass"), panel="Materials")
    water = graph.inp("Water", "MATERIAL", default=M.get("RainGarden.WhaleWater"), panel="Materials")
    keel_material = graph.inp("Keel", "MATERIAL", default=M.get("RainGarden.GoldTrim"), panel="Materials")

    shape = (radius, length_ratio, taper)
    body = closed_lens(graph, *shape, top, bottom, 1.0)
    core = measured(graph, closed_lens(graph, *shape, top, bottom, 0.965), top + bottom)
    half_length = radius * length_ratio
    outline = graph.n("GeometryNodeCurveSplineType", graph.transform(graph.polyline(FIN_OUTLINE, cyclic=True), s=fin_size),
                      props={"spline_type": "CATMULL_ROM"}).o
    blade = graph.fill(graph.resample(outline, 48), "NGONS")
    blade = graph.n("GeometryNodeFlipFaces", blade, Selection=graph.compare(graph.normal().z, 0.0, "LESS_THAN")).o
    blade = graph.move(graph.solid(blade, fin_thickness), z=fin_thickness * -0.5)
    fin = graph.transform(blade, t=graph.vec(fin_position * half_length, 0.0, top * 0.8), r=(math.pi * 0.5, 0.0, 0.0))
    tail = graph.n("GeometryNodeMeshCone", Vertices=16, Radius_Bottom=radius * 0.08, Radius_Top=0.0, Depth=tail_length)["Mesh"]
    tail = graph.transform(tail, t=graph.vec(half_length * 0.82 + tail_length * 0.5, 0.0, 0.0), r=(0.0, math.pi * 0.5, 0.0))
    x, y = teardrop(graph, graph.n("GeometryNodeSplineParameter")["Factor"], *shape, 1.003)
    keel_line = graph.set_pos(graph.circle(1.0, TEARDROP_SEGMENTS), pos=graph.vec(x, y, keel_radius * -0.5))
    keel = graph.smooth(graph.sweep(keel_line, graph.circle(keel_radius, 8), False))
    graph.result(graph.join(graph.mat(graph.join(body, graph.smooth(fin), graph.smooth(tail)), glass), graph.mat(core, water),
                            graph.mat(keel, keel_material)))
    return graph


@asset("RainGarden.Water.WaterfallCurtain", "Water")
def waterfall_curtain():
    """Falling water sheet hanging from a lip at the origin: it widens as it
    falls (``Spread``), drifts forward along +Y (``Throw``), can curl into a
    tube (``Curl``) and twist about its fall, and carries the ``fall_uv``
    that streaks its material."""
    graph = GN("RainGarden.Water.WaterfallCurtain", waterfall_curtain.__doc__)
    width = graph.inp("Width", "FLOAT", 2.0, 0.01, 100.0, "DISTANCE")
    spread = graph.inp("Spread", "FLOAT", 1.6, 0.1, 20.0)
    length = graph.inp("Length", "FLOAT", 12.0, 0.05, 500.0, "DISTANCE")
    throw = graph.inp("Throw", "FLOAT", 0.4, -50.0, 50.0, "DISTANCE")
    curl = graph.inp("Curl", "FLOAT", 0.25, 0.0, 1.0, "FACTOR")
    twist = graph.inp("Twist", "FLOAT", 0.0, -50.0, 50.0, "ANGLE")
    turbulence = graph.inp("Turbulence", "FLOAT", 0.18, 0.0, 10.0, "DISTANCE")
    ripple_scale = graph.inp("Ripple Scale", "FLOAT", 0.6, 0.0, 50.0)
    columns = graph.inp("Columns", "INT", 48, 3, 1000)
    rows = graph.inp("Rows", "INT", 96, 3, 4000)
    seed = graph.inp("Seed", "INT", 1, 0, 100000)
    material = graph.inp("Material", "MATERIAL", default=M.get("RainGarden.Waterfall"))
    position = graph.position()
    u = position.x
    v = 0.5 - position.y
    local_width = width * (1.0 + (spread - 1.0) * graph.math("POWER", v, 0.7))
    bend = graph.max(curl, 0.001) * math.tau
    angle = u * bend
    bend_radius = local_width / bend
    x = graph.sin(angle) * bend_radius
    y = bend_radius * (1.0 - curl) - graph.cos(angle) * bend_radius
    spin = twist * v
    twisted_x = x * graph.cos(spin) - y * graph.sin(spin)
    twisted_y = x * graph.sin(spin) + y * graph.cos(spin)
    base = graph.vec(twisted_x, twisted_y + throw * graph.math("SQRT", v), length * (v * -1.0))
    ripples = graph.n("ShaderNodeTexNoise", props={"noise_dimensions": "3D"}, Vector=graph.vec(u * 3.0, v * length * ripple_scale, seed * 1.37),
                      Scale=1.0, Detail=3.0, Roughness=0.5)["Color"]
    displaced = base + (ripples - (0.5, 0.5, 0.5)) * (turbulence * (0.25 + v))
    sheet = graph.set_pos(graph.grid(1.0, 1.0, columns, rows), pos=displaced)
    sheet = graph.store(sheet, "fall_uv", graph.vec(u * local_width, v * length, 0.0), "FLOAT_VECTOR")
    graph.result(graph.mat(graph.smooth(graph.merge(sheet, 0.00001)), material))
    return graph


@asset("RainGarden.Water.RibbonCascade", "Water")
def ribbon_cascade():
    """Row of twisted water ribbons spilling from an edge along local +X,
    each with its own width, drop and turn."""
    graph = GN("RainGarden.Water.RibbonCascade", ribbon_cascade.__doc__)
    length = graph.inp("Length", "FLOAT", 20.0, 0.1, 500.0, "DISTANCE")
    count = graph.inp("Count", "INT", 14, 1, 500)
    width = graph.inp("Ribbon Width", "FLOAT", 0.35, 0.01, 10.0, "DISTANCE")
    drop = graph.inp("Drop", "FLOAT", 3.0, 0.05, 100.0, "DISTANCE")
    twist = graph.inp("Twist", "FLOAT", 3.2, -50.0, 50.0, "ANGLE")
    seed = graph.inp("Seed", "INT", 12, 0, 100000)
    material = graph.inp("Material", "MATERIAL", default=M.get("RainGarden.WaterRibbon"))
    ribbon = graph.group(get_asset("RainGarden.Water.WaterfallCurtain"), Width=1.0, Spread=1.25, Length=1.0, Throw=0.0, Curl=0.35, Twist=twist,
                         Turbulence=0.02, Ripple_Scale=4.0, Columns=10, Rows=48, Seed=seed, Material=material).o
    index = graph.index()
    points = graph.mesh_line(count, (0.0, 0.0, 0.0), graph.vec(length / graph.max(count - 1.0, 1.0), 0.0, 0.0))
    jitter = graph.random(-0.35, 0.35, seed, ID=index) * (length / graph.max(count, 1.0))
    points = graph.set_pos(points, offset=graph.vec(jitter, 0.0, 0.0))
    ribbon_width = width * graph.random(0.6, 1.5, seed + 1, ID=index)
    ribbon_drop = drop * graph.random(0.55, 1.1, seed + 2, ID=index)
    turn = euler(graph, graph.vec(0.0, 0.0, graph.random(-0.6, 0.6, seed + 3, ID=index)))
    graph.result(graph.realize(graph.iop(points, ribbon, rot=turn, scale=graph.vec(ribbon_width, ribbon_width, ribbon_drop))))
    return graph


@asset("RainGarden.Water.WaterJet", "Water")
def water_jet():
    """Fountain jet erupting upward from the origin: a flared central column
    ringed by splash spikes and a halo of spray droplets."""
    graph = GN("RainGarden.Water.WaterJet", water_jet.__doc__)
    height = graph.inp("Height", "FLOAT", 6.0, 0.1, 200.0, "DISTANCE")
    base_radius = graph.inp("Base Radius", "FLOAT", 0.35, 0.01, 20.0, "DISTANCE")
    top_radius = graph.inp("Top Radius", "FLOAT", 0.9, 0.01, 30.0, "DISTANCE")
    spikes = graph.inp("Spikes", "INT", 14, 0, 500)
    spike_spread = graph.inp("Spike Spread", "FLOAT", 0.35, 0.0, 1.5, "ANGLE")
    droplets = graph.inp("Droplets", "INT", 220, 0, 20000)
    seed = graph.inp("Seed", "INT", 2, 0, 100000)
    material = graph.inp("Material", "MATERIAL", default=M.get("RainGarden.Waterfall"))
    spray_material = graph.inp("Spray Material", "MATERIAL", default=M.get("RainGarden.Spray"))
    column = graph.group(get_asset("RainGarden.Water.WaterfallCurtain"), Width=top_radius * math.tau, Spread=base_radius / top_radius,
                         Length=height, Throw=0.0, Curl=1.0, Turbulence=top_radius * 0.25, Ripple_Scale=1.1, Columns=32, Rows=80,
                         Seed=seed, Material=material).o
    column = graph.move(column, z=height)

    index = graph.index()
    ring = graph.mesh_to_points(graph.n("GeometryNodeMeshCircle", Vertices=spikes, Radius=base_radius)["Mesh"])
    spike = graph.n("GeometryNodeMeshCone", Vertices=6, Side_Segments=6, Radius_Bottom=1.0, Radius_Top=0.0, Depth=1.0)["Mesh"]
    spike = graph.move(spike, z=0.5)
    position = graph.position()
    tilt = euler(graph, graph.vec(0.0, spike_spread * graph.random(0.4, 1.0, seed + 3, ID=index), 0.0))
    outward = euler(graph, graph.vec(0.0, 0.0, graph.math("ARCTAN2", position.y, position.x)))
    spike_width = base_radius * graph.random(0.18, 0.4, seed + 5, ID=index)
    spike_height = height * graph.random(0.3, 0.85, seed, ID=index)
    splashes = graph.iop(ring, spike, rot=graph.rotate_rotation(tilt, outward, local=False), scale=graph.vec(spike_width, spike_width, spike_height))
    splashes = graph.store(splashes, "fall_uv", graph.vec(0.0, graph.random(0.0, 50.0, seed + 7, ID=index), 0.0), "FLOAT_VECTOR", "INSTANCE")
    splashes = graph.realize(splashes)
    splashes = graph.store(splashes, "fall_uv", graph.named("fall_uv", "FLOAT_VECTOR") + graph.vec(position.x, position.z, 0.0), "FLOAT_VECTOR")

    cloud = graph.n("GeometryNodeMeshUVSphere", Segments=16, Rings=8, Radius=1.0)["Mesh"]
    cloud = graph.transform(cloud, t=graph.vec(0.0, 0.0, height * 0.8), s=graph.vec(top_radius, top_radius, height * 0.35))
    volume = graph.n("GeometryNodeMeshToVolume", Mesh=cloud, Interior_Band_Width=0.2).o
    spray_points = graph.n("GeometryNodeDistributePointsInVolume", Volume=volume, Mode="Random",
                           Density=droplets / (top_radius * top_radius * (height * 1.5)), Seed=seed).o
    droplet = graph.n("GeometryNodeMeshIcoSphere", Radius=1.0, Subdivisions=1)["Mesh"]
    spray = graph.realize(graph.iop(spray_points, droplet, scale=base_radius * graph.random(0.02, 0.07, seed + 9, ID=graph.id())))
    graph.result(graph.join(column, graph.mat(graph.smooth(splashes), material), graph.mat(spray, spray_material)))
    return graph
