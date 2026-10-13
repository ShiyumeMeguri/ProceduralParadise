import importlib

import bpy

from .gn import TreeBuilder


class BuildContext:
    def __init__(self, materials):
        self.materials = materials
        self.groups = {}
        self.registry = {}

    def register(self, module_name):
        module = importlib.import_module(f"rain_garden.modules.{module_name}")
        self.registry[module.GROUP_NAME] = module
        return module.GROUP_NAME

    def require(self, group_name):
        if group_name in self.groups:
            return self.groups[group_name]
        module = self.registry[group_name]
        builder = TreeBuilder.geometry(group_name, is_modifier=getattr(module, "IS_MODIFIER", True))
        module.build(builder, self)
        builder.arrange()
        self.groups[group_name] = builder.tree
        return builder.tree

    def material(self, name):
        return self.materials[name]
