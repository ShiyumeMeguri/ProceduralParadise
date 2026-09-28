"""
Vessel kit -- geometry-node groups (``CF.Vessel.*``): the glassware of the
conservatory and what grows in it.

Glass walls are lathed from the outer profiles of ``Realm.json`` into walls
of constant thickness (``Core.gn.shell_profile``).  A liquid is the vessel's
cavity cut at its fill level by a boolean; it stands a fraction of a
millimetre into the glass, so the two dielectrics never leave a film of air
between them.

Local frames: standing vessels rest on z = 0; hanging ones hang from the
origin (their suspension point); orbs are centred on the origin.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, inner_profile, shell_profile
from Fractals import phyllotaxis as PHY
from .. import PROFILES
from ..values import apply
from . import materials as M
from .flora import flower_node

TAU = math.tau
OVERLAP = 0.0008


def cut_below(graph, solid, level, floor):
    """The part of the closed mesh ``solid`` below the plane z = ``level``."""
    below = graph.box(-10.0, -10.0, floor - 1.0, 10.0, 10.0, level)
    node = graph.n("GeometryNodeMeshBoolean", props={"operation": "INTERSECT", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(node.n, "Mesh 2"), [solid, below])
    return node["Mesh"]


def union(graph, *meshes):
    node = graph.n("GeometryNodeMeshBoolean", props={"operation": "UNION", "solver": "MANIFOLD"})
    graph.assign(graph._in_socket(node.n, "Mesh 2"), list(meshes))
    return node["Mesh"]


def sphere(graph, radius, segments=48, rings=24):
    return graph.n("GeometryNodeMeshUVSphere", Segments=segments, Rings=rings, Radius=radius)["Mesh"]


def group(graph, name, values):
    """Group node of kit asset ``name`` with data or socket ``values``."""
    return apply(graph, graph.group(get_asset(name)), values)


def sprinkle(graph, count, radius, height, instance, seed, scale=1.0, dome=0.0):
    """``instance`` on a golden-angle disc of ``radius`` at ``height``,
    each copy turned at random about the vertical."""
    points = graph.set_pos(PHY.disc_points(graph, count, radius, dome=dome), offset=graph.vec(0.0, 0.0, height))
    rotation = graph.axis_angle((0.0, 0.0, 1.0), graph.random(0.0, TAU, seed))
    return graph.iop(points, instance, rot=rotation, scale=scale * graph.random(0.8, 1.15, seed + 1))


@asset("CF.Vessel.Jar", "Vessels")
def jar():
    """Apothecary jar on a short foot with a glass lid and silver finial,
    partly filled with glowing water and planted (``Content``: 0 water only,
    1 blue foliage, 2 hydrangea heads, 3 floating camellias, 4 crystal
    coral)."""
    graph = GN("CF.Vessel.Jar", jar.__doc__)
    size = graph.inp("Size", default=1.0, desc="Height of the body in metres")
    width = graph.inp("Width", default=1.0, desc="Radial stretch")
    fill = graph.inp("Fill", default=0.6, min=0.0, max=1.0)
    lid = graph.inp("Lid", "BOOL", default=True)
    content = graph.inp("Content", "INT", default=1, min=0, max=4)
    inner = graph.inp("Inner Color", "COLOR", default=M.color("pink"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("blush"))
    leaf_color = graph.inp("Leaf Color", "COLOR", default=M.color("leaf_blue"))
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.Glass"))
    water = graph.inp("Water Material", "MATERIAL", default=M.get("CF.Water"))
    metal = graph.inp("Metal Material", "MATERIAL", default=M.get("CF.Silver"))

    profile = PROFILES["apothecary"]
    outline = profile["outer"]
    cavity_profile = inner_profile(outline, profile["thickness"] - OVERLAP)
    bottom = cavity_profile[0][1]
    level = bottom + fill * (profile["fill_top"] - bottom)
    shell = graph.lathe(shell_profile(outline, profile["thickness"]), 48)
    liquid = cut_below(graph, graph.lathe(cavity_profile, 48), level, bottom)
    cover = graph.join(graph.mat(graph.lathe(profile["lid"], 48), glass),
                       graph.mat(graph.lathe(profile["finial"], 32), metal))

    colors = {"Inner Color": inner, "Outer Color": outer, "Seed": seed}
    foliage = graph.join(
        graph.move(group(graph, "CF.Flora.Plant", {"Height": 0.55, "Bend": 0.12, "Leaves": 12, "Leaf Length": 0.13,
                                                   "Leaf Width": 0.045, "Generations": 1, "Branches": 2,
                                                   "Leaf Color": leaf_color, "Seed": seed}).o, z=bottom),
        graph.transform(group(graph, "CF.Flora.Plant", {"Height": 0.4, "Bend": 0.3, "Leaves": 9, "Leaf Length": 0.1,
                                                        "Leaf Width": 0.035, "Generations": 1, "Branches": 2,
                                                        "Leaf Color": leaf_color, "Seed": seed + 11}).o,
                        t=(0.08, 0.05, bottom), r=(0.0, 0.0, 2.2)))
    heads = sprinkle(graph, 3, 0.12, level + 0.03,
                     group(graph, "CF.Flora.Hydrangea", {"Radius": 0.1, "Florets": 120, **colors}).o, seed)
    floating = sprinkle(graph, 5, 0.2, level, flower_node(graph, "camellia", colors).o, seed, 1.3)
    reef = graph.move(group(graph, "CF.Crystal.Coral", {"Radius": 0.1, "Levels": 2, "Children": 7, "Seed": seed}).o,
                      z=bottom + 0.1)
    inside = graph.index_switch(content, [None, foliage, heads, floating, reef], "GEOMETRY")
    body = graph.join(graph.smooth_by_angle(graph.mat(shell, glass), 0.7),
                      graph.smooth_by_angle(graph.mat(liquid, water), 0.7),
                      graph.switch(lid, None, graph.smooth_by_angle(cover, 0.7)), inside)
    graph.result(graph.transform(body, s=graph.vec(size * width, size * width, size)))
    return graph


@asset("CF.Vessel.Globe", "Vessels")
def globe():
    """Hanging terrarium: a glass sphere under a silver collar with a finial
    and a crystal drop below, half filled with water and planted
    (``Content``: 0 water only, 1 foliage, 2 floating flowers, 3 crystal
    druse), hung on a thread from the origin."""
    graph = GN("CF.Vessel.Globe", globe.__doc__)
    radius = graph.inp("Radius", default=0.25, subtype="DISTANCE")
    drop = graph.inp("Drop", default=1.0, subtype="DISTANCE", desc="Thread length")
    fill = graph.inp("Fill", default=0.45, min=0.0, max=1.0)
    content = graph.inp("Content", "INT", default=1, min=0, max=3)
    inner = graph.inp("Inner Color", "COLOR", default=M.color("pink"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("blush"))
    leaf_color = graph.inp("Leaf Color", "COLOR", default=M.color("leaf_teal"))
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.Glass"))
    water = graph.inp("Water Material", "MATERIAL", default=M.get("CF.Water"))
    metal = graph.inp("Metal Material", "MATERIAL", default=M.get("CF.Silver"))
    thread_material = graph.inp("Thread Material", "MATERIAL", default=M.get("CF.Thread"))

    profile = PROFILES["globe"]
    wall = profile["thickness"]
    shell = graph.join(sphere(graph, 1.0, 64, 32), graph.n("GeometryNodeFlipFaces", sphere(graph, 1.0 - wall, 64, 32)).o)
    bottom = -1.0 + wall
    level = bottom + fill * 2.0 * (1.0 - wall)
    liquid = cut_below(graph, sphere(graph, 1.0 - wall + OVERLAP * 4.0, 64, 32), level, bottom)
    fittings = graph.join(graph.lathe(profile["collar"], 32), graph.lathe(profile["finial"], 32))
    tear = graph.move(group(graph, "CF.Crystal.Pendant", {"Size": 0.42, "Width": 0.3, "Drop": 0.0}).o,
                      z=profile["finial"][-1][1])
    colors = {"Inner Color": inner, "Outer Color": outer, "Seed": seed}
    foliage = graph.move(group(graph, "CF.Flora.Plant", {"Height": 0.9, "Bend": 0.25, "Leaves": 10, "Leaf Length": 0.28,
                                                         "Leaf Width": 0.09, "Stem Radius": 0.015, "Generations": 1,
                                                         "Branches": 2, "Leaf Color": leaf_color, "Seed": seed}).o,
                         z=bottom)
    floating = sprinkle(graph, 4, 0.35, level, flower_node(graph, "camellia", colors).o, seed, 2.4)
    druse = graph.move(group(graph, "CF.Crystal.Druse", {"Count": 7, "Length": 0.6, "Levels": 1, "Seed": seed}).o,
                       z=bottom)
    inside = graph.index_switch(content, [None, foliage, floating, druse], "GEOMETRY")
    body = graph.join(graph.smooth(graph.mat(shell, glass)), graph.smooth(graph.mat(liquid, water)),
                      graph.smooth_by_angle(graph.mat(fittings, metal), 0.7), tear, inside)
    top = profile["collar"][-1][1]
    hung = graph.transform(body, t=graph.vec(0.0, 0.0, -drop - radius * top), s=graph.vec(radius, radius, radius))
    thread = graph.mat(graph.rod((0.0, 0.0, 0.0), graph.vec(0.0, 0.0, -drop), 0.0012, 6), thread_material)
    graph.result(graph.join(hung, thread))
    return graph


@asset("CF.Vessel.LensBowl", "Vessels")
def lens_bowl():
    """Wide, shallow lens of a bowl brimming with blue water, camellias
    floating and flowering sprigs rising from it, a crystal drip hanging
    from its centre.  The rim is at z = 0.02 x Radius / 0.712."""
    graph = GN("CF.Vessel.LensBowl", lens_bowl.__doc__)
    radius = graph.inp("Radius", default=0.712, subtype="DISTANCE")
    fill = graph.inp("Fill", default=0.8, min=0.0, max=1.0)
    blossoms = graph.inp("Blossoms", "INT", default=6, min=0, max=40)
    sprigs = graph.inp("Sprigs", "INT", default=3, min=0, max=12)
    drip = graph.inp("Drip", "BOOL", default=True)
    inner = graph.inp("Inner Color", "COLOR", default=M.color("pink"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("blush"))
    leaf_color = graph.inp("Leaf Color", "COLOR", default=M.color("leaf_teal"))
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.Glass"))
    water = graph.inp("Water Material", "MATERIAL", default=M.get("CF.Water"))

    profile = PROFILES["lens_bowl"]
    outline = profile["outer"]
    rim = outline[-1]
    cavity_profile = inner_profile(outline, profile["thickness"] - OVERLAP)
    bottom = cavity_profile[0][1]
    level = bottom + fill * (rim[1] - bottom)
    shell = graph.lathe(shell_profile(outline, profile["thickness"]), 64)
    liquid = cut_below(graph, graph.lathe(cavity_profile, 64), level, bottom)
    colors = {"Inner Color": inner, "Outer Color": outer, "Seed": seed}
    floating = sprinkle(graph, blossoms, rim[0] * 0.62, level, flower_node(graph, "camellia", colors).o, seed, 1.8)
    sprig = group(graph, "CF.Flora.Plant", {"Height": 0.32, "Bend": 0.35, "Leaves": 7, "Leaf Length": 0.09,
                                             "Leaf Width": 0.03, "Generations": 1, "Branches": 2, "Flower": 2,
                                             "Flower Scale": 1.1, "Leaf Color": leaf_color, **colors}).o
    rising = sprinkle(graph, sprigs, rim[0] * 0.35, level - 0.02, sprig, seed + 5)
    tear = graph.move(group(graph, "CF.Crystal.Pendant", {"Size": 0.24, "Width": 0.22, "Drop": 0.0}).o,
                      z=outline[0][1] + 0.01)
    body = graph.join(graph.smooth_by_angle(graph.mat(shell, glass), 0.7),
                      graph.smooth_by_angle(graph.mat(liquid, water), 0.7),
                      floating, rising, graph.switch(drip, None, tear))
    scale = radius / rim[0]
    graph.result(graph.transform(body, s=graph.vec(scale, scale, scale)))
    return graph


@asset("CF.Vessel.Cascade", "Vessels")
def cascade():
    """Hanging cascade: lens bowls threaded on one rod below the origin,
    each smaller than the one above by ``Ratio`` and hanging closer, the
    spacing shrinking in the same geometric series."""
    graph = GN("CF.Vessel.Cascade", cascade.__doc__)
    count = graph.inp("Count", "INT", default=4, min=1, max=8)
    first = graph.inp("First Drop", default=1.2, subtype="DISTANCE")
    spacing = graph.inp("Spacing", default=1.3, subtype="DISTANCE")
    ratio = graph.inp("Ratio", default=0.8, min=0.3, max=0.99)
    radius = graph.inp("Radius", default=0.7, subtype="DISTANCE")
    inner = graph.inp("Inner Color", "COLOR", default=M.color("pink"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("blush"))
    leaf_color = graph.inp("Leaf Color", "COLOR", default=M.color("leaf_teal"))
    seed = graph.inp("Seed", "INT", default=0)
    rod_material = graph.inp("Rod Material", "MATERIAL", default=M.get("CF.Thread"))

    bowls = [group(graph, "CF.Vessel.LensBowl", {"Radius": 1.0, "Inner Color": inner, "Outer Color": outer,
                                                  "Leaf Color": leaf_color, "Seed": seed * 5 + variant,
                                                  "Blossoms": 5 + variant, "Sprigs": 2 + variant}).o
             for variant in range(3)]
    variants = graph.n("GeometryNodeGeometryToInstance", Geometry=bowls).o
    index = graph.index()
    shrink = graph.math("POWER", ratio, index)
    depth = first + spacing * (1.0 - shrink) / graph.max(1.0 - ratio, 0.001)
    points = graph.points(count, graph.vec(0.0, 0.0, -depth))
    hung = graph.iop(points, variants, scale=radius * shrink, pick=True,
                     index=graph.math("MODULO", index + seed, 3.0))
    last = first + spacing * (1.0 - graph.math("POWER", ratio, count - 1)) / graph.max(1.0 - ratio, 0.001)
    rod = graph.mat(graph.rod((0.0, 0.0, 0.0), graph.vec(0.0, 0.0, -last - 0.12), 0.004, 8), rod_material)
    graph.result(graph.join(hung, rod))
    return graph


@asset("CF.Vessel.Tazza", "Vessels")
def tazza():
    """Glass cake stand -- a wide dish on a baluster stem -- bearing a mound
    of hydrangeas, a druse, crystal coral or orbs (``Content`` 1..4)."""
    graph = GN("CF.Vessel.Tazza", tazza.__doc__)
    scale = graph.inp("Scale", default=1.0)
    content = graph.inp("Content", "INT", default=1, min=0, max=4)
    inner = graph.inp("Inner Color", "COLOR", default=M.color("azure"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("cyan"))
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.Glass"))

    profile = PROFILES["tazza"]
    dish = graph.lathe(shell_profile(profile["dish"], profile["thickness"]), 64)
    stem = graph.lathe(profile["stem"], 40)
    top = profile["dish"][0][1] + profile["thickness"]
    colors = {"Inner Color": inner, "Outer Color": outer, "Seed": seed}
    mound = sprinkle(graph, 6, 0.26, top + 0.08,
                     group(graph, "CF.Flora.Hydrangea", {"Radius": 0.13, "Florets": 150, **colors}).o, seed,
                     dome=0.1)
    druse = graph.move(group(graph, "CF.Crystal.Druse", {"Count": 11, "Length": 0.42, "Levels": 2, "Seed": seed}).o,
                       z=top)
    reef = graph.move(group(graph, "CF.Crystal.Coral", {"Radius": 0.16, "Levels": 2, "Children": 7, "Seed": seed}).o,
                      z=top + 0.14)
    orbs = sprinkle(graph, 3, 0.2, top + 0.1, group(graph, "CF.Vessel.Orb", {"Radius": 0.1, "Seed": seed}).o, seed)
    load = graph.index_switch(content, [None, mound, druse, reef, orbs], "GEOMETRY")
    body = graph.join(graph.smooth_by_angle(graph.mat(graph.join(dish, stem), glass), 0.7), load)
    graph.result(graph.transform(body, s=graph.vec(scale, scale, scale)))
    return graph


@asset("CF.Vessel.Orb", "Vessels")
def orb():
    """Orb of deep cobalt glass holding a spiral galaxy (``Style`` 0): stars
    on logarithmic arms, denser and warmer towards a glowing core, turning
    slowly with the scene clock.  ``Style`` 1 is a marbled planet.  ``Tail``
    adds the dewdrop tip the orbs grow from."""
    graph = GN("CF.Vessel.Orb", orb.__doc__)
    radius = graph.inp("Radius", default=0.12, subtype="DISTANCE")
    style = graph.inp("Style", "INT", default=0, min=0, max=1)
    stars = graph.inp("Stars", "INT", default=1400, min=0, max=20000)
    arms = graph.inp("Arms", "INT", default=3, min=1, max=6)
    winding = graph.inp("Winding", default=2.6, desc="Turns of the arms per e-fold of radius (1 / tan pitch)")
    spin = graph.inp("Spin", default=0.2, desc="Radians per second")
    tail = graph.inp("Tail", "BOOL", default=False)
    seed = graph.inp("Seed", "INT", default=0)
    glass = graph.inp("Glass Material", "MATERIAL", default=M.get("CF.OrbGlass"))
    star_material = graph.inp("Star Material", "MATERIAL", default=M.get("CF.Star"))
    marble = graph.inp("Marble Material", "MATERIAL", default=M.get("CF.OrbMarble"))

    ball = sphere(graph, 1.0, 64, 32)
    tip = graph.move(graph.n("GeometryNodeMeshCone", Vertices=32, Radius_Top=0.3, Radius_Bottom=0.0,
                             Depth=0.5)["Mesh"], z=-1.12)
    shape = graph.smooth(graph.switch(tail, ball, union(graph, ball, tip)))

    index = graph.index()
    arm = graph.math("MODULO", index, arms)
    t = graph.math("POWER", graph.random(0.0, 1.0, seed), 0.6)
    distance = 0.05 + t * 0.67
    angle = (arm * TAU / arms + graph.math("LOGARITHM", distance / 0.05, math.e) * winding
             + graph.random(-0.5, 0.5, seed + 1) * (0.3 + (1.0 - t) * 0.7)
             + graph.scene_time() * spin)
    height = graph.random(-1.0, 1.0, seed + 2) * 0.07 * (1.0 - t * 0.7)
    tilt = graph.vec(graph.random(-0.9, 0.9, seed + 3, ID=0), graph.random(-0.9, 0.9, seed + 4, ID=0), 0.0)
    position = graph.rotate_vector(graph.vec(distance * graph.cos(angle), distance * graph.sin(angle), height), tilt)
    size = 0.006 + graph.math("POWER", graph.random(0.0, 1.0, seed + 5), 4.0) * 0.016
    cloud = graph.points(stars, position, size)
    hue = graph.mix(t, (1.0, 0.86, 0.72, 1.0), graph.mix(graph.random(0.0, 1.0, seed + 6), M.color("azure"),
                                                          M.color("lilac"), "RGBA"), "RGBA")
    cloud = graph.store(cloud, "star_color", hue, "FLOAT_COLOR")
    core = graph.store(graph.n("GeometryNodeMeshIcoSphere", Radius=0.07, Subdivisions=3)["Mesh"], "star_color",
                       (1.0, 0.92, 0.82, 1.0), "FLOAT_COLOR")
    galaxy = graph.mat(graph.join(cloud, graph.smooth(core)), star_material)
    inside = graph.join(graph.mat(shape, glass), galaxy)
    body = graph.index_switch(style, [inside, graph.mat(shape, marble)], "GEOMETRY")
    graph.result(graph.transform(body, s=graph.vec(radius, radius, radius)))
    return graph
