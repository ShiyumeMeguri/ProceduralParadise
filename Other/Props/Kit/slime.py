"""
Slime kit (``Props.Slime.*``): a jelly body on :mod:`Core.physics.membrane`
that can be poked to death and then bleeds its goo into a FLIP liquid.

The body is the membrane with shape matching (Mueller 2005: every substep it
is pulled elastically towards the best rigid motion plus a share of volume-
preserving linear deformation of its rest shape) around incompressible,
heavy goo.  A hit is a frame whose collider impulse / frame time exceeds
``Hit Force`` while alive and past the cooldown; the wound is the skin vertex
nearest the impulse's point of action.  At death shape matching fades as
e^(-t/tau), the skin's rest lengths creep towards current length /
pre-stretch with the same tau (a broken gel creeps and keeps a little
tension, so it shrinks with its volume instead of wrinkling), and goo leaves
through the wound as creeping flow through a thin-walled orifice (Sampson):
Q = r^3 max(p, 0) / (3 mu), p = internal pressure + rho g (centroid height -
wound height).  What leaves the body's target volume enters the FLIP liquid
as particles of equal volume; the flow stops when the wound pressure drops
to zero or the body is down to its ``Remaining`` share.

The face -- eyes that blink, wince (> <) or die (X X), a mouth that smiles,
gasps or wavers -- rides on the body's ``left_eye``, ``right_eye`` and
``mouth`` vertices.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset
from Core.physics import GRAVITY, fluid, liquid, membrane
from .. import LIQUIDS
from . import materials as M
from .shapes import FACE

GOO = "Slime Goo"


def strokes(graph, segments, radius):
    """Round strokes along straight ``segments`` [(start, end), ...] in the XY plane."""
    profile = graph.circle(radius, 10)
    return graph.smooth(graph.join(*[graph.sweep(graph.curve_line(start, end), profile) for start, end in segments]))


def swept(graph, curve, radius, count=24):
    return graph.smooth(graph.sweep(graph.resample(curve, count), graph.circle(radius, 10)))


@asset("Props.Slime.Eye", "Slime")
def eye():
    """One eye by expression: 0 calm (a glossy oval with a glint that closes
    to ``Blink``), 1 hurt (a > chevron, < when mirrored), 2 dead (an X).
    Faces +Z, centred on the origin."""
    graph = GN("Props.Slime.Eye", eye.__doc__)
    expression = graph.inp("Expression", "INT", default=0, min=0, max=2)
    blink = graph.inp("Blink", default=1.0, min=0.0, max=1.0, desc="How open a calm eye is")
    mirror = graph.inp("Mirror", "BOOL", default=False)
    black = graph.inp("Material", "MATERIAL", default=M.get("Props.EyeBlack"))
    shine = graph.inp("Shine Material", "MATERIAL", default=M.get("Props.EyeShine"))
    ball = graph.n("GeometryNodeMeshUVSphere", Segments=24, Rings=12, Radius=1.0)["Mesh"]
    ball = graph.mat(graph.smooth(graph.transform(ball, s=graph.vec(0.0043, blink * 0.006, 0.0022))), black)
    glint = graph.n("GeometryNodeMeshCircle", Vertices=16, Radius=0.0011, props={"fill_type": "NGON"})["Mesh"]
    glint = graph.mat(graph.transform(glint, t=graph.vec(-0.0013, blink * 0.0024, 0.0021)), shine)
    side = graph.switch(mirror, 1.0, -1.0, "FLOAT")
    chevron = strokes(graph, [(graph.vec(side * -0.003, 0.0032, 0.0), graph.vec(side * 0.0022, 0.0, 0.0)),
                              (graph.vec(side * 0.0022, 0.0, 0.0), graph.vec(side * -0.003, -0.0032, 0.0))], 0.0009)
    cross = strokes(graph, [((-0.0032, -0.0032, 0.0), (0.0032, 0.0032, 0.0)), ((-0.0032, 0.0032, 0.0), (0.0032, -0.0032, 0.0))], 0.0009)
    graph.result(graph.index_switch(expression, [graph.join(ball, glint), graph.mat(chevron, black), graph.mat(cross, black)], "GEOMETRY"))
    return graph


@asset("Props.Slime.Mouth", "Slime")
def mouth():
    """The mouth by expression: 0 calm (a smile), 1 hurt (a gasp), 2 dead (a
    wavering line).  Faces +Z, centred on the origin."""
    graph = GN("Props.Slime.Mouth", mouth.__doc__)
    expression = graph.inp("Expression", "INT", default=0, min=0, max=2)
    lips = graph.inp("Material", "MATERIAL", default=M.get("Props.Mouth"))
    smile = graph.n("GeometryNodeCurveQuadraticBezier", Start=(-0.0055, 0.0014, 0.0), Middle=(0.0, -0.0032, 0.0), End=(0.0055, 0.0014, 0.0)).o
    gasp = graph.n("GeometryNodeMeshCircle", Vertices=24, Radius=1.0, props={"fill_type": "NGON"})["Mesh"]
    gasp = graph.transform(gasp, t=(0.0, 0.0, 0.0006), s=(0.0036, 0.0046, 1.0))
    line = graph.resample(graph.curve_line((-0.0062, 0.0, 0.0), (0.0062, 0.0, 0.0)), 32)
    wave = graph.set_pos(line, offset=graph.vec(0.0, graph.sin(graph.position().x * (2.0 * math.pi * 1.5 / 0.0124)) * 0.0011, 0.0))
    shapes = [swept(graph, smile, 0.0008), gasp, swept(graph, wave, 0.0008, 32)]
    graph.result(graph.mat(graph.index_switch(expression, shapes, "GEOMETRY"), lips))
    return graph


def place(graph, part, body, anchor_name, lift):
    """``part`` (facing +Z) on the body at the mean of the ``anchor_name``
    vertices, facing along their normal, kept upright."""
    selection = graph.compare(graph.named(anchor_name), 0.5, "GREATER_THAN")
    anchor = graph.statistic(body, graph.position(), "FLOAT_VECTOR", sel=selection)["Mean"]
    normal = graph.statistic(body, graph.normal(), "FLOAT_VECTOR", sel=selection)["Mean"].normalized()
    facing = graph.align_rotation(normal, axis="Z")
    upright = graph.align_rotation((0.0, 0.0, 1.0), rotation=facing, axis="Y", pivot="Z")
    return graph.transform(part, t=anchor + normal * lift, r=upright)


@asset("Props.Slime.Simulation", "Slime")
def simulation():
    """Interactive slime (see the kit's notes): a jelly body that flashes and
    winces when hit hard enough, dies after ``Health`` hits and bleeds its goo
    into a FLIP liquid.  Everything in ``Colliders`` touches the body; the
    goo meets the ground, the body and the ``Stick``."""
    graph = GN("Props.Slime.Simulation", simulation.__doc__, modifier=True)
    geometry = graph.inp("Geometry", "GEOMETRY")
    for name in ("Interaction", "Life", "Jelly Body"):
        graph.panel(name, closed=False)
    ground = graph.inp("Ground", "OBJECT", desc="The top of this object's bounding box is an infinite floor", panel="Interaction")
    colliders = graph.inp("Colliders", "COLLECTION", desc="Every object in this collection touches the slime", panel="Interaction")
    stick = graph.inp("Stick", "OBJECT", desc="The goo meets it too", panel="Interaction")
    health = graph.inp("Health", "INT", default=3, min=1, max=99, desc="Hits it takes to die", panel="Life")
    hit_force = graph.inp("Hit Force", default=0.15, min=0.0, desc="N; a frame counts as a hit when the colliders' impulse on the skin / frame time exceeds it", panel="Life")
    cooldown = graph.inp("Hit Cooldown", default=0.45, min=0.0, desc="s; how long the hurt face lasts, no further hits count meanwhile", panel="Life")
    shape_frequency = graph.inp("Shape Frequency", default=6.0, min=0.0, desc="Hz; how fast the skin springs back into jelly shape, higher is firmer", panel="Jelly Body")
    shape_blend = graph.inp("Linear Deformation", default=0.3, min=0.0, max=1.0, desc="0: the shape goal only moves rigidly; 1: the whole body may squash and stretch at constant volume", panel="Jelly Body")
    skin_stiffness = graph.inp("Skin Stiffness", default=220.0, min=1.0, desc="Spring stiffness of an edge, N/m", panel="Jelly Body")
    pre_stretch = graph.inp("Skin Pre-stretch", default=1.02, min=1.0, max=2.0, panel="Jelly Body")
    compression = graph.inp("Compression Ratio", default=0.02, min=0.0, max=1.0, desc="Stiffness of a compressed edge / of a stretched one; a thin skin wrinkles instead of holding a dent like a hard shell", panel="Jelly Body")
    skin_density = graph.inp("Skin Density", default=0.4, min=0.0, desc="kg/m^2", panel="Jelly Body")
    slosh = graph.inp("Slosh Damping", default=1.5, min=0.0, desc="1/s", panel="Jelly Body")
    drag = graph.inp("Air Drag", default=0.02, min=0.0, desc="1/s", panel="Jelly Body")
    goo = liquid.declare_inputs(graph, "Wound and Goo", LIQUIDS[GOO])
    wound_radius = graph.inp("Wound Radius", default=0.012, min=0.0005, desc="m; the outflow grows with its cube; particles start on this disc at the outflow speed Q / area", panel="Wound and Goo")
    softening = graph.inp("Softening Time", default=0.35, min=0.01, desc="s; after death shape matching fades as e^(-t/tau) and the skin creeps at the same rate", panel="Wound and Goo")
    remaining = graph.inp("Remaining", default=0.06, min=0.01, max=1.0, desc="Least share of its volume the body keeps", panel="Wound and Goo")
    voxel = graph.inp("Goo Voxel", default=0.003, min=0.0005, desc="m; cell size of the goo's FLIP grid", panel="Wound and Goo")
    per_cell = graph.inp("Particles Per Cell", default=8.0, min=1.0, panel="Wound and Goo")
    goo_cfl = graph.inp("Goo CFL", default=3.0, min=0.1, desc="Cells a goo particle may cross per substep; lower is steadier and slower", panel="Wound and Goo")
    substeps = graph.inp("Substeps", "INT", default=membrane.MINIMUM_SUBSTEPS, min=membrane.MINIMUM_SUBSTEPS, max=100, panel="Solver")
    iterations = graph.inp("Iterations", "INT", default=3, min=1, max=100, panel="Solver")
    radius = graph.inp("Collision Radius", default=0.0025, min=0.0, panel="Solver")
    friction = graph.inp("Friction", default=0.9, min=0.0, panel="Solver")
    flash_time = graph.inp("Flash Time", default=0.12, min=0.001, desc="s; decay of the red flash of a hit", panel="Look")
    wound_mark = graph.inp("Wound Mark", default=2.2, min=0.0, desc="Radius of the torn look around the wound, in wound radii", panel="Look")
    blink_period = graph.inp("Blink Period", default=3.3, min=0.1, desc="s between blinks", panel="Look")
    blink_time = graph.inp("Blink Time", default=0.12, min=0.001, desc="s an eye takes to close and open", panel="Look")
    body_material = graph.inp("Body Material", "MATERIAL", default=M.get("Props.Slime"), panel="Look")
    goo_material = graph.inp("Goo Material", "MATERIAL", default=M.get(LIQUIDS[GOO]["material"]), panel="Look")
    eye_material = graph.inp("Eye Material", "MATERIAL", default=M.get("Props.EyeBlack"), panel="Look")
    shine_material = graph.inp("Eye Shine Material", "MATERIAL", default=M.get("Props.EyeShine"), panel="Look")
    mouth_material = graph.inp("Mouth Material", "MATERIAL", default=M.get("Props.Mouth"), panel="Look")
    for name, stype, desc in (("Geometry", "GEOMETRY", ""), ("Health", "FLOAT", ""),
                              ("Force", "FLOAT", "N; this frame's collider force on the skin, compared with Hit Force"),
                              ("Goo Particles", "INT", "")):
        graph.out(name, stype, desc)

    density = goo["density"]
    self_transform = graph.object_info(graph.self_object())["Transform"]
    compliance = 1.0 / skin_stiffness
    world_geometry = graph.transform_by(geometry, self_transform)
    rest_volume = graph.group(get_asset("Physics.Membrane.Volume"), Geometry=world_geometry)["Volume"]
    prepared = graph.group(get_asset("Physics.Membrane.Prepare"), Geometry=world_geometry, Friction=friction, **{
        "Pre-stretch": pre_stretch, "Content Mass": density * rest_volume, "Skin Density": skin_density, "Collision Radius": radius})["Geometry"]
    pressure = graph.group(get_asset("Physics.Membrane.EquilibriumPressure"), Geometry=prepared, **{"Stretch Compliance": compliance})["Pressure"]
    floor = graph.group(get_asset("Physics.Ground"), Object=ground)

    zone = graph.simulation([
        ("Body", "GEOMETRY"), ("Pressure", "FLOAT"), ("TargetVolume", "FLOAT"), ("Goo", "GEOMETRY"),
        ("Health", "FLOAT"), ("HurtTime", "FLOAT"), ("Dead", "BOOLEAN"), ("DeathTime", "FLOAT"),
        ("Wound", "INT"), ("Remainder", "FLOAT"), ("PreviousColliders", "GEOMETRY"), ("PreviousStick", "MATRIX"), ("Force", "FLOAT"),
        ("GooPressure", "GEOMETRY"),
    ])
    for name, value in (("Body", prepared), ("Pressure", pressure), ("TargetVolume", rest_volume), ("Health", health), ("HurtTime", 1000.0),
                        ("PreviousColliders", graph.collection_info(colliders)), ("PreviousStick", graph.object_info(stick)["Transform"]),
                        ("GooPressure", fluid.pressure_volume(graph))):
        zone.initial(name, value)
    delta_time = zone.delta_time
    dead = zone.state("Dead")

    current_colliders = graph.collection_info(colliders)
    bundle = membrane.collider_bundle(graph, current_colliders, zone.state("PreviousColliders"), friction, 0.0005)
    firmness = graph.switch(dead, 1.0, graph.math("EXPONENT", zone.state("DeathTime") * -1.0 / softening), "FLOAT")
    step = graph.group(get_asset("Physics.Membrane.Step"), Geometry=zone.state("Body"), Colliders=bundle, Substeps=substeps, Iterations=iterations,
                       Hydrostatic=1.0, Pressure=zone.state("Pressure"), **{
                           "Frame Time": delta_time, "Stretch Compliance": compliance, "Target Volume": zone.state("TargetVolume"),
                           "Content Density": density, "Air Drag": drag, "Slosh Damping": slosh, "Ground Height": floor["Height"],
                           "Ground Friction": friction, "Use Ground": floor["Has Ground"], "Shape Matching": True,
                           "Shape Frequency": shape_frequency * graph.math("SQRT", firmness), "Linear Deformation": shape_blend,
                           "Compression Ratio": compression, "Creep Rate": graph.switch(dead, 0.0, 1.0 / softening, "FLOAT")})
    body = step["Geometry"]

    force = step["Impulse"] / graph.max(delta_time, 1e-6)
    ready = graph.bool_and(graph.bool_not(dead), graph.compare(zone.state("HurtTime"), cooldown, "GREATER_THAN"))
    hit = graph.bool_and(graph.bool_and(ready, graph.compare(force, hit_force, "GREATER_THAN")), graph.compare(delta_time, 0.0, "GREATER_THAN"))
    health_after = zone.state("Health") - graph.switch(hit, 0.0, 1.0, "FLOAT")
    died_now = graph.bool_and(hit, graph.compare(health_after, 0.0, "LESS_EQUAL"))
    dead_after = graph.bool_or(dead, died_now)
    wound = graph.switch(hit, zone.state("Wound"), graph.sample_nearest(body, step["Impulse Center"]), "INT")
    hurt_time = graph.switch(hit, zone.state("HurtTime") + delta_time, 0.0, "FLOAT")
    death_time = graph.switch(dead_after, 0.0, graph.switch(died_now, zone.state("DeathTime") + delta_time, 0.0, "FLOAT"), "FLOAT")

    wound_position = graph.sample_index(body, graph.position(), wound, "FLOAT_VECTOR")
    wound_normal = graph.sample_index(body, graph.normal(), wound, "FLOAT_VECTOR").normalized()
    wound_velocity = graph.sample_index(body, graph.named("velocity", "FLOAT_VECTOR"), wound, "FLOAT_VECTOR")
    centroid_height = graph.statistic(body, graph.position(), "FLOAT_VECTOR")["Mean"].z
    wound_pressure = step["Pressure"] + density * -GRAVITY[2] * (centroid_height - wound_position.z)
    orifice = graph.math("POWER", wound_radius, 3.0) / (3.0 * goo["dynamic_viscosity"])
    flow = orifice * graph.max(wound_pressure, 0.0)
    kept = rest_volume * remaining
    released = graph.switch(dead_after, 0.0, graph.min(flow * delta_time, graph.max(zone.state("TargetVolume") - kept, 0.0)), "FLOAT")
    particle_volume = graph.math("POWER", voxel, 3.0) / per_cell
    owed = released / particle_volume + zone.state("Remainder")
    count = graph.to_int(graph.floor(owed), "FLOOR")
    exit_speed = flow / (math.pi * (wound_radius * wound_radius))
    seed = graph.to_int(death_time * 1000.0, "ROUND")
    angle = graph.random(0.0, 2.0 * math.pi, seed)
    spread = wound_radius * graph.math("SQRT", graph.random(0.0, 1.0, seed + 7))
    travelled = exit_speed * delta_time * graph.random(0.0, 1.0, seed + 13)
    helper = graph.switch(graph.compare(graph.abs(wound_normal.z), 0.9, "GREATER_THAN"), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), "VECTOR")
    side = wound_normal.cross(helper).normalized()
    other = wound_normal.cross(side)
    disc = side * (spread * graph.cos(angle)) + other * (spread * graph.sin(angle))
    spawned = graph.new_points(count)
    spawned = graph.set_pos(spawned, pos=wound_position + wound_normal * (voxel * 0.75 + travelled) + disc)
    spawned = graph.store(spawned, "velocity", wound_velocity + wound_normal * exit_speed, "FLOAT_VECTOR")
    goo_points = graph.join(zone.state("Goo"), spawned)

    stick_info = graph.object_info(stick)
    stick_solid = graph.group(get_asset("Physics.Fluid.RigidSolid"), Geometry=stick_info["Geometry"], Voxel=voxel * 0.66)["Solid"]
    body_solid = graph.group(get_asset("Physics.Fluid.DeformingSolid"), Mesh=body, Voxel=voxel)
    flowed = graph.group(get_asset("Physics.Fluid.Step"), Points=liquid.store(graph, goo_points, liquid.particle_values(graph, goo)),
                         Pressure=zone.state("GooPressure"), Voxel=voxel,
                         CFL=goo_cfl, Rigid=stick_solid, Deforming=body_solid["Solid"], **{
                             "Frame Time": delta_time, "Min Substeps": 2, "Max Substeps": 16, "Rest Density": per_cell,
                             "Density Correction": 0.3, "Fluid Threshold": 0.3, "Particle Radius": voxel * 0.5, "Adhesion Range": voxel,
                             "Ground Height": floor["Height"], "Has Rigid": True, "Rigid Transform": stick_info["Transform"],
                             "Rigid Previous": zone.state("PreviousStick"), "Has Deforming": True, "Deforming Moves": body_solid["Moving"]})
    has_goo = graph.compare(graph.domain_size(goo_points, "POINTCLOUD")["Point Count"], 0, "GREATER_THAN")
    goo_after = fluid.forget(graph, graph.switch(has_goo, goo_points, flowed["Points"]))
    goo_pressure = graph.switch(has_goo, zone.state("GooPressure"), flowed["Pressure"])
    for name, value in (("Body", body), ("Pressure", step["Pressure"]), ("TargetVolume", zone.state("TargetVolume") - released), ("Goo", goo_after),
                        ("Health", health_after), ("HurtTime", hurt_time), ("Dead", dead_after), ("DeathTime", death_time), ("Wound", wound),
                        ("Remainder", owed - count), ("PreviousColliders", current_colliders), ("PreviousStick", stick_info["Transform"]), ("Force", force),
                        ("GooPressure", goo_pressure)):
        zone.set(name, value)

    inverse = graph.invert(self_transform)
    simulated = zone.result("Body")
    finished = zone.result("Dead")
    flash = graph.switch(finished, graph.math("EXPONENT", zone.result("HurtTime") * -1.0 / flash_time), 0.0, "FLOAT")
    wound_point = graph.sample_index(simulated, graph.position(), zone.result("Wound"), "FLOAT_VECTOR")
    torn = 1.0 - graph.map_range(graph.vmath("DISTANCE", graph.position(), wound_point), 0.0, wound_radius * wound_mark, 0.0, 1.0)
    surface = graph.store(simulated, "flash", flash)
    surface = graph.store(surface, "wound", graph.switch(finished, 0.0, torn, "FLOAT"))
    local = graph.transform_by(surface, inverse)
    body_mesh = graph.group(get_asset("Shading.Thickness"), Mesh=graph.mat(graph.smooth(local), body_material)).o

    hurting = graph.compare(zone.result("HurtTime"), cooldown, "LESS_THAN")
    expression = graph.switch(finished, graph.switch(hurting, 0, 1, "INT"), 2, "INT")
    phase = graph.math("FLOORED_MODULO", graph.scene_time(), blink_period)
    shut = graph.clamp01(1.0 - graph.abs((phase - (blink_period - blink_time)) / (blink_time * 0.5)))
    blink = graph.max(1.0 - shut, 0.08)
    eyes = [graph.group(get_asset("Props.Slime.Eye"), Expression=expression, Blink=blink, Mirror=mirror, Material=eye_material,
                        **{"Shine Material": shine_material}).o for mirror in (False, True)]
    lips = graph.group(get_asset("Props.Slime.Mouth"), Expression=expression, Material=mouth_material).o
    face = graph.join(*[place(graph, part, local, name, lift) for part, name, lift in zip((*eyes, lips), FACE, (0.0004, 0.0004, 0.0003))])

    viewport = graph.n("GeometryNodeIsViewport").o
    goo_surface = graph.group(get_asset("Physics.Fluid.Surface"), Points=zone.result("Goo"), Voxel=graph.switch(viewport, voxel * 0.5, voxel, "FLOAT"), Smoothing=voxel,
                              Erosion=voxel * 0.5, **{"Sphere Radius": voxel * 1.2})["Mesh"]
    goo_mesh = graph.mat(graph.transform_by(goo_surface, inverse), goo_material)
    goo_mesh = graph.store(goo_mesh, "velocity", graph.transform_direction(graph.named("velocity", "FLOAT_VECTOR"), inverse), "FLOAT_VECTOR")
    goo_mesh = graph.group(get_asset("Shading.Thickness"), Mesh=goo_mesh).o
    graph.result(graph.join(body_mesh, face, goo_mesh), zone.result("Health"), zone.result("Force"),
                 graph.domain_size(zone.result("Goo"), "POINTCLOUD")["Point Count"])
    return graph
