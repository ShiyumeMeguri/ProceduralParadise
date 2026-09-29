"""
Core.physics.membrane -- a pressurised elastic skin on the native XPBD solver.

The skin is a triangle mesh whose edges are length constraints with a rest
length of (filled length / pre-stretch), so the rubber is always under
tension.  The content is not simulated as a fluid but as

* incompressible: after every substep a pressure impulse along
  grad V = sum(A n) / 3 cancels the volume rate, and the leftover drift is
  pushed back to the target volume; what is pressed in bulges elsewhere;
* heavy: the potential energy -rho g . integral(x dV) differentiated with
  respect to the skin vertices gives the hydrostatic pressure, which carries
  the weight of the content to the bottom;
* inertial: the content's mass is spread over the vertices by area; slosh
  damping acts on the motion relative to the centre of mass, including rigid
  rotation (the content does not co-rotate with the skin).

Why the step looks the way it does: the native solver resets its Lagrange
multipliers every call, and its colour-ordered Gauss-Seidel projection of a
pre-stretched skin leaves a residual rigid rotation that no iteration count
removes (the balloon would spin and crawl).  Each substep therefore runs its
own inner steps: internal constraints only, then an angular-momentum
projection back to (start value + external angular impulse), then contact.
Pins and colliders are solved in a second native call re-integrated from the
virtual start x - dt v, so friction sees the true relative motion.
"""
from __future__ import annotations

import math

from ..gn import GN, asset, get_asset
from . import GRAVITY

INNER_SUBSTEPS = 4
MINIMUM_SUBSTEPS = 8


def vertex_area_normal_sum(g):
    area = g.n("GeometryNodeInputMeshFaceArea").o
    mean = g.on_domain(g.normal() * area, "FACE", "FLOAT_VECTOR")
    return mean * g.n("GeometryNodeInputMeshVertexNeighbors")["Face Count"]


def vertex_area(g):
    area = g.n("GeometryNodeInputMeshFaceArea").o
    mean = g.on_domain(area, "FACE", "FLOAT")
    return mean * g.n("GeometryNodeInputMeshVertexNeighbors")["Face Count"] / 3.0


def matrix_3x3(g, columns):
    node = g.n("FunctionNodeCombineMatrix")
    for column_index, column in enumerate(columns):
        for row, value in enumerate(column):
            g.assign(node.n.inputs[column_index * 4 + row], value)
        node.n.inputs[column_index * 4 + 3].default_value = 0.0
    for row in range(3):
        node.n.inputs[12 + row].default_value = 0.0
    node.n.inputs[15].default_value = 1.0
    return node.o


def store_face_vertices(g, geometry):
    """The three vertex indices of every face as ``contact_vertex_0/1/2``."""
    for sort_index in range(3):
        geometry = g.store(geometry, f"contact_vertex_{sort_index}", g.face_vertex(sort_index), "INT", "FACE")
    return geometry


def face_point_weights(g, mesh, face, point):
    """Vertex indices and barycentric weights of ``point`` on triangle ``face``."""
    vertices = [g.sample_index(mesh, g.named(f"contact_vertex_{sort_index}", "INT"), face, "INT", "FACE") for sort_index in range(3)]
    corners = [g.sample_index(mesh, g.position(), vertex, "FLOAT_VECTOR") for vertex in vertices]
    edge_first = corners[1] - corners[0]
    edge_second = corners[2] - corners[0]
    offset = point - corners[0]
    first_first = edge_first.dot(edge_first)
    first_second = edge_first.dot(edge_second)
    second_second = edge_second.dot(edge_second)
    offset_first = offset.dot(edge_first)
    offset_second = offset.dot(edge_second)
    determinant = g.max(first_first * second_second - first_second * first_second, 1e-20)
    beta = g.clamp01((second_second * offset_first - first_second * offset_second) / determinant)
    gamma = g.clamp01((first_first * offset_second - first_second * offset_first) / determinant)
    alpha = g.max(1.0 - beta - gamma, 0.0)
    return vertices, [alpha, beta, gamma]


def blend_at(g, mesh, value, vertices, weights, dtype="FLOAT"):
    total = None
    for weight, vertex in zip(weights, vertices):
        term = g.sample_index(mesh, value, vertex, dtype) * weight
        total = term if total is None else total + term
    return total


def gather_pushes(g, mesh, pushes):
    """Per-vertex push from a point cloud of pushes (``contact_target``,
    ``contact_push``, ``contact_magnitude``): the deepest magnitude a vertex
    receives, along the sum of its pushes.  Averaging would under-push and let
    a pressed skin sink in a little every step."""
    own = g.points(g.domain_size(mesh, "MESH")["Point Count"], radius=0.0)
    own = g.store(own, "contact_target", g.index(), "INT")
    own = g.store(own, "contact_push", (0.0, 0.0, 0.0), "FLOAT_VECTOR")
    own = g.store(own, "contact_magnitude", 0.0)
    own = g.store(own, "contact_is_vertex", True, "BOOLEAN")
    pooled = g.join(own, pushes)
    target = g.named("contact_target", "INT")
    deepest = g.field_max(g.named("contact_magnitude"), target)
    totals, sums = g.capture(pooled, push=g.accumulate(g.named("contact_push", "FLOAT_VECTOR"), target, "FLOAT_VECTOR")["Total"], deepest=deepest)
    gathered = g.delete(totals, g.bool_not(g.named("contact_is_vertex", "BOOLEAN")))
    gathered = g.store(gathered, "contact_push", sums["push"].normalized() * sums["deepest"], "FLOAT_VECTOR")
    return g.sample_index(gathered, g.named("contact_push", "FLOAT_VECTOR"), g.index(), "FLOAT_VECTOR")


def collider_bundle(g, current, previous, friction, margin, deforming=False, edge_contacts=False):
    """Native XPBD mesh collider from the collider geometry now and one frame
    ago (the solver interpolates between them inside a frame)."""
    fields = [
        ("Type", "STRING", "Blender.Collider.Mesh"),
        ("filter", "STRING", ""),
        ("margin", "FLOAT", margin),
        ("friction", "FLOAT", friction),
        ("compliance", "FLOAT", 0.0),
        ("deforming", "BOOLEAN", deforming),
        ("use_edge_contacts", "BOOLEAN", edge_contacts),
        ("is_boundary", "BOOLEAN", False),
    ]
    previous_bundle = g.bundle([*fields, ("geometry", "GEOMETRY", previous)])
    return g.bundle([*fields, ("geometry", "GEOMETRY", current), ("previous", "BUNDLE", previous_bundle)])


@asset("Physics.Membrane.Volume", "Physics")
def volume():
    """Signed volume of a closed triangle mesh, V = sum(A (c . n)) / 3."""
    g = GN("Physics.Membrane.Volume", volume.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    g.out("Volume", "FLOAT")
    area = g.n("GeometryNodeInputMeshFaceArea").o
    g.result(Volume=g.statistic(geometry, area * g.normal().dot(g.position()) / 3.0, domain="FACE")["Sum"])
    return g


@asset("Physics.Membrane.RigidBody", "Physics")
def rigid_body():
    """Mass-weighted rigid quantities: centre c, centre velocity, angular
    momentum L = sum(m r x (v - v_c)), inertia tensor I = sum(m (|r|^2 E - r r^T))
    and angular velocity I^-1 L."""
    g = GN("Physics.Membrane.RigidBody", rigid_body.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    position = g.inp("Position", "VECTOR", desc="Position field to use (may differ from the current one, e.g. the substep start)")
    velocity = g.inp("Velocity", "VECTOR", desc="Velocity field to use")
    for name, stype in (("Center", "VECTOR"), ("Center Velocity", "VECTOR"), ("Angular Momentum", "VECTOR"), ("Inertia", "MATRIX"), ("Angular Velocity", "VECTOR")):
        g.out(name, stype)
    mass = g.named("mass")
    inverse_total = 1.0 / g.statistic(geometry, mass)["Sum"]
    center = g.statistic(geometry, position * mass, "FLOAT_VECTOR")["Sum"] * inverse_total
    center_velocity = g.statistic(geometry, velocity * mass, "FLOAT_VECTOR")["Sum"] * inverse_total
    lever = position - center
    momentum = g.statistic(geometry, lever.cross(velocity - center_velocity) * mass, "FLOAT_VECTOR")["Sum"]
    lever_x, lever_y, lever_z = g.sep(lever)
    squares = g.statistic(geometry, g.vec(lever_x * lever_x, lever_y * lever_y, lever_z * lever_z) * mass, "FLOAT_VECTOR")["Sum"]
    products = g.statistic(geometry, g.vec(lever_x * lever_y, lever_y * lever_z, lever_z * lever_x) * mass, "FLOAT_VECTOR")["Sum"]
    square_x, square_y, square_z = g.sep(squares)
    product_xy, product_yz, product_zx = g.sep(products)
    negative_xy = product_xy * -1.0
    negative_yz = product_yz * -1.0
    negative_zx = product_zx * -1.0
    inertia = matrix_3x3(g, [
        (square_y + square_z, negative_xy, negative_zx),
        (negative_xy, square_x + square_z, negative_yz),
        (negative_zx, negative_yz, square_x + square_y),
    ])
    g.result(Center=center, **{"Center Velocity": center_velocity, "Angular Momentum": momentum, "Inertia": inertia,
                               "Angular Velocity": g.transform_direction(momentum, g.invert(inertia))})
    return g


@asset("Physics.Membrane.VolumeConstraint", "Physics")
def volume_constraint():
    """Incompressible content, projected at two levels along grad V = sum(A n) / 3.
    Velocity level: a pressure impulse J makes the volume rate sum(grad V . v)
    zero; J / dt is this substep's pressure correction (a true Lagrange
    multiplier estimate).  Position level: only the remaining non-linear
    drift is pushed back to the target, without counting as pressure."""
    g = GN("Physics.Membrane.VolumeConstraint", volume_constraint.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    target = g.inp("Target Volume", default=0.0, min=0.0, desc="Volume to keep (cubic metres)")
    delta_time = g.inp("Substep Time", default=1.0 / 240.0, min=1e-6)
    movable = g.inp("Movable", default=1.0, min=0.0, max=1.0, desc="Field: 0 for vertices pushed by colliders or pins; the correction leaves them alone")
    blocked = g.inp("Blocked Normal", "VECTOR", default=(0.0, 0.0, 0.0), desc="Field: the support normal (unit) of vertices resting on a support, zero elsewhere; they are corrected tangentially only, so the support reacts along its normal only")
    g.out("Geometry", "GEOMETRY")
    g.out("Volume", "FLOAT")
    g.out("Pressure", "FLOAT", desc="This substep's pressure correction J / dt, Pa")
    gradient = vertex_area_normal_sum(g) * (1.0 / 3.0)
    allowed = (gradient - blocked * gradient.dot(blocked)) * movable
    inverse_mass = g.named("pressure_weight") / g.named("mass")
    denominator = g.max(g.statistic(geometry, inverse_mass * allowed.dot(allowed))["Sum"], 1e-12)
    velocity = g.named("velocity", "FLOAT_VECTOR")
    rate = g.statistic(geometry, gradient.dot(velocity))["Sum"]
    impulse = rate * -1.0 / denominator
    measured = g.group(get_asset("Physics.Membrane.Volume"), Geometry=geometry)["Volume"]
    multiplier = (target - measured) / denominator
    projected, shares = g.capture(geometry, share=allowed * inverse_mass)
    projected = g.store(projected, "velocity", velocity + shares["share"] * impulse, "FLOAT_VECTOR")
    projected = g.set_pos(projected, offset=shares["share"] * multiplier)
    g.result(projected, measured, impulse / delta_time)
    return g


@asset("Physics.Membrane.Forces", "Physics")
def forces():
    """External force per vertex (``external_force``): weight of skin and
    content; hydrostatic pressure rho (g . x) sum(A n) / 3 from the content's
    potential energy; internal pressure p sum(A n) / 3; slosh damping on the
    motion relative to the centre of mass (rigid rotation included -- the
    content hardly turns with the skin, a lumped-mass model would otherwise
    spin like a solid ball); air drag on the absolute velocity."""
    g = GN("Physics.Membrane.Forces", forces.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    gravity = g.inp("Gravity", "VECTOR", default=GRAVITY)
    density = g.inp("Content Density", default=1000.0, min=0.0, desc="kg/m^3")
    slosh = g.inp("Slosh Damping", default=3.0, min=0.0, desc="1/s; damps sloshing and rotation relative to the centre of mass, not the overall translation")
    drag = g.inp("Air Drag", default=0.02, min=0.0, desc="1/s; linear damping of the absolute velocity")
    blend = g.inp("Hydrostatic", default=1.0, min=0.0, max=1.0, desc="0: the content's weight stays on each vertex; 1: it reaches the bottom through the pressure gradient")
    internal_pressure = g.inp("Pressure", default=0.0, desc="Pa, accumulated from the volume constraint's pressure impulses; integrated as a real force so rubber tension and pressure balance in one solve")
    g.out("Geometry", "GEOMETRY")
    mass = g.named("mass")
    velocity = g.named("velocity", "FLOAT_VECTOR")
    pressure_weight = g.named("pressure_weight")
    centroid = g.statistic(geometry, g.position(), "FLOAT_VECTOR")["Mean"]
    local_pressure = internal_pressure + blend * density * gravity.dot(g.position() - centroid)
    pressure_force = vertex_area_normal_sum(g) * (local_pressure / 3.0 * pressure_weight)
    center_velocity = g.statistic(geometry, velocity * mass, "FLOAT_VECTOR")["Sum"] * (1.0 / g.statistic(geometry, mass)["Sum"])
    content_mass = mass - g.named("shell_mass")
    weight = gravity * (mass - blend * pressure_weight * content_mass)
    sloshing = (velocity - center_velocity) * (mass * (slosh * -1.0))
    air = velocity * (mass * (drag * -1.0))
    g.result(g.store(geometry, "external_force", weight + pressure_force + sloshing + air, "FLOAT_VECTOR"))
    return g


@asset("Physics.Membrane.Momentum", "Physics")
def momentum():
    """Angular-momentum projection.  The native solver's colour-ordered
    Gauss-Seidel projection leaves a residual rotation in the rigid null space
    that iterations cannot remove, and position corrections move the lever arms
    of the momentum; internal constraints produce no torque, so the angular
    momentum about the start centre is set back to its target
    sum((x - c) x (m v + dt F_ext)) by adding a rigid rotation velocity
    dw x (x - c); linear momentum is unchanged.  With symplectic Euler
    L(n+1) = sum(m x(n) x v(n+1)), so it is measured at the start positions."""
    g = GN("Physics.Membrane.Momentum", momentum.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    target = g.inp("Target", "VECTOR", desc="Angular momentum about the start centre")
    center = g.inp("Start Center", "VECTOR", desc="Mass-weighted mean of the start positions; the rigid rotation is added about it so linear momentum stays unchanged")
    inertia = g.inp("Inertia", "MATRIX", desc="Inertia tensor about the centre")
    start = g.inp("Start Position", "VECTOR", desc="Start position field")
    g.out("Geometry", "GEOMETRY")
    velocity = g.named("velocity", "FLOAT_VECTOR")
    lever = start - center
    measured = g.statistic(geometry, lever.cross(velocity) * g.named("mass"), "FLOAT_VECTOR")["Sum"]
    correction = g.transform_direction(target - measured, g.invert(inertia))
    g.result(g.store(geometry, "velocity", velocity + correction.cross(lever), "FLOAT_VECTOR"))
    return g


@asset("Physics.Membrane.EquilibriumPressure", "Physics")
def equilibrium_pressure():
    """Internal pressure balancing the pre-stretched rubber (Laplace pressure).
    An edge pulls vertex a with T (x_b - x_a) / L, T = (L - L_rest) / compliance;
    the pressure p grad V cancelling it in the least-squares sense is
    p = -sum(w F . grad V) / sum(w^2 |grad V|^2) (w: pressure weight).  Starting
    from it the balloon is in equilibrium at once instead of shrinking and
    swelling back."""
    g = GN("Physics.Membrane.EquilibriumPressure", equilibrium_pressure.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    compliance = g.inp("Stretch Compliance", default=0.004, min=1e-9, desc="Per-edge field, the same as in the solve")
    g.out("Pressure", "FLOAT", desc="Pa")
    gradient = vertex_area_normal_sum(g) * (g.named("pressure_weight") * (1.0 / 3.0))
    with_gradient = g.store(geometry, "pressure_gradient", gradient, "FLOAT_VECTOR")
    edge = g.n("GeometryNodeInputMeshEdgeVertices")
    gradient_first = g.sample_index(with_gradient, g.named("pressure_gradient", "FLOAT_VECTOR"), edge["Vertex Index 1"], "FLOAT_VECTOR")
    gradient_second = g.sample_index(with_gradient, g.named("pressure_gradient", "FLOAT_VECTOR"), edge["Vertex Index 2"], "FLOAT_VECTOR")
    span = edge["Position 2"] - edge["Position 1"]
    length = span.length()
    tension = (length - g.named("rest_length")) / compliance
    work = tension / length * span.dot(gradient_first - gradient_second)
    numerator = g.statistic(with_gradient, work, domain="EDGE")["Sum"]
    denominator = g.statistic(with_gradient, g.named("pressure_gradient", "FLOAT_VECTOR").dot(g.named("pressure_gradient", "FLOAT_VECTOR")))["Sum"]
    g.result(numerator * -1.0 / g.max(denominator, 1e-18))
    return g


@asset("Physics.Membrane.Ground", "Physics")
def ground():
    """Analytic ground plane z >= height + radius: vertices below are lifted
    back, their normal velocity is made non-negative and their tangential
    velocity loses at most mu times the normal impulse (Coulomb friction;
    normal impulse = lift / dt + incoming downward speed)."""
    g = GN("Physics.Membrane.Ground", ground.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    use_ground = g.inp("Use Ground", "BOOL", default=True)
    height = g.inp("Height", default=0.0)
    friction = g.inp("Friction", default=0.9, min=0.0, desc="Coulomb friction coefficient")
    delta_time = g.inp("Step", default=1.0 / 960.0, min=1e-6)
    g.out("Geometry", "GEOMETRY")
    floor = height + g.named("radius")
    velocity = g.named("velocity", "FLOAT_VECTOR")
    vx, vy, vz = g.sep(velocity)
    lift = g.max(floor - g.position().z, 0.0)
    touching = g.bool_and(use_ground, g.compare(g.position().z, floor + 1e-5, "LESS_EQUAL"))
    normal_impulse = lift / delta_time + g.max(vz * -1.0, 0.0)
    tangential_speed = g.vec(vx, vy, 0.0).length()
    keep = g.max(tangential_speed - friction * normal_impulse, 0.0) / g.max(tangential_speed, 1e-9)
    stopped = g.vec(vx * keep, vy * keep, g.max(vz, 0.0))
    new_velocity = g.switch(touching, velocity, stopped, "VECTOR")
    shift = g.vec(0.0, 0.0, g.switch(touching, 0.0, lift, "FLOAT"))
    grounded, values = g.capture(geometry, velocity=new_velocity, shift=shift)
    grounded = g.store(grounded, "velocity", values["velocity"], "FLOAT_VECTOR")
    g.result(g.set_pos(grounded, offset=values["shift"]))
    return g


@asset("Physics.Membrane.FaceContact", "Physics")
def face_contact():
    """Collider vertices against the skin's triangles.  The native solver
    tests only skin vertices against colliders, and a thin round stick pushes
    them aside and slips between them.  Here every collider vertex p finds the
    nearest skin point q (normal interpolated from the vertex normals); when
    the signed distance s = (p - q) . n is below the thickness the triangle is
    pushed along -n, its three vertices sharing by barycentric weight w and
    mass: lambda = (thickness - s) / sum(w^2 / m), dx_i = -lambda w_i / m_i n.
    A vertex pushed by several points takes the deepest push; velocities gain
    dx / dt.  Colliders are always outside the skin."""
    g = GN("Physics.Membrane.FaceContact", face_contact.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY", desc="Triangle skin with contact_vertex_0/1/2 on its faces (store_face_vertices)")
    collider_points = g.inp("Collider Points", "GEOMETRY", desc="Collider vertices at the end of the substep, world space")
    margin = g.inp("Margin", default=0.0005, min=0.0)
    delta_time = g.inp("Substep Time", default=1.0 / 192.0, min=1e-6)
    g.out("Geometry", "GEOMETRY")
    g.out("Impulse", "FLOAT", desc="N s, sum(|m dv|) of the pushed vertices")
    g.out("Impulse Moment", "VECTOR", desc="sum(x |m dv|); divided by the impulse it is the point of action")
    g.out("Impulse Vector", "VECTOR", desc="sum(m dv)")
    indexed = geometry
    bounds = g.bound_box(geometry)
    reach = g.statistic(geometry, g.named("radius"))["Max"] + margin
    low = bounds["Min"] - g.vec(reach, reach, reach)
    high = bounds["Max"] + g.vec(reach, reach, reach)
    position = g.position()
    outside = g.bool_or(g.bool_or(g.compare(position.x, low.x, "LESS_THAN"), g.compare(position.x, high.x, "GREATER_THAN")),
                        g.bool_or(g.bool_or(g.compare(position.y, low.y, "LESS_THAN"), g.compare(position.y, high.y, "GREATER_THAN")),
                                  g.bool_or(g.compare(position.z, low.z, "LESS_THAN"), g.compare(position.z, high.z, "GREATER_THAN"))))
    nearby = g.delete(g.mesh_to_points(collider_points), outside)

    located, sampled = g.capture(nearby, face=g.to_int(g.sample_nearest_surface(indexed, g.on_domain(g.index(), "FACE"), g.position()), "ROUND"),
                                 point=g.sample_nearest_surface(indexed, g.position(), g.position(), "FLOAT_VECTOR"))
    vertices, weights = face_point_weights(g, indexed, sampled["face"], sampled["point"])
    vertex_normal = g.on_domain(g.normal(), "POINT", "FLOAT_VECTOR")
    surface_normal = blend_at(g, indexed, vertex_normal, vertices, weights, "FLOAT_VECTOR").normalized()
    blended_radius = blend_at(g, indexed, g.named("radius"), vertices, weights)
    penetration = blended_radius + margin - (g.position() - sampled["point"]).dot(surface_normal)
    inverse_masses = [1.0 / g.sample_index(indexed, g.named("mass"), vertex) for vertex in vertices]
    shares = [weight * inverse_mass for weight, inverse_mass in zip(weights, inverse_masses)]
    denominator = None
    for weight, share in zip(weights, shares):
        denominator = weight * share if denominator is None else denominator + weight * share
    touching, contact = g.capture(located, penetration=penetration, direction=surface_normal * -1.0,
                                  multiplier=penetration / g.max(denominator, 1e-20),
                                  vertex_0=vertices[0], vertex_1=vertices[1], vertex_2=vertices[2],
                                  share_0=shares[0], share_1=shares[1], share_2=shares[2])
    touching = g.delete(touching, g.compare(contact["penetration"], 0.0, "LESS_EQUAL"))

    duplicated = g.n("GeometryNodeDuplicateElements", Geometry=touching, Amount=3, props={"domain": "POINT"})
    copy = duplicated["Duplicate Index"]
    chosen_vertex = g.index_switch(copy, [contact[f"vertex_{item}"] for item in range(3)], "INT")
    chosen_share = g.index_switch(copy, [contact[f"share_{item}"] for item in range(3)], "FLOAT")
    magnitude = contact["multiplier"] * chosen_share
    pushes = g.store(duplicated["Geometry"], "contact_target", chosen_vertex, "INT")
    pushes = g.store(pushes, "contact_push", contact["direction"] * magnitude, "FLOAT_VECTOR")
    pushes = g.store(pushes, "contact_magnitude", magnitude)
    vertex_push = gather_pushes(g, indexed, pushes)

    corrected, values = g.capture(geometry, correction=vertex_push)
    change = values["correction"] * (1.0 / delta_time)
    corrected = g.store(corrected, "velocity", g.named("velocity", "FLOAT_VECTOR") + change, "FLOAT_VECTOR")
    impulse = change * g.named("mass")
    impulse_size = impulse.length()
    impulse_total = g.statistic(corrected, impulse_size)["Sum"]
    impulse_moment = g.statistic(corrected, g.position() * impulse_size, "FLOAT_VECTOR")["Sum"]
    impulse_vector = g.statistic(corrected, impulse, "FLOAT_VECTOR")["Sum"]
    corrected = g.set_pos(corrected, offset=values["correction"])
    has_contact = g.compare(g.domain_size(touching, "POINTCLOUD")["Point Count"], 0, "GREATER_THAN", "INT")
    g.result(g.switch(has_contact, geometry, corrected), g.switch(has_contact, 0.0, impulse_total, "FLOAT"),
             g.switch(has_contact, (0.0, 0.0, 0.0), impulse_moment, "VECTOR"), g.switch(has_contact, (0.0, 0.0, 0.0), impulse_vector, "VECTOR"))
    return g


@asset("Physics.Membrane.ShapeMatch", "Physics")
def shape_match():
    """Shape matching (Mueller 2005): the polar decomposition A = U S V^T gives
    the best rotation R = U V^T and the goal g = R (X - c0) + c, optionally
    blended with a volume-preserving linear deformation.  The goal is computed
    from the given position field; the step passes the solver's predicted
    positions x + dt v + dt^2 f / m, so goal and projected points belong to the
    same instant and the constraint exerts neither net force nor torque."""
    g = GN("Physics.Membrane.ShapeMatch", shape_match.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    position = g.inp("Position", "VECTOR", desc="Position field the goal is fitted to")
    blend = g.inp("Linear Deformation", default=0.25, min=0.0, max=1.0, desc="0: rigid goal (firm jelly); 1: the whole body may squash and stretch (soft jelly)")
    g.out("Goal", "VECTOR")
    mass = g.named("mass")
    rest = g.named("rest_position", "FLOAT_VECTOR")
    inverse_total = 1.0 / g.statistic(geometry, mass)["Sum"]
    center = g.statistic(geometry, position * mass, "FLOAT_VECTOR")["Sum"] * inverse_total
    rest_center = g.statistic(geometry, rest * mass, "FLOAT_VECTOR")["Sum"] * inverse_total
    p = position - center
    q = rest - rest_center
    columns = []
    rest_columns = []
    for component in g.sep(q):
        weight = mass * component
        columns.append(g.sep(g.statistic(geometry, p * weight, "FLOAT_VECTOR")["Sum"]))
        rest_columns.append(g.sep(g.statistic(geometry, q * weight, "FLOAT_VECTOR")["Sum"]))
    moment = matrix_3x3(g, columns)
    rest_moment = matrix_3x3(g, rest_columns)
    svd = g.n("FunctionNodeMatrixSVD", moment)
    v_transposed = g.n("FunctionNodeTransposeMatrix", svd["V"]).o
    rotation_raw = g.matmul(svd["U"], v_transposed)
    determinant = g.n("FunctionNodeMatrixDeterminant", rotation_raw).o
    flip = g.combine_transform((0.0, 0.0, 0.0), None, (1.0, 1.0, -1.0))
    rotation_flipped = g.matmul(g.matmul(svd["U"], flip), v_transposed)
    rotation = g.switch(g.compare(determinant, 0.0, "LESS_THAN"), rotation_raw, rotation_flipped, "MATRIX")
    linear = g.matmul(moment, g.invert(rest_moment))
    linear_determinant = g.n("FunctionNodeMatrixDeterminant", linear).o
    volume_scale = g.math("POWER", g.max(linear_determinant, 1e-6), 1.0 / 3.0)
    rigid_goal = g.transform_direction(q, rotation) + center
    linear_goal = g.transform_direction(q, linear) * (1.0 / volume_scale) + center
    g.result(g.mix(blend, rigid_goal, linear_goal, "VECTOR"))
    return g


@asset("Physics.Membrane.Prepare", "Physics")
def prepare():
    """Turn a mesh into skin state: triangulated, rest lengths (with
    pre-stretch), mass spread by area (skin + content), collision radius,
    friction, zero velocity."""
    g = GN("Physics.Membrane.Prepare", prepare.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    pre_stretch = g.inp("Pre-stretch", default=1.0, min=0.2, desc="Field: how far the filled rubber is stretched; rest length = current length / pre-stretch; 1 for unstretched thick rubber (a balloon's neck)")
    content_mass = g.inp("Content Mass", default=0.5, min=0.0, desc="kg, spread over the vertices by area as inertia")
    shell_density = g.inp("Skin Density", default=0.3, min=0.0, desc="kg/m^2; rubber about 1100 kg/m^3 x 0.3 mm")
    radius = g.inp("Collision Radius", default=0.002, min=0.0)
    friction = g.inp("Friction", default=0.4, min=0.0)
    pressure_weight = g.inp("Pressure Weight", default=1.0, min=0.0, max=1.0, desc="Field: how much the content's pressure (volume constraint and hydrostatics) acts; 0 where no content touches the skin (a balloon's neck)")
    g.out("Geometry", "GEOMETRY")
    g.out("Rest Volume", "FLOAT")
    triangulated = g.n("GeometryNodeTriangulate", Mesh=geometry).o
    edge = g.n("GeometryNodeInputMeshEdgeVertices")
    length = g.vmath("DISTANCE", edge["Position 1"], edge["Position 2"])
    prepared = g.store(triangulated, "pre_stretch", pre_stretch)
    prepared = g.store(prepared, "rest_length", length / g.named("pre_stretch"), domain="EDGE")
    prepared = g.store(prepared, "rest_position", g.position(), "FLOAT_VECTOR")
    wetted_area = vertex_area(g) * pressure_weight
    share = wetted_area / g.statistic(prepared, wetted_area)["Sum"]
    shell_mass = vertex_area(g) * shell_density
    prepared = g.store(prepared, "shell_mass", shell_mass)
    prepared = g.store(prepared, "mass", shell_mass + share * content_mass)
    prepared = g.store(prepared, "radius", radius)
    prepared = g.store(prepared, "pressure_weight", pressure_weight)
    prepared = g.store(prepared, "static_friction", friction)
    prepared = g.store(prepared, "dynamic_friction", friction)
    prepared = g.store(prepared, "velocity", (0.0, 0.0, 0.0), "FLOAT_VECTOR")
    prepared = g.store(prepared, "external_force", (0.0, 0.0, 0.0), "FLOAT_VECTOR")
    g.result(prepared, g.group(get_asset("Physics.Membrane.Volume"), Geometry=prepared)["Volume"])
    return g


@asset("Physics.Membrane.Step", "Physics")
def step():
    """One frame of the skin.  Each substep: external forces -> inner steps
    (native XPBD internal constraints only: stretch / shape -> angular-momentum
    projection -> collider vertices against the skin's triangles -> analytic
    ground) -> re-integration from the virtual start with the native solver for
    pins and colliders (skin vertices against colliders, with friction and
    continuous collision) -> ground -> incompressible volume (velocity and
    position level).  Contact is solved in every inner step: pressed only at
    the end of a substep, the skin springing back would slip through the gap
    beside a stick's tip first and the nearest point would then lie on the
    other side.  The shape goal is taken at the predicted positions (the same
    instant the solver projects); taken at the step start it lags the motion,
    drags translation and pumps rotational energy back through the momentum
    projection."""
    g = GN("Physics.Membrane.Step", step.__doc__)
    geometry = g.inp("Geometry", "GEOMETRY")
    colliders = g.inp("Colliders", "BUNDLE", desc="Collider bundle (collider_bundle)")
    delta_time = g.inp("Frame Time", default=1.0 / 24.0)
    substeps = g.inp("Substeps", "INT", default=MINIMUM_SUBSTEPS, min=MINIMUM_SUBSTEPS, max=200,
                     desc=f"Forces, pressure, colliders and the volume are updated once per substep; each substep solves internal constraints, momentum and ground in {INNER_SUBSTEPS} inner steps.  Below {MINIMUM_SUBSTEPS} a resting contact sinks too far each step and friction rectifies it into a slow crawl")
    iterations = g.inp("Iterations", "INT", default=3, min=1, max=200, desc="Constraint iterations per inner step; the pre-stretched rubber's tension converges by iteration, 3 reach the physical pressure within 1 %")
    stretch = g.inp("Stretch Compliance", default=0.004, min=0.0, desc="1/k, k the spring stiffness of an edge in N/m; for rubber k is about 0.87 E h")
    target_volume = g.inp("Target Volume", default=0.0)
    density = g.inp("Content Density", default=1000.0, min=0.0)
    gravity = g.inp("Gravity", "VECTOR", default=GRAVITY)
    drag = g.inp("Air Drag", default=0.02, min=0.0, desc="1/s, linear damping of the absolute velocity")
    slosh_damping = g.inp("Slosh Damping", default=3.0, min=0.0, desc="1/s, damps sloshing and rotation relative to the centre of mass")
    hydrostatic_blend = g.inp("Hydrostatic", default=1.0, min=0.0, max=1.0)
    ground_height = g.inp("Ground Height", default=0.0, desc="Analytic ground plane (infinite, never penetrated); moving objects belong in the colliders")
    ground_friction = g.inp("Ground Friction", default=0.9, min=0.0, desc="Coulomb coefficient: the tangential velocity loses at most mu times the normal impulse")
    use_ground = g.inp("Use Ground", "BOOL", default=True)
    pin_compliance = g.inp("Pin Compliance", default=0.0, min=0.0)
    use_shape = g.inp("Shape Matching", "BOOL", default=False)
    shape_frequency = g.inp("Shape Frequency", default=6.0, min=0.0, desc="Hz; natural frequency with which each vertex is pulled back to the shape goal.  The compliance 1/(m w^2) follows the mass, so every vertex is pulled back by the same fraction and shape matching exerts no net force or torque")
    shape_blend = g.inp("Linear Deformation", default=0.25, min=0.0, max=1.0)
    previous_pressure = g.inp("Pressure", default=0.0, desc="Internal pressure at the end of the previous frame (simulation state)")
    creep = g.inp("Creep Rate", default=0.0, min=0.0, desc="1/s; rate at which rest lengths relax towards current length / pre-stretch, 0 = purely elastic.  A gel skin whose structure is broken creeps: it shrinks with the volume and keeps the small tension of its pre-stretch (like a drop's surface tension) instead of going slack, wrinkling and folding through itself")
    compression = g.inp("Compression Ratio", default=1.0, min=0.0, max=1.0, desc="Stiffness of a compressed edge / of a stretched edge.  A thin skin wrinkles under compression and hardly resists it, but edge constraints are two-sided and a slack skin would hold its shape like a crushed can.  Edges shortened at the predicted positions use the lower stiffness; 1 = two-sided (a taut balloon is unaffected and pays nothing extra)")
    g.out("Geometry", "GEOMETRY")
    g.out("Volume", "FLOAT")
    g.out("Pressure", "FLOAT")
    g.out("Impulse", "FLOAT", desc="Sum of the impulse magnitudes colliders and pins applied this frame, N s")
    g.out("Impulse Center", "VECTOR", desc="Impulse-weighted point of action")
    g.out("Impulse Direction", "VECTOR", desc="Direction of the total impulse")

    def effector(type_name, extra=()):
        return g.bundle([("Type", "STRING", type_name), ("filter", "STRING", ""), *extra])

    def prop(path):
        return "sim:prop:Membrane/" + path

    edge_ends = g.n("GeometryNodeInputMeshEdgeVertices")
    relaxed_length = g.vmath("DISTANCE", edge_ends["Position 1"], edge_ends["Position 2"]) / g.on_domain(g.named("pre_stretch"), "EDGE")
    creep_share = 1.0 - g.math("EXPONENT", creep * delta_time * -1.0)
    crept = g.store(geometry, "rest_length", g.mix(creep_share, g.named("rest_length"), relaxed_length), domain="EDGE")
    geometry = g.switch(g.compare(creep, 0.0, "GREATER_THAN"), geometry, crept)

    prepared = g.store(geometry, prop("Stretch:rest_length"), g.named("rest_length"), domain="EDGE")
    prepared = g.store(prepared, prop("Stretch:compliance"), stretch, domain="EDGE")
    prepared = g.store(prepared, prop("Pin:selection"), g.compare(g.named("pin_weight"), 0.5, "GREATER_THAN"), "BOOLEAN")
    prepared = g.store(prepared, prop("Pin:position"), g.named("pin_target", "FLOAT_VECTOR"), "FLOAT_VECTOR")
    prepared = g.store(prepared, prop("Pin:compliance"), pin_compliance)
    prepared = g.store(prepared, prop("Shape:selection"), use_shape, "BOOLEAN")
    angular_frequency = shape_frequency * (2.0 * math.pi)
    stiffness_per_mass = g.max(angular_frequency * angular_frequency, 1e-6)
    prepared = g.store(prepared, prop("Shape:compliance"), 1.0 / (g.named("mass") * stiffness_per_mass))
    prepared = g.store(prepared, prop("Shape:position"), g.position(), "FLOAT_VECTOR")
    prepared = store_face_vertices(g, prepared)
    internal_constraints = [
        ("Stretch", "BUNDLE", effector("Blender.Constraint.EdgeLength")),
        ("Shape", "BUNDLE", effector("Blender.Constraint.PinPosition", [("lambda_attribute", "STRING", "")])),
    ]
    external_constraints = [
        ("Pin", "BUNDLE", effector("Blender.Constraint.PinPosition", [("lambda_attribute", "STRING", "")])),
    ]
    sub_time = delta_time / substeps
    active_substeps = g.switch(g.compare(delta_time, 0.0, "GREATER_THAN"), 0, substeps, "INT")
    total_mass = g.statistic(prepared, g.named("mass"))["Sum"]

    collider_now = g.realize(g.bundle_item(colliders, "geometry", "GEOMETRY"))
    collider_before = g.realize(g.bundle_item(colliders, "previous/geometry", "GEOMETRY"))
    collider_margin = g.bundle_item(colliders, "margin", "FLOAT")
    same_topology = g.compare(g.domain_size(collider_now, "MESH")["Point Count"], g.domain_size(collider_before, "MESH")["Point Count"], "EQUAL", "INT")
    previous_position = g.switch(same_topology, g.position(), g.sample_index(collider_before, g.position(), g.index(), "FLOAT_VECTOR"), "VECTOR")
    collider_points = g.store(collider_now, "previous_position", previous_position, "FLOAT_VECTOR")

    outer = g.repeat(active_substeps, [
        ("Geometry", "GEOMETRY", prepared),
        ("Volume", "FLOAT", target_volume),
        ("Pressure", "FLOAT", previous_pressure),
        ("Impulse", "FLOAT", 0.0),
        ("ImpulseMoment", "VECTOR", (0.0, 0.0, 0.0)),
        ("ImpulseVector", "VECTOR", (0.0, 0.0, 0.0)),
    ])
    begin = outer.iteration / substeps
    end = (outer.iteration + 1.0) / substeps
    velocity = g.named("velocity", "FLOAT_VECTOR")
    forced = g.group(get_asset("Physics.Membrane.Forces"), Geometry=outer.state("Geometry"), Gravity=gravity, **{
        "Content Density": density, "Slosh Damping": slosh_damping, "Air Drag": drag, "Hydrostatic": hydrostatic_blend, "Pressure": outer.state("Pressure")})["Geometry"]
    substep_start = g.group(get_asset("Physics.Membrane.RigidBody"), Geometry=forced, Position=g.position(), Velocity=velocity)
    inertia = substep_start["Inertia"]
    torque = g.statistic(forced, (g.position() - substep_start["Center"]).cross(g.named("external_force", "FLOAT_VECTOR")), "FLOAT_VECTOR")["Sum"]
    inner_time = sub_time / INNER_SUBSTEPS

    inner = g.repeat(INNER_SUBSTEPS, [("Geometry", "GEOMETRY", forced), ("Impulse", "FLOAT", 0.0),
                                      ("ImpulseMoment", "VECTOR", (0.0, 0.0, 0.0)), ("ImpulseVector", "VECTOR", (0.0, 0.0, 0.0))])
    step_start = inner.state("Geometry")
    mass = g.named("mass")
    center = g.statistic(step_start, g.position() * mass, "FLOAT_VECTOR")["Sum"] * (1.0 / total_mass)
    target = g.statistic(step_start, (g.position() - center).cross(velocity) * mass, "FLOAT_VECTOR")["Sum"] + torque * inner_time
    predicted = g.position() + velocity * inner_time + g.named("external_force", "FLOAT_VECTOR") * (inner_time * inner_time / mass)
    edge = g.n("GeometryNodeInputMeshEdgeVertices")
    predicted_first = g.sample_index(step_start, predicted, edge["Vertex Index 1"], "FLOAT_VECTOR")
    predicted_second = g.sample_index(step_start, predicted, edge["Vertex Index 2"], "FLOAT_VECTOR")
    slack = g.compare(g.vmath("DISTANCE", predicted_first, predicted_second), g.named("rest_length"), "LESS_THAN")
    unilateral = g.store(step_start, prop("Stretch:compliance"), g.switch(slack, stretch, stretch / g.max(compression, 1e-6), "FLOAT"), domain="EDGE")
    stretched = g.switch(g.compare(compression, 1.0, "LESS_THAN"), step_start, unilateral)
    goal = g.group(get_asset("Physics.Membrane.ShapeMatch"), Geometry=step_start, Position=predicted, **{"Linear Deformation": shape_blend})["Goal"]
    goal_follows = g.store(stretched, prop("Shape:position"), goal, "FLOAT_VECTOR")
    solver_input = g.switch(use_shape, stretched, goal_follows)
    internal_world = g.bundle([("Membrane", "BUNDLE", g.bundle([("Geometry", "GEOMETRY", solver_input), *internal_constraints]))])
    internal = g.n("GeometryNodeXPBDSolver", World=internal_world, Delta_Time=inner_time, Substeps=1, Constraint_Iterations=iterations, Begin=begin, End=end)
    solved = g.bundle_item(internal["World"], "Membrane/Geometry", "GEOMETRY")
    solved = g.store(solved, "membrane:restart", g.position() - velocity * inner_time, "FLOAT_VECTOR")
    restart = g.named("membrane:restart", "FLOAT_VECTOR")
    conserved = g.group(get_asset("Physics.Membrane.Momentum"), Geometry=solved, Target=target, Inertia=inertia,
                        **{"Start Center": center, "Start Position": restart})["Geometry"]
    conserved = g.set_pos(conserved, pos=restart + velocity * inner_time)
    inner_end = begin + (end - begin) * ((inner.iteration + 1.0) / INNER_SUBSTEPS)
    inner_swept = g.set_pos(collider_points, pos=g.mix(inner_end, g.named("previous_position", "FLOAT_VECTOR"), g.position(), "VECTOR"))
    pressed = g.group(get_asset("Physics.Membrane.FaceContact"), Geometry=conserved, Margin=collider_margin,
                      **{"Collider Points": inner_swept, "Substep Time": inner_time})
    inner.set("Geometry", g.group(get_asset("Physics.Membrane.Ground"), Geometry=pressed["Geometry"], Height=ground_height,
                                  Friction=ground_friction, Step=inner_time, **{"Use Ground": use_ground})["Geometry"])
    inner.set("Impulse", inner.state("Impulse") + pressed["Impulse"])
    inner.set("ImpulseMoment", inner.state("ImpulseMoment") + pressed["Impulse Moment"])
    inner.set("ImpulseVector", inner.state("ImpulseVector") + pressed["Impulse Vector"])
    conserved = g.store(inner.result("Geometry"), "membrane:restart", g.position() - velocity * sub_time, "FLOAT_VECTOR")

    rewound = g.set_pos(conserved, pos=restart)
    rewound = g.store(rewound, "external_force", (0.0, 0.0, 0.0), "FLOAT_VECTOR")
    rewound = g.store(rewound, "membrane:free_flight", g.position() + velocity * sub_time, "FLOAT_VECTOR")
    rewound = g.store(rewound, "membrane:free_velocity", velocity, "FLOAT_VECTOR")
    external_world = g.bundle([
        ("Membrane", "BUNDLE", g.bundle([("Geometry", "GEOMETRY", rewound), *external_constraints])),
        ("Colliders", "BUNDLE", colliders),
    ])
    external = g.n("GeometryNodeXPBDSolver", World=external_world, Delta_Time=sub_time, Substeps=1, Constraint_Iterations=1, Begin=begin, End=end)
    contacted = g.bundle_item(external["World"], "Membrane/Geometry", "GEOMETRY")
    pushed = g.compare(g.vmath("DISTANCE", g.position(), g.named("membrane:free_flight", "FLOAT_VECTOR")), 1e-7, "GREATER_THAN")

    impulse = (velocity - g.named("membrane:free_velocity", "FLOAT_VECTOR")) * g.switch(pushed, 0.0, g.named("mass"), "FLOAT")
    impulse_size = impulse.length()
    outer.set("Impulse", outer.state("Impulse") + inner.result("Impulse") + g.statistic(contacted, impulse_size)["Sum"])
    outer.set("ImpulseMoment", outer.state("ImpulseMoment") + inner.result("ImpulseMoment") + g.statistic(contacted, g.position() * impulse_size, "FLOAT_VECTOR")["Sum"])
    outer.set("ImpulseVector", outer.state("ImpulseVector") + inner.result("ImpulseVector") + g.statistic(contacted, impulse, "FLOAT_VECTOR")["Sum"])

    movable_flag, movable_values = g.capture(contacted, movable=g.switch(pushed, 1.0, 0.0, "FLOAT"))
    grounded = g.group(get_asset("Physics.Membrane.Ground"), Geometry=movable_flag, Height=ground_height, Friction=ground_friction,
                       Step=sub_time, **{"Use Ground": use_ground})["Geometry"]
    touching = g.bool_and(use_ground, g.compare(g.position().z, ground_height + g.named("radius") + 1e-5, "LESS_EQUAL"))
    constrained = g.group(get_asset("Physics.Membrane.VolumeConstraint"), Geometry=grounded, Movable=movable_values["movable"], **{
        "Target Volume": target_volume, "Substep Time": sub_time,
        "Blocked Normal": g.switch(touching, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), "VECTOR")})
    outer.set("Geometry", constrained["Geometry"])
    outer.set("Volume", constrained["Volume"])
    outer.set("Pressure", outer.state("Pressure") + constrained["Pressure"])
    cleaned = g.remove_attribute(outer.result("Geometry"), "sim:prop*", wildcard=True)
    cleaned = g.remove_attribute(cleaned, "membrane:*", wildcard=True)
    cleaned = g.remove_attribute(cleaned, "contact_vertex_*", wildcard=True)
    impulse_total = outer.result("Impulse")
    g.result(cleaned, outer.result("Volume"), outer.result("Pressure"), impulse_total,
             outer.result("ImpulseMoment") * (1.0 / g.max(impulse_total, 1e-12)), outer.result("ImpulseVector").normalized())
    return g


@asset("Physics.Membrane.ObjectCollider", "Physics")
def object_collider():
    """An object as an XPBD collider; its transform one frame ago is used for
    sub-frame interpolation, so fast motion does not tunnel."""
    g = GN("Physics.Membrane.ObjectCollider", object_collider.__doc__)
    target = g.inp("Object", "OBJECT")
    previous_transform = g.inp("Previous Transform", "MATRIX")
    has_previous = g.inp("Has Previous", "BOOL", default=False)
    friction = g.inp("Friction", default=0.4, min=0.0)
    margin = g.inp("Margin", default=0.001, min=0.0)
    g.out("Collider", "BUNDLE")
    g.out("Transform", "MATRIX")
    info = g.object_info(target, as_instance=True)
    current = g.transform_by(info["Geometry"], info["Transform"])
    previous_matrix = g.switch(has_previous, info["Transform"], previous_transform, "MATRIX")
    previous = g.transform_by(info["Geometry"], previous_matrix)
    g.result(collider_bundle(g, current, previous, friction, margin), info["Transform"])
    return g
