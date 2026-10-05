"""Weapons (武器) -- weapons from design sheets that belong to no world.

Sub-packages
------------
Kit      geometry-node assets: solids built from outlines traced on a design
         sheet (plates, rings, a lofted blade, lettering and painted strokes)
         and the material library (EEVEE)
<Name>/  one folder per weapon: its parts (``weapon.json``), the outlines
         traced on its sheet (``trace.json``), shots, reference and renders

``WEAPONS`` is the design system loaded from ``Weapons.json``: the palette,
the finishes made from it and the studio a weapon is shown in.
"""
import os

from Core import jsonio

HERE = os.path.dirname(os.path.abspath(__file__))

WEAPONS = jsonio.load(os.path.join(HERE, "Weapons.json"))

PALETTE = {key: tuple(value) for key, value in WEAPONS["palette"].items()}
FINISHES = WEAPONS["finishes"]
STUDIO = WEAPONS["studio"]
