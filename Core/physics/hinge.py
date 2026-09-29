"""
Core.physics.hinge -- a rigid body turning about a fixed axle that holds
liquid (FLIP particles) in a cavity and pours it out: a shishi-odoshi's
bamboo tube, the buckets of a water wheel.

The body is a closed mesh in its own frame, the axle is that frame's X axis
through its origin.  Its mass, centre and inertia about the axle are
integrated exactly over the mesh (a tetrahedron from the origin per
triangle); ``Physics.Hinge.Body`` turns the body's and its cavity's meshes
into those numbers and the cavity's distance field once, and
``Physics.Hinge.Step`` takes them every frame.  Liquid counts as held while
it rests inside the cavity (airborne drops do not); held liquid adds its
weight torque from the particles' actual positions and turns with the body
(its inertia joins the body's, which keeps the coupling stable however much
liquid the body holds).  Angular momentum L about the axle is the state:

* particles entering the cavity bring their angular momentum m (r x v) . a
  (a jet's impact); particles leaving take their co-rotating share
  m r_perp^2 w with them;
* torque = gravity on body and held liquid - axle damping w;
* the stops (rest and tip angle) reflect the angular velocity with their
  restitution; slower than two frames of torque it comes to rest instead
  of chattering.

Held flags ride on the particles (``hinge_held``) from frame to frame.
"""
from __future__ import annotations

from ..gn import GN, asset, get_asset
from . import GRAVITY
from . import liquid
from .fluid import empty_volume, named_grid, sample_grid, store_grid

X_AXIS = (1.0, 0.0, 0.0)


@asset("Physics.Hinge.MassProperties", "Physics")
def mass_properties():
    """Mass, centre of mass and moment of inertia about the local X axis of a
    closed, outward-facing mesh of uniform density, integrated exactly: for a
    tetrahedron (0, a, b, c) with d = a . (b x c), V = d / 6,
    integral(x) = d (a + b + c) / 24 and integral(y^2) = d (a_y^2 + b_y^2 + c_y^2 +
    a_y b_y + a_y c_y + b_y c_y) / 60."""
    g = GN("Physics.Hinge.MassProperties", mass_properties.__doc__)
    mesh = g.inp("Geometry", "GEOMETRY", desc="Closed mesh in the body's local frame")
    density = g.inp("Density", default=650.0, min=0.0, desc="kg/m^3")
    g.out("Mass", "FLOAT")
    g.out("Center", "VECTOR")
    g.out("Axle Inertia", "FLOAT", desc="kg m^2 about the local X axis")
    triangles = g.n("GeometryNodeTriangulate", Mesh=mesh).o
    a, b, c = (g.sample_index(triangles, g.position(), g.face_vertex(corner), "FLOAT_VECTOR") for corner in range(3))
    determinant = a.dot(b.cross(c))

    def second_moment(axis):
        pa, pb, pc = (g.sep(point)[axis] for point in (a, b, c))
        return pa * pa + pb * pb + pc * pc + pa * pb + pa * pc + pb * pc

    volume = g.statistic(triangles, determinant / 6.0, domain="FACE")["Sum"]
    first = g.statistic(triangles, (a + b + c) * (determinant / 24.0), "FLOAT_VECTOR", "FACE")["Sum"]
    inertia = g.statistic(triangles, determinant / 60.0 * (second_moment(1) + second_moment(2)), domain="FACE")["Sum"]
    g.result(volume * density, first * (1.0 / volume), inertia * density)
    return g


@asset("Physics.Hinge.Body", "Physics")
def body():
    """What ``Physics.Hinge.Step`` needs of a body, from its closed mesh and
    the closed mesh of the cavity that holds liquid (both in the body's local
    frame): mass, centre of mass and moment of inertia about the axle
    (``Physics.Hinge.MassProperties``) and the cavity as a volume with the
    signed distance field ``sdf``.  They depend on the shapes alone, so a
    simulation builds them when the shapes change, not every frame."""
    g = GN("Physics.Hinge.Body", body.__doc__)
    mesh = g.inp("Body", "GEOMETRY", desc="Closed mesh of the body in its local frame (axle = local X)")
    cavity = g.inp("Cavity", "GEOMETRY", desc="Closed mesh of the region that holds liquid, local frame")
    density = g.inp("Density", default=650.0, min=0.0, desc="kg/m^3 of the body")
    cavity_voxel = g.inp("Cavity Voxel", default=0.0015, min=0.0002, desc="Voxel of the cavity's distance field")
    for name, stype in (("Mass", "FLOAT"), ("Center", "VECTOR"), ("Axle Inertia", "FLOAT"), ("Cavity", "GEOMETRY")):
        g.out(name, stype)
    properties = g.group(get_asset("Physics.Hinge.MassProperties"), Geometry=mesh, Density=density)
    sdf = g.n("GeometryNodeMeshToSDFGrid", Mesh=cavity, Voxel_Size=cavity_voxel, Band_Width=2)["SDF Grid"]
    g.result(properties["Mass"], properties["Center"], properties["Axle Inertia"], store_grid(g, empty_volume(g), "sdf", sdf))
    return g


@asset("Physics.Hinge.Step", "Physics")
def step():
    """One frame of a hinged body holding liquid (see Core.physics.hinge).
    Returns the new angle and angular momentum, the body's transforms at the
    start and end of the frame (for Physics.Fluid.Step's rigid solid) and the
    particles with updated ``hinge_held`` flags."""
    g = GN("Physics.Hinge.Step", step.__doc__)
    particles = g.inp("Particles", "GEOMETRY", desc="Liquid particles (world): velocity, airborne, the liquid material, hinge_held of the previous frame")
    body_mass = g.inp("Mass", default=0.1, min=0.0, desc="kg of the body (Physics.Hinge.Body)")
    body_center = g.inp("Center", "VECTOR", default=(0.0, 0.0, 0.0), desc="The body's centre of mass in its local frame")
    body_inertia = g.inp("Axle Inertia", default=1e-4, min=1e-12, desc="kg m^2 of the body about the axle")
    cavity = g.inp("Cavity", "GEOMETRY", desc="Volume with the cavity's signed distance field sdf, local frame (Physics.Hinge.Body)")
    axle = g.inp("Axle", "MATRIX", desc="World transform of the local frame at angle 0")
    angle = g.inp("Angle", default=0.0, subtype="ANGLE", desc="Current angle about the axle")
    momentum = g.inp("Angular Momentum", default=0.0, desc="kg m^2/s about the axle, body and held liquid")
    delta_time = g.inp("Frame Time", default=1.0 / 24.0)
    gravity = g.inp("Gravity", "VECTOR", default=GRAVITY)
    particle_volume = g.inp("Particle Volume", default=8e-9, min=0.0, desc="m^3 of liquid per particle")
    damping = g.inp("Damping", default=0.0, min=0.0, desc="N m s; viscous friction of the axle")
    rest_angle = g.inp("Rest Angle", default=0.5, subtype="ANGLE", desc="Upper stop (e.g. the stone an empty tube rests on)")
    rest_restitution = g.inp("Rest Restitution", default=0.3, min=0.0, max=1.0)
    tip_angle = g.inp("Tip Angle", default=-0.6, subtype="ANGLE", desc="Lower stop, reached when the body tips")
    tip_restitution = g.inp("Tip Restitution", default=0.1, min=0.0, max=1.0)
    for name, stype in (("Particles", "GEOMETRY"), ("Angle", "FLOAT"), ("Angular Momentum", "FLOAT"), ("Transform", "MATRIX"),
                        ("Previous Transform", "MATRIX"), ("Angular Velocity", "FLOAT"), ("Held Volume", "FLOAT")):
        g.out(name, stype)

    def placed(theta):
        return g.matmul(axle, g.combine_transform(None, g.axis_angle(X_AXIS, theta), None))

    start = placed(angle)
    origin = g.transform_point((0.0, 0.0, 0.0), axle)
    axis = g.transform_direction(X_AXIS, axle).normalized()
    local = g.transform_point(g.position(), g.invert(start))
    inside = g.compare(sample_grid(g, named_grid(g, cavity, "sdf"), local), 0.0, "LESS_THAN")
    held = g.bool_and(inside, g.bool_not(g.named("airborne", "BOOLEAN")))
    was_held = g.named("hinge_held", "BOOLEAN")
    entering = g.bool_and(held, g.bool_not(was_held))
    leaving = g.bool_and(was_held, g.bool_not(held))
    mass = liquid.read(g, "density") * particle_volume
    lever = g.position() - origin
    along = lever.dot(axis)
    perpendicular_square = lever.dot(lever) - along * along
    swing = mass * perpendicular_square

    def total(value, selection):
        return g.statistic(particles, value, sel=selection)["Sum"]

    inertia_before = body_inertia + total(swing, was_held)
    inertia_now = body_inertia + total(swing, held)
    omega_before = momentum / inertia_before
    captured = momentum - total(swing, leaving) * omega_before + total(lever.cross(g.named("velocity", "FLOAT_VECTOR") * mass).dot(axis), entering)
    omega_captured = captured / inertia_now
    body_center_world = g.transform_point(body_center, start)
    torque = (body_center_world - origin).cross(gravity * body_mass).dot(axis) + total(lever.cross(gravity * mass).dot(axis), held) - damping * omega_captured
    free_omega = (captured + torque * delta_time) / inertia_now
    free_angle = angle + free_omega * delta_time
    settle = 2.0 * g.abs(torque) * delta_time / inertia_now

    def stop(angle_value, omega, limit, restitution, sign):
        hits = g.compare(angle_value * sign, limit * sign, "GREATER_THAN")
        into = g.compare(omega * sign, 0.0, "GREATER_THAN")
        bounce = g.switch(g.compare(g.abs(omega), settle, "GREATER_THAN"), 0.0, omega * -restitution, "FLOAT")
        return (g.switch(hits, angle_value, limit, "FLOAT"),
                g.switch(g.bool_and(hits, into), omega, bounce, "FLOAT"))

    rest_limited_angle, rest_limited_omega = stop(free_angle, free_omega, rest_angle, rest_restitution, 1.0)
    final_angle, final_omega = stop(rest_limited_angle, rest_limited_omega, tip_angle, tip_restitution, -1.0)
    marked = g.store(particles, "hinge_held", held, "BOOLEAN")
    g.result(marked, final_angle, final_omega * inertia_now, placed(final_angle), start, final_omega,
             total(particle_volume, held))
    return g
