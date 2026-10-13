import importlib
import pkgutil
import uuid
from pathlib import Path

import bpy

from . import modules as module_package
from .context import BuildContext
from .materials import MaterialLibrary

PACK_NAME = "RainGarden"
MATERIAL_CATEGORY = "Materials"
CATEGORY_ORDER = ["Architecture", "Water", "Plants", "Creatures", "Decorative", "Lights"]
CATALOG_NAMESPACE = uuid.UUID("6f1d3c2a-4b8e-4f5a-9c7d-2e1b0a9f8d7c")


def discover_modules():
    found = {}
    for info in pkgutil.iter_modules(module_package.__path__):
        module = importlib.import_module(f"rain_garden.modules.{info.name}")
        found[module.GROUP_NAME] = module
    return found


def catalog_id(category):
    return str(uuid.uuid5(CATALOG_NAMESPACE, f"Procedural/{category}"))


def category_file(root, category):
    return Path(root) / category / f"{PACK_NAME}.blend"


def mark_asset(data_block, category, description, tags):
    data_block.asset_mark()
    data_block.asset_data.catalog_id = catalog_id(category)
    data_block.asset_data.description = description
    for tag in tags:
        data_block.asset_data.tags.new(tag, skip_if_exists=True)


def write_catalogs(root, categories):
    lines = ["VERSION 1", ""]
    for category in categories:
        lines.append(f"{catalog_id(category)}:Procedural/{category}:Procedural-{category}")
    (Path(root) / "blender_assets.cats.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


class LinkedMaterials:
    def __init__(self, materials_file):
        self.materials_file = materials_file
        self.cache = {}

    def __getitem__(self, name):
        if name not in self.cache:
            with bpy.data.libraries.load(str(self.materials_file), link=True, relative=True) as (source, target):
                if name not in source.materials:
                    raise KeyError(f"material {name!r} is not in {self.materials_file}")
                target.materials = [name]
            self.cache[name] = target.materials[0]
        return self.cache[name]


class CategoryContext(BuildContext):
    def __init__(self, materials, registry):
        super().__init__(materials)
        self.registry = registry


def build_materials_file(root, palette):
    bpy.ops.wm.read_homefile(use_empty=True)
    path = category_file(root, MATERIAL_CATEGORY)
    path.parent.mkdir(parents=True, exist_ok=True)
    library = MaterialLibrary(palette)
    for name in palette:
        material = library[name]
        mark_asset(material, MATERIAL_CATEGORY, palette[name].get("description", name), ["RainGarden", "Material"])
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    return path


def build_library(root, palette, log):
    registry = discover_modules()
    materials_path = build_materials_file(root, palette)
    log(f"LIBRARY materials -> {materials_path}")
    built = []
    for category in CATEGORY_ORDER:
        names = sorted(name for name, module in registry.items() if module.CATEGORY == category)
        if not names:
            continue
        bpy.ops.wm.read_homefile(use_empty=True)
        path = category_file(root, category)
        path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
        context = CategoryContext(LinkedMaterials(materials_path), registry)
        for name in names:
            tree = context.require(name)
            module = registry[name]
            mark_asset(tree, category, module.DESCRIPTION, ["RainGarden", category])
        bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True, relative_remap=True)
        built.append(category)
        log(f"LIBRARY {category}: {len(names)} groups -> {path}")
    write_catalogs(root, [MATERIAL_CATEGORY] + built)
    return registry
