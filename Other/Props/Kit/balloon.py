"""
Water balloon kit (``Props.Balloon.*``): a latex skin full of water on
:mod:`Core.physics.membrane`, poked by whatever is in its colliders and
lifted by the knot.

The body comes in as a mesh with ``knot`` and ``neck`` (``Props.Balloon.Shape``
or any closed mesh carrying them).  The rubber's rest length is its filled
length / pre-stretch, so the skin is always under tension, balanced from the
first frame by the matching Laplace pressure; the neck is unstretched thick
rubber (ten times stiffer) and the tied knot feels no water pressure.  The
water is incompressible and heavy (hydrostatic pressure); its inertia rides
on the skin.  With ``Grab`` the knot is pinned to the ``Hand`` object.
"""
from __future__ import annotations

from Core.gn import GN, asset, get_asset
from Core.physics import membrane
from . import materials as M
from .shapes import KNOT, NECK


def torus(graph, radius, thickness, location, rotation, resolution=28, profile_resolution=12):
    ring = graph.sweep(graph.circle(radius, resolution), graph.circle(thickness, profile_resolution), False)
    return graph.transform(ring, t=location, r=rotation)


@asset("Props.Balloon.Knot", "Balloon")
def knot():
    """A balloon's knot: the pinched neck, the loop of rubber tied around it,
    its lump and the rolled lip; base at the origin, pointing up +Z."""
    graph = GN("Props.Balloon.Knot", knot.__doc__)
    scale = graph.inp("Scale", default=1.0, min=0.0)
    material = graph.inp("Material", "MATERIAL", default=M.get("Props.Latex"))
    path = graph.resample(graph.curve_line((0.0, 0.0, -0.003), (0.0, 0.0, 0.0065)), 12)
    taper = graph.map_range(graph.n("GeometryNodeSplineParameter")["Factor"], 0.0, 1.0, 0.0046, 0.003)
    neck = graph.n("GeometryNodeCurveToMesh", Curve=path, Profile_Curve=graph.circle(1.0, 20), Scale=taper, Fill_Caps=True)["Mesh"]
    loop = torus(graph, 0.0036, 0.0024, (0.0, 0.0, 0.0078), (0.5, 0.25, 0.0))
    lump = graph.n("GeometryNodeMeshUVSphere", Segments=24, Rings=14, Radius=0.0047)["Mesh"]
    lump = graph.transform(lump, t=(0.0009, 0.0, 0.0088), s=(1.0, 0.86, 0.74))
    lip = torus(graph, 0.0042, 0.0013, (0.0022, 0.003, 0.0128), (0.95, 0.3, 0.0), profile_resolution=10)
    whole = graph.transform(graph.join(neck, loop, lump, lip), s=graph.vec(scale, scale, scale))
    graph.result(graph.mat(graph.store(graph.smooth(whole), "stretch", 1.0), material))
    return graph


@asset("Props.Balloon.Simulation", "Balloon")
def simulation():
    """Interactive water balloon (see the kit's notes).  Every object in
    ``Colliders`` pokes and carries it; the ``Ground`` object's top is an
    infinite floor it never passes."""
    graph = GN("Props.Balloon.Simulation", simulation.__doc__, modifier=True)
    geometry = graph.inp("Geometry", "GEOMETRY")
    for name in ("Interaction", "Rubber and Water"):
        graph.panel(name, closed=False)
    ground = graph.inp("Ground", "OBJECT", desc="The top of this object's bounding box is an infinite floor (a table, the ground); never pressed through", panel="Interaction")
    colliders = graph.inp("Colliders", "COLLECTION", desc="Every object in this collection collides with the balloon (a stick, a hand, a cup)", panel="Interaction")
    hand = graph.inp("Hand", "OBJECT", desc="With Grab the knot follows this object's position and rotation", panel="Interaction")
    grab = graph.inp("Grab", "BOOL", default=False, desc="Pin the knot to the hand (can be switched during playback)", panel="Interaction")
    pre_stretch = graph.inp("Pre-stretch", default=1.5, min=1.0, max=3.0, desc="How far the filled rubber is stretched", panel="Rubber and Water")
    stiffness = graph.inp("Rubber Stiffness", default=220.0, min=1.0, desc="Spring stiffness of an edge, N/m (about 0.87 x Young's modulus x thickness)", panel="Rubber and Water")
    skin_density = graph.inp("Skin Density", default=0.3, min=0.0, desc="kg/m^2", panel="Rubber and Water")
    water_density = graph.inp("Water Density", default=1000.0, min=0.0, desc="kg/m^3", panel="Rubber and Water")
    hydrostatic = graph.inp("Hydrostatic", default=1.0, min=0.0, max=1.0, desc="How much of the water's weight reaches the bottom through pressure", panel="Rubber and Water")
    slosh = graph.inp("Slosh Damping", default=2.5, min=0.0, desc="1/s; damps sloshing and rolling", panel="Rubber and Water")
    drag = graph.inp("Air Drag", default=0.02, min=0.0, desc="1/s", panel="Rubber and Water")
    substeps = graph.inp("Substeps", "INT", default=membrane.MINIMUM_SUBSTEPS, min=membrane.MINIMUM_SUBSTEPS, max=100,
                         desc=f"Substeps per frame, each solved in {membrane.INNER_SUBSTEPS} inner steps; below {membrane.MINIMUM_SUBSTEPS} a resting contact sinks too far each step and friction turns it into a slow crawl.  Fast pokes or stiffer rubber may want more", panel="Solver")
    iterations = graph.inp("Iterations", "INT", default=3, min=1, max=100, desc="Constraint iterations per inner step; 3 bring the pressure within 1 % of its physical value", panel="Solver")
    radius = graph.inp("Collision Radius", default=0.0025, min=0.0, desc="Thickness of the skin for collisions", panel="Solver")
    friction = graph.inp("Friction", default=0.9, min=0.0, desc="Friction of rubber on surfaces", panel="Solver")
    water_material = graph.inp("Water Material", "MATERIAL", default=M.get("Props.WaterBalloon"), panel="Look")
    rubber_material = graph.inp("Rubber Material", "MATERIAL", default=M.get("Props.Latex"), panel="Look")
    graph.out("Geometry", "GEOMETRY")
    graph.out("Volume", "FLOAT")

    knot_weight = graph.named(KNOT)
    neck_weight = graph.named(NECK)
    self_transform = graph.object_info(graph.self_object())["Transform"]
    world_geometry = graph.transform_by(geometry, self_transform)
    rest_volume = graph.group(get_asset("Physics.Membrane.Volume"), Geometry=world_geometry)["Volume"]
    prepared = graph.group(get_asset("Physics.Membrane.Prepare"), Geometry=world_geometry, Friction=friction, **{
        "Pre-stretch": graph.mix(neck_weight, pre_stretch, 1.0), "Content Mass": water_density * rest_volume,
        "Skin Density": skin_density, "Collision Radius": radius, "Pressure Weight": 1.0 - knot_weight})["Geometry"]
    compliance = (1.0 / stiffness) * graph.mix(neck_weight, 1.0, 0.1)
    pressure = graph.group(get_asset("Physics.Membrane.EquilibriumPressure"), Geometry=prepared, **{"Stretch Compliance": compliance})["Pressure"]
    floor = graph.group(get_asset("Physics.Ground"), Object=ground)

    zone = graph.simulation([("Geometry", "GEOMETRY"), ("RestVolume", "FLOAT"), ("PreviousColliders", "GEOMETRY"),
                             ("Volume", "FLOAT"), ("HandInitial", "MATRIX"), ("Pressure", "FLOAT")])
    for name, value in (("Geometry", prepared), ("RestVolume", rest_volume), ("PreviousColliders", graph.collection_info(colliders)),
                        ("Volume", rest_volume), ("HandInitial", graph.object_info(hand)["Transform"]), ("Pressure", pressure)):
        zone.initial(name, value)
    current_colliders = graph.collection_info(colliders)
    bundle = membrane.collider_bundle(graph, current_colliders, zone.state("PreviousColliders"), friction, 0.0005)
    hand_motion = graph.matmul(graph.object_info(hand)["Transform"], graph.invert(zone.state("HandInitial")))
    state = graph.store(zone.state("Geometry"), "pin_weight", graph.switch(grab, 0.0, knot_weight, "FLOAT"))
    state = graph.store(state, "pin_target", graph.transform_point(graph.named("rest_position", "FLOAT_VECTOR"), hand_motion), "FLOAT_VECTOR")
    step = graph.group(get_asset("Physics.Membrane.Step"), Geometry=state, Colliders=bundle, Substeps=substeps, Iterations=iterations,
                       Hydrostatic=hydrostatic, Pressure=zone.state("Pressure"), **{
                           "Frame Time": zone.delta_time, "Stretch Compliance": compliance, "Target Volume": zone.state("RestVolume"),
                           "Content Density": water_density, "Air Drag": drag, "Slosh Damping": slosh, "Pin Compliance": 0.0,
                           "Ground Height": floor["Height"], "Ground Friction": friction, "Use Ground": floor["Has Ground"]})
    for name, value in (("Geometry", step["Geometry"]), ("RestVolume", zone.state("RestVolume")), ("PreviousColliders", current_colliders),
                        ("Volume", step["Volume"]), ("HandInitial", zone.state("HandInitial")), ("Pressure", step["Pressure"])):
        zone.set(name, value)

    simulated = zone.result("Geometry")
    edge = graph.n("GeometryNodeInputMeshEdgeVertices")
    ratio = graph.vmath("DISTANCE", edge["Position 1"], edge["Position 2"]) / (graph.named("rest_length") * graph.named("pre_stretch"))
    simulated = graph.store(simulated, "stretch", graph.on_domain(ratio, "EDGE"))
    simulated = graph.store(simulated, "volume_ratio", graph.group(get_asset("Physics.Membrane.Volume"), Geometry=simulated)["Volume"] / zone.result("RestVolume"))
    simulated = graph.store(simulated, "pressure", zone.result("Pressure"))
    local = graph.transform_by(simulated, graph.invert(self_transform))
    body = graph.group(get_asset("Shading.Thickness"), Mesh=graph.mat(graph.smooth(local), water_material)).o
    anchor = graph.statistic(local, graph.position(), "FLOAT_VECTOR", sel=graph.compare(knot_weight, 0.5, "GREATER_THAN"))["Mean"]
    center = graph.statistic(local, graph.position(), "FLOAT_VECTOR")["Mean"]
    tied = graph.group(get_asset("Props.Balloon.Knot"), Material=rubber_material).o
    tied = graph.transform(tied, t=anchor, r=graph.align_rotation((anchor - center).normalized(), axis="Z"))
    graph.result(graph.join(body, tied), zone.result("Volume"))
    return graph
