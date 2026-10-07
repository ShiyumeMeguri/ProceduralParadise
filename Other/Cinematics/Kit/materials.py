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


def _scaled(rgba, factor):
    return tuple(component * factor for component in rgba[:3]) + (rgba[3],)


@register("CIN.Facade")
def facade():
    """The towers of the district (``CIN.City.Field``): storeys and bays laid by every block's own
    coordinates (``facade``) -- a band of windows under every floor, piers between the bays --
    the walls of a block lighter or darker by its ``variant``, its windows dark or catching the
    sky one by one, its roof bare."""
    def build(tree: Tree):
        place = tree.n("ShaderNodeAttribute", props={"attribute_name": "facade", "attribute_type": "GEOMETRY"})["Vector"]
        variant = tree.n("ShaderNodeAttribute", props={"attribute_name": "variant", "attribute_type": "GEOMETRY"})["Fac"]
        normal = tree.n("ShaderNodeNewGeometry")["True Normal"]
        x, y, z = tree.sep(place)
        nx, _ny, nz = tree.sep(normal)
        across = tree.mix(tree.map_range(tree.abs(nx), 0.4, 0.6, 0.0, 1.0), x, y)
        storey = param("CIN.Facade.storey", 3.6)
        bay = tree.math("MULTIPLY", variant * 0.5 + 0.8, param("CIN.Facade.bay", 3.2))
        u = tree.math("FRACT", across / bay)
        v = tree.math("FRACT", z / storey)
        glass_across = tree.map_range(tree.abs(u - 0.5), 0.34, 0.37, 1.0, 0.0)
        glass_up = tree.map_range(tree.abs(v - 0.56), 0.25, 0.28, 1.0, 0.0)
        roof = tree.map_range(tree.abs(nz), 0.5, 0.7, 0.0, 1.0)
        window = glass_across * glass_up * (1.0 - roof)
        cell = tree.vec(tree.floor(across / bay), tree.floor(z / storey), variant * 97.0)
        catch = tree.n("ShaderNodeTexWhiteNoise", Vector=cell, props={"noise_dimensions": "3D"})["Value"]
        wall = tree.mix(variant, _scaled(color("facade_far"), 0.82), _scaled(color("facade_far"), 1.16), "RGBA")
        pane = tree.mix(catch, color("window_far"), _scaled(color("window_far"), 2.6), "RGBA")
        base = tree.mix(window, wall, pane, "RGBA")
        base = tree.mix(roof, base, color("roof_far"), "RGBA")
        return S.bsdf(tree, Base_Color=base, Roughness=tree.mix(window, 0.82, 0.14),
                      Specular_IOR_Level=tree.mix(window, 0.3, 0.8))["BSDF"]
    return S.material("CIN.Facade", build)


@register("CIN.Dust")
def dust():
    """Dust of a breach, a volume (``CIN.FX.Plume``): the plume's ``density`` broken into billows
    ``CIN.Dust.billow`` metres across, ``CIN.Dust.density`` per metre at its thickest,
    scattering the ``dust`` colour a little more forwards (``CIN.Dust.anisotropy``)."""
    def build(tree: Tree):
        grid = tree.n("ShaderNodeAttribute", props={"attribute_name": "density", "attribute_type": "GEOMETRY"})["Fac"]
        position = tree.n("ShaderNodeNewGeometry")["Position"]
        billows = tree.n("ShaderNodeTexNoise", Vector=position, Scale=1.0 / param("CIN.Dust.billow", 2.5), Detail=5.0,
                         Roughness=0.55, props={"noise_dimensions": "3D"})["Fac"]
        breakup = tree.map_range(billows, 0.38, 0.62, 0.0, 1.0, interp="SMOOTHSTEP")
        density = tree.math("MULTIPLY", grid * breakup, param("CIN.Dust.density", 3.0))
        return {"Volume": tree.n("ShaderNodeVolumePrincipled", Color=color("dust"), Density=density, Density_Attribute="",
                                 Anisotropy=param("CIN.Dust.anisotropy", 0.25))["Volume"]}
    return S.material("CIN.Dust", build)


@register("CIN.Debris")
def debris():
    """Fragments of a breach: broken concrete, dark with grime, a piece lighter or darker by its
    ``variant``."""
    def build(tree: Tree):
        variant = tree.n("ShaderNodeAttribute", props={"attribute_name": "variant", "attribute_type": "INSTANCER"})["Fac"]
        base = tree.mix(variant, _scaled(color("debris"), 0.6), _scaled(color("debris"), 1.5), "RGBA")
        return S.bsdf(tree, Base_Color=base, Roughness=0.85)["BSDF"]
    return S.material("CIN.Debris", build)


@register("CIN.Air")
def air():
    """Haze (a volume): ``CIN.Air.density`` per metre at the ground, thinning to 1/e every
    ``CIN.Air.height`` metres up, scattering the ``air`` colour, a little more forwards
    (``CIN.Air.anisotropy``)."""
    def build(tree: Tree):
        height = tree.sep(tree.n("ShaderNodeNewGeometry")["Position"])[2]
        thinning = tree.math("EXPONENT", tree.math("MAXIMUM", height, 0.0) * (-1.0 / param("CIN.Air.height", 120.0)))
        density = tree.math("MULTIPLY", thinning, param("CIN.Air.density", 0.002))
        return {"Volume": tree.n("ShaderNodeVolumePrincipled", Color=color("air"), Density=density,
                                 Anisotropy=param("CIN.Air.anisotropy", 0.3))["Volume"]}
    return S.material("CIN.Air", build)


@register("CIN.Cloud")
def cloud():
    """Cumulus: a white body that the sun lights and the blue sky fills in the shade, light
    carried a little way through it (subsurface, metres deep) so its folds read soft, the light
    a cloud scatters on through itself many times standing in as a glow of its own
    (``CIN.Cloud.glow``: the renderer follows light a few metres into it, not hundreds), a silver
    sheen at grazing angles, and a silhouette that thins out where the surface turns away."""
    def build(tree: Tree):
        body = S.bsdf(tree, Base_Color=color("cloud"), Roughness=1.0, Subsurface_Weight=param("CIN.Cloud.subsurface", 0.6),
                      Subsurface_Radius=(1.0, 1.0, 1.0), Subsurface_Scale=param("CIN.Cloud.depth", 18.0),
                      Sheen_Weight=param("CIN.Cloud.sheen", 0.4), Sheen_Roughness=0.6,
                      Emission_Color=color("cloud"), Emission_Strength=param("CIN.Cloud.glow", 0.0))["BSDF"]
        facing = tree.n("ShaderNodeLayerWeight", Blend=0.5)["Facing"]
        solid = tree.map_range(facing, param("CIN.Cloud.edge", 0.62), 0.95, 1.0, 0.0, interp="SMOOTHSTEP")
        clear = tree.n("ShaderNodeBsdfTransparent")["BSDF"]
        return tree.n("ShaderNodeMixShader", solid, clear, body)["Shader"]
    return S.material("CIN.Cloud", build)
