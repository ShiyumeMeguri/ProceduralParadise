"""Rain Garden (雨花之庭) -- an aquarium atrium of falling water under a glass vault.

Sub-packages
------------
Kit      geometry-node assets (architecture, water, lights, plants,
         creatures, decorative) and the material library
Scenes   scene definitions (one folder per scene) assembled from the kit

``REALM`` is the design system loaded from ``Realm.json``: the material
definitions every kit asset shares.  Colours live inside them, so the realm
has no separate palette.
"""
import os

from Core import jsonio

HERE = os.path.dirname(os.path.abspath(__file__))

REALM = jsonio.load(os.path.join(HERE, "Realm.json"))

PALETTE = {}
MATERIALS = REALM["materials"]
