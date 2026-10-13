import bpy

VECTOR_TYPES = {"VECTOR"}
FLOAT_TYPES = {"VALUE", "INT", "BOOLEAN"}
SOCKET_CLASS = {
    "FLOAT": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "BOOL": "NodeSocketBool",
    "VECTOR": "NodeSocketVector",
    "COLOR": "NodeSocketColor",
    "GEOMETRY": "NodeSocketGeometry",
    "MATERIAL": "NodeSocketMaterial",
    "OBJECT": "NodeSocketObject",
    "COLLECTION": "NodeSocketCollection",
    "ROTATION": "NodeSocketRotation",
    "SHADER": "NodeSocketShader",
    "STRING": "NodeSocketString",
    "MATRIX": "NodeSocketMatrix",
}


class Socket:
    def __init__(self, builder, socket):
        self.builder = builder
        self.socket = socket

    @property
    def kind(self):
        return self.socket.type

    def _binary(self, operation, other, reverse=False):
        left, right = (other, self) if reverse else (self, other)
        vector = self.kind in VECTOR_TYPES or (isinstance(other, Socket) and other.kind in VECTOR_TYPES) or isinstance(other, (tuple, list))
        if vector:
            if operation == "MULTIPLY" and not isinstance(other, (tuple, list)) and not (isinstance(other, Socket) and other.kind in VECTOR_TYPES):
                return self.builder.vmath("SCALE", self, other)
            if operation == "MULTIPLY" and self.kind not in VECTOR_TYPES:
                return self.builder.vmath("SCALE", other, self)
            if operation == "DIVIDE" and not isinstance(other, (tuple, list)) and not (isinstance(other, Socket) and other.kind in VECTOR_TYPES):
                return self.builder.vmath("SCALE", self, self.builder.math("DIVIDE", 1.0, other))
            return self.builder.vmath(operation, left, right)
        return self.builder.math(operation, left, right)

    def __add__(self, other):
        return self._binary("ADD", other)

    def __radd__(self, other):
        return self._binary("ADD", other, reverse=True)

    def __sub__(self, other):
        return self._binary("SUBTRACT", other)

    def __rsub__(self, other):
        return self._binary("SUBTRACT", other, reverse=True)

    def __mul__(self, other):
        return self._binary("MULTIPLY", other)

    def __rmul__(self, other):
        return self._binary("MULTIPLY", other, reverse=True)

    def __truediv__(self, other):
        return self._binary("DIVIDE", other)

    def __rtruediv__(self, other):
        return self._binary("DIVIDE", other, reverse=True)

    def __neg__(self):
        if self.kind in VECTOR_TYPES:
            return self.builder.vmath("SCALE", self, -1.0)
        return self.builder.math("MULTIPLY", self, -1.0)

    def __pow__(self, other):
        return self.builder.math("POWER", self, other)

    @property
    def x(self):
        return self.builder.separate(self)[0]

    @property
    def y(self):
        return self.builder.separate(self)[1]

    @property
    def z(self):
        return self.builder.separate(self)[2]


class NodeHandle:
    def __init__(self, builder, node):
        self.builder = builder
        self.node = node

    def __getitem__(self, key):
        return Socket(self.builder, self.builder.find_output(self.node, key))

    @property
    def out(self):
        return Socket(self.builder, self.builder.find_output(self.node, 0))

    def output(self, key):
        return self[key]


class TreeBuilder:
    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        self.group_input = None
        self.group_output = None
        self.interface_inputs = {}

    @classmethod
    def geometry(cls, name, is_modifier=False):
        tree = bpy.data.node_groups.get(name)
        if tree is None:
            tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
        tree.nodes.clear()
        tree.interface.clear()
        tree.is_modifier = is_modifier
        builder = cls(tree)
        builder.group_input = tree.nodes.new("NodeGroupInput")
        builder.group_output = tree.nodes.new("NodeGroupOutput")
        return builder

    @classmethod
    def shader(cls, material):
        tree = material.node_tree
        tree.nodes.clear()
        return cls(tree)

    @classmethod
    def shader_group(cls, name):
        tree = bpy.data.node_groups.get(name)
        if tree is None:
            tree = bpy.data.node_groups.new(name, "ShaderNodeTree")
        tree.nodes.clear()
        tree.interface.clear()
        builder = cls(tree)
        builder.group_input = tree.nodes.new("NodeGroupInput")
        builder.group_output = tree.nodes.new("NodeGroupOutput")
        return builder

    def input(self, name, kind, default=None, minimum=None, maximum=None, subtype=None, description="", panel=None):
        item = self.tree.interface.new_socket(name, in_out="INPUT", socket_type=SOCKET_CLASS[kind])
        if subtype is not None:
            item.subtype = subtype
        if default is not None and hasattr(item, "default_value"):
            item.default_value = default
        if minimum is not None and hasattr(item, "min_value"):
            item.min_value = minimum
        if maximum is not None and hasattr(item, "max_value"):
            item.max_value = maximum
        if description:
            item.description = description
        if panel is not None:
            self.tree.interface.move_to_parent(item, panel, len(panel.interface_items))
        self.interface_inputs[name] = item
        return Socket(self, self.group_input.outputs[item.identifier])

    def panel(self, name):
        return self.tree.interface.new_panel(name)

    def output(self, name, kind, value):
        item = self.tree.interface.new_socket(name, in_out="OUTPUT", socket_type=SOCKET_CLASS[kind])
        self.link(value, self.group_output.inputs[item.identifier])
        return item

    def find_output(self, node, key):
        if isinstance(key, int):
            available = [socket for socket in node.outputs if not socket.is_unavailable]
            return available[key]
        for socket in node.outputs:
            if socket.identifier == key and not socket.is_unavailable:
                return socket
        for socket in node.outputs:
            if socket.name == key and not socket.is_unavailable:
                return socket
        raise KeyError(f"{node.bl_idname} has no output {key!r}: {[socket.name for socket in node.outputs if not socket.is_unavailable]}")

    def find_input(self, node, key):
        if isinstance(key, int):
            available = [socket for socket in node.inputs if not socket.is_unavailable]
            return available[key]
        for socket in node.inputs:
            if socket.identifier == key and not socket.is_unavailable:
                return socket
        for socket in node.inputs:
            if socket.name == key and not socket.is_unavailable:
                return socket
        raise KeyError(f"{node.bl_idname} has no input {key!r}: {[socket.name for socket in node.inputs if not socket.is_unavailable]}")

    def link(self, value, target):
        if isinstance(value, NodeHandle):
            value = value.out
        if isinstance(value, Socket):
            self.links.new(value.socket, target)
            return
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, target)
            return
        if value is None:
            return
        if isinstance(value, (tuple, list)) and target.type == "RGBA" and len(value) == 3:
            value = (*value, 1.0)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and target.type == "VECTOR":
            value = (float(value),) * len(target.default_value)
        target.default_value = value

    def node(self, bl_idname, *positional, props=None, **named):
        node = self.nodes.new(bl_idname)
        for key, value in (props or {}).items():
            setattr(node, key, value)
        available = [socket for socket in node.inputs if not socket.is_unavailable]
        for index, value in enumerate(positional):
            if value is not None:
                self.link(value, available[index])
        for key, value in named.items():
            socket_key = key.replace("_", " ")
            candidates = [socket for socket in node.inputs if not socket.is_unavailable and (socket.identifier == key or socket.name in (key, socket_key))]
            if len(candidates) > 1 and isinstance(value, (tuple, list)):
                typed = [socket for socket in candidates if socket.type in ("RGBA", "VECTOR")]
                candidates = typed or candidates
            elif len(candidates) > 1 and isinstance(value, (int, float)):
                typed = [socket for socket in candidates if socket.type in ("VALUE", "INT")]
                candidates = typed or candidates
            if not candidates:
                raise KeyError(f"{node.bl_idname} has no input {key!r}: {[socket.name for socket in node.inputs if not socket.is_unavailable]}")
            self.link(value, candidates[0])
        return NodeHandle(self, node)

    def math(self, operation, a, b=None, c=None, clamp=False):
        return self.node("ShaderNodeMath", a, b, c, props={"operation": operation, "use_clamp": clamp}).out

    def vmath(self, operation, a, b=None, c=None):
        handle = self.node("ShaderNodeVectorMath", props={"operation": operation})
        available = [socket for socket in handle.node.inputs if not socket.is_unavailable]
        values = [a, b, c]
        vector_inputs = [socket for socket in available if socket.type == "VECTOR"]
        scale_inputs = [socket for socket in available if socket.type == "VALUE"]
        cursor = 0
        for value in values:
            if value is None:
                continue
            if cursor < len(vector_inputs) and not (operation in ("SCALE",) and cursor == 1) and not (operation == "REFRACT" and cursor == 2):
                self.link(value, vector_inputs[cursor])
            else:
                self.link(value, scale_inputs[0])
            cursor += 1
        output_name = "Value" if operation in ("DOT_PRODUCT", "DISTANCE", "LENGTH") else "Vector"
        return handle[output_name]

    def combine(self, x=0.0, y=0.0, z=0.0):
        return self.node("ShaderNodeCombineXYZ", x, y, z).out

    def separate(self, vector):
        handle = self.node("ShaderNodeSeparateXYZ", vector)
        return handle["X"], handle["Y"], handle["Z"]

    def value(self, number):
        handle = self.node("ShaderNodeValue")
        handle.node.outputs[0].default_value = number
        return handle.out

    def vector(self, values):
        handle = self.node("FunctionNodeInputVector")
        handle.node.vector = values
        return handle.out

    def integer(self, number):
        handle = self.node("FunctionNodeInputInt")
        handle.node.integer = number
        return handle.out

    def map_range(self, value, from_min=0.0, from_max=1.0, to_min=0.0, to_max=1.0, clamp=True, interpolation="LINEAR"):
        return self.node("ShaderNodeMapRange", value, from_min, from_max, to_min, to_max, props={"clamp": clamp, "interpolation_type": interpolation, "data_type": "FLOAT"}).out

    def clamp(self, value, minimum=0.0, maximum=1.0):
        return self.node("ShaderNodeClamp", value, minimum, maximum).out

    def mix(self, factor, a, b, data_type="FLOAT", blend="MIX", clamp=True):
        handle = self.node("ShaderNodeMix", props={"data_type": data_type, "blend_type": blend, "clamp_factor": clamp})
        available = [socket for socket in handle.node.inputs if not socket.is_unavailable]
        self.link(factor, available[0])
        self.link(a, available[1])
        self.link(b, available[2])
        return handle.out

    def compare(self, a, b, operation="GREATER_THAN", data_type="FLOAT"):
        handle = self.node("FunctionNodeCompare", props={"data_type": data_type, "operation": operation})
        available = [socket for socket in handle.node.inputs if not socket.is_unavailable]
        self.link(a, available[0])
        self.link(b, available[1])
        return handle.out

    def boolean(self, operation, a, b=None):
        return self.node("FunctionNodeBooleanMath", a, b, props={"operation": operation}).out

    def switch(self, condition, false_value, true_value, input_type="GEOMETRY"):
        return self.node("GeometryNodeSwitch", condition, false_value, true_value, props={"input_type": input_type}).out

    def random(self, minimum=0.0, maximum=1.0, seed=0, data_type="FLOAT", identifier=None, probability=None):
        handle = self.node("FunctionNodeRandomValue", props={"data_type": data_type})
        available = [socket for socket in handle.node.inputs if not socket.is_unavailable]
        if data_type == "BOOLEAN":
            self.link(probability if probability is not None else 0.5, available[0])
            self.link(identifier, available[1])
            self.link(seed, available[2])
        else:
            self.link(minimum, available[0])
            self.link(maximum, available[1])
            self.link(identifier, available[2])
            self.link(seed, available[3])
        return handle.out

    def euler(self, vector):
        return self.node("FunctionNodeEulerToRotation", vector).out

    def align_z(self, direction, axis="Z"):
        return self.node("FunctionNodeAlignRotationToVector", props={"axis": axis}, Vector=direction).out

    def position(self):
        return self.node("GeometryNodeInputPosition").out

    def normal(self):
        return self.node("GeometryNodeInputNormal")["Normal"]

    def index(self):
        return self.node("GeometryNodeInputIndex").out

    def transform(self, geometry, translation=None, rotation=None, scale=None):
        rotation_socket = self.euler(rotation) if isinstance(rotation, (tuple, list)) or (isinstance(rotation, Socket) and rotation.kind == "VECTOR") else rotation
        return self.node("GeometryNodeTransform", Geometry=geometry, Translation=translation, Rotation=rotation_socket, Scale=scale).out

    def join(self, *geometries):
        handle = self.node("GeometryNodeJoinGeometry")
        target = handle.node.inputs[0]
        for geometry in reversed([item for item in geometries if item is not None]):
            self.link(geometry, target)
        return handle.out

    def set_material(self, geometry, material, selection=None):
        return self.node("GeometryNodeSetMaterial", Geometry=geometry, Selection=selection, Material=material).out

    def smooth(self, geometry, smooth=True, selection=None):
        return self.node("GeometryNodeSetShadeSmooth", Mesh=geometry, Selection=selection, Shade_Smooth=smooth).out

    def realize(self, geometry):
        return self.node("GeometryNodeRealizeInstances", Geometry=geometry).out

    def store(self, geometry, name, value, data_type="FLOAT", domain="POINT", selection=None):
        return self.node("GeometryNodeStoreNamedAttribute", props={"data_type": data_type, "domain": domain}, Geometry=geometry, Selection=selection, Name=name, Value=value).out

    def named(self, name, data_type="FLOAT"):
        return self.node("GeometryNodeInputNamedAttribute", props={"data_type": data_type}, Name=name)["Attribute"]

    def set_position(self, geometry, position=None, offset=None, selection=None):
        return self.node("GeometryNodeSetPosition", Geometry=geometry, Selection=selection, Position=position, Offset=offset).out

    def instance(self, points, instance, rotation=None, scale=None, selection=None, pick=False, instance_index=None):
        return self.node("GeometryNodeInstanceOnPoints", Points=points, Selection=selection, Instance=instance, Pick_Instance=pick, Instance_Index=instance_index, Rotation=rotation, Scale=scale).out

    def curve_to_mesh(self, curve, profile=None, fill_caps=False, scale=None):
        return self.node("GeometryNodeCurveToMesh", Curve=curve, Profile_Curve=profile, Fill_Caps=fill_caps, Scale=scale).out

    def curve_to_mesh_by_radius(self, curve, profile, fill_caps=False):
        return self.curve_to_mesh(curve, profile, fill_caps=fill_caps, scale=self.node("GeometryNodeInputRadius").out)

    def group(self, tree, **inputs):
        handle = self.node("GeometryNodeGroup" if self.tree.bl_idname == "GeometryNodeTree" else "ShaderNodeGroup")
        handle.node.node_tree = tree
        for key, value in inputs.items():
            socket_key = key.replace("_", " ")
            try:
                target = self.find_input(handle.node, socket_key)
            except KeyError:
                target = self.find_input(handle.node, key)
            self.link(value, target)
        return handle

    def arrange(self):
        depth = {}
        incoming = {node: [] for node in self.nodes}
        for link in self.links:
            incoming[link.to_node].append(link.from_node)

        def resolve(node, stack=()):
            if node in depth:
                return depth[node]
            if node in stack:
                return 0
            parents = incoming[node]
            value = 0 if not parents else 1 + max(resolve(parent, stack + (node,)) for parent in parents)
            depth[node] = value
            return value

        for node in self.nodes:
            resolve(node)
        if self.group_output is not None:
            depth[self.group_output] = max(depth.values(), default=0) + 1
        columns = {}
        for node, column in depth.items():
            columns.setdefault(column, []).append(node)
        placed_y = {}
        for column in sorted(columns):
            members = columns[column]

            def key(node):
                parents = [placed_y[parent] for parent in incoming[node] if parent in placed_y]
                return -(sum(parents) / len(parents)) if parents else 0.0

            members.sort(key=key)
            cursor = 0.0
            for node in members:
                visible = sum(1 for socket in node.inputs if not socket.is_unavailable and not socket.hide) + sum(1 for socket in node.outputs if not socket.is_unavailable and not socket.hide)
                height = 60 + 22 * visible
                node.location = (column * 260.0, -cursor)
                placed_y[node] = -cursor - height / 2
                cursor += height + 30
