"""
Shishi-odoshi kit (``Props.ShishiOdoshi.*``): the bamboo tube of a Japanese
garden that fills from a spout, tips, pours out and falls back onto its
stone with a clack.

Frame of the tube: the axle is the X axis through the origin, the tube lies
along Y with its mouth at +Y; turned by theta about X the mouth rises for
theta > 0.  Behind the axle a sealed chamber (hollow between the end node and
the septum) keeps the empty tube's centre of mass behind the axle, so it
rests mouth-up at the rest angle with its end on the stone; the chamber in
front of the septum fills through the mouth, cut aslant with its lower lip
longest -- a scoop facing up at rest, a spout when tipped.  Once the liquid's
torque outweighs the tube's, it turns (Core.physics.hinge, with the tube as
the FLIP liquid's rigid solid), pours, and swings back.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, remembered_items
from Core.physics import liquid
from . import liquids, materials as M

X_AXIS = (1.0, 0.0, 0.0)
RINGS = 6
SEGMENTS = 48


def spaced(start, end, count):
    return [start + (end - start) * (index / count) for index in range(1, count)]


def along_y(graph, mesh):
    """A lathe about Z turned so its axis runs along +Y."""
    return graph.transform(mesh, r=(-0.5 * math.pi, 0.0, 0.0))


def slant(graph, mesh, septum, front, radius, cut):
    """Cut the front (y > septum) aslant: every point keeps its share of the
    way from the septum to the front, now ending on the plane
    y = front - (z + radius) tan(cut) -- the lower lip (z = -radius) longest."""
    y = graph.position().y
    mouth = front - (graph.position().z + radius) * graph.math("TANGENT", cut)
    share = (y - septum) / (front - septum)
    slanted = septum + share * (mouth - septum)
    x, _, z = graph.sep(graph.position())
    return graph.set_pos(mesh, pos=graph.vec(x, graph.switch(graph.compare(y, septum, "GREATER_THAN"), y, slanted, "FLOAT"), z))


def bamboo_coordinates(graph, mesh, axis_index):
    """``bamboo_coordinate``: (arc length around, distance along, radius) about
    the culm axis (local Y for the tube, Z for a post)."""
    x, y, z = graph.sep(graph.position())
    across = (x, z) if axis_index == 1 else (x, y)
    along = y if axis_index == 1 else z
    radial = graph.vec(across[0], across[1], 0.0).length()
    around = graph.math("ARCTAN2", across[1], across[0]) * radial
    return graph.store(mesh, "bamboo_coordinate", graph.vec(around, along, radial), "FLOAT_VECTOR")


def node_rings(graph, mesh, along, nodes, width):
    """``bamboo_node``: 1 on a node ring, fading over ``width`` either side."""
    strongest = None
    for node in nodes:
        ring = graph.clamp01(1.0 - graph.abs(along - node) / width)
        strongest = ring if strongest is None else graph.max(strongest, ring)
    return graph.store(mesh, "bamboo_node", strongest)


@asset("Props.ShishiOdoshi.Tube", "Shishi-odoshi")
def tube():
    """The bamboo tube and the cavity its chamber holds liquid in, both
    closed meshes in the tube's frame (see the kit's notes).  The tube carries
    the bamboo attributes: ``bamboo_coordinate``, ``bamboo_node`` (the end node
    and the septum, ridged on the outside) and ``bamboo_cut`` (1 on cut faces:
    the mouth's rim, the bore, the end)."""
    graph = GN("Props.ShishiOdoshi.Tube", tube.__doc__)
    radius = graph.inp("Radius", default=0.024, min=0.002, subtype="DISTANCE")
    wall = graph.inp("Wall", default=0.006, min=0.0005, subtype="DISTANCE")
    front = graph.inp("Front Length", default=0.2, min=0.01, subtype="DISTANCE", desc="From the axle to the tip of the mouth's lower lip")
    rear = graph.inp("Rear Length", default=0.24, min=0.01, subtype="DISTANCE", desc="From the axle to the closed end")
    septum = graph.inp("Septum", default=0.004, subtype="DISTANCE", desc="Where the chamber ends: the front face of the node the axle passes through")
    node_wall = graph.inp("Node Wall", default=0.008, min=0.001, subtype="DISTANCE", desc="Thickness of the end node and the septum")
    ridge = graph.inp("Node Ridge", default=0.0015, min=0.0, subtype="DISTANCE", desc="How far a node's ring stands out")
    cut = graph.inp("Mouth Cut", default=math.radians(40.0), min=0.0, max=math.radians(75.0), subtype="ANGLE",
                    desc="Slant of the mouth from square: the lower lip is 2 radius tan(cut) longer than the upper")
    material = graph.inp("Material", "MATERIAL", default=M.get("Props.Bamboo"))
    graph.out("Tube", "GEOMETRY")
    graph.out("Cavity", "GEOMETRY")
    bore = radius - wall
    end = rear * -1.0
    half = radius * 0.2
    end_node = end + half * 1.5
    septum_node = septum - node_wall * 0.5
    skin = [(0.0, end), (radius, end)]
    for node in (end_node, septum_node):
        skin += [(radius, node - half), (radius + ridge, node), (radius, node + half)]
    skin += [(radius, t) for t in spaced(septum_node + half, front, RINGS)]
    skin += [(radius, front), (bore, front)]
    skin += [(bore, t) for t in spaced(front, septum, RINGS)]
    skin += [(bore, septum), (0.0, septum)]
    chamber = [(0.0, end + node_wall), (bore, end + node_wall), (bore, septum - node_wall), (0.0, septum - node_wall)]
    body = along_y(graph, graph.join(graph.lathe(skin, SEGMENTS), graph.n("GeometryNodeFlipFaces", graph.lathe(chamber, SEGMENTS)).o))
    body = slant(graph, body, septum, front, radius, cut)
    body = bamboo_coordinates(graph, body, 1)
    body = node_rings(graph, body, graph.position().y, (end_node, septum_node), half * 2.0)
    outward = graph.n("GeometryNodeInputNormal").o.dot(graph.vec(graph.position().x, 0.0, graph.position().z).normalized())
    on_skin = graph.bool_and(graph.compare(outward, 0.3, "GREATER_THAN"),
                             graph.compare(graph.vec(graph.position().x, 0.0, graph.position().z).length(), radius - wall * 0.25, "GREATER_THAN"))
    body = graph.store(body, "bamboo_cut", graph.switch(on_skin, 1.0, 0.0, "FLOAT"), domain="FACE")
    cavity = along_y(graph, graph.lathe([(0.0, septum), (bore, septum), (bore, front), (0.0, front)], SEGMENTS))
    graph.result(graph.mat(graph.smooth_by_angle(body, 0.7), material), slant(graph, cavity, septum, front, radius, cut))
    return graph


@asset("Props.ShishiOdoshi.Stand", "Shishi-odoshi")
def stand():
    """The frame the tube swings in, in the tube's frame: two bamboo posts
    beside the tube, the pin through them along the axle, and the stone the
    tube's end strikes -- its flat top exactly at the tube's lowest point at
    the rest angle."""
    graph = GN("Props.ShishiOdoshi.Stand", stand.__doc__)
    tube_mesh = graph.inp("Tube", "GEOMETRY", desc="The tube in its own frame")
    rest = graph.inp("Rest Angle", default=math.radians(28.0), subtype="ANGLE")
    floor = graph.inp("Floor", default=-0.22, desc="Height of the ground in the tube's frame")
    post_radius = graph.inp("Post Radius", default=0.012, min=0.001, subtype="DISTANCE")
    gap = graph.inp("Post Gap", default=0.004, min=0.0, subtype="DISTANCE", desc="Clearance between the tube and a post")
    rise = graph.inp("Post Rise", default=0.035, min=0.0, subtype="DISTANCE", desc="How far the posts reach above the axle")
    stone_width = graph.inp("Stone Width", default=0.07, min=0.005, subtype="DISTANCE")
    stone_depth = graph.inp("Stone Depth", default=0.06, min=0.005, subtype="DISTANCE")
    seed = graph.inp("Stone Seed", "INT", default=3)
    bamboo = graph.inp("Bamboo Material", "MATERIAL", default=M.get("Props.Bamboo"))
    wood = graph.inp("Pin Material", "MATERIAL", default=M.get("Props.Wood"))
    stone_material = graph.inp("Stone Material", "MATERIAL", default=M.get("Props.Stone"))
    bounds = graph.bound_box(tube_mesh)
    half_width = graph.max(bounds["Max"].x, bounds["Min"].x * -1.0)
    post_x = half_width + gap + post_radius
    length = rise - floor
    post = graph.move(graph.cylinder(post_radius, length, 32, "NGON", 8), z=floor + length * 0.5)
    post = bamboo_coordinates(graph, post, 2)
    post = node_rings(graph, post, graph.position().z, (rise - post_radius * 1.5, floor + length * 0.45), post_radius * 0.5)
    post = graph.store(post, "bamboo_cut", graph.switch(graph.compare(graph.normal().z, 0.5, "GREATER_THAN"), 0.0, 1.0, "FLOAT"), domain="FACE")
    posts = graph.join(graph.move(post, x=post_x * -1.0), graph.move(post, x=post_x))
    pin_length = (post_x + post_radius * 1.3) * 2.0
    pin = graph.transform(graph.cylinder(post_radius * 0.3, pin_length, 16), r=(0.0, 0.5 * math.pi, 0.0))
    pin = graph.store(graph.store(pin, "whittled", 1.0), "wood_coordinate", graph.position(), "FLOAT_VECTOR")
    rested = graph.transform(tube_mesh, r=graph.vec(rest, 0.0, 0.0))
    lowest = graph.statistic(rested, graph.position().z)["Min"]
    contact = graph.statistic(rested, graph.position().y, sel=graph.compare(graph.position().z, lowest + 1e-6, "LESS_EQUAL"))["Mean"]
    stone = graph.group(get_asset("Props.Rock"), Size=graph.vec(stone_width, stone_depth, lowest - floor), Seed=seed, Material=stone_material,
                        **{"Flat Top": True}).o
    stone = graph.move(stone, y=contact, z=floor)
    graph.result(graph.join(graph.mat(graph.smooth_by_angle(posts, 0.7), bamboo), graph.mat(graph.smooth_by_angle(pin, 0.7), wood), stone))
    return graph


@asset("Props.ShishiOdoshi.Simulation", "Shishi-odoshi")
def simulation():
    """Interactive shishi-odoshi (see the kit's notes) fed by a spray wand.
    Put on an object whose origin is the axle and whose X axis runs along it;
    the tube's mouth points along its +Y.  ``Spraying`` switches the wand's
    stream on and off (also during playback); everything in ``Solids`` stands
    in the liquid's way; liquid that reaches the ``Drain`` leaves."""
    graph = GN("Props.ShishiOdoshi.Simulation", simulation.__doc__, modifier=True)
    graph.inp("Geometry", "GEOMETRY")
    for name in ("Spray", "Scene", "Tube"):
        graph.panel(name, closed=False)
    spraying = graph.inp("Spraying", "BOOL", default=True, desc="Switch the wand's stream on and off; can be switched or keyed during playback", panel="Spray")
    chosen = liquids.choice(graph, "Spray")
    flow = graph.inp("Flow", default=45.0, min=0.0, desc="mL/s", panel="Spray")
    nozzle_radius = graph.inp("Nozzle Radius", default=0.0055, min=0.0005, subtype="DISTANCE",
                              desc="The exit speed is flow / nozzle area: a smaller nozzle shoots farther", panel="Spray")
    spread = graph.inp("Spread", default=math.radians(2.0), min=0.0, max=math.radians(45.0), subtype="ANGLE",
                       desc="0 for one jet, wider like a shower head", panel="Spray")
    wand = graph.inp("Wand", "OBJECT", desc="The nozzle is at its origin and sprays along its -Z", panel="Spray")
    solids = graph.inp("Solids", "COLLECTION", desc="What stands in the liquid's way (the basin, the wand ...); may move during playback", panel="Scene")
    ground = graph.inp("Ground", "OBJECT", desc="The top of this object's bounding box is an infinite floor", panel="Scene")
    drain = graph.inp("Drain", "OBJECT", desc="An empty: liquid inside the upright cylinder on its origin (radius = X scale, height = Z scale) leaves", panel="Scene")
    tube_inputs = {name: graph.inp(name, default=default, min=minimum, subtype=subtype, desc=desc, panel="Tube")
                   for name, default, minimum, subtype, desc in (
                       ("Radius", 0.024, 0.002, "DISTANCE", ""),
                       ("Wall", 0.006, 0.0005, "DISTANCE", "Keep it at 1.5 voxels or more, or the liquid seeps through"),
                       ("Front Length", 0.2, 0.01, "DISTANCE", "From the axle to the tip of the mouth's lower lip"),
                       ("Rear Length", 0.24, 0.01, "DISTANCE", "From the axle to the closed end; longer holds more liquid before tipping"),
                       ("Septum", 0.004, None, "DISTANCE", "Where the chamber ends: the front face of the node the axle passes through; keep the axle pin inside the node"),
                       ("Mouth Cut", math.radians(40.0), 0.0, "ANGLE", "Slant of the mouth"))}
    bamboo_density = graph.inp("Bamboo Density", default=700.0, min=1.0, desc="kg/m^3", panel="Tube")
    rest_angle = graph.inp("Rest Angle", default=math.radians(28.0), subtype="ANGLE", desc="Resting on the stone, mouth up", panel="Tube")
    tip_angle = graph.inp("Tip Angle", default=math.radians(-35.0), subtype="ANGLE", desc="Lowest the mouth tips", panel="Tube")
    rest_restitution = graph.inp("Rest Restitution", default=0.3, min=0.0, max=1.0, desc="Bounce off the stone", panel="Tube")
    tip_restitution = graph.inp("Tip Restitution", default=0.1, min=0.0, max=1.0, panel="Tube")
    damping = graph.inp("Axle Damping", default=0.0005, min=0.0, desc="N m s", panel="Tube")
    post_radius = graph.inp("Post Radius", default=0.012, min=0.001, subtype="DISTANCE", panel="Stand")
    stone_seed = graph.inp("Stone Seed", "INT", default=3, panel="Stand")
    typed_values, liquid_materials = liquids.presets(graph, "Look")
    voxel = graph.inp("Voxel", default=0.004, min=0.001, subtype="DISTANCE", desc="Cell size of the FLIP grid", panel="Solver")
    per_cell = graph.inp("Particles Per Cell", default=8.0, min=1.0, panel="Solver")
    cfl = graph.inp("CFL", default=3.0, min=0.1, desc="Cells a particle on the grid may cross per substep", panel="Solver")
    maximum_substeps = graph.inp("Max Substeps", "INT", default=16, min=1, max=64, desc="Safety limit; the CFL sets the count", panel="Solver")
    bamboo = graph.inp("Bamboo Material", "MATERIAL", default=M.get("Props.Bamboo"), panel="Look")
    stone_material = graph.inp("Stone Material", "MATERIAL", default=M.get("Props.Stone"), panel="Look")
    for name, stype, desc in (("Geometry", "GEOMETRY", ""), ("Angle", "FLOAT", "The tube's angle, radians"), ("Held Volume", "FLOAT", "mL in the chamber"),
                              ("Liquid Particles", "INT", ""), ("Airborne Particles", "INT", ""),
                              ("Grid Substeps", "INT", "FLIP substeps this frame (CFL, Max Substeps)"),
                              ("Pressure Residual", "FLOAT", "Largest residual of this frame's pressure solves relative to their right-hand sides"),
                              ("Pressure Iterations", "INT", "Most conjugate gradient iterations of a pressure solve this frame")):
        graph.out(name, stype, desc)

    radius = voxel * 0.5
    particle_volume = graph.math("POWER", voxel, 3.0) / per_cell
    self_transform = graph.object_info(graph.self_object())["Transform"]
    floor = graph.group(get_asset("Physics.Ground"), Object=ground)
    floor_height = floor["Height"] - graph.transform_point((0.0, 0.0, 0.0), self_transform).z
    wand_now = graph.object_info(wand)["Transform"]

    zone = graph.simulation([("Liquid", "GEOMETRY"), ("Remainder", "FLOAT"), ("PreviousWand", "MATRIX"), ("PreviousPlacements", "GEOMETRY"),
                             ("Angle", "FLOAT"), ("Momentum", "FLOAT"), ("HeldVolume", "FLOAT"), ("Substeps", "INT"), ("Residual", "FLOAT"),
                             ("Iterations", "INT"),
                             *remembered_items("Shape", 4, [("Tube", "GEOMETRY"), ("Stand", "GEOMETRY"), ("Mass", "FLOAT"), ("Center", "VECTOR"),
                                                            ("Inertia", "FLOAT"), ("Cavity", "GEOMETRY"), ("Solid", "GEOMETRY")]),
                             *remembered_items("Scene", 2, [("Solid", "GEOMETRY"), ("Moving", "BOOLEAN")])])
    starting = graph.group(get_asset("Physics.Fluid.CollectionMesh"), Collection=solids)["Placements"]
    for name, value in (("PreviousWand", wand_now), ("PreviousPlacements", starting), ("Angle", rest_angle)):
        zone.initial(name, value)
    delta_time = zone.delta_time

    def built_shape():
        shape = graph.group(get_asset("Props.ShishiOdoshi.Tube"), Material=bamboo, **tube_inputs)
        stand_mesh = graph.group(get_asset("Props.ShishiOdoshi.Stand"), Tube=shape["Tube"], Floor=floor_height, **{
            "Rest Angle": rest_angle, "Post Radius": post_radius, "Stone Seed": stone_seed, "Bamboo Material": bamboo,
            "Stone Material": stone_material}).o
        body = graph.group(get_asset("Physics.Hinge.Body"), Body=shape["Tube"], Cavity=shape["Cavity"], Density=bamboo_density,
                           **{"Cavity Voxel": radius * 0.75})
        rigid = graph.group(get_asset("Physics.Fluid.RigidSolid"), Geometry=shape["Tube"], Voxel=radius, Band=4)["Solid"]
        return {"Tube": shape["Tube"], "Stand": stand_mesh, "Mass": body["Mass"], "Center": body["Center"],
                "Inertia": body["Axle Inertia"], "Cavity": body["Cavity"], "Solid": rigid}

    shape = zone.remember("Shape", [graph.vec(tube_inputs["Radius"], tube_inputs["Wall"], tube_inputs["Front Length"]),
                                      graph.vec(tube_inputs["Rear Length"], tube_inputs["Septum"], tube_inputs["Mouth Cut"]),
                                      graph.vec(floor_height, rest_angle, post_radius), graph.vec(stone_seed, bamboo_density, voxel)], built_shape)
    scene_mesh = graph.group(get_asset("Physics.Fluid.CollectionMesh"), Collection=solids, Resting=graph.transform_by(shape["Stand"], self_transform), **{
        "Previous Placements": zone.state("PreviousPlacements"), "Frame Time": delta_time})

    def built_scene():
        solid = graph.group(get_asset("Physics.Fluid.DeformingSolid"), Mesh=scene_mesh["Mesh"], Voxel=radius, Band=2)
        return {"Solid": solid["Solid"], "Moving": solid["Moving"]}

    scene = zone.remember("Scene", [graph.fingerprint(scene_mesh["Mesh"], graph.position(), graph.named("velocity", "FLOAT_VECTOR")),
                                      graph.vec(radius, 2.0, 0.0)], built_scene)
    state = liquid.store(graph, zone.state("Liquid"), typed_values)
    hinge = graph.group(get_asset("Physics.Hinge.Step"), Particles=state, Mass=shape["Mass"], Center=shape["Center"], Cavity=shape["Cavity"],
                        Axle=self_transform, Angle=zone.state("Angle"), Damping=damping, **{
                            "Axle Inertia": shape["Inertia"], "Angular Momentum": zone.state("Momentum"), "Frame Time": delta_time,
                            "Particle Volume": particle_volume, "Rest Angle": rest_angle, "Rest Restitution": rest_restitution,
                            "Tip Angle": tip_angle, "Tip Restitution": tip_restitution})
    emitted = graph.group(get_asset("Props.Spray.Nozzle"), Transform=wand_now, Spraying=spraying, Flow=flow, Spread=spread, Remainder=zone.state("Remainder"), **{
        "Previous Transform": zone.state("PreviousWand"), "Nozzle Radius": nozzle_radius, "Particle Volume": particle_volume,
        "Particle Radius": radius, "Frame Time": delta_time, "Liquid Type": chosen})
    stepped = graph.group(get_asset("Physics.Fluid.Frame"), Points=hinge["Particles"], Spawned=emitted["Points"], Voxel=voxel, CFL=cfl,
                          Rigid=shape["Solid"], Deforming=scene["Solid"], **{
                              "Frame Time": delta_time, "Max Substeps": maximum_substeps, "Rest Density": per_cell,
                              "Ground Height": floor["Height"], "Has Rigid": True, "Rigid Transform": hinge["Transform"],
                              "Rigid Previous": hinge["Previous Transform"], "Has Deforming": True, "Deforming Moves": scene["Moving"]})
    drained = graph.group(get_asset("Physics.Fluid.Drain"), Points=stepped["Points"], Drain=drain, **{"Ground Height": floor["Height"]}).o
    for name, value in (("Liquid", drained), ("Remainder", emitted["Remainder"]), ("PreviousWand", wand_now),
                        ("PreviousPlacements", scene_mesh["Placements"]), ("Angle", hinge["Angle"]), ("Momentum", hinge["Angular Momentum"]),
                        ("HeldVolume", hinge["Held Volume"]), ("Substeps", stepped["Substeps"]), ("Residual", stepped["Pressure Residual"]),
                        ("Iterations", stepped["Pressure Iterations"])):
        zone.set(name, value)

    particles = zone.result("Liquid")
    angle = zone.result("Angle")
    swung = graph.transform_by(zone.result("Shape Tube"), graph.combine_transform(None, graph.axis_angle(X_AXIS, angle), None))
    viewport = graph.n("GeometryNodeIsViewport").o
    meshed = graph.group(get_asset("Physics.Fluid.Surface"), Points=particles, Voxel=graph.switch(viewport, voxel * 0.4, voxel, "FLOAT"),
                         Smoothing=voxel, Erosion=voxel * 0.35, **{"Sphere Radius": voxel * 1.1})
    surface = liquids.dress(graph, meshed["Mesh"], particles, meshed["Nearest Particle"], liquid_materials)
    to_local = graph.invert(self_transform)
    surface = graph.transform_by(surface, to_local)
    surface = graph.store(surface, "velocity", graph.transform_direction(graph.named("velocity", "FLOAT_VECTOR"), to_local), "FLOAT_VECTOR")
    surface = graph.group(get_asset("Shading.Thickness"), Mesh=surface).o
    airborne = graph.delete(particles, graph.bool_not(graph.named("airborne", "BOOLEAN")))
    graph.result(graph.join(swung, zone.result("Shape Stand"), surface), angle, zone.result("HeldVolume") * 1e6,
                 graph.domain_size(particles, "POINTCLOUD")["Point Count"], graph.domain_size(airborne, "POINTCLOUD")["Point Count"],
                 zone.result("Substeps"), zone.result("Residual"), zone.result("Iterations"))
    return graph
