"""
Core.nodes -- a small declarative DSL for building Blender node trees from Python.

Works for Geometry Nodes groups, shader node trees (materials / worlds / shader
groups) and compositor trees.  Design goals:

* Readable asset code:  ``top = g.cube((w, d, t))``, ``h = height - t * 0.5``.
  Python operators on sockets create Math / Vector Math nodes, and pure-Python
  constants are folded so trees stay small.
* Stable across Blender 4.2 LTS .. 5.x (socket lookup by *enabled* sockets,
  properties set before inputs so dynamic sockets resolve correctly).
* Produced trees are laid out automatically so they stay pleasant to open and
  tweak by hand in the node editor.
"""
from __future__ import annotations

import bpy

__all__ = ["Sock", "Node", "Tree", "SOCKET_TYPES"]

# Interface socket type aliases -> bl socket idnames
SOCKET_TYPES = {
    "FLOAT": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "BOOL": "NodeSocketBool",
    "VECTOR": "NodeSocketVector",
    "COLOR": "NodeSocketColor",
    "ROTATION": "NodeSocketRotation",
    "MATRIX": "NodeSocketMatrix",
    "GEOMETRY": "NodeSocketGeometry",
    "MATERIAL": "NodeSocketMaterial",
    "OBJECT": "NodeSocketObject",
    "COLLECTION": "NodeSocketCollection",
    "IMAGE": "NodeSocketImage",
    "STRING": "NodeSocketString",
    "SHADER": "NodeSocketShader",
    "MENU": "NodeSocketMenu",
}

_VEC = {"VECTOR", "RGBA", "ROTATION"}
_NUM = (int, float)


def _is_num(v):
    return isinstance(v, _NUM) and not isinstance(v, bool)


def _enabled(sock):
    # 4.x: .enabled ; 5.x keeps .enabled and adds .is_unavailable / .is_inactive
    if getattr(sock, "is_unavailable", False):
        return False
    return getattr(sock, "enabled", True)


class Sock:
    """Wrapper around an output socket that supports Python arithmetic."""

    __slots__ = ("t", "s")

    def __init__(self, tree: "Tree", socket):
        self.t = tree
        self.s = socket

    # -- introspection ------------------------------------------------------
    @property
    def type(self):
        return self.s.type

    @property
    def is_vec(self):
        return self.s.type in _VEC

    # -- arithmetic -----------------------------------------------------------
    def _b(self, op, o, rev=False):
        return self.t.arith(op, o, self) if rev else self.t.arith(op, self, o)

    def __add__(self, o): return self._b("ADD", o)
    def __radd__(self, o): return self._b("ADD", o, True)
    def __sub__(self, o): return self._b("SUBTRACT", o)
    def __rsub__(self, o): return self._b("SUBTRACT", o, True)
    def __mul__(self, o): return self._b("MULTIPLY", o)
    def __rmul__(self, o): return self._b("MULTIPLY", o, True)
    def __truediv__(self, o): return self._b("DIVIDE", o)
    def __rtruediv__(self, o): return self._b("DIVIDE", o, True)
    def __pow__(self, o): return self._b("POWER", o)
    def __mod__(self, o): return self._b("MODULO", o)
    def __neg__(self): return self.t.arith("MULTIPLY", self, -1.0)

    # -- vector component access (cached separate node) -----------------------
    @property
    def x(self): return self.t.sep(self)[0]
    @property
    def y(self): return self.t.sep(self)[1]
    @property
    def z(self): return self.t.sep(self)[2]

    def __repr__(self):
        return f"<Sock {self.s.node.name}.{self.s.identifier} {self.s.type}>"


class Node:
    """Wrapper around a created node. ``node.o`` is its first enabled output."""

    __slots__ = ("t", "n")

    def __init__(self, tree: "Tree", node):
        self.t = tree
        self.n = node

    @property
    def o(self) -> Sock:
        for s in self.n.outputs:
            if _enabled(s):
                return Sock(self.t, s)
        raise ValueError(f"node {self.n.bl_idname} has no enabled output")

    def __getitem__(self, key) -> Sock:
        outs = [s for s in self.n.outputs if _enabled(s)]
        if isinstance(key, int):
            return Sock(self.t, outs[key])
        for s in outs:
            if s.name == key or s.identifier == key:
                return Sock(self.t, s)
        for s in self.n.outputs:  # disabled but addressed explicitly
            if s.identifier == key or s.name == key:
                return Sock(self.t, s)
        raise KeyError(f"{self.n.bl_idname}: no output '{key}' "
                       f"(has {[s.name for s in outs]})")

    # delegate arithmetic to first output so nodes can be used like sockets
    def __getattr__(self, item):
        if item in ("x", "y", "z", "type", "is_vec"):
            return getattr(self.o, item)
        raise AttributeError(item)

    def _b(self, op, o, rev=False): return self.o._b(op, o, rev)
    def __add__(self, o): return self._b("ADD", o)
    def __radd__(self, o): return self._b("ADD", o, True)
    def __sub__(self, o): return self._b("SUBTRACT", o)
    def __rsub__(self, o): return self._b("SUBTRACT", o, True)
    def __mul__(self, o): return self._b("MULTIPLY", o)
    def __rmul__(self, o): return self._b("MULTIPLY", o, True)
    def __truediv__(self, o): return self._b("DIVIDE", o)
    def __rtruediv__(self, o): return self._b("DIVIDE", o, True)
    def __neg__(self): return -self.o


def _kind(v):
    if isinstance(v, Node):
        v = v.o
    if isinstance(v, Sock):
        return "v" if v.is_vec else "f"
    if isinstance(v, (tuple, list)):
        return "v"
    return "f"


class Tree:
    """Builder for one node tree.

    ``Tree("Name", "GeometryNodeTree")`` creates (or rebuilds) a node group.
    ``Tree.wrap(material.node_tree)`` builds into an existing embedded tree.
    """

    GROUP_NODE = {
        "GeometryNodeTree": "GeometryNodeGroup",
        "ShaderNodeTree": "ShaderNodeGroup",
        "CompositorNodeTree": "CompositorNodeGroup",
    }

    def __init__(self, name=None, tree_type="GeometryNodeTree", *, nodetree=None,
                 clear=True, description=""):
        if nodetree is None:
            ng = bpy.data.node_groups.get(name)
            if ng is not None and ng.bl_idname != tree_type:
                ng = None
            if ng is None:
                ng = bpy.data.node_groups.new(name, tree_type)
            self.is_group = True
        else:
            ng = nodetree
            self.is_group = False
        self.ng = ng
        self.tree_type = ng.bl_idname
        if clear:
            ng.nodes.clear()
            if self.is_group:
                ng.interface.clear()
        if description and hasattr(ng, "description"):
            ng.description = description
        self._gin = None
        self._gout = None
        self._sep_cache = {}
        self._panels = {}
        self._outputs_linked = set()

    @classmethod
    def wrap(cls, nodetree, clear=True):
        return cls(nodetree=nodetree, clear=clear)

    # ------------------------------------------------------------------ nodes
    _RESOLVED: dict = {}

    def resolve(self, *candidates):
        """First node idname from ``candidates`` that this tree type accepts
        (node sets differ between Blender versions, e.g. the compositor's
        math/gamma nodes became shader-style nodes in 5.x)."""
        key = (self.tree_type, candidates)
        if key not in Tree._RESOLVED:
            found = None
            for idn in candidates:
                try:
                    n = self.ng.nodes.new(idn)
                except RuntimeError:
                    continue
                self.ng.nodes.remove(n)
                found = idn
                break
            if found is None:
                raise RuntimeError(f"none of {candidates} available in {self.tree_type}")
            Tree._RESOLVED[key] = found
        return Tree._RESOLVED[key]

    @property
    def nodes(self):
        return self.ng.nodes

    def link(self, a, b):
        if isinstance(a, Node):
            a = a.o
        if isinstance(a, Sock):
            a = a.s
        if isinstance(b, Sock):
            b = b.s
        return self.ng.links.new(a, b)

    def _in_socket(self, node, key):
        ins = [s for s in node.inputs if _enabled(s)]
        if isinstance(key, int):
            return ins[key]
        for s in ins:
            if s.name == key or s.identifier == key:
                return s
        for s in node.inputs:
            if s.identifier == key or s.name == key:
                return s
        raise KeyError(f"{node.bl_idname}: no input '{key}' "
                       f"(has {[s.name for s in ins]})")

    def assign(self, sock, val):
        """Link a Sock/Node into ``sock`` or set its default value."""
        if val is None:
            return
        if isinstance(val, Node):
            val = val.o
        if isinstance(val, Sock):
            self.ng.links.new(val.s, sock)
            return
        if isinstance(val, (list,)) and getattr(sock, "is_multi_input", False):
            for v in val:
                self.assign(sock, v)
            return
        if not hasattr(sock, "default_value"):
            raise TypeError(f"socket {sock.identifier} of {sock.node.bl_idname} "
                            f"has no default value; got {val!r}")
        dv = sock.default_value
        if sock.type in _VEC or (hasattr(dv, "__len__") and not isinstance(dv, str)):
            try:
                n = len(dv)
            except TypeError:
                n = 0
            if n and _is_num(val):
                val = (float(val),) * n
            elif n == 4 and isinstance(val, (tuple, list)) and len(val) == 3:
                val = (*val, 1.0)
        sock.default_value = val

    def n(self, idname, *args, props=None, label=None, name=None, **kwargs) -> Node:
        """Create node ``idname``; positional args map to enabled inputs in order,
        keyword args map to inputs by name/identifier (spaces may be written as
        underscores: ``Vertices_X``). ``props`` sets node properties first."""
        node = self.ng.nodes.new(idname)
        if props:
            for k, v in props.items():
                setattr(node, k, v)
        if label:
            node.label = label
        if name:
            node.name = name
        ins = [s for s in node.inputs if _enabled(s)]
        for i, a in enumerate(args):
            if a is not None:
                self.assign(ins[i], a)
        for k, v in kwargs.items():
            if v is None:
                continue
            try:
                s = self._in_socket(node, k)
            except KeyError:
                s = self._in_socket(node, k.replace("_", " "))
            self.assign(s, v)
        return Node(self, node)

    def group(self, tree, *args, label=None, **kwargs) -> Node:
        """Instantiate a node group (Tree / NodeTree / name)."""
        if isinstance(tree, Tree):
            tree = tree.ng
        elif isinstance(tree, str):
            tree = bpy.data.node_groups[tree]
        idname = self.GROUP_NODE[self.tree_type]
        node = self.ng.nodes.new(idname)
        node.node_tree = tree
        node.label = label or tree.name
        ins = [s for s in node.inputs if _enabled(s)]
        for i, a in enumerate(args):
            if a is not None:
                self.assign(ins[i], a)
        for k, v in kwargs.items():
            if v is None:
                continue
            try:
                s = self._in_socket(node, k)
            except KeyError:
                s = self._in_socket(node, k.replace("_", " "))
            self.assign(s, v)
        return Node(self, node)

    # -------------------------------------------------------------- interface
    def panel(self, name, closed=True):
        if name not in self._panels:
            p = self.ng.interface.new_panel(name)
            try:
                p.default_closed = closed
            except AttributeError:
                pass
            self._panels[name] = p
        return self._panels[name]

    def _group_input_node(self):
        if self._gin is None:
            self._gin = self.ng.nodes.new("NodeGroupInput")
        return self._gin

    def _group_output_node(self):
        if self._gout is None:
            self._gout = self.ng.nodes.new("NodeGroupOutput")
            try:
                self._gout.is_active_output = True
            except AttributeError:
                pass
        return self._gout

    def inp(self, name, stype="FLOAT", default=None, min=None, max=None,
            subtype=None, desc="", panel=None, hide_value=False) -> Sock:
        """Declare a group input and return the Group Input socket."""
        stype_id = SOCKET_TYPES.get(stype, stype)
        parent = self.panel(panel) if panel else None
        item = self.ng.interface.new_socket(name, in_out="INPUT", socket_type=stype_id,
                                            description=desc, parent=parent)
        if subtype:
            try:
                item.subtype = subtype
            except (AttributeError, TypeError):
                pass
        if default is not None and hasattr(item, "default_value"):
            dv = default
            if stype in ("COLOR",) and len(dv) == 3:
                dv = (*dv, 1.0)
            try:
                item.default_value = dv
            except TypeError:
                pass
        if min is not None and hasattr(item, "min_value"):
            item.min_value = min
        if max is not None and hasattr(item, "max_value"):
            item.max_value = max
        if hide_value and hasattr(item, "hide_value"):
            item.hide_value = True
        gin = self._group_input_node()
        for s in gin.outputs:
            if s.identifier == item.identifier:
                return Sock(self, s)
        raise RuntimeError("input socket not found after creation")

    def out(self, name, stype="GEOMETRY", desc="", panel=None):
        stype_id = SOCKET_TYPES.get(stype, stype)
        parent = self.panel(panel) if panel else None
        return self.ng.interface.new_socket(name, in_out="OUTPUT", socket_type=stype_id,
                                            description=desc, parent=parent)

    def result(self, *vals, **named):
        """Connect values to group outputs (declared with ``out``).
        Positional values map to outputs in order; if no output was declared,
        a ``Geometry`` output is created for a single positional value."""
        gout = self._group_output_node()
        outs = [it for it in self.ng.interface.items_tree
                if getattr(it, "in_out", None) == "OUTPUT"]
        if vals and not outs:
            self.out("Geometry", "GEOMETRY")
            outs = [it for it in self.ng.interface.items_tree
                    if getattr(it, "in_out", None) == "OUTPUT"]
        mapping = {}
        for it, v in zip(outs, vals):
            mapping[it.identifier] = v
        for k, v in named.items():
            for it in outs:
                if it.name == k:
                    mapping[it.identifier] = v
        for ident, v in mapping.items():
            for s in gout.inputs:
                if s.identifier == ident:
                    self.assign(s, v)
        self.layout()
        return self

    # ---------------------------------------------------------------- math
    def arith(self, op, a, b):
        if isinstance(a, Node):
            a = a.o
        if isinstance(b, Node):
            b = b.o
        if _is_num(a) and _is_num(b):
            return _fold(op, a, b)
        ka, kb = _kind(a), _kind(b)
        if "v" in (ka, kb):
            if op == "MULTIPLY" and ka == "v" and kb == "f":
                return self.vmath("SCALE", a, scale=b)
            if op == "MULTIPLY" and ka == "f" and kb == "v":
                return self.vmath("SCALE", b, scale=a)
            if op == "DIVIDE" and ka == "v" and kb == "f":
                inv = (1.0 / b) if _is_num(b) else self.math("DIVIDE", 1.0, b)
                return self.vmath("SCALE", a, scale=inv)
            if op == "POWER":
                raise TypeError("vector power not supported")
            return self.vmath(op, a, b)
        # neutral-element folding
        if op in ("ADD", "SUBTRACT") and _is_num(b) and b == 0:
            return a
        if op == "ADD" and _is_num(a) and a == 0:
            return b
        if op in ("MULTIPLY", "DIVIDE") and _is_num(b) and b == 1:
            return a
        if op == "MULTIPLY" and _is_num(a) and a == 1:
            return b
        return self.math(op, a, b)

    def math(self, op, a, b=None, c=None, clamp=False) -> Sock:
        idn = "ShaderNodeMath" if self.tree_type != "CompositorNodeTree" else \
            self.resolve("CompositorNodeMath", "ShaderNodeMath")
        node = self.ng.nodes.new(idn)
        node.operation = op
        node.use_clamp = clamp
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.assign(node.inputs[i], v)
        return Node(self, node).o

    def vmath(self, op, a, b=None, c=None, scale=None) -> Sock:
        node = self.ng.nodes.new("ShaderNodeVectorMath")
        node.operation = op
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.assign(node.inputs[i], v)
        if scale is not None:
            self.assign(node.inputs[3], scale)
        out = node.outputs[1] if op in ("DOT_PRODUCT", "DISTANCE", "LENGTH") else node.outputs[0]
        return Sock(self, out)

    def vec(self, x=0.0, y=0.0, z=0.0):
        """Vector from components; returns a tuple when all are constants."""
        if isinstance(x, (tuple, list)):
            x, y, z = x
        if all(_is_num(v) for v in (x, y, z)):
            return (float(x), float(y), float(z))
        return self.n("ShaderNodeCombineXYZ", x, y, z).o

    def sep(self, v):
        if isinstance(v, Node):
            v = v.o
        if isinstance(v, (tuple, list)):
            return tuple(v)
        key = (v.s.node.name, v.s.identifier)
        if key not in self._sep_cache:
            n = self.n("ShaderNodeSeparateXYZ", v)
            self._sep_cache[key] = (n["X"], n["Y"], n["Z"])
        return self._sep_cache[key]

    # common scalar helpers (constant-folding where possible)
    def min(self, a, b): return _fold("MINIMUM", a, b) if _is_num(a) and _is_num(b) else self.math("MINIMUM", a, b)
    def max(self, a, b): return _fold("MAXIMUM", a, b) if _is_num(a) and _is_num(b) else self.math("MAXIMUM", a, b)
    def abs(self, a): return abs(a) if _is_num(a) else self.math("ABSOLUTE", a)
    def floor(self, a): return float(int(a // 1)) if _is_num(a) else self.math("FLOOR", a)
    def sin(self, a):
        import math as _m
        return _m.sin(a) if _is_num(a) else self.math("SINE", a)
    def cos(self, a):
        import math as _m
        return _m.cos(a) if _is_num(a) else self.math("COSINE", a)
    def clamp01(self, a): return min(max(a, 0.0), 1.0) if _is_num(a) else self.math("ADD", a, 0.0, clamp=True)

    def map_range(self, v, fmin=0.0, fmax=1.0, tmin=0.0, tmax=1.0, clamp=True, interp="LINEAR"):
        return self.n("ShaderNodeMapRange", v, fmin, fmax, tmin, tmax,
                      props={"interpolation_type": interp, "clamp": clamp}).o

    def mix(self, fac, a, b, data_type="FLOAT", blend="MIX", clamp=True):
        """Generic Mix node (float / vector / color)."""
        node = self.ng.nodes.new("ShaderNodeMix")
        node.data_type = data_type
        if data_type == "RGBA":
            node.blend_type = blend
            node.clamp_result = False
        node.clamp_factor = clamp
        ins = [s for s in node.inputs if _enabled(s)]
        self.assign(ins[0], fac)
        self.assign(ins[1], a)
        self.assign(ins[2], b)
        outs = [s for s in node.outputs if _enabled(s)]
        return Sock(self, outs[0])

    # ---------------------------------------------------------------- layout
    def layout(self, dx=240, dy=190):
        """Rank nodes by longest path to the output and lay them out in columns."""
        nodes = list(self.ng.nodes)
        if not nodes:
            return
        succ = {n.name: set() for n in nodes}
        for l in self.ng.links:
            succ[l.from_node.name].add(l.to_node.name)
        rank = {}

        def r(name, stack=()):
            if name in rank:
                return rank[name]
            if name in stack:
                return 0
            s = succ[name]
            v = 0 if not s else 1 + max(r(x, stack + (name,)) for x in s)
            rank[name] = v
            return v

        for n in nodes:
            r(n.name)
        cols = {}
        for n in nodes:
            cols.setdefault(rank[n.name], []).append(n)
        for k, col in cols.items():
            y = 0.0
            for n in col:
                n.location = (-k * dx, -y)
                h = 60 + 22 * (len([s for s in n.inputs if _enabled(s)]) +
                               len([s for s in n.outputs if _enabled(s)]))
                y += max(dy * 0.6, h)


def _fold(op, a, b):
    import math as _m
    if op == "ADD": return a + b
    if op == "SUBTRACT": return a - b
    if op == "MULTIPLY": return a * b
    if op == "DIVIDE": return a / b if b != 0 else 0.0
    if op == "POWER": return a ** b
    if op == "MODULO": return _m.fmod(a, b) if b != 0 else 0.0
    if op == "MINIMUM": return min(a, b)
    if op == "MAXIMUM": return max(a, b)
    raise ValueError(op)
