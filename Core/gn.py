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

__all__ = ["GN", "asset", "get_asset", "ASSETS", "set_mode"]


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


class GN(Tree):
    def __init__(self, name, description="", clear=True):
        super().__init__(name, "GeometryNodeTree", clear=clear, description=description)

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
