"""Shanhaijing Senior Secondary School (山海经高级中学) -- academy package.

Sub-packages
------------
Kit     modular geometry-node assets (architecture, furniture, props, emblem)
Rooms   room definitions (one folder per room) built from the kit

``ACADEMY`` holds the design system loaded from ``Academy.json``; kit assets
take their default dimensions and colours from it so every Shanhaijing room
shares one architectural language.
"""
import os

from Core import jsonio

HERE = os.path.dirname(os.path.abspath(__file__))

ACADEMY = jsonio.load(os.path.join(HERE, "Academy.json"))

PALETTE = {k: tuple(v) for k, v in ACADEMY["palette"].items()}
LEVELS = ACADEMY["levels"]
TIMBER = ACADEMY["timber"]
FURN = ACADEMY["furniture"]
FLOOR = ACADEMY["floor"]
