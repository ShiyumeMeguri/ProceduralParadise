"""
Birds kit (``CIN.Birds.*``): crows, posed and flown by geometry nodes.

``CIN.Birds.Crow``: one crow at a moment of its wingbeat, built at a crow's size (half a metre
long, a metre across the wings) nose along +X and up +Z: a body tapering into a fan of tail
feathers, head and beak, and two wings -- an arm and a hand whose primaries spread into the
slotted fingers a crow's silhouette is known by.  ``Phase`` runs the beat: 0 wings high, 0.5
low; on the downstroke the wings reach out, on the upstroke the hands sweep back and fold.

``CIN.Birds.Flock``: crows flying straight through the set from the frame ``Start``: each
starts at its own place in the box ``Origin`` +- ``Extent``, heads within ``Spread`` of
``Heading`` at its own speed about ``Speed``, and beats its wings at its own rate about
``Beat`` (a share ``Glide`` of them glide, wings out); each is its own size about ``Size``.
The wingbeat is drawn from ``POSES`` posed crows.  Nothing is kept between frames: a flock
is where its birds are at the frame's time.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset
from . import materials as M

POSES = 12
SEEDS = {"place x": 1.0, "place y": 2.0, "place z": 3.0, "turn": 4.0, "climb": 5.0, "speed": 6.0, "beat": 7.0,
         "phase": 8.0, "glide": 9.0, "size": 10.0, "bank": 11.0}


def plate(graph, outline, thickness):
    """A flat feathered plate: the closed ``outline`` [(x, y), ...] in the XY plane, ``thickness`` thick."""
    face = graph.fill(graph.polyline([(x, y, 0.0) for x, y in outline], cyclic=True))
    return graph.solid(graph.move(face, z=thickness * -0.5), thickness)


def fingers(graph, thickness):
    """The parted tips of the hand's outer primaries in the wrist's frame (+Y out along the wing):
    five feathers fanning from the end of the hand, the gaps between them the slots a crow is
    known by in the sky."""
    feathers = []
    for k in range(5):
        root_x, root_y = 0.05 - k * 0.034, 0.15 - k * 0.006
        angle = math.radians(-8.0 - k * 11.0)
        length = 0.15 - k * 0.012
        width = 0.03
        tip = (root_x + math.sin(angle) * length, root_y + math.cos(angle) * length)
        side = (math.cos(angle) * width * 0.5, -math.sin(angle) * width * 0.5)
        feathers.append(plate(graph, [(root_x + side[0], root_y + side[1]), (tip[0] + side[0] * 0.45, tip[1] + side[1] * 0.45),
                                      (tip[0] + math.sin(angle) * 0.01, tip[1] + math.cos(angle) * 0.01),
                                      (tip[0] - side[0] * 0.45, tip[1] - side[1] * 0.45), (root_x - side[0], root_y - side[1])],
                              thickness))
    return graph.join(*feathers)


@asset("CIN.Birds.Crow", "Birds")
def crow():
    """One crow at the moment ``Phase`` of its wingbeat (0 wings high, 0.5 low), nose along +X,
    up +Z, its left wing towards +Y (see the module notes)."""
    graph = GN("CIN.Birds.Crow", crow.__doc__)
    phase = graph.inp("Phase", default=0.25, min=0.0, max=1.0)
    stroke = graph.inp("Stroke", default=math.radians(52.0), min=0.0, max=math.radians(80.0), subtype="ANGLE",
                       desc="How far above and below level the wings swing")
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.Crow"))
    turn = phase * (2.0 * math.pi)
    raised = stroke * graph.cos(turn)
    folding = graph.max(graph.sin(turn) * -1.0, 0.0)
    thickness = 0.012
    arm = plate(graph, [(0.045, 0.0), (0.075, 0.1), (0.07, 0.19), (-0.115, 0.19), (-0.13, 0.15), (-0.12, 0.11),
                        (-0.14, 0.07), (-0.13, 0.03), (-0.14, 0.0)], thickness)
    hand = graph.join(plate(graph, [(0.07, 0.0), (0.06, 0.08), (0.045, 0.16), (-0.12, 0.13), (-0.13, 0.06), (-0.115, 0.0)], thickness),
                      fingers(graph, thickness * 0.7))
    hand = graph.transform(hand, r=graph.vec(folding * math.radians(-25.0), 0.0, folding * math.radians(38.0)))
    wing = graph.join(arm, graph.move(hand, x=0.0, y=0.185, z=0.0))
    wing = graph.transform(wing, r=graph.vec(raised, 0.0, 0.0))
    left = graph.move(wing, y=0.035, z=0.02)
    right = graph.n("GeometryNodeFlipFaces", graph.transform(left, s=graph.vec(1.0, -1.0, 1.0))).o
    body = graph.transform(graph.lathe([(0.0, -0.215), (0.028, -0.2), (0.042, -0.16), (0.038, -0.11), (0.06, -0.05),
                                        (0.063, 0.02), (0.052, 0.08), (0.04, 0.12), (0.042, 0.15), (0.028, 0.185), (0.0, 0.205)], segments=20),
                           t=graph.vec(0.0, 0.0, 0.01), r=graph.vec(0.0, math.radians(90.0), 0.0))
    beak = graph.transform(graph.n("GeometryNodeMeshCone", Vertices=10, Radius_Top=0.0, Radius_Bottom=0.018, Depth=0.075)["Mesh"],
                           t=graph.vec(0.195, 0.0, 0.005), r=graph.vec(0.0, math.radians(95.0), 0.0))
    tail = plate(graph, [(-0.15, 0.025), (-0.3, 0.06), (-0.335, 0.045), (-0.345, 0.0), (-0.335, -0.045), (-0.3, -0.06), (-0.15, -0.025)],
                 thickness)
    tail = graph.transform(tail, t=graph.vec(0.0, 0.0, 0.008), r=graph.vec(0.0, math.radians(-5.0), 0.0))
    bird = graph.join(graph.smooth(body), beak, tail, left, right)
    graph.result(graph.mat(bird, material))
    return graph


@asset("CIN.Birds.Flock", "Birds")
def flock():
    """Crows flying straight through the set (see the module notes): ``Count`` of them from the
    box ``Origin`` +- ``Extent`` at the frame ``Start``, each on its own heading, speed, wingbeat
    and size about the flock's."""
    graph = GN("CIN.Birds.Flock", flock.__doc__)
    count = graph.inp("Count", "INT", default=24, min=0)
    seed = graph.inp("Seed", "INT", default=0)
    origin = graph.inp("Origin", "VECTOR", default=(0.0, 0.0, 0.0), subtype="TRANSLATION")
    extent = graph.inp("Extent", "VECTOR", default=(20.0, 20.0, 10.0), subtype="TRANSLATION")
    heading = graph.inp("Heading", "VECTOR", default=(1.0, 0.0, 0.0))
    spread = graph.inp("Spread", default=math.radians(25.0), min=0.0, max=math.pi, subtype="ANGLE")
    climb = graph.inp("Climb", default=math.radians(8.0), min=0.0, max=math.radians(60.0), subtype="ANGLE")
    speed = graph.inp("Speed", default=12.0, min=0.0, desc="m/s")
    speed_spread = graph.inp("Speed Spread", default=0.25, min=0.0, max=1.0)
    beat = graph.inp("Beat", default=4.0, min=0.0, desc="Wingbeats a second")
    glide = graph.inp("Glide", default=0.2, min=0.0, max=1.0, desc="Share of the birds gliding")
    size = graph.inp("Size", default=1.0, min=0.0)
    size_spread = graph.inp("Size Spread", default=0.15, min=0.0, max=1.0)
    start = graph.inp("Start", default=0.0, desc="Frame at which the birds are where they start")
    fps = graph.inp("FPS", default=30.0, min=1.0)
    time = (graph.scene_frame() - start) * (1.0 / fps)

    def draw(key, low=0.0, high=1.0):
        return graph.random(low, high, seed * 37 + int(SEEDS[key]), ID=graph.index())

    birds = graph.new_points(count)
    place = origin + graph.vec(draw("place x", -1.0, 1.0), draw("place y", -1.0, 1.0), draw("place z", -1.0, 1.0)) * extent
    course = heading.normalized()
    level = graph.align_rotation(course, axis="X")
    level = graph.rotate_rotation(level, graph.vec(0.0, draw("climb", -1.0, 1.0) * climb * -1.0, draw("turn", -1.0, 1.0) * spread))
    forward = graph.rotate_vector(graph.vec(1.0, 0.0, 0.0), level)
    pace = speed * (1.0 + draw("speed", -1.0, 1.0) * speed_spread)
    birds = graph.set_pos(birds, pos=place + forward * (pace * time))
    gliding = graph.compare(draw("glide"), glide, "LESS_THAN")
    moment = graph.math("FRACT", time * beat * (1.0 + draw("beat", -0.15, 0.15)) + draw("phase"))
    moment = graph.switch(gliding, moment, 0.25, "FLOAT")
    pose = graph.math("MODULO", graph.to_int(moment * POSES, "FLOOR"), POSES)
    shapes = [graph.group(get_asset("CIN.Birds.Crow"), Phase=(k + 0.5) / POSES).o for k in range(POSES)]
    poses = graph.n("GeometryNodeGeometryToInstance", Geometry=list(reversed(shapes))).o
    bank = graph.rotate_rotation(level, graph.vec(draw("bank", -1.0, 1.0) * math.radians(20.0), 0.0, 0.0))
    scale = size * (1.0 + draw("size", -1.0, 1.0) * size_spread)
    graph.result(graph.iop(birds, poses, rot=bank, scale=graph.vec(scale, scale, scale), pick=True, index=pose))
    return graph
