"""Shanhaijing Senior Secondary School (山海经高级中学) -- academy package.

Sub-packages
------------
Kit     modular geometry-node assets (architecture, furniture, props, emblem)
Rooms   room definitions (one folder per room) built from the kit

``ACADEMY`` holds the design system loaded from ``Academy.json``; kit assets
take their default dimensions and colours from it so every Shanhaijing room
shares one architectural language.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "Academy.json"), encoding="utf-8") as _f:
    ACADEMY = json.load(_f)

PALETTE = {k: tuple(v) for k, v in ACADEMY["palette"].items()}
LEVELS = ACADEMY["levels"]
TIMBER = ACADEMY["timber"]
FURN = ACADEMY["furniture"]
FLOOR = ACADEMY["floor"]
