"""
Cinematics material library (``CIN.*``), made for EEVEE.

Every finish is a row of the design system's ``finishes``
(``Cinematics.json``) built by one builder (:func:`finish`): a palette
``color`` and its ``roughness`` and ``metallic``ness, weathered towards
``grime_color`` in broad patches (``grime``: strength, size in metres) and
in streaks down vertical faces (``streaks``: strength, spacing in metres).
Weathering is laid in world space, so instanced modules weather each in
their own place.  A film's set may override parameters and palette colours
(``"color:<key>"``) through ``PARAMS`` before anything is built.
"""
from __future__ import annotations

from Core import shaders as S
from Core.nodes import Tree
from .. import FINISHES, PALETTE

LIBRARY = S.MaterialLibrary(PALETTE, "cinematics_built")
PARAMS = LIBRARY.params
register = LIBRARY.register
get = LIBRARY.get
color = LIBRARY.color
param = LIBRARY.param


def weathering(tree: Tree, name, spec):
    """Grime factor 0..1 of the finish ``name`` at the shading point."""
    position = tree.n("ShaderNodeNewGeometry")["Position"]
    normal = tree.n("ShaderNodeNewGeometry")["Normal"]
    grime_strength, grime_size = param(f"{name}.grime", spec["grime"])
    streak_strength, streak_spacing = param(f"{name}.streaks", spec["streaks"])
    patches = tree.n("ShaderNodeTexNoise", Vector=position, Scale=1.0 / grime_size, Detail=6.0, Roughness=0.62,
                     props={"noise_dimensions": "3D"})["Fac"]
    patches = tree.map_range(patches, 0.42, 0.78, 0.0, 1.0)
    stretched = tree.vmath("MULTIPLY", position, (1.0 / streak_spacing, 1.0 / streak_spacing, 0.08 / streak_spacing))
    streaks = tree.n("ShaderNodeTexNoise", Vector=stretched, Scale=1.0, Detail=3.0, Roughness=0.5,
                     props={"noise_dimensions": "3D"})["Fac"]
    upright = 1.0 - tree.abs(normal.z)
    streaks = tree.map_range(streaks, 0.5, 0.75, 0.0, 1.0) * upright
    return tree.clamp01(patches * grime_strength + streaks * streak_strength)


def finish(name):
    """Material ``name`` from its row of ``finishes``."""
    spec = FINISHES[name]

    def build(tree: Tree):
        grime = weathering(tree, name, spec)
        tint = tree.mix(grime, color(spec["color"]), color(spec["grime_color"]), "RGBA")
        roughness = param(f"{name}.roughness", spec["roughness"])
        return S.bsdf(tree, Base_Color=tint, Roughness=tree.clamp01(roughness + grime * 0.15),
                      Metallic=spec.get("metallic", 0.0))["BSDF"]
    return S.material(name, build)


for _name in FINISHES:
    register(_name)(lambda _name=_name: finish(_name))


@register("CIN.Glass")
def glass():
    """Window glass: clear for light, a faint grey film for the camera and
    a Fresnel sheen of the sky."""
    return S.glass_mat("CIN.Glass", color=color("glass")[:3], roughness=param("CIN.Glass.roughness", 0.05),
                       reflect=param("CIN.Glass.reflect", 1.0))


@register("CIN.Crow")
def crow():
    """Crow feathers: near-black, a soft blue-grey sheen at grazing angles."""
    def build(tree: Tree):
        return S.bsdf(tree, Base_Color=color("crow"), Roughness=param("CIN.Crow.roughness", 0.55),
                      Sheen_Weight=param("CIN.Crow.sheen", 0.35), Sheen_Tint=(0.55, 0.6, 0.7, 1.0))["BSDF"]
    return S.material("CIN.Crow", build)


@register("CIN.Cloud")
def cloud():
    """Cumulus: a white body that the sun lights and the blue sky fills in the shade, light
    carried a little way through it (subsurface, metres deep) so its folds read soft, a silver
    sheen at grazing angles, and a silhouette that thins out where the surface turns away."""
    def build(tree: Tree):
        body = S.bsdf(tree, Base_Color=color("cloud"), Roughness=1.0, Subsurface_Weight=param("CIN.Cloud.subsurface", 0.6),
                      Subsurface_Radius=(1.0, 1.0, 1.0), Subsurface_Scale=param("CIN.Cloud.depth", 18.0),
                      Sheen_Weight=param("CIN.Cloud.sheen", 0.4), Sheen_Roughness=0.6)["BSDF"]
        facing = tree.n("ShaderNodeLayerWeight", Blend=0.5)["Facing"]
        solid = tree.map_range(facing, param("CIN.Cloud.edge", 0.62), 0.95, 1.0, 0.0, interp="SMOOTHSTEP")
        clear = tree.n("ShaderNodeBsdfTransparent")["BSDF"]
        return tree.n("ShaderNodeMixShader", solid, clear, body)["Shader"]
    return S.material("CIN.Cloud", build)
