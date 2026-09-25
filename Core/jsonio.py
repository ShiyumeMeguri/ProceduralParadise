"""Core.jsonio -- human-friendly JSON: numeric/short lists stay on one line.

Every build input is read through :func:`load`, which records the file in
``LOADED``; together with the project modules a build imported, these are
the sources its renders depend on."""
from __future__ import annotations

import json
import os

__all__ = ["dumps", "dump", "load", "LOADED"]

LOADED: set = set()


def _inline(v):
    return isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v) and len(v) <= 8


def dumps(obj, indent=2, _lvl=0):
    pad = " " * (indent * (_lvl + 1))
    end = " " * (indent * _lvl)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent, _lvl + 1)}" for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + "\n" + end + "}"
    if isinstance(obj, list):
        if _inline(obj):
            return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in obj) + "]"
        if all(isinstance(x, list) and _inline(x) for x in obj) and len(obj) <= 12:
            return "[" + ", ".join(dumps(x, indent, _lvl + 1) for x in obj) + "]"
        items = [f"{pad}{dumps(v, indent, _lvl + 1)}" for v in obj]
        return "[\n" + ",\n".join(items) + "\n" + end + "]"
    return json.dumps(obj, ensure_ascii=False)


def dump(obj, path, indent=2):
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(obj, indent) + "\n")


def load(path):
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    LOADED.add(path)
    return data
