"""
Weapons material library (``WPN.*``), made for EEVEE.

Every finish is a row of the design system's ``finishes`` (``Weapons.json``)
built by one builder (:func:`finish`): a palette ``color``, its
``roughness`` and ``metallic``ness, and for a light its ``emission``
strength.  A weapon may override parameters and palette colours
(``"color:<key>"``) through ``PARAMS`` before anything is built -- its
studio fit leaves the colours its finishes are lit to there.
"""
from __future__ import annotations

import bpy

from Core import shaders as S
from Core.nodes import Tree
from .. import FINISHES, PALETTE

LIBRARY = S.MaterialLibrary(PALETTE, "weapons_built")
PARAMS = LIBRARY.params
register = LIBRARY.register
get = LIBRARY.get
color = LIBRARY.color
param = LIBRARY.param


def finish(name):
    """Material ``name`` from its row of ``finishes``."""
    spec = FINISHES[name]

    def build(tree: Tree):
        tint = color(spec["color"])
        inputs = dict(Base_Color=tint, Roughness=param(f"{name}.roughness", spec["roughness"]), Metallic=spec.get("metallic", 0.0),
                      Specular_IOR_Level=spec.get("specular", 0.5))
        if "emission" in spec:
            inputs.update(Emission_Color=tint, Emission_Strength=param(f"{name}.emission", spec["emission"]))
        return S.bsdf(tree, **inputs)["BSDF"]
    return S.material(name, build)


for _name in FINISHES:
    register(_name)(lambda _name=_name: finish(_name))


def studio_world(spec):
    """The studio world: the soft gradient of ``spec`` (``top``, ``horizon``,
    ``bottom``, linear RGB) at ``strength``, which lights the weapon and
    fills its reflections.  It casts no shadows of its own (EEVEE would
    pick its brightest part as a sun): the weapon's shadows are its soft
    boxes'.  The paper a sheet is drawn on is no part of it -- a shot lays
    its transparent render on the paper (its look's ``backdrop``)."""
    target = S.new_world(spec.get("name", "Studio"))
    tree = Tree.wrap(target.node_tree, clear=True)
    height = tree.n("ShaderNodeTexCoord")["Generated"].normalized().z
    upper = tree.mix(tree.clamp01(height * 1.6), tuple(spec["horizon"]), tuple(spec["top"]), "RGBA")
    lower = tree.mix(tree.clamp01(height * -3.0), tuple(spec["horizon"]), tuple(spec["bottom"]), "RGBA")
    shade = tree.mix(tree.math("GREATER_THAN", height, 0.0), lower, upper, "RGBA")
    light = tree.n("ShaderNodeEmission", Color=shade, Strength=spec.get("strength", 1.0))["Emission"]
    tree.link(light, tree.n("ShaderNodeOutputWorld").n.inputs["Surface"])
    tree.layout()
    target.use_sun_shadow = False
    target.sun_threshold = 1000.0
    bpy.context.scene.world = target
    return target
