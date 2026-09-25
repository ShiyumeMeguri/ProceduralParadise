"""Millennium Science School (千年科学学园) -- academy package.

Sub-packages
------------
Kit     modular geometry-node assets (architecture, furniture, fixtures, emblem)
Campus  campus master plan + tower generator (exterior)
Rooms   room definitions (one folder per room) built from the kit

``ACADEMY`` holds the design system loaded from ``Academy.json``; every kit
asset reads its defaults from it so the whole academy stays dimensionally and
visually consistent.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "Academy.json"), encoding="utf-8") as _f:
    ACADEMY = json.load(_f)

PALETTE = {k: tuple(v) for k, v in ACADEMY["palette"].items()}
MOD = ACADEMY["modules"]
LEVELS = ACADEMY["levels"]
CW = ACADEMY["curtain_wall"]
