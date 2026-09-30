"""
Flora kit -- geometry-node groups (``GH.Flora.*``): the plants of the
conservatory, each one generator whose presets (``Greenhouse.json``) give
the species.

A blade (leaf or leaflet) is a grid bent into shape: a width profile along
its length, cupped across, curled along, stored with ``leaf_u`` (0 at the
base, 1 at the tip) and ``leaf_v`` (-1..1 across).  Every leaf also carries
its own ``leaf_color``, drawn between the plant's two colours, so the one
leaf material (``GH.Leaf``) serves the whole garden.

* ``Pinnate``: fronds of leaflets on an arching rachis around a crown --
  areca and kentia palms, sword and Boston ferns.
* ``Rosette``: strap leaves from one point -- dracaena, spider plant, grass.
* ``Broadleaf``: big leaves on long petioles -- monstera (split margins),
  alocasia, philodendron.
* ``Umbrella``: leaflets radiating from a petiole tip, the leaves filling a
  crown -- schefflera, and the round leafy crowns of trees and shrubs.
* ``Succulent``: fleshy leaves on the golden-angle spiral -- echeveria,
  aloe, haworthia.

Local frames: every plant grows from the origin along +Z.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset
from Core.render import INK_QUIET
from . import materials as M

TAU = math.tau
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))
UP = (0.0, 0.0, 1.0)


def blade(graph, length, width, cup, curl, fullness, taper, resolution=(5, 10)):
    """Blade along +Z from the origin, width along X, cupped towards +Y and
    curling back towards -Y along its length.  The half width at ``u`` is
    ``width / 2 * sin(pi * u ** fullness) ** taper``."""
    grid = graph.grid(1.0, 1.0, resolution[0], resolution[1])
    x, y, _ = graph.sep(graph.position())
    u = y + 0.5
    v = x * 2.0
    grid = graph.store(grid, "leaf_u", u)
    grid = graph.store(grid, "leaf_v", v)
    swell = graph.max(graph.sin(graph.math("POWER", graph.max(u, 0.0001), fullness) * math.pi), 0.0)
    half = graph.math("POWER", swell, taper) * width * 0.5
    lift = cup * half * v * v - curl * length * u * u
    return graph.smooth(graph.set_pos(grid, pos=graph.vec(v * half, lift, u * length)))


def leaf_colors(graph, geometry, first, second, seed, domain="INSTANCE"):
    """``leaf_color`` on every element of ``domain``: a random mix of the two
    colours; foliage is quiet for the ink pass (outlined against what lies
    behind it, not leaf by leaf)."""
    mix = graph.mix(graph.random(0.0, 1.0, seed), first, second, "RGBA")
    geometry = graph.store(geometry, "leaf_color", mix, "FLOAT_COLOR", domain)
    return graph.store(geometry, INK_QUIET, 1.0, "FLOAT", domain)


def crown_points(graph, count, spread_low, spread_high, seed):
    """``count`` points at the origin carrying ``azimuth`` (golden-angle
    spiral) and ``elevation`` (from ``spread_high`` for the first, most
    upright, to ``spread_low``); returns (points, azimuth, elevation)."""
    points = graph.points(count, (0.0, 0.0, 0.0))
    index = graph.index()
    t = (index + 0.5) / graph.max(count, 1)
    azimuth = index * GOLDEN_ANGLE + graph.random(-0.25, 0.25, seed)
    elevation = spread_high + (spread_low - spread_high) * t + graph.random(-0.08, 0.08, seed + 1)
    return points, azimuth, elevation


@asset("GH.Flora.Pinnate", "Flora")
def pinnate():
    """Fronds of paired leaflets on arching rachises around a crown.  A frond
    rises at its elevation, arches (``Arch``) and droops towards the tip
    (``Droop``); leaflets leave the rachis at ``Leaflet Angle``, hang by
    ``Leaflet Droop`` and are longest at mid-frond.  ``Stem`` lifts the
    crown on a trunk (palms)."""
    graph = GN("GH.Flora.Pinnate", pinnate.__doc__)
    fronds = graph.inp("Fronds", "INT", default=14, min=1, max=200)
    length = graph.inp("Frond Length", default=1.2, subtype="DISTANCE")
    length_jitter = graph.inp("Length Jitter", default=0.25, min=0.0, max=1.0)
    spread_low = graph.inp("Spread Low", default=math.radians(10.0), subtype="ANGLE")
    spread_high = graph.inp("Spread High", default=math.radians(70.0), subtype="ANGLE")
    arch = graph.inp("Arch", default=0.5)
    droop = graph.inp("Droop", default=0.6)
    bare = graph.inp("Bare Base", default=0.15, min=0.0, max=0.9)
    leaflets = graph.inp("Leaflets", "INT", default=30, min=1, max=200)
    leaflet_length = graph.inp("Leaflet Length", default=0.3, subtype="DISTANCE")
    leaflet_width = graph.inp("Leaflet Width", default=0.03, subtype="DISTANCE")
    leaflet_angle = graph.inp("Leaflet Angle", default=math.radians(45.0), subtype="ANGLE")
    leaflet_droop = graph.inp("Leaflet Droop", default=math.radians(20.0), subtype="ANGLE")
    leaflet_curl = graph.inp("Leaflet Curl", default=0.15)
    leaflet_cup = graph.inp("Leaflet Cup", default=0.3)
    stem = graph.inp("Stem", default=0.0, subtype="DISTANCE")
    stem_radius = graph.inp("Stem Radius", default=0.03, subtype="DISTANCE")
    first = graph.inp("Color A", "COLOR", default=M.color("leaf"))
    second = graph.inp("Color B", "COLOR", default=M.color("leaf_light"))
    seed = graph.inp("Seed", "INT", default=0)
    leaf_material = graph.inp("Material", "MATERIAL", default=M.get("GH.Leaf"))
    stem_material = graph.inp("Stem Material", "MATERIAL", default=M.get("GH.Bark"))

    steps = leaflets
    line = graph.mesh_line(steps, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    t = bare + (1.0 - bare) * graph.index() / graph.max(steps - 1, 1)
    along = graph.vec(t, 0.0, arch * t - droop * t * t)
    tangent = graph.vec(1.0, 0.0, arch - droop * 2.0 * t).normalized()
    spine = graph.set_pos(line, pos=along)
    spine, captured = graph.capture(spine, "POINT", tangent=tangent, t=t)
    size = graph.math("POWER", graph.max(graph.sin(captured["t"] * math.pi), 0.05), 0.6)
    leaf = blade(graph, 1.0, 1.0, leaflet_cup, leaflet_curl, 0.8, 0.9, (3, 8))

    def side(sign):
        outward = graph.vec(0.0, sign, 0.0)
        heading = graph.vec(0.0, 0.0, -1.0) * graph.sin(leaflet_droop) + (
            captured["tangent"] * graph.cos(leaflet_angle) + outward * graph.sin(leaflet_angle)) * graph.cos(leaflet_droop)
        rotation = graph.align_rotation(captured["tangent"] * -sign, rotation=graph.align_rotation(heading, axis="Z"), axis="X", pivot="Z")
        scale = graph.vec(leaflet_width, leaflet_width, leaflet_length) * (size * graph.random(0.85, 1.1, seed + 7) / graph.max(length, 0.001))
        return graph.iop(spine, leaf, rot=rotation, scale=scale)

    frond = graph.realize(graph.join(side(1.0), side(-1.0)))
    rachis_curve = graph.n("GeometryNodeMeshToCurve", spine).o
    rachis = graph.sweep(rachis_curve, graph.circle(0.007 / graph.max(length, 0.001), 6), True)
    rachis = graph.store(rachis, "leaf_u", 0.0)
    frond = graph.join(frond, rachis)

    points, azimuth, elevation = crown_points(graph, fronds, spread_low, spread_high, seed)
    points = graph.set_pos(points, offset=graph.vec(0.0, 0.0, stem))
    scale = length * graph.random(1.0 - length_jitter, 1.0, seed + 3)
    crown = graph.iop(points, frond, rot=graph.vec(0.0, elevation * -1.0, azimuth), scale=scale)
    crown = leaf_colors(graph, crown, first, second, seed + 5)
    plant = graph.mat(graph.realize(crown), leaf_material)
    trunk = graph.mat(graph.smooth(graph.cylinder(stem_radius, stem, 12)), stem_material)
    trunk = graph.move(trunk, z=stem * 0.5)
    graph.result(graph.join(plant, graph.switch(graph.compare(stem, 0.001, "GREATER_THAN"), None, trunk)))
    return graph


@asset("GH.Flora.Rosette", "Flora")
def rosette():
    """Strap leaves from one point: long narrow blades leaving the centre on
    the golden-angle spiral, the inner ones upright, the outer ones
    spreading and arching over (``Arch``)."""
    graph = GN("GH.Flora.Rosette", rosette.__doc__)
    leaves = graph.inp("Leaves", "INT", default=24, min=1, max=400)
    length = graph.inp("Leaf Length", default=0.6, subtype="DISTANCE")
    width = graph.inp("Leaf Width", default=0.05, subtype="DISTANCE")
    length_jitter = graph.inp("Length Jitter", default=0.3, min=0.0, max=1.0)
    spread_low = graph.inp("Spread Low", default=math.radians(15.0), subtype="ANGLE")
    spread_high = graph.inp("Spread High", default=math.radians(80.0), subtype="ANGLE")
    arch = graph.inp("Arch", default=0.35)
    cup = graph.inp("Cup", default=0.4)
    fullness = graph.inp("Fullness", default=0.35)
    stem = graph.inp("Stem", default=0.0, subtype="DISTANCE")
    first = graph.inp("Color A", "COLOR", default=M.color("leaf"))
    second = graph.inp("Color B", "COLOR", default=M.color("leaf_light"))
    seed = graph.inp("Seed", "INT", default=0)
    leaf_material = graph.inp("Material", "MATERIAL", default=M.get("GH.Leaf"))
    stem_material = graph.inp("Stem Material", "MATERIAL", default=M.get("GH.Bark"))

    leaf = blade(graph, 1.0, 1.0, cup * -1.0, arch * -1.0, fullness, 0.8, (3, 12))
    points, azimuth, elevation = crown_points(graph, leaves, spread_low, spread_high, seed)
    points = graph.set_pos(points, offset=graph.vec(0.0, 0.0, stem))
    size = length * graph.random(1.0 - length_jitter, 1.0, seed + 3)
    tilt = math.pi * 0.5 - elevation
    rotation = graph.vec(tilt * -1.0, 0.0, azimuth - math.pi * 0.5)
    crown = graph.iop(points, leaf, rot=rotation, scale=graph.vec(width / graph.max(length, 0.001), 1.0, 1.0) * size)
    crown = leaf_colors(graph, crown, first, second, seed + 5)
    plant = graph.mat(graph.realize(crown), leaf_material)
    trunk = graph.move(graph.mat(graph.smooth(graph.cylinder(0.02, stem, 10)), stem_material), z=stem * 0.5)
    graph.result(graph.join(plant, graph.switch(graph.compare(stem, 0.001, "GREATER_THAN"), None, trunk)))
    return graph


def broad_blade(graph, splits, split_depth, lobe):
    """Unit broad leaf along +Z (length 1, width 1): an acuminate ovate
    outline (widest at two fifths of the length, drawn to a point), basal
    lobes swept back past the petiole by ``lobe`` (heart-shaped leaves),
    folded along the midrib and drooping to the tip, with ``splits`` pairs
    of slanted slits cut from the margin to ``split_depth`` of the half
    width (monstera)."""
    grid = graph.grid(1.0, 1.0, 29, 81)
    x, y, _ = graph.sep(graph.position())
    u = y + 0.5
    v = x * 2.0
    grid = graph.store(grid, "leaf_u", u)
    grid = graph.store(grid, "leaf_v", v)
    outline = graph.math("POWER", graph.max(u, 0.0), 0.5) * graph.math("POWER", graph.max(1.0 - u, 0.0), 0.75) * 2.32
    basal = graph.max(1.0 - u * 4.0, 0.0)
    half = (outline + lobe * basal) * 0.5
    across = graph.abs(v)
    fold = half * across * 0.22
    droop = u * u * 0.18
    back = lobe * basal * across * 0.35
    shaped = graph.set_pos(grid, pos=graph.vec(v * half, fold - droop, u - back))
    slit_phase = graph.math("FRACT", u * splits + across * 0.35)
    in_slit = graph.bool_and(graph.compare(graph.abs(slit_phase - 0.5), across * 0.12 + 0.02, "LESS_THAN"),
                             graph.compare(across, 1.0 - split_depth, "GREATER_THAN"))
    in_slit = graph.bool_and(in_slit, graph.compare(splits, 0.5, "GREATER_THAN"))
    in_slit = graph.bool_and(in_slit, graph.bool_and(graph.compare(u, 0.15, "GREATER_THAN"), graph.compare(u, 0.9, "LESS_THAN")))
    face_slit = graph.on_domain(graph.switch(in_slit, 0.0, 1.0, "FLOAT"), "FACE")
    return graph.smooth(graph.delete(shaped, graph.compare(face_slit, 0.5, "GREATER_THAN"), "FACE"))


@asset("GH.Flora.Broadleaf", "Flora")
def broadleaf():
    """Big leaves on long petioles from one base: each petiole rises at its
    elevation and bends over, the blade hangs from its tip facing up and
    out.  ``Splits`` cuts monstera slits; ``Lobe`` gives heart-shaped
    bases (alocasia, philodendron)."""
    graph = GN("GH.Flora.Broadleaf", broadleaf.__doc__)
    leaves = graph.inp("Leaves", "INT", default=7, min=1, max=60)
    leaf_length = graph.inp("Leaf Length", default=0.45, subtype="DISTANCE")
    leaf_width = graph.inp("Leaf Width", default=0.38, subtype="DISTANCE")
    petiole = graph.inp("Petiole", default=0.6, subtype="DISTANCE")
    length_jitter = graph.inp("Length Jitter", default=0.3, min=0.0, max=1.0)
    spread_low = graph.inp("Spread Low", default=math.radians(25.0), subtype="ANGLE")
    spread_high = graph.inp("Spread High", default=math.radians(75.0), subtype="ANGLE")
    blade_tilt = graph.inp("Blade Tilt", default=math.radians(55.0), subtype="ANGLE")
    splits = graph.inp("Splits", default=0.0)
    split_depth = graph.inp("Split Depth", default=0.6)
    lobe = graph.inp("Lobe", default=0.15)
    first = graph.inp("Color A", "COLOR", default=M.color("leaf_deep"))
    second = graph.inp("Color B", "COLOR", default=M.color("leaf"))
    seed = graph.inp("Seed", "INT", default=0)
    leaf_material = graph.inp("Material", "MATERIAL", default=M.get("GH.Leaf"))

    leaf = broad_blade(graph, splits, split_depth, lobe)
    leaf = graph.transform(leaf, r=graph.vec(blade_tilt * -1.0, 0.0, 0.0), s=graph.vec(leaf_width, leaf_width, leaf_length))
    stalk = graph.sweep(graph.curve_line((0.0, 0.0, -1.0), (0.0, 0.0, 0.0)), graph.circle(0.008, 6), True)
    stalk = graph.store(stalk, "leaf_u", 0.0)
    unit = graph.join(graph.move(leaf, z=0.0), graph.transform(stalk, s=graph.vec(1.0, 1.0, petiole)))
    unit = graph.move(unit, z=petiole)
    points, azimuth, elevation = crown_points(graph, leaves, spread_low, spread_high, seed)
    tilt = math.pi * 0.5 - elevation
    size = graph.random(1.0 - length_jitter, 1.0, seed + 3)
    crown = graph.iop(points, unit, rot=graph.vec(tilt * -1.0, 0.0, azimuth - math.pi * 0.5), scale=size)
    crown = leaf_colors(graph, crown, first, second, seed + 5)
    graph.result(graph.mat(graph.realize(crown), leaf_material))
    return graph


def umbrella_leaf(graph, leaflets, leaflet_length, leaflet_width, droop):
    """Palmately compound leaf facing +Z: ``leaflets`` obovate blades --
    widest two thirds of the way out, round-tipped, like schefflera's --
    radiating from the origin in the XY plane, drooping by ``droop``."""
    blade_mesh = blade(graph, 1.0, 1.0, 0.25, 0.1, 1.7, 0.45, (5, 9))
    ring = graph.points(leaflets, (0.0, 0.0, 0.0))
    angle = graph.index() * (TAU / graph.max(leaflets, 1))
    rotation = graph.vec(math.pi * 0.5 + droop, 0.0, angle)
    return graph.realize(graph.iop(ring, blade_mesh, rot=rotation,
                                   scale=graph.vec(leaflet_width, leaflet_width, leaflet_length) * graph.random(0.8, 1.1, 11)))


@asset("GH.Flora.Umbrella", "Flora")
def umbrella():
    """A crown of leaves gathered in clumps: ``Clumps`` clump centres lie
    through an ellipsoid crown (``Crown Radius``, ``Crown Height`` above
    ``Stem``), and ``Leaves`` palmate leaves gather round them within
    ``Clump Size`` of the crown radius, each facing out of its clump and up
    (``Facing``).  ``Leaflets`` 1 gives simple leaves -- the lumpy crowns of
    trees and shrubs; more give the umbrellas of schefflera.  ``Stems``
    branches fork from the top of the trunk (``Stem`` tall) to the first
    clumps."""
    graph = GN("GH.Flora.Umbrella", umbrella.__doc__)
    leaves = graph.inp("Leaves", "INT", default=80, min=1, max=40000)
    leaflets = graph.inp("Leaflets", "INT", default=7, min=1, max=16)
    leaflet_length = graph.inp("Leaflet Length", default=0.12, subtype="DISTANCE")
    leaflet_width = graph.inp("Leaflet Width", default=0.045, subtype="DISTANCE")
    droop = graph.inp("Droop", default=math.radians(15.0), subtype="ANGLE")
    radius = graph.inp("Crown Radius", default=0.5, subtype="DISTANCE")
    height = graph.inp("Crown Height", default=0.8, subtype="DISTANCE")
    clumps = graph.inp("Clumps", "INT", default=8, min=1, max=400)
    clump_size = graph.inp("Clump Size", default=0.35, min=0.01, max=1.0)
    stem = graph.inp("Stem", default=0.3, subtype="DISTANCE")
    stems = graph.inp("Stems", "INT", default=5, min=0, max=64)
    stem_radius = graph.inp("Stem Radius", default=0.012, subtype="DISTANCE")
    facing = graph.inp("Facing", default=0.6, min=0.0, max=1.0)
    first = graph.inp("Color A", "COLOR", default=M.color("leaf"))
    second = graph.inp("Color B", "COLOR", default=M.color("leaf_yellow"))
    seed = graph.inp("Seed", "INT", default=0)
    leaf_material = graph.inp("Material", "MATERIAL", default=M.get("GH.Leaf"))
    stem_material = graph.inp("Stem Material", "MATERIAL", default=M.get("GH.Bark"))

    center = graph.vec(0.0, 0.0, stem + height * 0.5)
    semi_axes = graph.vec(radius, radius, height * 0.5)
    index = graph.index()
    azimuth = index * GOLDEN_ANGLE + graph.random(0.0, 0.5, seed)
    lift = graph.random(-0.55, 0.95, seed + 1)
    reach = graph.math("POWER", graph.random(0.0, 1.0, seed + 2), 0.5) * (1.0 - clump_size * 0.5)
    ring = graph.math("SQRT", graph.max(1.0 - lift * lift, 0.0)) * reach
    unit_direction = graph.vec(graph.cos(azimuth) * ring, graph.sin(azimuth) * ring, lift * reach)
    hubs = graph.set_pos(graph.points(clumps, (0.0, 0.0, 0.0)), pos=center + graph.vmath("MULTIPLY", unit_direction, semi_axes))

    owner = graph.random(0, 100000, seed + 3, dtype="INT") % graph.max(clumps, 1)
    hub = graph.sample_index(hubs, graph.position(), owner, "FLOAT_VECTOR")
    spin = graph.random(0.0, TAU, seed + 4)
    rise = graph.random(-0.6, 1.0, seed + 5)
    spread = graph.math("SQRT", graph.max(1.0 - rise * rise, 0.0))
    offset_direction = graph.vec(graph.cos(spin) * spread, graph.sin(spin) * spread, rise)
    offset = offset_direction * (graph.math("POWER", graph.random(0.0, 1.0, seed + 6), 0.4) * clump_size * radius)
    points = graph.set_pos(graph.points(leaves, (0.0, 0.0, 0.0)), pos=hub + offset)
    outward = (offset_direction + graph.vec(0.0, 0.0, 0.35)).normalized()
    normal = (graph.vec(0.0, 0.0, 1.0) * (1.0 - facing) + outward * facing).normalized()
    rotation = graph.random_spin(graph.align_rotation(normal, axis="Z"), seed + 7)
    leaf = umbrella_leaf(graph, leaflets, leaflet_length, leaflet_width, droop)
    crown = graph.iop(points, leaf, rot=rotation, scale=graph.random(0.75, 1.15, seed + 8))
    crown = leaf_colors(graph, crown, first, second, seed + 9)
    foliage = graph.mat(graph.realize(crown), leaf_material)

    fork = graph.vec(0.0, 0.0, stem)
    tip = graph.sample_index(hubs, graph.position(), graph.index() % graph.max(clumps, 1), "FLOAT_VECTOR") * graph.vec(0.8, 0.8, 0.92) - fork
    base = graph.points(stems, fork)
    branch = graph.sweep(graph.curve_line((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), graph.circle(1.0, 6), True)
    branches = graph.iop(base, branch, rot=graph.align_rotation(tip, axis="Z"), scale=graph.vec(stem_radius * 0.6, stem_radius * 0.6, tip.length()))
    trunk = graph.transform(branch, s=graph.vec(stem_radius, stem_radius, stem))
    wood = graph.mat(graph.smooth(graph.join(graph.realize(branches), trunk)), stem_material)
    graph.result(graph.join(foliage, graph.switch(graph.compare(stems, 0, "GREATER_THAN", "INT"), None, wood)))
    return graph


def fleshy_leaf(graph, taper, thickness):
    """Unit fleshy leaf along +Z (length 1, width 1): a flattened spheroid
    pointed at the tip by ``taper``, ``thickness`` of its width thick,
    carrying ``leaf_u``/``leaf_v``."""
    body = graph.n("GeometryNodeMeshUVSphere", Segments=16, Rings=12, Radius=0.5)["Mesh"]
    x, y, z = graph.sep(graph.position())
    u = z + 0.5
    body = graph.store(body, "leaf_u", u)
    body = graph.store(body, "leaf_v", x * 2.0)
    narrowing = 1.0 - graph.math("POWER", graph.max(u, 0.0), 1.5) * taper
    body = graph.set_pos(body, pos=graph.vec(x * narrowing, y * thickness * narrowing, u))
    return graph.smooth(body)


@asset("GH.Flora.Succulent", "Flora")
def succulent():
    """Fleshy leaves on the golden-angle spiral: leaf k of n leaves the stem
    at elevation from ``Upright`` (the youngest, innermost) to ``Open``,
    growing from ``Size Min`` to full size, cupping up at the tips
    (``Tip Lift``) -- echeveria with short broad spoon leaves, aloe and
    haworthia with long tapering ones."""
    graph = GN("GH.Flora.Succulent", succulent.__doc__)
    leaves = graph.inp("Leaves", "INT", default=34, min=1, max=300)
    length = graph.inp("Leaf Length", default=0.07, subtype="DISTANCE")
    width = graph.inp("Leaf Width", default=0.04, subtype="DISTANCE")
    thickness = graph.inp("Thickness", default=0.35)
    taper = graph.inp("Taper", default=0.6, min=0.0, max=1.0)
    upright = graph.inp("Upright", default=math.radians(80.0), subtype="ANGLE")
    opened = graph.inp("Open", default=math.radians(10.0), subtype="ANGLE")
    size_min = graph.inp("Size Min", default=0.35, min=0.0, max=1.0)
    tip_lift = graph.inp("Tip Lift", default=0.15)
    first = graph.inp("Color A", "COLOR", default=M.color("succulent"))
    second = graph.inp("Color B", "COLOR", default=M.color("leaf_light"))
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("GH.Succulent"))

    leaf = fleshy_leaf(graph, taper, thickness)
    _, _, z = graph.sep(graph.position())
    leaf = graph.set_pos(leaf, offset=graph.vec(0.0, z * z * tip_lift, 0.0))
    points = graph.points(leaves, (0.0, 0.0, 0.0))
    index = graph.index()
    age = (index + 0.5) / graph.max(leaves, 1)
    elevation = upright + (opened - upright) * age
    azimuth = index * GOLDEN_ANGLE
    size = size_min + (1.0 - size_min) * graph.math("SQRT", age)
    rotation = graph.vec(math.pi * 0.5 - elevation, 0.0, azimuth - math.pi * 0.5)
    rosette_mesh = graph.iop(points, leaf, rot=rotation, scale=graph.vec(width, width, length) * size)
    rosette_mesh = leaf_colors(graph, rosette_mesh, first, second, seed)
    graph.result(graph.mat(graph.realize(rosette_mesh), material))
    return graph
