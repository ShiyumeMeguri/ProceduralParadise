"""Greenhouse (温室) -- glass conservatories that belong to no world.

Sub-packages
------------
Kit      geometry-node assets: the steel-and-glass structure, furniture,
         glassware, plants and the outdoor backdrop, and the material
         library (Cycles)
Scenes   scene definitions (one folder per space) assembled from the kit

``GREENHOUSE`` is the design system loaded from ``Greenhouse.json``: the
palette, the glasses and the plant presets every scene of the family
shares.
"""
import os

from Core import jsonio

HERE = os.path.dirname(os.path.abspath(__file__))

GREENHOUSE = jsonio.load(os.path.join(HERE, "Greenhouse.json"))

PALETTE = {key: tuple(value) for key, value in GREENHOUSE["palette"].items()}
GLASSES = GREENHOUSE["glasses"]
ROOM = GREENHOUSE["reflection_room"]
PLANTS = GREENHOUSE["plants"]
