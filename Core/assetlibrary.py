"""
Core.assetlibrary -- a kit's geometry-node assets as a Blender asset library.

:func:`export` writes the node groups a package registered with
:func:`Core.gn.asset` to ``<root>/<category>/<pack>.blend``, one file per
category.  Every group in a file is marked as an asset in the catalog
``<pack>/<category>`` and set up as a modifier, so it can be dragged onto an
object from the Asset Browser.  A file carries everything its groups need
-- the groups they nest and their materials -- so any one of them can be
appended on its own.  The catalogs go to ``<root>/blender_assets.cats.txt``;
add ``root`` as an asset library in Blender's preferences to browse them.

Catalog identifiers are derived from the catalog path, so re-exporting a
pack keeps the catalogs of assets already placed in other files.
"""
from __future__ import annotations

import os
import uuid

import bpy

from .gn import ASSETS, get_asset

__all__ = ["export", "package_assets", "catalog_id"]

CATALOG_NAMESPACE = uuid.UUID("5d0e8a3c-6c1f-4f7e-9a4b-2f8e1c7d9b60")
CATALOG_FILE = "blender_assets.cats.txt"


def package_assets(package):
    """Names of the assets whose builders live in ``package`` (and its
    sub-packages)."""
    prefix = package + "."
    return sorted(name for name, entry in ASSETS.items() if entry["fn"].__module__.startswith(prefix))


def catalog_id(path):
    return str(uuid.uuid5(CATALOG_NAMESPACE, path))


def _mark(group, catalog, description, tags):
    group.is_modifier = True
    group.asset_mark()
    data = group.asset_data
    data.catalog_id = catalog
    data.description = description
    for tag in tags:
        data.tags.new(tag, skip_if_exists=True)


def export(root, package, pack=None):
    """Write the asset library of ``package`` to ``root``; ``pack`` names
    the files and the catalog root (default: the package name).  Returns
    the written ``.blend`` paths."""
    pack = pack or package
    names = package_assets(package)
    if not names:
        raise ValueError(f"package {package!r} registered no assets")
    categories = {}
    for name in names:
        categories.setdefault(ASSETS[name]["category"], []).append(name)
    root = os.path.abspath(root)
    written = []
    for category, members in sorted(categories.items()):
        groups = [get_asset(name) for name in members]
        catalog = catalog_id(f"{pack}/{category}")
        for name, group in zip(members, groups):
            _mark(group, catalog, ASSETS[name]["doc"], (pack, category))
        folder = os.path.join(root, category)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{pack}.blend")
        bpy.data.libraries.write(path, set(groups), path_remap="RELATIVE_ALL", fake_user=True, compress=True)
        for group in groups:
            group.asset_clear()
        written.append(path)
    _write_catalogs(os.path.join(root, CATALOG_FILE), pack, sorted(categories))
    return written


def _write_catalogs(path, pack, categories):
    """The catalog file with this pack's catalogs replaced and every other
    pack's kept."""
    kept = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle.read().splitlines():
                fields = line.split(":")
                if len(fields) == 3 and not (fields[1] == pack or fields[1].startswith(f"{pack}/")):
                    kept.append(line)
    ours = [f"{catalog_id(f'{pack}/{category}')}:{pack}/{category}:{pack}-{category}" for category in categories]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(["VERSION 1", ""] + kept + ours) + "\n")
