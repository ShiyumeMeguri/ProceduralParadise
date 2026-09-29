"""
Spray kit (``Props.Spray.*``): liquid leaving a nozzle that moves.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset
from Core.physics import fluid, liquid

SEEDS = {"moment": 1.0, "ring angle": 2.0, "ring radius": 3.0, "tilt": 4.0, "tilt angle": 5.0}


@asset("Props.Spray.Nozzle", "Spray")
def nozzle():
    """The particles a nozzle emits this frame.  Flow x frame time of volume
    is split into particles of ``Particle Volume`` (the fraction left over
    carries to the next frame).  Each leaves at its own moment tau of the
    frame from the nozzle interpolated between its previous and current
    transform (origin, spraying along local -Z), anywhere on the nozzle's
    disc, tilted by up to ``Spread``, at flow / nozzle area plus the nozzle's
    own velocity -- a waved nozzle draws one continuous stream -- and flies
    the rest of the frame (``fluid:flight_time``)."""
    graph = GN("Props.Spray.Nozzle", nozzle.__doc__)
    transform = graph.inp("Transform", "MATRIX")
    previous = graph.inp("Previous Transform", "MATRIX")
    spraying = graph.inp("Spraying", "BOOL", default=True)
    flow = graph.inp("Flow", default=110.0, min=0.0, desc="mL/s")
    nozzle_radius = graph.inp("Nozzle Radius", default=0.0055, min=0.0005, subtype="DISTANCE")
    spread = graph.inp("Spread", default=math.radians(2.0), min=0.0, max=math.radians(45.0), subtype="ANGLE")
    particle_volume = graph.inp("Particle Volume", default=8e-9, min=1e-15, desc="m^3 of liquid per particle")
    radius = graph.inp("Particle Radius", default=0.002, min=0.0, desc="Particles start this far ahead of the nozzle")
    delta_time = graph.inp("Frame Time", default=1.0 / 24.0)
    remainder = graph.inp("Remainder", default=0.0, desc="Particles owed from earlier frames (the fraction left over)")
    kind = graph.inp("Liquid Type", "INT", default=0, min=0)
    graph.out("Points", "GEOMETRY")
    graph.out("Remainder", "FLOAT")
    frame = graph.scene_frame()

    def draw(key):
        return graph.random(0.0, 1.0, frame * 16.0 + SEEDS[key], ID=graph.index())

    flow_rate = flow * 1e-6
    owed = remainder + graph.switch(spraying, 0.0, flow_rate * delta_time / particle_volume, "FLOAT")
    count = graph.to_int(graph.floor(owed), "FLOOR")
    moment = draw("moment")
    at_moment = fluid.interpolate_transform(graph, previous, transform, moment)
    axis = graph.transform_direction((0.0, 0.0, -1.0), at_moment).normalized()
    helper = graph.switch(graph.compare(graph.abs(axis.z), 0.9, "GREATER_THAN"), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), "VECTOR")
    side = axis.cross(helper).normalized()
    other = axis.cross(side)
    ring_angle = draw("ring angle") * (2.0 * math.pi)
    ring = nozzle_radius * graph.math("SQRT", draw("ring radius"))
    offset = side * (ring * graph.cos(ring_angle)) + other * (ring * graph.sin(ring_angle))
    tilt = graph.math("TANGENT", spread) * graph.math("SQRT", draw("tilt"))
    tilt_angle = draw("tilt angle") * (2.0 * math.pi)
    direction = (axis + (side * graph.cos(tilt_angle) + other * graph.sin(tilt_angle)) * tilt).normalized()
    speed = flow_rate / (math.pi * (nozzle_radius * nozzle_radius))
    origin = (0.0, 0.0, 0.0)
    nozzle_velocity = (graph.transform_point(origin, transform) - graph.transform_point(origin, previous)) * (1.0 / graph.max(delta_time, 1e-6))
    spawned = graph.new_points(count)
    spawned = graph.set_pos(spawned, pos=graph.transform_point(origin, at_moment) + offset + axis * radius)
    spawned = graph.store(spawned, "velocity", direction * speed + nozzle_velocity, "FLOAT_VECTOR")
    spawned = graph.store(spawned, liquid.TYPE_ATTRIBUTE, kind, "INT8")
    spawned = graph.store(spawned, fluid.FLIGHT_TIME, (1.0 - moment) * delta_time)
    graph.result(spawned, owed - count)
    return graph
