"""
Effects kit (``CIN.FX.*``): what a breach throws into the air, built by geometry nodes in
closed form of the scene's time -- nothing is simulated or kept between frames.

``CIN.FX.Plume``: dust pouring out of a breach.  ``Count`` puffs leave the box ``Source`` +-
``Source Size`` one by one between the frame ``Start`` and ``Duration`` frames after it, each
thrown along ``Direction`` within ``Spread`` at about ``Speed`` m/s and slowed by the air
(the speed falls to 1/e in ``Drag`` seconds), sinking at ``Sink`` m/s and carried by ``Wind``;
a puff swells from ``Radius`` by ``Growth`` metres times the square root of its age in
seconds.  The plume is a volume ``Voxel`` metres fine round the puffs, ``Thickness`` times as
dense as its dust (``CIN.Dust``) in a puff's core, thinning out over the outer ``Softness`` of
its radius, the nearest puff's alone where puffs overlap.  A puff's outline billows: swelling
out by up to ``Billows`` of its radius in rounded lumps ``Billow Size`` of its radius across,
creased where they meet (the folds of a cauliflower), a pattern of its own that it carries
along, that grows with it and that churns as it ages (``Churn`` turns of the pattern a
second).  A puff that has not left yet is not there;
before the first one leaves there is no plume.  Beside its ``density`` the plume keeps two
grids, the density gathered from each voxel over :data:`SHADE_STEPS` metres: towards the sun
(``shade``; ``Sun Direction``, which the set fills in from its sun) and straight up (``cover``),
density-metres the dust's material dims the sun's and the sky's light by.

``CIN.FX.Debris``: fragments thrown out of a breach.  ``Count`` pieces leave ``Source`` +-
``Source Size`` between the frame ``Start`` and ``Burst`` frames after it, along
``Direction`` within ``Spread`` at about ``Speed`` m/s, slowed by the air (the speed falls to 1/e
in ``Drag`` seconds), falling under ``Gravity`` (to no faster than gravity times the drag) and
turning about axes of their own at up to ``Spin`` turns a second.  Sizes run from ``Size`` down by the
power ``Size Power`` of a draw (a few large pieces, many small ones); a share ``Flat`` of them
are slabs and shards, the rest chunks.  A share ``Girders`` of all the pieces are broken girders
instead -- lengths of the tower's I-section in its steel paint (``Girder Material``), between half
``Girder Size`` and ``Girder Size`` deep (a girder is never a crumb) and ``Girder Length`` times as
long as deep.  Every piece carries a draw of its own (``variant``) for its shading.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset
from Core.nodes import Node
from . import materials as M
from .structure import i_section

CHUNKS = 6
PLATES = 3
SWELL = 1.0
SHADE_STEPS = [0.06, 0.12, 0.24, 0.48, 0.96, 1.92]
SEEDS = {"leave": 1.0, "x": 2.0, "y": 3.0, "z": 4.0, "aim x": 5.0, "aim y": 6.0, "aim z": 7.0, "speed": 8.0, "radius": 9.0,
         "turn": 10.0, "spin": 11.0, "size": 12.0, "flat": 13.0, "shape": 14.0, "variant": 15.0, "axis x": 16.0,
         "axis y": 17.0, "axis z": 18.0, "pattern x": 19.0, "pattern y": 20.0, "pattern z": 21.0, "girder": 22.0,
         "girder size": 23.0}


def _draws(graph, seed, salt):
    def draw(key, low=0.0, high=1.0):
        return graph.random(low, high, seed * salt + int(SEEDS[key]), ID=graph.index())
    return draw


def _thrown(graph, draw, source, source_size, direction, spread, speed, speed_spread):
    """The place a piece leaves from and its velocity."""
    start = source + graph.vec(draw("x", -1.0, 1.0), draw("y", -1.0, 1.0), draw("z", -1.0, 1.0)) * source_size
    aim = (direction.normalized() + graph.vec(draw("aim x", -1.0, 1.0), draw("aim y", -1.0, 1.0), draw("aim z", -1.0, 1.0))
           * graph.sin(spread)).normalized()
    return start, aim * (speed * (1.0 + draw("speed", -1.0, 1.0) * speed_spread))


@asset("CIN.FX.Plume", "Effects")
def plume():
    """Dust pouring out of a breach, a volume (see the module notes)."""
    graph = GN("CIN.FX.Plume", plume.__doc__)
    count = graph.inp("Count", "INT", default=160, min=0)
    seed = graph.inp("Seed", "INT", default=0)
    source = graph.inp("Source", "VECTOR", default=(0.0, 0.0, 0.0), subtype="TRANSLATION")
    source_size = graph.inp("Source Size", "VECTOR", default=(2.0, 0.5, 1.0), subtype="TRANSLATION")
    direction = graph.inp("Direction", "VECTOR", default=(0.0, -1.0, 0.0))
    spread = graph.inp("Spread", default=math.radians(35.0), min=0.0, max=math.pi, subtype="ANGLE")
    speed = graph.inp("Speed", default=8.0, min=0.0, desc="m/s")
    speed_spread = graph.inp("Speed Spread", default=0.5, min=0.0, max=1.0)
    drag = graph.inp("Drag", default=1.2, min=0.01, desc="Seconds for the speed to fall to 1/e")
    sink = graph.inp("Sink", default=0.6, desc="m/s downwards")
    wind = graph.inp("Wind", "VECTOR", default=(1.0, 0.0, 0.0), desc="m/s")
    radius = graph.inp("Radius", default=1.2, min=0.0, subtype="DISTANCE")
    growth = graph.inp("Growth", default=2.2, min=0.0, desc="Metres per square root of a second")
    start = graph.inp("Start", default=0.0)
    duration = graph.inp("Duration", default=30.0, min=0.0, desc="Frames over which the puffs leave")
    voxel = graph.inp("Voxel", default=0.3, min=0.02, subtype="DISTANCE")
    softness = graph.inp("Softness", default=0.6, min=0.01, max=1.0, desc="Share of a puff's radius over which it thins out")
    thickness = graph.inp("Thickness", default=1.0, min=0.0, desc="How many times the dust's density a puff's core is")
    billows = graph.inp("Billows", default=0.35, min=0.0, max=1.0, desc="Share of a puff's radius its outline swells out by")
    billow_size = graph.inp("Billow Size", default=0.35, min=0.01, desc="Billows across, as a share of a puff's radius")
    churn = graph.inp("Churn", default=0.4, min=0.0, desc="Turns of a puff's billows a second")
    fps = graph.inp("FPS", default=30.0, min=1.0)
    sun = graph.inp("Sun Direction", "VECTOR", default=(0.0, 0.0, 1.0), desc="Towards the sun: the set fills it in from its sun")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Dust"))
    draw = _draws(graph, seed, 59)
    leave = start + draw("leave") * duration
    age = graph.max((graph.scene_frame() - leave) * (1.0 / fps), 0.0)
    puffs = graph.new_points(count)
    origin, velocity = _thrown(graph, draw, source, source_size, direction, spread, speed, speed_spread)
    slowed = drag * (1.0 - graph.math("EXPONENT", age * -1.0 / drag))
    place = origin + velocity * slowed + wind * age + graph.vec(0.0, 0.0, -1.0) * (sink * age)
    puffs = graph.set_pos(puffs, pos=place)
    puffs = graph.store(puffs, "pattern", graph.vec(draw("pattern x", -50.0, 50.0), draw("pattern y", -50.0, 50.0),
                                                    draw("pattern z", -50.0, 50.0)), "FLOAT_VECTOR")
    puffs = graph.store(puffs, "age", age)
    puffs = graph.delete(puffs, graph.compare(graph.scene_frame(), leave, "LESS_THAN"))
    size = radius * draw("radius", 0.6, 1.0) + growth * graph.math("SQRT", age)
    puffs = graph.n("GeometryNodeSetPointRadius", Points=puffs, Radius=size).o
    swollen = graph.n("GeometryNodeSetPointRadius", Points=puffs, Radius=size * (1.0 + billows * SWELL)).o
    bounds = graph.n("GeometryNodeBoundBox", Geometry=swollen, Use_Radius=True)
    span = bounds["Max"] - bounds["Min"]
    cells = [graph.to_int(graph.math("MINIMUM", graph.math("MAXIMUM", axis / voxel, 2.0), 320.0), "CEILING") for axis in graph.sep(span)]
    nearest = graph.sample_nearest(puffs, graph.position())
    centre = graph.sample_index(puffs, graph.position(), nearest, "FLOAT_VECTOR")
    reach = graph.max(graph.sample_index(puffs, graph.n("GeometryNodeInputRadius").o, nearest), 0.001)
    pattern = graph.sample_index(puffs, graph.named("pattern", "FLOAT_VECTOR"), nearest, "FLOAT_VECTOR")
    puff_age = graph.sample_index(puffs, graph.named("age"), nearest)
    local = (graph.position() - centre) / reach
    lumps = graph.n("ShaderNodeTexNoise", Vector=local / billow_size + pattern, W=puff_age * churn, Scale=1.0, Detail=3.0,
                    Roughness=0.55, props={"noise_dimensions": "4D"})["Fac"]
    swell = graph.min(graph.abs(lumps - 0.5) * 4.0, SWELL)
    inside = graph.vmath("LENGTH", local) - swell * billows
    density = graph.map_range(inside, 1.0 - softness, 1.0, thickness, 0.0, interp="SMOOTHSTEP")
    cloud = graph.n("GeometryNodeVolumeCube", Density=density, Background=0.0, Min=bounds["Min"], Max=bounds["Max"],
                    Resolution_X=cells[0], Resolution_Y=cells[1], Resolution_Z=cells[2]).o
    present = graph.compare(graph.domain_size(puffs, "POINTCLOUD")["Point Count"], 0, "GREATER_THAN", "INT")
    graph.result(graph.switch(present, graph.n("GeometryNodeMeshLine", Count=0)["Mesh"], graph.mat(_shaded(graph, cloud, sun), material)))
    return graph


def _gathered(graph, density, toward):
    """The density of the grid ``density`` gathered from the field's position along ``toward`` over :data:`SHADE_STEPS`
    (density-metres)."""
    gathered = 0.0
    travelled = 0.0
    for step in SHADE_STEPS:
        middle = graph.position() + toward * (travelled + step * 0.5)
        sample = graph.n("GeometryNodeSampleGrid", Grid=density, Position=middle, props={"data_type": "FLOAT"})["Value"]
        gathered = gathered + sample * step
        travelled += step
    return gathered


def _shaded(graph, volume, sun):
    """``volume`` with grids ``shade`` and ``cover`` beside its ``density``: the density gathered from every voxel towards
    ``sun`` and straight up."""
    density = graph.n("GeometryNodeGetNamedGrid", Volume=volume, Name="density", props={"data_type": "FLOAT"})["Grid"]
    gather = graph.ng.nodes.new("GeometryNodeFieldToGrid")
    gather.data_type = "FLOAT"
    graph.assign(gather.inputs["Topology"], density)
    upward = graph.n("FunctionNodeInputVector", props={"vector": (0.0, 0.0, 1.0)}).o
    for name, toward in (("shade", graph.vmath("NORMALIZE", sun)), ("cover", upward)):
        gather.grid_items.new("FLOAT", name)
        graph.assign(gather.inputs[name], _gathered(graph, density, toward))
    for name in ("shade", "cover"):
        volume = graph.n("GeometryNodeStoreNamedGrid", Volume=volume, Name=name, Grid=Node(graph, gather)[name],
                         props={"data_type": "FLOAT"}).o
    return volume


def _chunk(graph, variant):
    """A broken lump of concrete a metre across: a coarse sphere knocked out of round."""
    lump = graph.n("GeometryNodeMeshIcoSphere", Radius=0.5, Subdivisions=2)["Mesh"]
    dent = graph.n("ShaderNodeTexNoise", Vector=graph.position() + graph.vec(variant * 7.3, variant * 3.1, variant * 5.7), Scale=1.6,
                   Detail=1.0, props={"noise_dimensions": "3D"})["Fac"]
    lump = graph.set_pos(lump, offset=graph.normal() * ((dent - 0.5) * 0.8))
    return graph.transform(lump, s=graph.vec(1.0, 0.75 - variant * 0.04, 0.6 - variant * 0.05))


def _plate(graph, variant):
    """A slab or shard a metre long: a thin plate with a broken outline."""
    outline = [(-0.5, -0.32), (0.1 + variant * 0.08, -0.36), (0.5, -0.12 + variant * 0.1), (0.38, 0.3), (-0.2, 0.36 - variant * 0.08),
               (-0.46, 0.08)]
    face = graph.fill(graph.polyline([(x, y, 0.0) for x, y in outline], cyclic=True))
    return graph.solid(graph.move(face, z=-0.03 - variant * 0.01), 0.06 + variant * 0.02)


@asset("CIN.FX.Debris", "Effects")
def debris():
    """Fragments thrown out of a breach (see the module notes)."""
    graph = GN("CIN.FX.Debris", debris.__doc__)
    count = graph.inp("Count", "INT", default=400, min=0)
    seed = graph.inp("Seed", "INT", default=0)
    source = graph.inp("Source", "VECTOR", default=(0.0, 0.0, 0.0), subtype="TRANSLATION")
    source_size = graph.inp("Source Size", "VECTOR", default=(2.0, 0.5, 1.5), subtype="TRANSLATION")
    direction = graph.inp("Direction", "VECTOR", default=(0.0, -1.0, 0.3))
    spread = graph.inp("Spread", default=math.radians(40.0), min=0.0, max=math.pi, subtype="ANGLE")
    speed = graph.inp("Speed", default=12.0, min=0.0, desc="m/s")
    speed_spread = graph.inp("Speed Spread", default=0.6, min=0.0, max=1.0)
    gravity = graph.inp("Gravity", default=9.81, min=0.0, desc="m/s²")
    drag = graph.inp("Drag", default=3.0, min=0.01, desc="Seconds for the speed to fall to 1/e")
    spin = graph.inp("Spin", default=1.5, min=0.0, desc="Turns a second at most")
    size = graph.inp("Size", default=0.6, min=0.0, subtype="DISTANCE")
    size_power = graph.inp("Size Power", default=3.0, min=0.1, desc="Above 1: many small pieces, few large ones")
    flat = graph.inp("Flat", default=0.35, min=0.0, max=1.0, desc="Share of slabs and shards")
    girders = graph.inp("Girders", default=0.0, min=0.0, max=1.0, desc="Share of broken girders")
    girder_size = graph.inp("Girder Size", default=0.4, min=0.0, subtype="DISTANCE", desc="The deepest girder's depth")
    girder_length = graph.inp("Girder Length", default=5.0, min=1.0, desc="A girder's length over its depth")
    start = graph.inp("Start", default=0.0)
    burst = graph.inp("Burst", default=4.0, min=0.0, desc="Frames over which the pieces leave")
    fps = graph.inp("FPS", default=30.0, min=1.0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Debris"))
    girder_material = graph.inp("Girder Material", "MATERIAL", default=M.get("CIN.SteelPaint"))
    draw = _draws(graph, seed, 61)
    leave = start + draw("leave") * burst
    age = graph.max((graph.scene_frame() - leave) * (1.0 / fps), 0.0)
    pieces = graph.new_points(count)
    origin, velocity = _thrown(graph, draw, source, source_size, direction, spread, speed, speed_spread)
    slowed = drag * (1.0 - graph.math("EXPONENT", age * -1.0 / drag))
    place = origin + velocity * slowed + graph.vec(0.0, 0.0, -1.0) * (gravity * drag * (age - slowed))
    pieces = graph.set_pos(pieces, pos=place)
    pieces = graph.store(pieces, "variant", draw("variant"))
    pieces = graph.delete(pieces, graph.compare(graph.scene_frame(), leave, "LESS_THAN"))
    girder = graph.transform(i_section(graph, 0.18, 0.12), s=graph.vec(1.0, 0.65, girder_length))
    shapes = [graph.mat(shape, material) for shape in
              [_chunk(graph, k / CHUNKS) for k in range(CHUNKS)] + [_plate(graph, k / PLATES) for k in range(PLATES)]]
    shapes.append(graph.mat(girder, girder_material))
    library = graph.n("GeometryNodeGeometryToInstance", Geometry=list(reversed(shapes))).o
    is_flat = graph.compare(draw("flat"), flat, "LESS_THAN")
    is_girder = graph.compare(draw("girder"), girders, "LESS_THAN")
    chunk = graph.to_int(draw("shape") * CHUNKS, "FLOOR")
    plate = CHUNKS + graph.to_int(draw("shape") * PLATES, "FLOOR")
    shape = graph.switch(is_girder, graph.switch(is_flat, chunk, plate, "INT"), CHUNKS + PLATES, "INT")
    axis = graph.vec(draw("axis x", -1.0, 1.0), draw("axis y", -1.0, 1.0), draw("axis z", -1.0, 1.0)).normalized()
    tumble = graph.axis_angle(axis, draw("turn") * (2.0 * math.pi) + draw("spin", -1.0, 1.0) * spin * (2.0 * math.pi) * age)
    scale = graph.switch(is_girder, size * (draw("size") ** size_power), girder_size * draw("girder size", 0.5, 1.0), "FLOAT")
    graph.result(graph.iop(pieces, library, rot=tumble, scale=graph.vec(scale, scale, scale), pick=True, index=shape))
    return graph
