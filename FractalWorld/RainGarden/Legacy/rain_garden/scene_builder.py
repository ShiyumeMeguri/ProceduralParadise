import math
from pathlib import Path

import bpy

from mathutils import Matrix, Vector

from .library import MATERIAL_CATEGORY, category_file
from .look import apply_look


def oriented_euler(local_x, local_z):
    x_axis = Vector(local_x).normalized()
    z_axis = Vector(local_z)
    z_axis = (z_axis - x_axis * z_axis.dot(x_axis)).normalized()
    y_axis = z_axis.cross(x_axis)
    return Matrix((x_axis, y_axis, z_axis)).transposed().to_euler("XYZ")


class SceneBuilder:
    def __init__(self, layout, library_root, registry, log):
        self.layout = layout
        self.library_root = library_root
        self.registry = registry
        self.log = log
        self.groups = {}
        self.materials = {}
        self.curves = {}
        self.objects = {}
        self.collections = {}

    def linked_group(self, name):
        if name not in self.groups:
            path = category_file(self.library_root, self.registry[name].CATEGORY)
            with bpy.data.libraries.load(str(path), link=True, relative=True) as (source, target):
                target.node_groups = [name]
            self.groups[name] = target.node_groups[0]
        return self.groups[name]

    def linked_material(self, name):
        if name not in self.materials:
            path = category_file(self.library_root, MATERIAL_CATEGORY)
            with bpy.data.libraries.load(str(path), link=True, relative=True) as (source, target):
                target.materials = [name]
            self.materials[name] = target.materials[0]
        return self.materials[name]

    def collection(self, path):
        if path in self.collections:
            return self.collections[path]
        parent = bpy.context.scene.collection
        built = ""
        for part in path.split("/"):
            built = f"{built}/{part}" if built else part
            if built not in self.collections:
                collection = bpy.data.collections.new(part)
                parent.children.link(collection)
                self.collections[built] = collection
            parent = self.collections[built]
        return self.collections[path]

    def build_curves(self):
        guides = self.collection("Guides")
        for name, definition in self.layout.get("curves", {}).items():
            data = bpy.data.curves.new(name, type="CURVE")
            data.dimensions = "3D"
            spline = data.splines.new(definition.get("type", "POLY"))
            points = definition["points"]
            spline.points.add(len(points) - 1)
            for point, coordinates in zip(spline.points, points):
                point.co = (*coordinates, 1.0)
            spline.use_cyclic_u = definition.get("cyclic", False)
            if definition.get("type") == "NURBS":
                spline.use_endpoint_u = True
                spline.order_u = definition.get("order", 3)
            obj = bpy.data.objects.new(name, data)
            obj.hide_render = True
            obj.display_type = "WIRE"
            guides.objects.link(obj)
            self.curves[name] = obj

    def resolve_value(self, value):
        if isinstance(value, dict):
            if "curve" in value:
                return self.curves[value["curve"]]
            if "material" in value:
                return self.linked_material(value["material"])
            if "object" in value:
                return self.objects[value["object"]]
            raise ValueError(f"unknown reference {value}")
        if isinstance(value, list):
            return tuple(value)
        return value

    def set_inputs(self, modifier, group, inputs):
        items = {item.name: item for item in group.interface.items_tree if item.item_type == "SOCKET" and item.in_out == "INPUT"}
        for name, value in inputs.items():
            if name not in items:
                raise KeyError(f"{group.name} has no input {name!r}; available: {sorted(items)}")
            getattr(modifier.properties.inputs, items[name].identifier).value = self.resolve_value(value)

    def build_instances(self):
        for definition in self.layout["instances"]:
            group = self.linked_group(definition["group"])
            if "source_curve" in definition:
                data = self.curves[definition["source_curve"]].data.copy()
                data.name = definition["name"]
            else:
                data = bpy.data.meshes.new(definition["name"])
            obj = bpy.data.objects.new(definition["name"], data)
            self.collection(definition.get("collection", "Scene")).objects.link(obj)
            obj.location = definition.get("location", (0.0, 0.0, 0.0))
            if "orient" in definition:
                obj.rotation_euler = oriented_euler(definition["orient"]["x"], definition["orient"]["z"])
            else:
                obj.rotation_euler = [math.radians(angle) for angle in definition.get("rotation_degrees", (0.0, 0.0, 0.0))]
            obj.scale = definition.get("scale", (1.0, 1.0, 1.0))
            modifier = obj.modifiers.new(definition["group"], "NODES")
            modifier.node_group = group
            self.objects[definition["name"]] = obj
        for definition in self.layout["instances"]:
            obj = self.objects[definition["name"]]
            modifier = obj.modifiers[0]
            self.set_inputs(modifier, modifier.node_group, definition.get("inputs", {}))

    def build_camera(self):
        settings = self.layout["camera"]
        data = bpy.data.cameras.new("Main Camera")
        data.lens = settings["focal_millimeters"]
        data.sensor_fit = "HORIZONTAL"
        data.sensor_width = settings["sensor_width"]
        data.clip_start = settings.get("clip_start", 0.05)
        data.clip_end = settings.get("clip_end", 3000.0)
        camera = bpy.data.objects.new("Main Camera", data)
        camera.location = settings["location"]
        camera.rotation_euler = [math.radians(angle) for angle in settings["rotation_degrees"]]
        self.collection("Cameras").objects.link(camera)
        bpy.context.scene.camera = camera

    def apply_render_preset(self, preset_name):
        preset = self.layout["render_presets"][preset_name]
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y = self.layout["resolution"]
        scene.render.resolution_percentage = preset.get("percentage", 100)
        scene.render.engine = preset["engine"]
        if preset["engine"] == "BLENDER_WORKBENCH":
            shading = scene.display.shading
            shading.light = preset.get("light", "STUDIO")
            shading.color_type = preset.get("color_type", "MATERIAL")
            shading.show_object_outline = True
            shading.show_cavity = preset.get("cavity", True)
            scene.display.render_aa = "8"
        else:
            scene.cycles.samples = preset.get("samples", 64)
            scene.cycles.use_denoising = preset.get("denoise", True)
            scene.cycles.device = "GPU"
            for key, value in preset.get("cycles", {}).items():
                setattr(scene.cycles, key, value)

    def build(self, preset_name):
        scene = bpy.context.scene
        scene.name = self.layout.get("scene_name", "Rain Garden")
        scene.unit_settings.system = "METRIC"
        self.build_curves()
        self.build_instances()
        self.build_camera()
        apply_look(self.layout, self.collection("Lights"))
        self.apply_render_preset(preset_name)
