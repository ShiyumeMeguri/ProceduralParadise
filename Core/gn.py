"""
Core.gn -- Geometry-Nodes flavoured builder on top of :mod:`Core.nodes`.

``GN("Kit.Desk")`` returns a tree builder whose methods wrap the geometry node
types used throughout the kits.  Every method returns a :class:`Sock` so calls
compose naturally::

    g = GN("Demo")
    w = g.inp("Width", default=1.0, subtype="DISTANCE")
    top = g.move(g.cube(g.vec(w, 0.6, 0.03)), z=0.735)
    g.result(g.mat(top, some_material))

A registry (:func:`asset`) memoises group construction so shared sub-assets
are built exactly once per Blender session.
"""
from __future__ import annotations

import math

import bpy

from .nodes import Tree, Sock, Node, _is_num

__all__ = ["GN", "Zone", "SimulationZone", "remembered_items", "asset", "get_asset", "ASSETS", "set_mode"]


def _norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def set_menu(sock, value):
    """Assign an enum/menu socket by identifier *or* display name, tolerant of
    spelling differences between Blender versions ('NGONS' == 'N-gons')."""
    import re
    try:
        sock.default_value = value
        return
    except TypeError as e:
        msg = str(e)
    cands = re.findall(r"'([^']+)'", msg.split("not found in")[-1])
    for c in cands:
        if _norm(c) == _norm(value):
            sock.default_value = c
            return
    raise TypeError(f"menu value {value!r} not in {cands}")


def set_mode(node: Node, value, prop_names=("mode",), input_names=("Mode",)):
    """Set a node 'mode' that is a property in some versions and a menu input
    socket in others."""
    n = node.n
    for p in prop_names:
        if hasattr(n, p):
            try:
                setattr(n, p, value)
                return
            except (TypeError, AttributeError):
                pass
    for s in n.inputs:
        if s.name in input_names and hasattr(s, "default_value"):
            set_menu(s, value)
            return


def _capture_type(value):
    if isinstance(value, Node):
        value = value.o
    if isinstance(value, Sock):
        return {"VALUE": "FLOAT", "INT": "INT", "BOOLEAN": "BOOLEAN", "VECTOR": "VECTOR", "RGBA": "RGBA",
                "ROTATION": "ROTATION", "MATRIX": "MATRIX"}[value.type]
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INT"
    if isinstance(value, (tuple, list)):
        return "VECTOR"
    return "FLOAT"


class Zone:
    """A pair of zone nodes (repeat or simulation) with named state items:
    ``state(name)`` inside the zone, ``set(name, value)`` at its end,
    ``result(name)`` after it."""

    def __init__(self, graph, input_node, output_node, names, state_offset, set_offset, initial_offset):
        self.g = graph
        self.input_node = input_node
        self.output_node = output_node
        self.names = list(names)
        self._state_offset = state_offset
        self._set_offset = set_offset
        self._initial_offset = initial_offset

    def _index(self, name):
        return self.names.index(name)

    def initial(self, name, value):
        self.g.assign(self.input_node.inputs[self._initial_offset + self._index(name)], value)

    def state(self, name):
        return Sock(self.g, self.input_node.outputs[self._state_offset + self._index(name)])

    def set(self, name, value):
        self.g.assign(self.output_node.inputs[self._set_offset + self._index(name)], value)

    def result(self, name):
        return Sock(self.g, self.output_node.outputs[self._index(name)])


class SimulationZone(Zone):
    """Simulation zone.  The cache keeps every frame's state geometry, so every
    geometry that enters, leaves or is read back from it passes through
    :meth:`GN.detach`; derived data built downstream is then never attached to a
    cached frame.  ``delta_time`` is the zone's time step in seconds."""

    def __init__(self, graph, input_node, output_node, names, kinds):
        super().__init__(graph, input_node, output_node, names, state_offset=1, set_offset=1, initial_offset=0)
        self.kinds = dict(zip(names, kinds))
        self.delta_time = Sock(graph, input_node.outputs[0])
        self._states = {}
        self._results = {}

    def state(self, name):
        if self.kinds[name] != "GEOMETRY":
            return super().state(name)
        if name not in self._states:
            self._states[name] = self.g.detach(super().state(name))
        return self._states[name]

    def set(self, name, value):
        super().set(name, self.g.detach(value) if self.kinds[name] == "GEOMETRY" else value)

    def result(self, name):
        if self.kinds[name] != "GEOMETRY":
            return super().result(name)
        if name not in self._results:
            self._results[name] = self.g.detach(super().result(name))
        return self._results[name]

    def remember(self, name, keys, build):
        """The values of ``build()`` (a dict: item -> value), built only on a
        frame whose ``keys`` (vectors) differ from the ones they were last
        built for and otherwise carried on from the previous frame -- a switch
        on a single value evaluates only the branch it takes, so nothing of
        ``build`` runs on the other frames.  The zone needs the state items
        of :func:`remembered_items`."""
        fresh = self.g.bool_not(self.state(f"{name} Built"))
        for index, key in enumerate(keys):
            fresh = self.g.bool_or(fresh, self.g.compare(self.g.vmath("DISTANCE", key, self.state(f"{name} Key {index}")), 0.0, "GREATER_THAN"))
        values = {}
        for item, value in build().items():
            state_name = f"{name} {item}"
            values[item] = self.g.switch(fresh, self.state(state_name), value, self.kinds[state_name])
            self.set(state_name, values[item])
        for index, key in enumerate(keys):
            self.set(f"{name} Key {index}", key)
        self.set(f"{name} Built", True)
        return values


def remembered_items(name, key_count, items):
    """Simulation state items for :meth:`SimulationZone.remember`: ``key_count``
    key vectors and ``items`` [(item, socket type), ...]."""
    return [(f"{name} Built", "BOOLEAN"), *[(f"{name} Key {index}", "VECTOR") for index in range(key_count)],
            *[(f"{name} {item}", kind) for item, kind in items]]


class GN(Tree):
    def __init__(self, name, description="", clear=True, modifier=False):
        super().__init__(name, "GeometryNodeTree", clear=clear, description=description)
        self.ng.is_modifier = modifier

    # -------------------------------------------------------------- inputs
    def position(self): return self.n("GeometryNodeInputPosition").o
    def index(self): return self.n("GeometryNodeInputIndex").o
    def normal(self): return self.n("GeometryNodeInputNormal").o
    def id(self): return self.n("GeometryNodeInputID").o

    def random(self, lo=0.0, hi=1.0, seed=0, ID=None, dtype="FLOAT"):
        return self.n("FunctionNodeRandomValue", props={"data_type": dtype},
                      Min=lo, Max=hi, ID=ID, Seed=seed).o

    def compare(self, a, b, op="LESS_THAN", dtype="FLOAT"):
        return self.n("FunctionNodeCompare", a, b,
                      props={"data_type": dtype, "operation": op}).o

    def switch(self, cond, false, true, input_type="GEOMETRY"):
        return self.n("GeometryNodeSwitch", props={"input_type": input_type},
                      Switch=cond, **{"False": false, "True": true}).o

    def index_switch(self, index, values, dtype="VECTOR"):
        """Pick ``values[index]`` (IndexSwitch node, Blender 4.1+)."""
        node = self.ng.nodes.new("GeometryNodeIndexSwitch")
        node.data_type = dtype
        items = node.index_switch_items
        while len(items) < len(values):
            items.new()
        ins = [s for s in node.inputs if s.name != "Index" and s.identifier != "Index"]
        self.assign(node.inputs["Index"], index)
        for s, v in zip(ins, values):
            if isinstance(v, (tuple, list)):
                v = self.vec(v)
            self.assign(s, v)
        return Node(self, node).o

    def bool_and(self, a, b):
        return self.n("FunctionNodeBooleanMath", a, b, props={"operation": "AND"}).o

    def bool_or(self, a, b):
        return self.n("FunctionNodeBooleanMath", a, b, props={"operation": "OR"}).o

    def bool_not(self, a):
        return self.n("FunctionNodeBooleanMath", a, props={"operation": "NOT"}).o

    def named(self, name, dtype="FLOAT"):
        """Field of the named attribute ``name``."""
        return self.n("GeometryNodeInputNamedAttribute", Name=name, props={"data_type": dtype})["Attribute"]

    def scene_time(self):
        """Scene time in seconds (makes the tree re-evaluate every frame)."""
        return self.n("GeometryNodeInputSceneTime")["Seconds"]

    def scene_frame(self):
        return self.n("GeometryNodeInputSceneTime")["Frame"]

    def to_int(self, value, rounding="FLOOR"):
        return self.n("FunctionNodeFloatToInt", value, props={"rounding_mode": rounding}).o

    def menu_switch(self, menu, names, dtype="INT"):
        """Index (0, 1, ...) of the item of ``names`` chosen by ``menu``."""
        node = self.ng.nodes.new("GeometryNodeMenuSwitch")
        node.data_type = dtype
        items = node.enum_items
        while len(items) < len(names):
            items.new("")
        for index, name in enumerate(names):
            items[index].name = name
        self.assign(node.inputs[0], menu)
        for index in range(len(names)):
            node.inputs[index + 1].default_value = index
        return Node(self, node).o

    # -------------------------------------------------------------- fields
    def capture(self, geo, domain="POINT", **items):
        """Capture the fields ``items`` on ``geo``: (geometry, {name: field})."""
        node = self.ng.nodes.new("GeometryNodeCaptureAttribute")
        node.domain = domain
        node.capture_items.clear()
        for name, value in items.items():
            node.capture_items.new(_capture_type(value), name)
        self.assign(node.inputs[0], geo)
        captured = Node(self, node)
        for name, value in items.items():
            self.assign(self._in_socket(node, name), value)
        return captured[0], {name: captured[name] for name in items}

    def statistic(self, geo, value, dtype="FLOAT", domain="POINT", sel=None):
        return self.n("GeometryNodeAttributeStatistic", Geometry=geo, Selection=sel, Attribute=value,
                      props={"data_type": dtype, "domain": domain})

    def accumulate(self, value, group=None, dtype="FLOAT", domain="POINT"):
        return self.n("GeometryNodeAccumulateField", Value=value, Group_ID=group,
                      props={"data_type": dtype, "domain": domain})

    def field_max(self, value, group=None, dtype="FLOAT", domain="POINT"):
        return self.n("GeometryNodeFieldMinAndMax", Value=value, Group_ID=group,
                      props={"data_type": dtype, "domain": domain})["Max"]

    def on_domain(self, value, domain, dtype="FLOAT"):
        return self.n("GeometryNodeFieldOnDomain", value, props={"data_type": dtype, "domain": domain}).o

    def sample_index(self, geo, value, index, dtype="FLOAT", domain="POINT", clamp=False):
        return self.n("GeometryNodeSampleIndex", Geometry=geo, Value=value, Index=index,
                      props={"data_type": dtype, "domain": domain, "clamp": clamp})["Value"]

    def sample_nearest(self, geo, position=None, domain="POINT"):
        return self.n("GeometryNodeSampleNearest", Geometry=geo, Sample_Position=position,
                      props={"domain": domain})["Index"]

    def sample_nearest_surface(self, mesh, value, position=None, dtype="FLOAT"):
        return self.n("GeometryNodeSampleNearestSurface", Mesh=mesh, Value=value, Sample_Position=position,
                      props={"data_type": dtype})["Value"]

    def raycast(self, target, source, direction, length):
        return self.n("GeometryNodeRaycast", Target_Geometry=target, Source_Position=source,
                      Ray_Direction=direction, Ray_Length=length)

    def face_vertex(self, sort_index):
        """Field on the face domain: index of the face's ``sort_index``-th vertex."""
        corner = self.n("GeometryNodeCornersOfFace", Face_Index=self.index(), Sort_Index=sort_index)["Corner Index"]
        return self.n("GeometryNodeVertexOfCorner", Corner_Index=corner)["Vertex Index"]

    def domain_size(self, geo, component="MESH"):
        return self.n("GeometryNodeAttributeDomainSize", Geometry=geo, props={"component": component})

    def remove_attribute(self, geo, name, wildcard=False):
        node = self.n("GeometryNodeRemoveAttribute", Geometry=geo, Name=name)
        if wildcard:
            set_mode(node, "Wildcard", prop_names=(), input_names=("Pattern Mode",))
        return node.o

    # ------------------------------------------------------------- objects
    def object_info(self, obj, relative=False, as_instance=False):
        return self.n("GeometryNodeObjectInfo", Object=obj, As_Instance=as_instance,
                      props={"transform_space": "RELATIVE" if relative else "ORIGINAL"})

    def collection_info(self, collection, separate=True, reset=False):
        """Instances of ``collection``'s objects, in world space."""
        return self.n("GeometryNodeCollectionInfo", Collection=collection, Separate_Children=separate,
                      Reset_Children=reset, props={"transform_space": "ORIGINAL"})["Instances"]

    def self_object(self):
        return self.n("GeometryNodeSelfObject").o

    def bound_box(self, geo):
        return self.n("GeometryNodeBoundBox", Geometry=geo)

    # ------------------------------------------------------------ matrices
    def transform_point(self, vector, matrix):
        return self.n("FunctionNodeTransformPoint", vector, matrix).o

    def transform_direction(self, vector, matrix):
        return self.n("FunctionNodeTransformDirection", vector, matrix).o

    def invert(self, matrix):
        return self.n("FunctionNodeInvertMatrix", matrix)["Matrix"]

    def matmul(self, first, second):
        return self.n("FunctionNodeMatrixMultiply", first, second).o

    def combine_transform(self, t=None, r=None, s=None):
        return self.n("FunctionNodeCombineTransform", Translation=t, Rotation=r, Scale=s).o

    def separate_transform(self, matrix):
        return self.n("FunctionNodeSeparateTransform", matrix)

    def transform_by(self, geo, matrix):
        """``geo`` transformed by the 4x4 ``matrix``."""
        node = self.n("GeometryNodeTransform", Geometry=geo)
        set_mode(node, "Matrix", prop_names=(), input_names=("Mode",))
        self.assign(self._in_socket(node.n, "Transform"), matrix)
        return node.o

    # ------------------------------------------------------------- bundles
    def bundle(self, items):
        """Combine Bundle from ``items`` [(name, socket type, value), ...]."""
        node = self.ng.nodes.new("NodeCombineBundle")
        node.bundle_items.clear()
        for name, stype, _value in items:
            node.bundle_items.new(stype, name)
        for name, _stype, value in items:
            self.assign(self._in_socket(node, name), value)
        return Node(self, node).o

    def bundle_item(self, bundle, path, stype):
        return self.n("NodeGetBundleItem", Bundle=bundle, Path=path, props={"socket_type": stype})["Item"]

    # --------------------------------------------------------------- zones
    def simulation(self, items):
        """Simulation zone with state ``items`` [(name, socket type), ...]."""
        input_node = self.ng.nodes.new("GeometryNodeSimulationInput")
        output_node = self.ng.nodes.new("GeometryNodeSimulationOutput")
        input_node.pair_with_output(output_node)
        output_node.state_items.clear()
        for name, stype in items:
            output_node.state_items.new(stype, name)
        return SimulationZone(self, input_node, output_node, [name for name, _ in items], [stype for _, stype in items])

    def repeat(self, iterations, items):
        """Repeat zone with ``items`` [(name, socket type, initial value), ...];
        ``zone.iteration`` counts from 0."""
        input_node = self.ng.nodes.new("GeometryNodeRepeatInput")
        output_node = self.ng.nodes.new("GeometryNodeRepeatOutput")
        input_node.pair_with_output(output_node)
        output_node.repeat_items.clear()
        for name, stype, _initial in items:
            output_node.repeat_items.new(stype, name)
        zone = Zone(self, input_node, output_node, [name for name, _, _ in items], state_offset=1, set_offset=0, initial_offset=1)
        self.assign(input_node.inputs[0], iterations)
        for name, _stype, initial in items:
            zone.initial(name, initial)
        zone.iteration = Sock(self, input_node.outputs[0])
        return zone

    def fingerprint(self, geometry, *fields):
        """A vector that changes whenever the points of ``geometry`` do: for
        each vector field (the position when none is given) the sum over the
        points of (field + 1) weighted component-wise by pseudo-random numbers
        fixed per point index.  Moving, turning, deforming, adding or removing
        points gives another sum, barring coincidences of measure zero."""
        total = None
        for seed, field in enumerate(fields or (self.position(),)):
            weights = self.random(-1.0, 1.0, seed + 1, ID=self.index(), dtype="FLOAT_VECTOR")
            term = self.statistic(geometry, weights * (field + (1.0, 1.0, 1.0)), "FLOAT_VECTOR")["Sum"]
            total = term if total is None else total + term
        return total

    def detach(self, geo):
        """``geo`` with derived data of its own (``Core.Detach``)."""
        return self.group(get_asset("Core.Detach"), Geometry=geo).o

    # ------------------------------------------------------------ rotations
    def align_rotation(self, vector, rotation=None, axis="Z", pivot="AUTO"):
        """Rotation turning local ``axis`` of ``rotation`` onto ``vector``."""
        return self.n("FunctionNodeAlignRotationToVector", Rotation=rotation, Vector=vector,
                      props={"axis": axis, "pivot_axis": pivot}).o

    def axis_angle(self, axis, angle):
        return self.n("FunctionNodeAxisAngleToRotation",
                      Axis=self.vec(axis) if isinstance(axis, (tuple, list)) else axis, Angle=angle).o

    def rotate_rotation(self, rotation, by, local=True):
        """``rotation`` turned by ``by`` about its own axes (local) or the
        world axes."""
        return self.n("FunctionNodeRotateRotation", Rotation=rotation, Rotate_By=by,
                      props={"rotation_space": "LOCAL" if local else "GLOBAL"}).o

    def rotate_vector(self, vector, rotation):
        return self.n("FunctionNodeRotateVector", Vector=vector, Rotation=rotation).o

    def random_spin(self, rotation, seed, axis=(0.0, 0.0, 1.0)):
        """``rotation`` turned by a random angle about its own ``axis``."""
        return self.rotate_rotation(rotation, self.axis_angle(axis, self.random(0.0, math.tau, seed)))

    # ------------------------------------------------------------ primitives
    def cube(self, size=(1, 1, 1), vx=2, vy=2, vz=2):
        return self.n("GeometryNodeMeshCube", Size=self.vec(size) if isinstance(size, (tuple, list)) else size,
                      Vertices_X=vx, Vertices_Y=vy, Vertices_Z=vz)["Mesh"]

    def box(self, x0, y0, z0, x1, y1, z1):
        """Axis aligned box between two corners (constants or sockets)."""
        size = self.vec(x1 - x0, y1 - y0, z1 - z0)
        c = self.vec((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)
        return self.transform(self.cube(size), t=c)

    def cylinder(self, r=0.5, depth=1.0, verts=16, fill="NGON", seg=1):
        return self.n("GeometryNodeMeshCylinder", props={"fill_type": fill},
                      Vertices=verts, Side_Segments=seg, Radius=r, Depth=depth)["Mesh"]

    def grid(self, sx=1.0, sy=1.0, nx=2, ny=2):
        return self.n("GeometryNodeMeshGrid", Size_X=sx, Size_Y=sy,
                      Vertices_X=nx, Vertices_Y=ny)["Mesh"]

    def mesh_line(self, count, start=(0, 0, 0), offset=(1, 0, 0)):
        nd = self.n("GeometryNodeMeshLine")
        set_mode(nd, "OFFSET")
        self.assign(self._in_socket(nd.n, "Count"), count)
        self.assign(self._in_socket(nd.n, "Start Location"), self.vec(start) if isinstance(start, (tuple, list)) else start)
        self.assign(self._in_socket(nd.n, "Offset"), self.vec(offset) if isinstance(offset, (tuple, list)) else offset)
        return nd["Mesh"]

    def points(self, count=1, position=(0, 0, 0), radius=0.05):
        return self.n("GeometryNodePoints", Count=count, Position=position, Radius=radius).o

    def new_points(self, count):
        """``count`` points that carry nothing but their position; no geometry
        at all for a count of zero (so removing the radius never warns)."""
        points = self.remove_attribute(self.points(count), "radius")
        return self.switch(self.compare(count, 0, "GREATER_THAN", "INT"), None, points)

    def mesh_to_points(self, mesh, sel=None):
        return self.n("GeometryNodeMeshToPoints", Mesh=mesh, Selection=sel).o

    # ---------------------------------------------------------------- curves
    def curve_line(self, a=(0, 0, 0), b=(0, 0, 1)):
        return self.n("GeometryNodeCurvePrimitiveLine",
                      Start=self.vec(a) if isinstance(a, (tuple, list)) else a,
                      End=self.vec(b) if isinstance(b, (tuple, list)) else b).o

    def circle(self, r=1.0, res=32):
        nd = self.n("GeometryNodeCurvePrimitiveCircle")
        set_mode(nd, "RADIUS")
        self.assign(self._in_socket(nd.n, "Resolution"), res)
        self.assign(self._in_socket(nd.n, "Radius"), r)
        return nd["Curve"]

    def rect(self, w=1.0, h=1.0):
        nd = self.n("GeometryNodeCurvePrimitiveQuadrilateral")
        set_mode(nd, "RECTANGLE")
        self.assign(self._in_socket(nd.n, "Width"), w)
        self.assign(self._in_socket(nd.n, "Height"), h)
        return nd.o

    def quad_points(self, p1, p2, p3, p4):
        nd = self.n("GeometryNodeCurvePrimitiveQuadrilateral")
        set_mode(nd, "POINTS")
        for i, p in enumerate((p1, p2, p3, p4), 1):
            self.assign(self._in_socket(nd.n, f"Point {i}"),
                        self.vec(p) if isinstance(p, (tuple, list)) else p)
        return nd.o

    def polyline(self, pts, cyclic=False):
        """Poly curve through a list of 3D points (constants or sockets)."""
        n = len(pts)
        line = self.mesh_line(n, (0, 0, 0), (1, 0, 0))
        pos = self.index_switch(self.index(), list(pts), "VECTOR")
        line = self.set_pos(line, pos=pos)
        crv = self.n("GeometryNodeMeshToCurve", line).o
        crv = self.n("GeometryNodeCurveSplineType", crv, props={"spline_type": "POLY"}).o
        if cyclic:
            crv = self.n("GeometryNodeSetSplineCyclic", crv, Cyclic=True).o
        return crv

    def fillet(self, curve, radius=0.05, count=4, limit=True, mode="POLY"):
        nd = self.n("GeometryNodeFilletCurve")
        set_mode(nd, mode)
        self.assign(self._in_socket(nd.n, "Curve"), curve)
        self.assign(self._in_socket(nd.n, "Radius"), radius)
        try:
            self.assign(self._in_socket(nd.n, "Count"), count)
        except KeyError:
            pass
        try:
            self.assign(self._in_socket(nd.n, "Limit Radius"), limit)
        except KeyError:
            pass
        return nd.o

    def resample(self, curve, count=16):
        nd = self.n("GeometryNodeResampleCurve")
        set_mode(nd, "COUNT")
        self.assign(self._in_socket(nd.n, "Curve"), curve)
        self.assign(self._in_socket(nd.n, "Count"), count)
        return nd.o

    def fill(self, curve, mode="NGONS"):
        nd = self.n("GeometryNodeFillCurve")
        set_mode(nd, mode)
        self.assign(self._in_socket(nd.n, "Curve"), curve)
        return nd.o

    def sweep(self, curve, profile=None, caps=True):
        return self.n("GeometryNodeCurveToMesh", Curve=curve, Profile_Curve=profile,
                      Fill_Caps=caps).o

    def tube(self, curve, r=0.01, res=8, caps=True):
        """Round tube along a curve (sweep of a circle)."""
        return self.sweep(curve, self.circle(r, res), caps)

    def rod(self, a, b, r=0.01, res=8):
        """Straight round rod from a to b."""
        return self.tube(self.curve_line(a, b), r, res)

    def lathe(self, pts, segments=40, scale=1.0):
        """Surface of revolution about Z from a profile [(r, z), ...] listed
        from the axis at the bottom, out, up and (optionally) back in.  ``scale``
        (constant or socket) multiplies the profile."""
        path = self.circle(1.0, segments)
        # Curve to Mesh along a unit circle: radius = 1 + profile x, z = -profile y
        prof = self.polyline([(r * scale - 1.0, z * scale * -1.0, 0.0) for r, z in pts])
        body = self.sweep(path, prof, False)
        return self.merge(self.n("GeometryNodeFlipFaces", body).o, 0.0005)

    def ellipsoid(self, rx, ry, rz, seg=24, rings=16):
        """UV sphere scaled to the semi-axes rx, ry, rz."""
        s = self.n("GeometryNodeMeshUVSphere", Segments=seg, Rings=rings, Radius=1.0)["Mesh"]
        return self.transform(s, s=self.vec(rx, ry, rz))

    # ------------------------------------------------------------- operators
    def transform(self, geo, t=None, r=None, s=None):
        kw = {}
        if t is not None:
            kw["Translation"] = self.vec(t) if isinstance(t, (tuple, list)) else t
        if r is not None:
            kw["Rotation"] = self.vec(r) if isinstance(r, (tuple, list)) else r
        if s is not None:
            kw["Scale"] = self.vec(s) if isinstance(s, (tuple, list)) else s
        return self.n("GeometryNodeTransform", Geometry=geo, **kw).o

    def move(self, geo, x=0.0, y=0.0, z=0.0):
        return self.transform(geo, t=self.vec(x, y, z))

    def rotate(self, geo, rx=0.0, ry=0.0, rz=0.0):
        return self.transform(geo, r=self.vec(rx, ry, rz))

    def join(self, *geos):
        geos = [g for g in geos if g is not None]
        if len(geos) == 1:
            return geos[0]
        return self.n("GeometryNodeJoinGeometry", Geometry=list(geos)).o

    def mat(self, geo, material, sel=None):
        return self.n("GeometryNodeSetMaterial", Geometry=geo, Selection=sel,
                      Material=material).o

    def smooth(self, geo, on=True):
        return self.n("GeometryNodeSetShadeSmooth", Geometry=geo, Shade_Smooth=on).o

    def smooth_by_angle(self, geo, angle=0.6):
        """Smooth faces, but keep edges sharper than ``angle`` (radians)."""
        geo = self.n("GeometryNodeSetShadeSmooth", Geometry=geo, Shade_Smooth=True,
                     props={"domain": "FACE"}).o
        ea = self.n("GeometryNodeInputMeshEdgeAngle")["Unsigned Angle"]
        sharp = self.compare(ea, angle, "GREATER_THAN")
        return self.n("GeometryNodeSetShadeSmooth", Geometry=geo, Selection=sharp,
                      Shade_Smooth=False, props={"domain": "EDGE"}).o

    def set_pos(self, geo, pos=None, offset=None, sel=None):
        return self.n("GeometryNodeSetPosition", Geometry=geo, Selection=sel,
                      Position=pos, Offset=offset).o

    def extrude(self, mesh, offset=0.01, sel=None, individual=False, direction=None):
        nd = self.n("GeometryNodeExtrudeMesh")
        set_mode(nd, "FACES")
        self.assign(self._in_socket(nd.n, "Mesh"), mesh)
        if sel is not None:
            self.assign(self._in_socket(nd.n, "Selection"), sel)
        if direction is not None:
            self.assign(self._in_socket(nd.n, "Offset"), direction)
        self.assign(self._in_socket(nd.n, "Offset Scale"), offset)
        try:
            self.assign(self._in_socket(nd.n, "Individual"), individual)
        except KeyError:
            pass
        return nd["Mesh"]

    def flat_sweep(self, curve, w, d):
        """Sweep a planar XY curve with a w (in plane) x d (along Z) bar."""
        nd = self.n("GeometryNodeSetCurveNormal", curve)
        set_mode(nd, "Z_UP")
        return self.sweep(nd.o, self.rect(w, d), True)

    def solid(self, face, depth, direction=(0.0, 0.0, 1.0)):
        """Closed prism: extrude a face along ``direction`` and keep the
        (flipped) original face as the back cap."""
        ext = self.extrude(face, depth, direction=direction)
        back = self.n("GeometryNodeFlipFaces", face).o
        return self.merge(self.join(ext, back), 0.0001)

    def slab(self, curve, thickness=0.02, z0=0.0):
        """Fill a closed planar (XY) curve and extrude it upward into a slab."""
        face = self.fill(curve)
        face = self.move(face, z=z0)
        return self.extrude(face, thickness, direction=(0, 0, 1))

    def iop(self, points, instance, rot=None, scale=None, sel=None, pick=False, index=None):
        return self.n("GeometryNodeInstanceOnPoints", Points=points, Selection=sel,
                      Instance=instance, Pick_Instance=pick, Instance_Index=index,
                      Rotation=rot, Scale=scale).o

    def realize(self, geo):
        return self.n("GeometryNodeRealizeInstances", geo).o

    def merge(self, geo, dist=0.0005):
        return self.n("GeometryNodeMergeByDistance", Geometry=geo, Distance=dist).o

    def delete(self, geo, sel, domain="POINT"):
        return self.n("GeometryNodeDeleteGeometry", Geometry=geo, Selection=sel,
                      props={"domain": domain}).o

    def store(self, geo, name, value, dtype="FLOAT", domain="POINT", sel=None):
        return self.n("GeometryNodeStoreNamedAttribute", Geometry=geo, Selection=sel,
                      Name=name, Value=value,
                      props={"data_type": dtype, "domain": domain}).o

    def subdiv(self, mesh, level=1):
        return self.n("GeometryNodeSubdivisionSurface", Mesh=mesh, Level=level).o

    def text_curves(self, text, size=1.0, spacing=1.0):
        return self.n("GeometryNodeStringToCurves", String=text, Size=size,
                      Character_Spacing=spacing)["Curve Instances"]

    # ---------------------------------------------------------- repetitions
    def array(self, geo, count, offset, start=(0, 0, 0), realize=False):
        """Linear array of ``geo``: ``count`` copies stepping by ``offset``."""
        pts = self.mesh_line(count, start, offset)
        out = self.iop(pts, geo)
        return self.realize(out) if realize else out

    def grid_points(self, nx, ny, dx, dy, origin=(0, 0, 0)):
        """Points on a regular nx*ny grid starting at origin."""
        row = self.mesh_line(nx, origin, self.vec(dx, 0, 0))
        col = self.mesh_line(ny, (0, 0, 0), self.vec(0, dy, 0))
        inst = self.iop(self.mesh_to_points(col), row)
        return self.mesh_to_points(self.realize(inst))


def shell_profile(outer, thickness):
    """Closed lathe profile of a vessel wall: the ``outer`` profile
    [(r, z), ...] from the axis at the bottom out and up to the rim, then
    the same line offset ``thickness`` inwards and back down to the axis.
    Lathing it gives a watertight glass wall of constant thickness."""
    count = len(outer)
    inner = []
    for i, (r, z) in enumerate(outer):
        before = outer[max(i - 1, 0)]
        after = outer[min(i + 1, count - 1)]
        tangent_r, tangent_z = after[0] - before[0], after[1] - before[1]
        norm = math.hypot(tangent_r, tangent_z) or 1.0
        inner.append((max(r - thickness * tangent_z / norm, 0.0), z + thickness * tangent_r / norm))
    inner[0] = (0.0, inner[0][1])
    return list(outer) + inner[::-1]


def inner_profile(outer, thickness):
    """The inner surface of :func:`shell_profile` as a solid of its own
    (from the axis at the inner bottom up to the rim and back to the axis):
    the cavity a liquid fills."""
    shell = shell_profile(outer, thickness)
    inner = shell[len(outer):][::-1]
    return inner + [(0.0, inner[-1][1])]


# ---------------------------------------------------------------- registry
ASSETS: dict = {}
_BUILT: dict = {}


def asset(name, category="Misc", doc=""):
    """Decorator registering a node-group builder under ``name``.

    The decorated function receives no arguments, builds the group with
    :class:`GN` (named exactly ``name``) and returns the GN builder.  Use
    :func:`get_asset` to obtain the node group (built on first use).
    """
    def deco(fn):
        ASSETS[name] = dict(fn=fn, category=category, doc=doc or (fn.__doc__ or "").strip())
        return fn
    return deco


def get_asset(name, rebuild=False):
    if not rebuild and name in _BUILT and _BUILT[name].name in bpy.data.node_groups:
        return _BUILT[name]
    if name not in ASSETS:
        raise KeyError(f"unknown asset '{name}'. Known: {sorted(ASSETS)}")
    g = ASSETS[name]["fn"]()
    ng = g.ng if isinstance(g, Tree) else g
    try:
        ng.use_fake_user = True
    except AttributeError:
        pass
    _BUILT[name] = ng
    return ng


def reset_registry():
    _BUILT.clear()


@asset("Core.Detach", "Core")
def detach_asset():
    """The geometry with derived data of its own.  A simulation cache keeps
    every frame's state geometry, and normals or BVH trees built on that object
    (Sample Nearest, Sample Nearest Surface, Raycast ...) would stay with every
    cached frame -- megabytes per frame.  Rewriting ``position`` gives a copy
    whose derived data is freed with the evaluation; every other attribute
    array stays shared.  (An identity Transform is skipped by Blender and does
    not detach.)"""
    graph = GN("Core.Detach", detach_asset.__doc__)
    geometry = graph.inp("Geometry", "GEOMETRY")
    graph.result(graph.store(geometry, "position", graph.position(), "FLOAT_VECTOR"))
    return graph
