"""Props (杂物) -- small interactive props that belong to no world, each a
simulation on a studio tabletop.

Sub-packages
------------
Kit      geometry-node assets: the props' shapes, their simulations (on
         Core.physics) and the material library (EEVEE)
<Prop>/  one folder per prop (scene.json, shots, README) assembled from the kit

``PROPS`` is the design system loaded from ``Props.json``: palette and
liquid presets.
"""
import os

from Core import jsonio

HERE = os.path.dirname(os.path.abspath(__file__))

PROPS = jsonio.load(os.path.join(HERE, "Props.json"))

PALETTE = {key: tuple(value) for key, value in PROPS["palette"].items()}
LIQUIDS = PROPS["liquids"]
