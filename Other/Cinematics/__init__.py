"""Cinematics (影片) -- short films rebuilt shot by shot from a reference
video: their sets, the cast that plays in them and every shot's camera.

Sub-packages
------------
Kit      geometry-node assets: the architecture of the sets (frame towers
         built from modular facade panels, the skyline), the sky, the
         effects (birds, debris, dust) and the material library (EEVEE)
<Film>/  one folder per film: ``film.json`` (cast, sets, shots, cadence),
         its sets, shots and performances, the calibration that measured
         them on the reference video, renders and README

``CINEMATICS`` is the design system loaded from ``Cinematics.json``: the
palette and the finishes every set of the family is made of.
"""
import os

from Core import jsonio

HERE = os.path.dirname(os.path.abspath(__file__))

CINEMATICS = jsonio.load(os.path.join(HERE, "Cinematics.json"))

PALETTE = {key: tuple(value) for key, value in CINEMATICS["palette"].items()}
FINISHES = CINEMATICS["finishes"]
