"""Crystal Fantasy (水晶幻想) -- a crystal conservatory floating in a starry void.

Sub-packages
------------
Kit      geometry-node assets (crystals, flora, vessels, displays,
         architecture, particles) and the material library
Scenes   scene definitions (one folder per scene) assembled from the kit

``REALM`` is the design system loaded from ``Realm.json``: palette, flower
presets and vessel profiles.  Kit assets take their shapes and colours from
it, so every scene of the realm shares one visual language.
"""
import os

from Core import jsonio

HERE = os.path.dirname(os.path.abspath(__file__))

REALM = jsonio.load(os.path.join(HERE, "Realm.json"))

PALETTE = {key: tuple(value) for key, value in REALM["palette"].items()}
FLOWERS = REALM["flowers"]
PROFILES = REALM["profiles"]
