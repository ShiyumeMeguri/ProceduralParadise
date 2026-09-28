"""
Particle kit -- geometry-node groups (``CF.FX.*``): the life of the scene.

Every particle is a closed-form function of the scene clock (Scene Time),
so the scene plays, scrubs and renders any frame without a bake:

* butterflies wander on smooth 4D-noise paths, facing along their flight
  and beating their wings;
* motes of light drift up through a region and twinkle;
* petals fall in tumbling spirals and fade before they touch the water;
* floaters (flowers on the pool) turn slowly around their spot.

Local frames: a swarm fills a box ``Region`` centred on the origin
(motes and petals: from z = 0 up).
"""
from __future__ import annotations

import math

from Core.gn import GN, asset
from Fractals import phyllotaxis as PHY
from .. import REALM
from . import materials as M
from .flora import blade, flower_node

TAU = math.tau
UP = (0.0, 0.0, 1.0)


def outline_mesh(graph, points, drop=0.0):
    """Filled planar polygon through ``points`` (x, y), subdivided so the
    wing shader has vertices inside it, lowered by ``drop``."""
    line = graph.set_pos(graph.mesh_line(len(points)),
                         pos=graph.index_switch(graph.index(), [(x, y, -drop) for x, y in points], "VECTOR"))
    curve = graph.n("GeometryNodeSetSplineCyclic", graph.n("GeometryNodeMeshToCurve", line).o, Cyclic=True).o
    face = graph.n("GeometryNodeSubdivideMesh", graph.fill(curve), Level=3).o
    edge = graph.n("GeometryNodeProximity", props={"target_element": "EDGES"})
    graph.assign(graph._in_socket(edge.n, "Target"), graph.n("GeometryNodeCurveToMesh", Curve=curve).o)
    face = graph.store(face, "wing_edge", edge["Distance"])
    return face


def noise_path(graph, seed_vector, time):
    """Smooth 4D-noise wander: a vector in -1..1 per particle."""
    noise = graph.n("ShaderNodeTexNoise", Vector=seed_vector, W=time, Scale=1.0, Detail=1.0, Roughness=0.5,
                    props={"noise_dimensions": "4D"})
    return (noise["Color"] - (0.5, 0.5, 0.5)) * 2.0


@asset("CF.FX.Butterflies", "Particles")
def butterflies():
    """Morpho butterflies wandering through ``Region`` on smooth 4D-noise
    paths, turned along their flight, beating their wings ``Flap Rate``
    times a second and bobbing with every stroke."""
    graph = GN("CF.FX.Butterflies", butterflies.__doc__)
    count = graph.inp("Count", "INT", default=12, min=0, max=1000)
    region = graph.inp("Region", "VECTOR", default=(6.0, 6.0, 2.5))
    span = graph.inp("Span", default=0.14, subtype="DISTANCE", desc="Wingspan")
    wander = graph.inp("Wander", default=1.5, subtype="DISTANCE")
    speed = graph.inp("Speed", default=0.08, desc="Noise-space speed of the paths")
    flap = graph.inp("Flap Rate", default=4.0, desc="Wing beats per second")
    seed = graph.inp("Seed", "INT", default=0)
    wing_material = graph.inp("Wing Material", "MATERIAL", default=M.get("CF.Wing"))
    body_material = graph.inp("Body Material", "MATERIAL", default=M.get("CF.ButterflyBody"))

    shape = REALM["butterfly"]
    right = graph.join(outline_mesh(graph, shape["forewing"]),
                       outline_mesh(graph, shape["hindwing"], shape["hindwing_drop"]))
    right = graph.store(right, "wing_u", graph.sep(graph.position())[0])
    right = graph.mat(right, wing_material)
    left = graph.n("GeometryNodeFlipFaces", graph.transform(right, s=(-1.0, 1.0, 1.0))).o
    body = shape["body"]
    length = body["head"] - body["tail"]
    trunk = graph.transform(graph.ellipsoid(body["radius"], length * 0.5, body["radius"], 12, 8),
                            t=(0.0, (body["head"] + body["tail"]) * 0.5, 0.0))
    head = graph.move(graph.ellipsoid(body["radius"] * 1.3, body["radius"] * 1.3, body["radius"] * 1.3, 10, 6),
                      y=body["head"])
    feelers = graph.join(graph.rod((0.0, body["head"], 0.0), (0.12, body["head"] + 0.3, 0.08), 0.006, 4),
                         graph.rod((0.0, body["head"], 0.0), (-0.12, body["head"] + 0.3, 0.08), 0.006, 4))
    torso = graph.mat(graph.smooth(graph.join(trunk, head, feelers)), body_material)

    seconds = graph.scene_time()
    anchor = graph.vmath("MULTIPLY", graph.random(-0.5, 0.5, seed, dtype="FLOAT_VECTOR"), region)
    phase = graph.random(0.0, 100.0, seed + 1)
    tag = anchor * 0.37 + graph.vec(seed * 1.7, seed * 0.3, 0.0)
    here = anchor + noise_path(graph, tag, seconds * speed + phase) * wander
    ahead = anchor + noise_path(graph, tag, (seconds + 0.08) * speed + phase) * wander
    beat = graph.sin((seconds * flap + graph.random(0.0, 1.0, seed + 2)) * TAU)
    position = here + graph.vec(0.0, 0.0, beat * span * 0.08)
    heading = graph.align_rotation(ahead - here, axis="Y")
    level = graph.align_rotation(UP, heading, axis="Z", pivot="Y")
    stroke = beat * math.radians(55.0) + math.radians(20.0)
    swarm = graph.points(count, position)
    size = span * 0.5
    bodies = graph.iop(swarm, torso, rot=level, scale=size)
    rights = graph.iop(swarm, right, rot=graph.rotate_rotation(level, graph.axis_angle((0.0, 1.0, 0.0), stroke * -1.0)),
                       scale=size)
    lefts = graph.iop(swarm, left, rot=graph.rotate_rotation(level, graph.axis_angle((0.0, 1.0, 0.0), stroke)),
                      scale=size)
    graph.result(graph.join(bodies, rights, lefts))
    return graph


@asset("CF.FX.Motes", "Particles")
def motes():
    """Motes of light rising slowly through ``Region`` (wrapping round at
    the top), drifting on 4D noise and twinkling."""
    graph = GN("CF.FX.Motes", motes.__doc__)
    count = graph.inp("Count", "INT", default=800, min=0, max=100000)
    region = graph.inp("Region", "VECTOR", default=(20.0, 20.0, 10.0))
    rise = graph.inp("Rise", default=0.06, desc="Metres per second")
    drift = graph.inp("Drift", default=0.35, subtype="DISTANCE")
    size = graph.inp("Size", default=0.01, subtype="DISTANCE")
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Mote"))

    seconds = graph.scene_time()
    x, y, z = graph.sep(region)
    start = graph.random(0.0, 1.0, seed, dtype="FLOAT_VECTOR")
    start_x, start_y, start_z = graph.sep(start)
    height = graph.math("FRACT", start_z + seconds * rise / z) * z
    sway = noise_path(graph, start * 7.0, seconds * 0.05)
    sway_x, sway_y, _ = graph.sep(sway)
    position = graph.vec((start_x - 0.5) * x + sway_x * drift, (start_y - 0.5) * y + sway_y * drift, height)
    radius = size * (0.4 + graph.math("POWER", graph.random(0.0, 1.0, seed + 1), 2.0) * 1.6)
    cloud = graph.points(count, position, radius)
    shimmer = 0.5 + graph.sin(seconds * graph.random(0.8, 3.0, seed + 2) + graph.random(0.0, TAU, seed + 3)) * 0.5
    fade = graph.map_range(height / z, 0.0, 0.08, 0.0, 1.0) * graph.map_range(height / z, 0.85, 1.0, 1.0, 0.0)
    cloud = graph.store(cloud, "glow", graph.math("POWER", shimmer, 3.0) * fade)
    cloud = graph.store(cloud, "hue", graph.random(0.0, 1.0, seed + 4))
    graph.result(graph.mat(cloud, material))
    return graph


@asset("CF.FX.Petals", "Particles")
def petals():
    """Petals falling through ``Region`` from its top to z = 0 in tumbling
    spirals, each on its own cycle, growing in at the top and fading out
    before the ground."""
    graph = GN("CF.FX.Petals", petals.__doc__)
    count = graph.inp("Count", "INT", default=40, min=0, max=5000)
    region = graph.inp("Region", "VECTOR", default=(8.0, 8.0, 6.0))
    fall = graph.inp("Fall Time", default=14.0, desc="Seconds from the top to the ground")
    size = graph.inp("Size", default=0.035, subtype="DISTANCE")
    inner = graph.inp("Inner Color", "COLOR", default=M.color("pink"))
    outer = graph.inp("Outer Color", "COLOR", default=M.color("blush"))
    seed = graph.inp("Seed", "INT", default=0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CF.Petal"))

    petal = blade(graph, 1.0, 0.8, 0.6, 0.2, 0.6, "petal", (5, 8))
    petal = graph.store(petal, "petal_t", 1.0)
    petal = graph.store(petal, "petal_inner", inner, "FLOAT_COLOR")
    petal = graph.store(petal, "petal_outer", outer, "FLOAT_COLOR")
    petal = graph.mat(petal, material)

    seconds = graph.scene_time()
    x, y, z = graph.sep(region)
    start = graph.random(0.0, 1.0, seed, dtype="FLOAT_VECTOR")
    start_x, start_y, start_z = graph.sep(start)
    life = graph.math("FRACT", start_z + seconds / fall)
    swirl = seconds * graph.random(0.4, 0.9, seed + 1) + start_z * TAU
    loop = graph.random(0.15, 0.45, seed + 2)
    position = graph.vec((start_x - 0.5) * x + graph.cos(swirl) * loop, (start_y - 0.5) * y + graph.sin(swirl) * loop,
                         (1.0 - life) * z)
    tumble = graph.vec(seconds * graph.random(0.6, 1.8, seed + 3), seconds * graph.random(0.4, 1.4, seed + 4),
                       swirl)
    visible = graph.map_range(life, 0.0, 0.04, 0.0, 1.0) * graph.map_range(life, 0.9, 0.99, 1.0, 0.0)
    flutter = graph.iop(graph.points(count, position), petal, rot=tumble,
                        scale=visible * size * graph.random(0.7, 1.3, seed + 5))
    graph.result(flutter)
    return graph


@asset("CF.FX.Floaters", "Particles")
def floaters():
    """Flowers floating on a pool: a flower preset scattered on the
    golden-angle annulus from ``Inner Radius`` to ``Radius`` (equal area per
    flower), each circling slowly round its spot and turning on the water."""
    graph = GN("CF.FX.Floaters", floaters.__doc__)
    count = graph.inp("Count", "INT", default=24, min=0, max=2000)
    radius = graph.inp("Radius", default=6.0, subtype="DISTANCE")
    inner = graph.inp("Inner Radius", default=0.0, subtype="DISTANCE")
    kind = graph.inp("Flower", "INT", default=2, min=1, max=5)
    scale = graph.inp("Scale", default=1.3)
    drift = graph.inp("Drift", default=0.25, subtype="DISTANCE")
    inner_color = graph.inp("Inner Color", "COLOR", default=M.color("pink"))
    outer_color = graph.inp("Outer Color", "COLOR", default=M.color("blush"))
    seed = graph.inp("Seed", "INT", default=0)

    seconds = graph.scene_time()
    t, azimuth = PHY.spiral(graph, count)
    reach = graph.math("SQRT", inner * inner + t * (radius * radius - inner * inner))
    orbit = seconds * graph.random(0.02, 0.06, seed) + graph.random(0.0, TAU, seed + 1)
    position = graph.vec(reach * graph.cos(azimuth) + graph.cos(orbit) * drift,
                         reach * graph.sin(azimuth) + graph.sin(orbit) * drift, 0.0)
    blooms = [flower_node(graph, name, {"Inner Color": inner_color, "Outer Color": outer_color, "Seed": seed}).o
              for name in REALM["flowers"]]
    bloom = graph.index_switch(kind - 1, blooms, "GEOMETRY")
    spin = graph.vec(0.0, 0.0, seconds * graph.random(-0.08, 0.08, seed + 2) + azimuth)
    graph.result(graph.iop(graph.points(count, position), bloom, rot=spin,
                           scale=scale * graph.random(0.75, 1.2, seed + 3)))
    return graph
