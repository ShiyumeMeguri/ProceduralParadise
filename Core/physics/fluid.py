"""
Core.physics.fluid -- FLIP liquid on a staggered MAC grid, in geometry nodes.

``Physics.Fluid.Step`` advances particles (``velocity`` plus the per-particle
material of :mod:`.liquid`) by one frame with CFL-adaptive substeps.  Solids
are an analytic ground plane, one rigid body (a local-space signed distance
field moved by a transform interpolated inside the frame) and one deforming
body (a world-space distance field with a velocity field; a collection of
moving objects becomes one with ``Physics.Fluid.CollectionMesh`` and
``Physics.Fluid.DeformingSolid``).
Free-falling drops leave the grid and fly exact parabolas
(``Physics.Fluid.Flight``); ``Physics.Fluid.Frame`` runs grid and flight
together, ``Physics.Fluid.Drain`` removes what drains away and
``Physics.Fluid.Surface`` meshes the particles.

Every node that creates or samples a grid costs about a millisecond on its
own, so quantities on one topology are packed into one vector grid and
per-voxel arithmetic is merged into a few Field to Grid nodes.
"""
from __future__ import annotations

from ..gn import GN, asset, get_asset, set_menu
from . import GRAVITY, liquid

AXES = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
DIRECTIONS = tuple(tuple(sign if index == axis else 0.0 for index in range(3)) for axis in range(3) for sign in (1.0, -1.0))
FLIGHT_TIME = "fluid:flight_time"
SOLID_DISTANCE = "fluid:solid_distance"
VELOCITY_START = "fluid:velocity_start"
SOLID_EPSILON = 1e-5
VELOCITY_GRIDS = ("velocity_x", "velocity_y", "velocity_z")
SOLID_INPUTS = (("Ground Height", "FLOAT", 0.0), ("Has Rigid", "BOOL", False), ("Rigid", "GEOMETRY", None),
                ("Has Deforming", "BOOL", False), ("Deforming", "GEOMETRY", None), ("Deforming Moves", "BOOL", False))


def sample_grid(g, grid, position, dtype="FLOAT", interpolation="Trilinear"):
    node = g.n("GeometryNodeSampleGrid", Grid=grid, Position=position, props={"data_type": dtype})
    set_menu(node.n.inputs["Interpolation"], interpolation)
    return node["Value"]


def named_grid(g, volume, name, dtype="FLOAT"):
    return g.n("GeometryNodeGetNamedGrid", Volume=volume, Name=name, props={"data_type": dtype})["Grid"]


def store_grid(g, volume, name, grid, dtype="FLOAT"):
    return g.n("GeometryNodeStoreNamedGrid", Volume=volume, Name=name, Grid=grid, props={"data_type": dtype}).o


def grid_ready(g, grid, dtype="FLOAT"):
    """A single value that exists only once ``grid`` does (``after`` of
    :func:`rasterize`).  It is sampled at a Vector node: Sample Grid's
    Position input left unlinked is the implicit position field, which would
    turn the value into a field that no geometry switch can wait on."""
    value = sample_grid(g, grid, g.n("FunctionNodeInputVector").o, dtype, interpolation="Nearest Neighbor")
    return value.length() if dtype == "VECTOR" else value


def rasterize(g, points, items, voxel=None, matrix=None, kernel="Linear", after=None):
    """Rasterize Points with ``items`` [(name, value, is_vector), ...].  ``after``
    (a value read from another grid) makes this rasterization wait for that
    grid: in Blender 5.3 two Rasterize Points running at once can deadlock on
    OpenVDB's attribute registry lock when TBB work stealing runs one inside
    the other's parallel loop."""
    if after is not None:
        points = g.switch(g.bool_or(g.compare(after, 0.0, "GREATER_THAN"), g.compare(after, 0.0, "LESS_EQUAL")), points, points)
    node = g.n("GeometryNodeRasterizePoints", Points=points)
    set_menu(node.n.inputs["Kernel Type"], kernel)
    if matrix is not None:
        set_menu(node.n.inputs["Grid Transform Mode"], "Matrix")
        g.assign(g._in_socket(node.n, "Matrix"), matrix)
    else:
        g.assign(g._in_socket(node.n, "Voxel Size"), voxel)
    for name, _value, vector in items:
        item = node.n.rasterize_items.new(name)
        item.type = "VECTOR" if vector else "SCALAR"
    for name, value, _vector in items:
        g.assign(g._in_socket(node.n, name), value)
    return node


def grid_mean(g, grid, iterations, width=1, dtype="FLOAT"):
    return g.n("GeometryNodeGridMean", Grid=grid, Width=width, Iterations=iterations, props={"data_type": dtype})["Grid"]


def field_to_grids(g, topology, items, topology_type="FLOAT"):
    """One Field to Grid node on ``topology`` with ``items`` [(name, type,
    value)], every grid with background zero.  Field to Grid takes its
    background from the field evaluated outside any voxel -- at the origin --
    so the empty space around the liquid would take whatever the field is
    there (solid wherever the origin lies inside a solid, which walls up free
    surfaces).  Outside any voxel Voxel Index reports an extent of zero, so
    every value is gated by it: exact, and no second pass over the grid."""
    node = g.n("GeometryNodeFieldToGrid", Topology=topology, props={"data_type": topology_type})
    inside = g.compare(g.n("GeometryNodeInputVoxelIndex")["Extent X"], 0, "GREATER_THAN", "INT")
    for name, kind, _value in items:
        node.n.grid_items.new(kind, name)
    for name, kind, value in items:
        empty = 0.0 if kind == "FLOAT" else (0.0, 0.0, 0.0)
        g.assign(g._in_socket(node.n, name), g.switch(inside, empty, value, kind))
    return {name: node[name] for name, _kind, _value in items}


def pressure(g, liquid_cells, rhs, walled, voxel, iterations, tolerance, minimum_island):
    """Pressure on the liquid cells (the active voxels of ``liquid_cells``)
    for the right-hand side field ``rhs``, zero towards air and no flux
    through the ``walled`` sides (a field counting each cell's solid
    neighbours).  The cells become the vertices of a mesh whose edges join
    face neighbours (a link from every cell towards +x, +y and +z, welded,
    keeping the ends that land on a liquid cell -- the grid says which, its
    liquid voxels hold 1); islands of fewer than ``minimum_island`` cells
    (splashes, drops on a rim) get no pressure and move freely.  One Blur
    Attribute, (v + sum) / (1 + n), gives every cell the sum over its
    neighbours, and every side is a neighbour, a wall or air, so the diagonal
    is 6 minus the walls.

    Jacobi-preconditioned conjugate gradient starts from zero (starting from
    the last solve's pressure was measured to save nothing: every substep's
    right-hand side is new) and iterates until the residual's Jacobi-weighted
    norm is ``tolerance`` times the right-hand side's, at most ``iterations``
    times.  An iteration is four nodes -- a capture of A p, the two inner
    products, one store of the packed state (x, r, p) -- and once converged
    the remaining iterations pass the state through untouched (a switch on a
    single value evaluates only the branch it takes, so they cost next to
    nothing).  Measured against the one-reduction form of Chronopoulos and
    Gear and against smoothing (polynomial) preconditioners built from
    Blur Attribute passes, this plain form takes the least time: a node's
    fixed cost outweighs the iterations the others save.  (Blender's Grid
    Solve Poisson is OpenVDB's conjugate gradient, which gives up as soon as
    the residual grows to twice its lowest value -- which the residual of a
    wall-bounded pool does on its way to converging.)  Returns the pressure
    grid, the final largest residual relative to the right-hand side and the
    iterations it took."""
    centres = g.n("GeometryNodeGridToPoints", Grid=liquid_cells, props={"data_type": "FLOAT"})["Points"]
    links = g.join(*[g.mesh_line(2, (0.0, 0.0, 0.0), g.vec(*axis) * voxel) for axis in AXES])
    mesh = g.merge(g.realize(g.iop(centres, links)), voxel * 0.25)
    cells = g.delete(mesh, g.compare(g.abs(sample_grid(g, liquid_cells, g.position(), interpolation="Nearest Neighbor") - 1.0), 0.5, "GREATER_THAN"))
    island_size = g.accumulate(1.0, g.n("GeometryNodeInputMeshIsland")["Island Index"])["Total"]
    cells = g.delete(cells, g.compare(island_size, minimum_island, "LESS_THAN"))
    cells = g.store(cells, "pressure:system", g.vec(rhs * (voxel * voxel * -1.0), g.max(6.0 - walled, 1.0),
                                                     g.n("GeometryNodeInputMeshVertexNeighbors")["Vertex Count"]), "FLOAT_VECTOR")
    b, diagonal, neighbours = g.sep(g.named("pressure:system", "FLOAT_VECTOR"))

    def apply(value):
        blurred = g.n("GeometryNodeBlurAttribute", Value=value, Iterations=1, Weight=1.0, props={"data_type": "FLOAT"}).o
        return diagonal * value - (blurred * (1.0 + neighbours) - value)

    def safe(numerator, denominator):
        return g.switch(g.compare(g.abs(denominator), 1e-30, "GREATER_THAN"), 0.0, numerator / denominator, "FLOAT")

    cells = g.store(cells, "pressure:state", g.vec(0.0, b, b / diagonal), "FLOAT_VECTOR")
    x, r, p = g.sep(g.named("pressure:state", "FLOAT_VECTOR"))
    count = g.domain_size(cells, "MESH")["Point Count"]
    enough = g.statistic(cells, b * b / diagonal)["Sum"] * (tolerance * tolerance)
    zone = g.repeat(g.switch(g.compare(count, 0, "GREATER_THAN", "INT"), 0, iterations, "INT"),
                    [("Cells", "GEOMETRY", cells), ("Fit", "FLOAT", g.statistic(cells, r * p)["Sum"]), ("Used", "INT", 0)])
    fit = zone.state("Fit")
    converged = g.compare(fit, enough, "LESS_EQUAL")
    captured, values = g.capture(zone.state("Cells"), q=apply(p))
    q = values["q"]
    alpha = safe(fit, g.statistic(captured, p * q)["Sum"])
    residual = r - alpha * q
    preconditioned = residual / diagonal
    refit = g.statistic(captured, residual * preconditioned)["Sum"]
    iterated = g.store(captured, "pressure:state", g.vec(x + alpha * p, residual, preconditioned + safe(refit, fit) * p), "FLOAT_VECTOR")
    zone.set("Cells", g.switch(converged, iterated, zone.state("Cells")))
    zone.set("Fit", g.switch(converged, refit, fit, "FLOAT"))
    zone.set("Used", g.switch(converged, zone.state("Used") + 1, zone.state("Used"), "INT"))
    solved = zone.result("Cells")
    lookup = g.sample_nearest(solved, g.position())
    found = g.compare(g.vmath("DISTANCE", g.sample_index(solved, g.position(), lookup, "FLOAT_VECTOR"), g.position()), voxel * 0.25, "LESS_THAN")
    solution = g.switch(found, 0.0, g.sample_index(solved, x, lookup), "FLOAT")
    grid = field_to_grids(g, liquid_cells, [("pressure", "FLOAT", solution)])["pressure"]
    worst = g.statistic(solved, g.abs(r))["Max"] / g.max(g.statistic(solved, g.abs(b))["Max"], 1e-30)
    return grid, worst, zone.result("Used")


def forget(g, points):
    """``points`` without the liquid material and this frame's working
    attributes (``fluid:*``), whether they are present or not."""
    return liquid.forget(g, g.remove_attribute(points, "fluid:*", wildcard=True))


def interpolate_transform(g, previous, current, fraction):
    """Transform at ``fraction`` of the way from ``previous`` to ``current``:
    location and scale linear, rotation spherical."""
    previous_parts = g.separate_transform(previous)
    current_parts = g.separate_transform(current)
    location = g.mix(fraction, previous_parts["Translation"], current_parts["Translation"], "VECTOR")
    rotation = g.mix(fraction, previous_parts["Rotation"], current_parts["Rotation"], "ROTATION")
    scale = g.mix(fraction, previous_parts["Scale"], current_parts["Scale"], "VECTOR")
    return g.combine_transform(location, rotation, scale)


def empty_volume(g):
    volume = g.n("GeometryNodeVolumeCube", Density=0.0, Resolution_X=2, Resolution_Y=2, Resolution_Z=2).o
    return g.n("GeometryNodeGetNamedGrid", Volume=volume, Name="density", Remove=True, props={"data_type": "FLOAT"})["Volume"]


def within_band(g, sdf, distance):
    """Whether a distance sampled from ``sdf`` lies inside its narrow band:
    beyond it the grid only holds its background (the band's width), which
    says "somewhere outside", not how far."""
    background = g.n("GeometryNodeGridInfo", Grid=sdf, props={"data_type": "FLOAT"})["Background Value"]
    return g.compare(distance, background * 0.9999, "LESS_THAN")


def solid_inputs(g):
    return {name: g.inp(name, stype, default=default) for name, stype, default in SOLID_INPUTS}


@asset("Physics.Fluid.SolidDistance", "Physics")
def solid_distance():
    """Every solid the liquid sees: the ground plane, one rigid body (local
    signed distance field, transform interpolated per substep) and one
    deforming body (world-space distance and velocity fields; the velocity
    grids are read only while it moves).  Returns the nearest solid's
    distance, normal and velocity; beyond a distance field's narrow band
    that solid counts as far away."""
    g = GN("Physics.Fluid.SolidDistance", solid_distance.__doc__)
    position = g.inp("Position", "VECTOR", default=(0.0, 0.0, 0.0))
    ground = g.inp("Ground Height", default=0.0)
    has_rigid = g.inp("Has Rigid", "BOOL", default=False)
    rigid = g.inp("Rigid", "GEOMETRY")
    rigid_transform = g.inp("Rigid Transform", "MATRIX")
    rigid_previous = g.inp("Rigid Previous", "MATRIX")
    has_deforming = g.inp("Has Deforming", "BOOL", default=False)
    deforming = g.inp("Deforming", "GEOMETRY")
    moves = g.inp("Deforming Moves", "BOOL", default=False, desc="Whether the deforming body carries velocity grids (Physics.Fluid.DeformingSolid's Moving)")
    duration = g.inp("Duration", default=1.0 / 240.0)
    for name, stype in (("Distance", "FLOAT"), ("Normal", "VECTOR"), ("Velocity", "VECTOR")):
        g.out(name, stype)
    far = 1.0e6
    ground_distance = position.z - ground
    local = g.transform_point(position, g.invert(rigid_transform))
    rigid_sdf = sample_grid(g, named_grid(g, rigid, "sdf"), local)
    rigid_distance = g.switch(g.bool_and(has_rigid, within_band(g, named_grid(g, rigid, "sdf"), rigid_sdf)), far, rigid_sdf, "FLOAT")
    rigid_normal = g.transform_direction(sample_grid(g, named_grid(g, rigid, "normal", "VECTOR"), local, "VECTOR"), rigid_transform).normalized()
    previous_position = g.transform_point(local, rigid_previous)
    rigid_velocity = (position - previous_position) * (1.0 / duration)
    deforming_sdf = sample_grid(g, named_grid(g, deforming, "sdf"), position)
    deforming_distance = g.switch(g.bool_and(has_deforming, within_band(g, named_grid(g, deforming, "sdf"), deforming_sdf)), far, deforming_sdf, "FLOAT")
    deforming_normal = sample_grid(g, named_grid(g, deforming, "normal", "VECTOR"), position, "VECTOR").normalized()
    deforming_velocity = g.switch(moves, (0.0, 0.0, 0.0), g.vec(*[sample_grid(g, named_grid(g, deforming, name), position) for name in VELOCITY_GRIDS]), "VECTOR")
    rigid_wins = g.compare(rigid_distance, deforming_distance, "LESS_THAN")
    nearest_solid = g.min(rigid_distance, deforming_distance)
    solid_normal = g.switch(rigid_wins, deforming_normal, rigid_normal, "VECTOR")
    solid_velocity = g.switch(rigid_wins, deforming_velocity, rigid_velocity, "VECTOR")
    ground_wins = g.compare(ground_distance, nearest_solid, "LESS_THAN")
    g.result(g.min(ground_distance, nearest_solid),
             g.switch(ground_wins, solid_normal, (0.0, 0.0, 1.0), "VECTOR"),
             g.switch(ground_wins, solid_velocity, (0.0, 0.0, 0.0), "VECTOR"))
    return g


def distance_volume(g, mesh, voxel, band):
    """Volume with the signed distance field ``sdf`` of ``mesh`` and its
    gradient ``normal``."""
    sdf = g.n("GeometryNodeMeshToSDFGrid", Mesh=mesh, Voxel_Size=voxel, Band_Width=band)["SDF Grid"]
    volume = store_grid(g, empty_volume(g), "sdf", sdf)
    return store_grid(g, volume, "normal", g.n("GeometryNodeGridGradient", Grid=sdf)["Gradient"], "VECTOR_FLOAT"), sdf


@asset("Physics.Fluid.RigidSolid", "Physics")
def rigid_solid():
    """A rigid body for the liquid: its mesh in its own local frame as a
    signed distance field plus gradient.  The caller moves it with a transform
    that the step interpolates inside the frame."""
    g = GN("Physics.Fluid.RigidSolid", rigid_solid.__doc__)
    mesh = g.inp("Geometry", "GEOMETRY", desc="Closed mesh in the body's local frame")
    voxel = g.inp("Voxel", default=0.002, min=0.0002)
    band = g.inp("Band", "INT", default=4, min=1)
    g.out("Solid", "GEOMETRY")
    g.result(distance_volume(g, mesh, voxel, band)[0])
    return g


@asset("Physics.Fluid.DeformingSolid", "Physics")
def deforming_solid():
    """A deforming closed mesh (world space, ``velocity`` on its points) as a
    signed distance field, its gradient and -- while any point moves -- a
    velocity field (three scalar grids from one Field to Grid).  ``Moving``
    tells the solid queries whether to read the velocity at all."""
    g = GN("Physics.Fluid.DeformingSolid", deforming_solid.__doc__)
    mesh = g.inp("Mesh", "GEOMETRY")
    voxel = g.inp("Voxel", default=0.004, min=0.0002)
    band = g.inp("Band", "INT", default=3, min=1)
    g.out("Solid", "GEOMETRY")
    g.out("Moving", "BOOL")
    volume, sdf = distance_volume(g, mesh, voxel, band)
    velocity = g.named("velocity", "FLOAT_VECTOR")
    moving = g.compare(g.statistic(mesh, velocity.length())["Max"], 0.0, "GREATER_THAN")
    field = g.sample_nearest_surface(mesh, velocity, g.position(), "FLOAT_VECTOR")
    velocity_grids = field_to_grids(g, sdf, [(name, "FLOAT", component) for name, component in zip(VELOCITY_GRIDS, g.sep(field))])
    moving_volume = volume
    for name in VELOCITY_GRIDS:
        moving_volume = store_grid(g, moving_volume, name, velocity_grids[name])
    g.result(g.switch(moving, volume, moving_volume), moving)
    return g


@asset("Physics.Fluid.Substep", "Physics")
def substep():
    """One FLIP substep on a staggered MAC grid: particles -> face grids ->
    gravity and viscosity -> solid faces -> divergence (with density
    correction) -> Poisson pressure (air Dirichlet, solid Neumann; see
    :func:`pressure`) -> projection -> masked, normalised interpolation
    back to the particles (PIC/FLIP) -> RK2 advection -> collision,
    friction, adhesion.  Over-dense cells relax towards the rest density
    with the time constant ``Density Relaxation``, whatever the substep,
    so the substep count does not change how much the liquid gives under
    its weight.

    Viscosity spreads momentum into a Gaussian of variance 2 nu dt per
    substep, assembled exactly from box means: ceil(passes) passes (for the
    most viscous liquid present), then every face blends between the raw and
    the diffused momentum by (nu / nu_max) (passes / ceil(passes)).  Solid
    faces join the means as phantom mass moving with the solid (weighted by
    the adjacent liquid's wall stick), so no-slip walls drag the liquid layer
    by layer.  Cells are classified one voxel beyond the particles (0 air,
    1 liquid, 2 solid), so every neighbour of a liquid cell is known to be
    solid (a wall for the pressure) or air (pressure zero).

    Sampling grids is most of a substep's work, so each face is looked at
    once: the first pass over a face grid queries the solids and the cell
    material and keeps what the later passes need -- the solid's velocity,
    how firmly the face follows it, the face's viscosity share, and the
    face's flags (1 solid, 2 liquid) beside the momentum -- in vector grids
    read back with one nearest sample each.  The divergence pass counts a
    cell's walls from the same face samples, and the projected faces pack
    (new, old, weight) into one vector, so a particle reads three vectors
    per point of its path.  With a single liquid material the cell material
    is that material rather than a sampled mixture."""
    g = GN("Physics.Fluid.Substep", substep.__doc__)
    points = g.inp("Points", "GEOMETRY")
    voxel = g.inp("Voxel", default=0.01, min=0.0005)
    delta_time = g.inp("Substep Time", default=1.0 / 240.0, min=1e-6)
    gravity = g.inp("Gravity", "VECTOR", default=GRAVITY)
    rest_density = g.inp("Rest Density", default=8.0, min=0.01, desc="Rasterized weight of a full cell = particles per cell")
    density_relaxation = g.inp("Density Relaxation", default=0.0234, min=1e-4, desc="s; time constant with which over-dense regions are pushed back to the rest density, so the volume does not drain away")
    fluid_threshold = g.inp("Fluid Threshold", default=0.3, min=0.0, max=1.0, desc="A cell joins the pressure solve when its weight exceeds rest density x this")
    radius = g.inp("Particle Radius", default=0.003, min=0.0)
    adhesion_range = g.inp("Adhesion Range", default=0.004, min=0.0)
    viscosity_width = g.inp("Viscosity Width", "INT", default=2, min=1, max=4, desc="Radius of every box-mean pass in cells; wider needs fewer passes, but below about 3 passes the kernel is less Gaussian")
    pressure_iterations = g.inp("Pressure Iterations", "INT", default=100, min=1, desc="Most conjugate gradient iterations of a pressure solve")
    pressure_tolerance = g.inp("Pressure Tolerance", default=1e-3, min=1e-9, desc="The solve stops once its residual is this share of the right-hand side (Jacobi-weighted norms)")
    minimum_island = g.inp("Min Island", "INT", default=27, min=1, desc="Liquid islands of fewer cells (splashes, drops on a rim) stay out of the pressure solve and move freely")
    solids = solid_inputs(g)
    solids["Rigid Transform"] = g.inp("Rigid Transform", "MATRIX")
    solids["Rigid Previous"] = g.inp("Rigid Previous", "MATRIX")
    g.out("Points", "GEOMETRY")
    g.out("Pressure Residual", "FLOAT", desc="Largest residual of the pressure solve relative to its right-hand side")
    g.out("Pressure Iterations", "INT", desc="Conjugate gradient iterations the pressure solve took")
    pic = liquid.read(g, "pic")
    friction = liquid.read(g, "friction")
    adhesion = liquid.read(g, "adhesion")
    yield_speed = liquid.read(g, "yield") * delta_time
    viscosities = g.statistic(points, liquid.read(g, "kinematic_viscosity"))
    sticks = g.statistic(points, liquid.read(g, "wall_stick"))
    kinematic_viscosity = viscosities["Max"]
    uniform = g.bool_and(g.compare(viscosities["Range"], 0.0, "LESS_EQUAL"), g.compare(sticks["Range"], 0.0, "LESS_EQUAL"))

    def solid(position):
        return g.group(get_asset("Physics.Fluid.SolidDistance"), Position=position, Duration=delta_time, **solids)

    def nearest(grid, position, kind="FLOAT"):
        return sample_grid(g, grid, position, kind, interpolation="Nearest Neighbor")

    half = voxel * 0.5
    inverse_voxel = 1.0 / voxel
    velocity = g.named("velocity", "FLOAT_VECTOR")
    components = g.sep(velocity)
    gravity_components = g.sep(gravity)
    offsets = [g.vmath("SCALE", axis, scale=half) for axis in AXES]
    use_viscosity = g.compare(kinematic_viscosity, 0.0, "GREATER_THAN")
    pass_variance = viscosity_width * (viscosity_width + 1.0) / 3.0
    diffusion_variance = 2.0 * kinematic_viscosity * delta_time / (voxel * voxel)
    passes = diffusion_variance / pass_variance
    total_passes = g.max(g.math("CEIL", passes), 1.0)
    pass_weight = passes / total_passes

    packed = []
    ready = None
    for axis_index in range(3):
        matrix = g.combine_transform(offsets[axis_index], None, g.vec(voxel, voxel, voxel))
        grid = rasterize(g, points, [("wm", g.vec(1.0, components[axis_index], 0.0), True)], matrix=matrix, after=ready)["wm"]
        packed.append(grid)
        ready = grid_ready(g, grid, "VECTOR")
    weight = rasterize(g, points, [("w", 1.0, False)], voxel=voxel, after=ready)["w"]
    mixture = rasterize(g, points, [("wv", liquid.read(g, "kinematic_viscosity"), False), ("ws", liquid.read(g, "wall_stick"), False)],
                        voxel=voxel, after=grid_ready(g, weight))

    def material_at(position):
        total = g.max(sample_grid(g, weight, position), 1e-6)
        return (g.switch(uniform, sample_grid(g, mixture["wv"], position) / total, kinematic_viscosity, "FLOAT"),
                g.switch(uniform, sample_grid(g, mixture["ws"], position) / total, sticks["Max"], "FLOAT"))

    position = g.position()
    solid_here = g.compare(solid(position)["Distance"], SOLID_EPSILON, "LESS_THAN")
    heavy = g.compare(nearest(weight, position), rest_density * fluid_threshold, "GREATER_THAN")
    reach = g.n("GeometryNodeGridDilateAndErode", Grid=weight, Steps=1, props={"data_type": "FLOAT"})
    set_menu(reach.n.inputs["Connectivity"], "Face")
    set_menu(reach.n.inputs["Tiles"], "Preserve")
    kinds = field_to_grids(g, reach.o, [("kind", "FLOAT", g.switch(solid_here, g.switch(heavy, 0.0, 1.0, "FLOAT"), 2.0, "FLOAT"))])["kind"]
    liquid_cells = g.n("GeometryNodeGridDeactivateVoxels", Grid=kinds,
                       Selection=g.compare(g.abs(nearest(kinds, g.position()) - 1.0), 0.5, "GREATER_THAN"),
                       props={"data_type": "FLOAT"})["Grid"]

    def solid_bit(flags):
        return g.switch(g.compare(g.math("FLOORED_MODULO", flags, 2.0), 0.5, "GREATER_THAN"), 0.0, 1.0, "FLOAT")

    faces = []
    for axis_index in range(3):
        position = g.position()
        raw = g.sep(nearest(packed[axis_index], position, "VECTOR"))
        before = nearest(kinds, position - offsets[axis_index])
        after = nearest(kinds, position + offsets[axis_index])
        solid_face = g.compare(g.max(before, after), 1.5, "GREATER_THAN")
        fluid_face = g.compare(g.max(g.math("FLOORED_MODULO", before, 2.0), g.math("FLOORED_MODULO", after, 2.0)), 0.5, "GREATER_THAN")
        face_viscosity, face_stick = material_at(position)
        query = solid(position)
        solid_velocity = g.sep(query["Velocity"])[axis_index]
        wall = g.switch(solid_face, 0.0, face_stick * rest_density, "FLOAT")
        grip = g.switch(solid_face, face_stick * g.clamp01(1.0 - query["Distance"] / voxel), 1.0, "FLOAT")
        share = g.clamp01(face_viscosity / g.max(kinematic_viscosity, 1e-12)) * pass_weight
        flags = g.switch(solid_face, 0.0, 1.0, "FLOAT") + g.switch(fluid_face, 0.0, 2.0, "FLOAT")
        looked = field_to_grids(g, packed[axis_index], [
            ("momentum", "VECTOR", g.vec(raw[0] + wall, raw[1] + wall * solid_velocity, flags)),
            ("solid", "VECTOR", g.vec(solid_velocity, grip, share)),
        ], "VECTOR")
        position = g.position()
        here = nearest(packed[axis_index], position, "VECTOR")
        weight_momentum = g.sep(here)
        noted = g.sep(nearest(looked["momentum"], position, "VECTOR"))
        solid_part = g.sep(nearest(looked["solid"], position, "VECTOR"))
        smooth = grid_mean(g, looked["momentum"], total_passes, width=viscosity_width, dtype="VECTOR")
        mixed = g.switch(use_viscosity, here, g.mix(solid_part[2], here, nearest(smooth, position, "VECTOR"), "VECTOR"), "VECTOR")
        smooth_momentum = g.sep(mixed)
        old = g.switch(g.compare(weight_momentum[0], 1e-6, "GREATER_THAN"), 0.0, weight_momentum[1] / weight_momentum[0], "FLOAT")
        smoothed = g.switch(g.compare(smooth_momentum[0], 1e-6, "GREATER_THAN"), old, smooth_momentum[1] / smooth_momentum[0], "FLOAT")
        forced = smoothed + gravity_components[axis_index] * delta_time
        current = g.mix(solid_part[1], forced, solid_part[0])
        faces.append(field_to_grids(g, packed[axis_index], [("face", "VECTOR", g.vec(current, old, noted[2]))], "VECTOR")["face"])

    position = g.position()
    divergence = None
    walled = None
    for axis_index in range(3):
        plus = g.sep(nearest(faces[axis_index], position + offsets[axis_index], "VECTOR"))
        minus = g.sep(nearest(faces[axis_index], position - offsets[axis_index], "VECTOR"))
        difference = plus[0] - minus[0]
        divergence = difference if divergence is None else divergence + difference
        sides = solid_bit(plus[2]) + solid_bit(minus[2])
        walled = sides if walled is None else walled + sides
    divergence = divergence * inverse_voxel
    crowding = g.max(nearest(weight, position) / rest_density - 1.0, 0.0)
    correction = crowding * (1.0 - g.math("EXPONENT", delta_time / density_relaxation * -1.0)) / delta_time
    solved_pressure, pressure_residual, pressure_used = pressure(g, liquid_cells, (divergence - correction) / delta_time, walled, voxel,
                                                                 pressure_iterations, pressure_tolerance, minimum_island)

    projected = []
    for axis_index in range(3):
        position = g.position()
        face = g.sep(nearest(faces[axis_index], position, "VECTOR"))
        gradient = (nearest(solved_pressure, position + offsets[axis_index]) - nearest(solved_pressure, position - offsets[axis_index])) * inverse_voxel
        solid_face = g.compare(solid_bit(face[2]), 0.5, "GREATER_THAN")
        updated = g.switch(solid_face, face[0] - gradient * delta_time, face[0], "FLOAT")
        valid = g.switch(g.compare(face[2], 0.5, "GREATER_THAN"), 0.0, 1.0, "FLOAT")
        projected.append(field_to_grids(g, faces[axis_index], [("projected", "VECTOR", g.vec(updated * valid, face[1] * valid, valid))], "VECTOR")["projected"])

    def masked(position):
        new_values = []
        old_values = []
        coverage = None
        for axis_index in range(3):
            new_share, old_share, weight_share = g.sep(sample_grid(g, projected[axis_index], position, "VECTOR"))
            safe = g.max(weight_share, 1e-4)
            covered = g.compare(weight_share, 1e-4, "GREATER_THAN")
            new_values.append(g.switch(covered, 0.0, new_share / safe, "FLOAT"))
            old_values.append(g.switch(covered, 0.0, old_share / safe, "FLOAT"))
            coverage = weight_share if coverage is None else g.min(coverage, weight_share)
        return g.vec(*new_values), g.vec(*old_values), coverage

    new_velocity, old_velocity, coverage = masked(g.position())
    sampled_points, sampled = g.capture(points, new=new_velocity, old=old_velocity, coverage=coverage)
    current_velocity = g.named("velocity", "FLOAT_VECTOR")
    flip_velocity = current_velocity + (sampled["new"] - sampled["old"])
    blended = g.mix(pic, flip_velocity, sampled["new"], "VECTOR")
    grid_covered = g.compare(sampled["coverage"], 1e-3, "GREATER_THAN")
    ballistic = current_velocity + gravity * delta_time
    chosen = g.switch(grid_covered, ballistic, blended, "VECTOR")
    position = g.position()
    midpoint = position + sampled["new"] * (delta_time * 0.5)
    middle_velocity, _, middle_coverage = masked(midpoint)
    middle = g.switch(g.compare(middle_coverage, 1e-3, "GREATER_THAN"), chosen, middle_velocity, "VECTOR")
    grid_advected = position + middle * delta_time
    advected = g.switch(grid_covered, position + ballistic * delta_time, grid_advected, "VECTOR")
    moved, targets = g.capture(sampled_points, velocity=chosen, target=advected)
    moved = g.store(moved, "velocity", targets["velocity"], "FLOAT_VECTOR")
    moved = g.set_pos(moved, pos=targets["target"])

    query = solid(g.position())
    moved, contact_values = g.capture(moved, distance=query["Distance"], normal=query["Normal"], velocity=query["Velocity"])
    position = g.position()
    distance = contact_values["distance"]
    normal = contact_values["normal"]
    solid_velocity = contact_values["velocity"]
    penetration = g.max(radius - distance, 0.0)
    pushed = position + normal * penetration
    relative = g.named("velocity", "FLOAT_VECTOR") - solid_velocity
    normal_speed = relative.dot(normal)
    contact = g.compare(distance, radius + voxel * 0.25, "LESS_THAN")
    inward = g.bool_and(contact, g.compare(normal_speed, 0.0, "LESS_THAN"))
    without_normal = g.switch(inward, relative, relative - normal * normal_speed, "VECTOR")
    tangential = without_normal - normal * without_normal.dot(normal)
    keep = g.math("EXPONENT", friction * delta_time * -1.0)
    rubbed = g.switch(contact, without_normal, without_normal - tangential * (1.0 - keep), "VECTOR")
    resting = g.compare(distance, radius + voxel, "LESS_THAN")
    rubbed_speed = rubbed.length()
    yield_factor = g.max(rubbed_speed - yield_speed, 0.0) / g.max(rubbed_speed, 1e-9)
    rubbed = g.switch(resting, rubbed, rubbed * yield_factor, "VECTOR")
    near = g.bool_and(g.compare(distance, radius + adhesion_range, "LESS_THAN"), g.compare(distance, radius * 0.5, "GREATER_THAN"))
    pulled = g.switch(near, rubbed, rubbed - normal * (adhesion * delta_time), "VECTOR")
    collided = g.store(moved, "velocity", pulled + solid_velocity, "FLOAT_VECTOR")
    collided = g.store(collided, SOLID_DISTANCE, distance)
    g.result(g.set_pos(collided, pos=pushed), pressure_residual, pressure_used)
    return g


@asset("Physics.Fluid.Step", "Physics")
def step():
    """One frame of FLIP with CFL-adaptive substeps; the rigid body's
    transform is interpolated between substeps (location linear, rotation
    spherical).  Liquid materials are per-particle attributes
    (Core.physics.liquid).  The particles come out with ``fluid:solid_distance``
    (distance to the nearest solid before the last substep's push-out)."""
    g = GN("Physics.Fluid.Step", step.__doc__)
    points = g.inp("Points", "GEOMETRY", desc="Particles: velocity plus every liquid material attribute")
    delta_time = g.inp("Frame Time", default=1.0 / 24.0)
    voxel = g.inp("Voxel", default=0.01, min=0.0005)
    cfl = g.inp("CFL", default=1.0, min=0.05, desc="Cells a particle may cross per substep")
    minimum_substeps = g.inp("Min Substeps", "INT", default=2, min=1)
    maximum_substeps = g.inp("Max Substeps", "INT", default=24, min=1)
    passthrough = {}
    for name, stype, default in (("Gravity", "VECTOR", GRAVITY), ("Rest Density", "FLOAT", 8.0), ("Density Relaxation", "FLOAT", 0.0234),
                                 ("Fluid Threshold", "FLOAT", 0.3), ("Particle Radius", "FLOAT", 0.003), ("Adhesion Range", "FLOAT", 0.004),
                                 ("Viscosity Width", "INT", 2), ("Pressure Iterations", "INT", 100), ("Pressure Tolerance", "FLOAT", 1e-3),
                                 ("Min Island", "INT", 27), *SOLID_INPUTS):
        passthrough[name] = g.inp(name, stype, default=default)
    rigid_transform = g.inp("Rigid Transform", "MATRIX")
    rigid_previous = g.inp("Rigid Previous", "MATRIX")
    g.out("Points", "GEOMETRY")
    g.out("Substeps", "INT")
    g.out("Pressure Residual", "FLOAT", desc="Largest over the substeps")
    g.out("Pressure Iterations", "INT", desc="Most conjugate gradient iterations of a substep's pressure solve")
    speed = g.statistic(points, g.named("velocity", "FLOAT_VECTOR").length())["Max"]
    travel = speed * delta_time / (voxel * cfl)
    count = g.min(g.max(g.math("CEIL", travel), minimum_substeps), maximum_substeps)
    active = g.switch(g.compare(delta_time, 0.0, "GREATER_THAN"), 0, g.to_int(count, "ROUND"), "INT")
    sub_time = delta_time / count
    zone = g.repeat(active, [("Points", "GEOMETRY", points), ("Residual", "FLOAT", 0.0), ("Iterations", "INT", 0)])
    begin = zone.iteration / count
    end = (zone.iteration + 1.0) / count
    stepped = g.group(get_asset("Physics.Fluid.Substep"), Points=zone.state("Points"), Voxel=voxel, **{
        "Substep Time": sub_time, "Rigid Transform": interpolate_transform(g, rigid_previous, rigid_transform, end),
        "Rigid Previous": interpolate_transform(g, rigid_previous, rigid_transform, begin), **passthrough})
    zone.set("Points", stepped["Points"])
    zone.set("Residual", g.max(zone.state("Residual"), stepped["Pressure Residual"]))
    zone.set("Iterations", g.max(zone.state("Iterations"), stepped["Pressure Iterations"]))
    g.result(zone.result("Points"), active, zone.result("Residual"), zone.result("Iterations"))
    return g


FLIGHT_SAMPLES = 8


@asset("Physics.Fluid.Flight", "Physics")
def flight():
    """Airborne particles fly the exact parabola x = x0 + v0 t + g t^2 / 2 for
    ``fluid:flight_time`` (free-falling liquid carries no pressure, so the parabola is
    the exact solution).  The path is checked at 8 points; at the first one
    that hits a solid (pushed out to the particle radius, inward relative
    normal velocity removed) or lands in liquid (the pool's particle count in
    that cell above a threshold) the particle stops and ``airborne`` turns
    false, handing it back to the grid."""
    g = GN("Physics.Fluid.Flight", flight.__doc__)
    points = g.inp("Points", "GEOMETRY", desc="Particles to fly: velocity, fluid:flight_time (how long they still fly this frame)")
    pool = g.inp("Pool", "GEOMETRY", desc="Liquid particles on the grid; landing in them ends a flight")
    delta_time = g.inp("Frame Time", default=1.0 / 24.0)
    voxel = g.inp("Voxel", default=0.004, min=0.0005)
    radius = g.inp("Particle Radius", default=0.002, min=0.0)
    landing = g.inp("Landing Count", default=2.4, min=0.0, desc="Pool particles in a cell above which a flight lands")
    gravity = g.inp("Gravity", "VECTOR", default=GRAVITY)
    solids = solid_inputs(g)
    rigid_transform = g.inp("Rigid Transform", "MATRIX")
    rigid_previous = g.inp("Rigid Previous", "MATRIX")
    g.out("Points", "GEOMETRY")
    safe_time = g.max(delta_time, 1e-6)
    pool_weight = rasterize(g, pool, [("w", 1.0, False)], voxel=voxel)["w"]
    flight_time = g.named(FLIGHT_TIME)
    origin = g.position()
    launch = g.named("velocity", "FLOAT_VECTOR")
    start_fraction = 1.0 - flight_time / safe_time
    sample_duration = g.max(flight_time / FLIGHT_SAMPLES, 1e-6)

    def ballistic(elapsed):
        return origin + launch * elapsed + gravity * (0.5 * (elapsed * elapsed)), launch + gravity * elapsed

    final_position, final_velocity = ballistic(flight_time)
    landed = None
    for sample in range(FLIGHT_SAMPLES, 0, -1):
        elapsed = flight_time * (sample / FLIGHT_SAMPLES)
        position, velocity = ballistic(elapsed)
        fraction = start_fraction + elapsed / safe_time
        earlier = g.max(fraction - sample_duration / safe_time, 0.0)
        query = g.group(get_asset("Physics.Fluid.SolidDistance"), Position=position, Duration=sample_duration, **solids, **{
            "Rigid Transform": interpolate_transform(g, rigid_previous, rigid_transform, fraction),
            "Rigid Previous": interpolate_transform(g, rigid_previous, rigid_transform, earlier)})
        hit_solid = g.compare(query["Distance"], radius, "LESS_THAN")
        hit_pool = g.compare(sample_grid(g, pool_weight, position), landing, "GREATER_THAN")
        hit = g.bool_or(hit_solid, hit_pool)
        relative = velocity - query["Velocity"]
        inward = g.min(relative.dot(query["Normal"]), 0.0)
        solid_velocity_after = query["Velocity"] + relative - query["Normal"] * inward
        pushed = position + query["Normal"] * g.max(radius - query["Distance"], 0.0)
        final_position = g.switch(hit, final_position, g.switch(hit_solid, position, pushed, "VECTOR"), "VECTOR")
        final_velocity = g.switch(hit, final_velocity, g.switch(hit_solid, velocity, solid_velocity_after, "VECTOR"), "VECTOR")
        landed = hit if landed is None else g.bool_or(landed, hit)
    flown, values = g.capture(points, position=final_position, velocity=final_velocity, landed=landed)
    flown = g.set_pos(flown, pos=values["position"])
    flown = g.store(flown, "velocity", values["velocity"], "FLOAT_VECTOR")
    g.result(g.store(flown, "airborne", g.bool_not(values["landed"]), "BOOLEAN"))
    return g


@asset("Physics.Fluid.Surface", "Physics")
def surface():
    """Particles -> smooth surface: union of spheres as a distance field ->
    smoothing -> inward offset (undoing the union's swelling) -> iso-surface.
    Vertices carry the nearest particle's ``velocity`` for motion blur.  The
    nearest-particle search runs on a throw-away mesh made from the points: on
    the simulation's own point cloud its search structure would stay with
    every cached frame.  ``Nearest Particle`` is a field evaluated on the
    caller's geometry (point order of the input), for reading other particle
    attributes."""
    g = GN("Physics.Fluid.Surface", surface.__doc__)
    points = g.inp("Points", "GEOMETRY")
    voxel = g.inp("Voxel", default=0.004, min=0.0003)
    radius = g.inp("Sphere Radius", default=0.008, min=0.0001)
    smoothing = g.inp("Smoothing", default=0.004, min=0.0, desc="m; standard deviation of the smoothing, converted into box-mean passes (each adds 2/3 voxel^2 of variance), so view and render voxels smooth by the same distance")
    erosion = g.inp("Erosion", default=0.003, min=0.0, desc="Inward offset after smoothing, undoing the swelling of the sphere union")
    adaptivity = g.inp("Adaptivity", default=0.0, min=0.0, max=1.0)
    g.out("Mesh", "GEOMETRY")
    g.out("Nearest Particle", "INT")
    with_radius = g.n("GeometryNodeSetPointRadius", Points=points, Radius=radius).o
    sdf = g.n("GeometryNodePointsToSDFGrid", Points=with_radius, Radius=radius, Voxel_Size=voxel)["SDF Grid"]
    passes = g.to_int(1.5 * (smoothing * smoothing) / (voxel * voxel), "ROUND")
    smooth = g.n("GeometryNodeSDFGridMean", Grid=sdf, Width=1, Iterations=passes)["Grid"]
    shrunk = g.n("GeometryNodeSDFGridOffset", Grid=smooth, Distance=erosion * -1.0)["Grid"]
    mesh = g.n("GeometryNodeGridToMesh", Grid=shrunk, Threshold=0.0, Adaptivity=adaptivity)["Mesh"]
    lookup = g.n("GeometryNodePointsToVertices", Points=points).o
    nearest = g.sample_nearest(lookup, g.position())
    velocity = g.sample_index(lookup, g.named("velocity", "FLOAT_VECTOR"), nearest, "FLOAT_VECTOR")
    g.result(g.smooth(g.store(mesh, "velocity", velocity, "FLOAT_VECTOR")), nearest)
    return g


@asset("Physics.Fluid.CollectionMesh", "Physics")
def collection_mesh():
    """The objects of a collection, and a resting mesh, as one world-space
    mesh with ``velocity`` on its points, for ``Physics.Fluid.DeformingSolid``.
    Each object's world transform is kept as a point (``placement``); with
    last frame's placements every vertex gets the velocity
    (M_now l - M_before l) / dt of its local position l = M_now^-1 x, so
    objects moved during playback push the liquid and an object that did
    not move has exactly zero velocity.  Only the placements belong in the
    simulation state -- the meshes of every frame would fill its cache."""
    g = GN("Physics.Fluid.CollectionMesh", collection_mesh.__doc__)
    collection = g.inp("Collection", "COLLECTION")
    previous = g.inp("Previous Placements", "GEOMETRY", desc="Placements output of the previous frame")
    resting = g.inp("Resting", "GEOMETRY", desc="World-space mesh that never moves (velocity zero)")
    delta_time = g.inp("Frame Time", default=1.0 / 24.0)
    g.out("Mesh", "GEOMETRY")
    g.out("Placements", "GEOMETRY")
    instances = g.collection_info(collection)
    instances = g.store(instances, "solid_part", g.index(), "INT", "INSTANCE")
    instances = g.store(instances, "placement", g.n("GeometryNodeInstanceTransform").o, "FLOAT4X4", "INSTANCE")
    placements = g.remove_attribute(g.n("GeometryNodeInstancesToPoints", Instances=instances).o, "solid_part")
    mesh = g.remove_attribute(g.realize(instances), "placement")
    part = g.named("solid_part", "INT")
    now = g.sample_index(placements, g.named("placement", "FLOAT4X4"), part, "FLOAT4X4")
    before = g.sample_index(previous, g.named("placement", "FLOAT4X4"), part, "FLOAT4X4")
    same_parts = g.compare(g.domain_size(placements, "POINTCLOUD")["Point Count"],
                           g.domain_size(previous, "POINTCLOUD")["Point Count"], "EQUAL", "INT")
    local = g.transform_point(g.position(), g.invert(now))
    travel = g.transform_point(local, now) - g.transform_point(local, before)
    velocity = g.switch(same_parts, (0.0, 0.0, 0.0), travel * (1.0 / g.max(delta_time, 1e-6)), "VECTOR")
    moving = g.store(mesh, "velocity", velocity, "FLOAT_VECTOR")
    still = g.store(resting, "velocity", (0.0, 0.0, 0.0), "FLOAT_VECTOR")
    g.result(g.join(moving, still), placements)
    return g


@asset("Physics.Fluid.Frame", "Physics")
def frame():
    """One frame of liquid that also flies.  Particles on the grid take a FLIP
    step (``Physics.Fluid.Step``); those whose acceleration over the frame was
    gravity alone, two cells or more from any solid, turn ``airborne``.
    Airborne particles and newly emitted ones fly exact parabolas
    (``Physics.Fluid.Flight``) until they hit a solid or land in the liquid on
    the grid.  Free-falling liquid carries no pressure, so the parabola is the
    exact solution, and the grid's substeps are set only by liquid that has
    landed.  The liquid material (stored by the caller on the particles on
    the grid) is removed again."""
    g = GN("Physics.Fluid.Frame", frame.__doc__)
    points = g.inp("Points", "GEOMETRY", desc="Particles: velocity, airborne; those on the grid carry the liquid material (Core.physics.liquid)")
    spawned = g.inp("Spawned", "GEOMETRY", desc="Particles entering airborne this frame: velocity, fluid:flight_time (how long they fly this frame)")
    delta_time = g.inp("Frame Time", default=1.0 / 24.0)
    voxel = g.inp("Voxel", default=0.004, min=0.0005)
    cfl = g.inp("CFL", default=3.0, min=0.05, desc="Cells a particle on the grid may cross per substep")
    maximum_substeps = g.inp("Max Substeps", "INT", default=16, min=1, desc="Safety limit; the CFL condition sets the count.  A limit below what the CFL asks for lets particles cross several cells per substep, pass through thin walls and run away")
    rest_density = g.inp("Rest Density", default=8.0, min=0.01, desc="Particles per cell")
    density_relaxation = g.inp("Density Relaxation", default=0.0234, min=1e-4, desc="s; time constant of pushing over-dense regions back to the rest density")
    fluid_threshold = g.inp("Fluid Threshold", default=0.3, min=0.0, max=1.0)
    landing_share = g.inp("Landing Share", default=0.3, min=0.0, desc="A flight lands in a cell holding more than rest density x this")
    gravity = g.inp("Gravity", "VECTOR", default=GRAVITY)
    solids = solid_inputs(g)
    solids["Rigid Transform"] = g.inp("Rigid Transform", "MATRIX")
    solids["Rigid Previous"] = g.inp("Rigid Previous", "MATRIX")
    g.out("Points", "GEOMETRY")
    g.out("Substeps", "INT")
    g.out("Pressure Residual", "FLOAT", desc="Largest residual of the pressure solves relative to their right-hand sides")
    g.out("Pressure Iterations", "INT", desc="Most conjugate gradient iterations of a pressure solve")
    radius = voxel * 0.5
    velocity = g.named("velocity", "FLOAT_VECTOR")
    airborne = g.named("airborne", "BOOLEAN")
    bound = g.store(g.delete(points, airborne), VELOCITY_START, velocity, "FLOAT_VECTOR")
    solved = g.group(get_asset("Physics.Fluid.Step"), Points=bound, Voxel=voxel, CFL=cfl, Gravity=gravity, **solids, **{
        "Frame Time": delta_time, "Min Substeps": 1, "Max Substeps": maximum_substeps, "Rest Density": rest_density,
        "Density Relaxation": density_relaxation, "Fluid Threshold": fluid_threshold, "Particle Radius": radius, "Adhesion Range": voxel})
    has_bound = g.compare(g.domain_size(bound, "POINTCLOUD")["Point Count"], 0, "GREATER_THAN", "INT")
    stepped = g.switch(has_bound, bound, solved["Points"])
    substeps = g.switch(has_bound, 0, solved["Substeps"], "INT")
    acceleration = (velocity - g.named(VELOCITY_START, "FLOAT_VECTOR")) * (1.0 / g.max(delta_time, 1e-6))
    falling = g.compare(g.vmath("DISTANCE", acceleration, gravity), gravity.length() * 0.25, "LESS_THAN")
    clear = g.compare(g.named(SOLID_DISTANCE), voxel * 2.0, "GREATER_THAN")
    stepped = g.store(stepped, "airborne", g.bool_and(falling, clear), "BOOLEAN")
    flying = g.store(g.delete(points, g.bool_not(airborne)), FLIGHT_TIME, delta_time)
    flown = g.group(get_asset("Physics.Fluid.Flight"), Points=g.join(flying, spawned), Pool=g.delete(stepped, airborne), Voxel=voxel,
                    Gravity=gravity, **solids, **{"Frame Time": delta_time, "Particle Radius": radius,
                                                  "Landing Count": rest_density * landing_share})["Points"]
    g.result(forget(g, g.join(stepped, flown)), substeps, g.switch(has_bound, 0.0, solved["Pressure Residual"], "FLOAT"),
             g.switch(has_bound, 0, solved["Pressure Iterations"], "INT"))
    return g


@asset("Physics.Fluid.Drain", "Physics")
def drain():
    """Particles that leave the simulation: inside the drain (an upright
    cylinder standing on the drain object's origin, radius its X scale,
    height its Z scale), more than ``Depth`` below the ground, or farther than
    ``Reach`` from the world origin."""
    g = GN("Physics.Fluid.Drain", drain.__doc__)
    points = g.inp("Points", "GEOMETRY")
    target = g.inp("Drain", "OBJECT")
    ground = g.inp("Ground Height", default=0.0)
    depth = g.inp("Depth", default=0.05, min=0.0)
    reach = g.inp("Reach", default=3.0, min=0.0)
    g.out("Points", "GEOMETRY")
    info = g.object_info(target)
    center = info["Location"]
    size = info["Scale"]
    position = g.position()
    horizontal = g.vec(position.x - center.x, position.y - center.y, 0.0).length()
    inside = g.bool_and(g.compare(horizontal, size.x, "LESS_THAN"), g.compare(position.z, center.z + size.z, "LESS_THAN"))
    lost = g.bool_or(g.compare(position.z, ground - depth, "LESS_THAN"), g.compare(position.length(), reach, "GREATER_THAN"))
    g.result(g.delete(points, g.bool_or(inside, lost)))
    return g
