"""
Core.shaders -- procedural material construction helpers.

Materials are built with the same node DSL as geometry (``Tree.wrap``) so the
look is fully procedural: no image textures, no camera projections.  Each
builder returns a ``bpy.types.Material`` and is idempotent (rebuilds in place
when called again with the same name).
"""
from __future__ import annotations

import bpy

from .nodes import Tree, Sock, Node

__all__ = ["material", "principled", "emission_mat", "glass_mat", "new_world"]


def _new_material(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True  # deprecated in 5.x (always on) -- harmless
    except (AttributeError, TypeError):
        pass
    return m


def material(name, build, **opts):
    """Create material ``name`` and call ``build(t, out)`` where ``t`` is a
    :class:`Tree` wrapping the material node tree and ``out`` is the Material
    Output node (connect a shader to ``out.n.inputs['Surface']``)."""
    m = _new_material(name)
    t = Tree.wrap(m.node_tree, clear=True)
    out = t.n("ShaderNodeOutputMaterial")
    try:
        out.n.target = "ALL"
    except AttributeError:
        pass
    shader = build(t, **opts)
    if isinstance(shader, (Sock, Node)):
        t.link(shader, out.n.inputs["Surface"])
    elif isinstance(shader, dict):
        for k, v in shader.items():
            if v is not None:
                t.link(v, out.n.inputs[k])
    t.layout()
    for k in ("blend_method",):
        if k in opts and hasattr(m, k):
            setattr(m, k, opts[k])
    return m


def bsdf(t: Tree, **inputs):
    """Principled BSDF node; keyword names use underscores for spaces."""
    return t.n("ShaderNodeBsdfPrincipled", **inputs)


def principled(name, color=(0.8, 0.8, 0.8), roughness=0.5, metallic=0.0, specular=0.5,
               coat=0.0, coat_roughness=0.05, emission=None, emission_strength=0.0,
               alpha=1.0, transmission=0.0, ior=1.45):
    def build(t):
        kw = dict(Base_Color=color, Roughness=roughness, Metallic=metallic,
                  Specular_IOR_Level=specular, IOR=ior)
        if coat:
            kw.update(Coat_Weight=coat, Coat_Roughness=coat_roughness)
        if emission is not None:
            kw.update(Emission_Color=emission, Emission_Strength=emission_strength)
        if alpha < 1.0:
            kw.update(Alpha=alpha)
        if transmission:
            kw.update(Transmission_Weight=transmission)
        return bsdf(t, **kw)["BSDF"]
    return material(name, build)


def emission_mat(name, color=(1, 1, 1), strength=5.0):
    def build(t):
        return t.n("ShaderNodeEmission", Color=color, Strength=strength)["Emission"]
    return material(name, build)


def glass_mat(name, color=(0.9, 0.95, 1.0), roughness=0.0, ior=1.45, thin=True, reflect=1.0,
              camera_boost=1.0, coating=None):
    """Architectural glass. ``thin`` uses a fresnel mix of transparent +
    glossy, which renders clean window panes without refraction offsets.

    ``camera_boost`` > 1 brightens what *cameras* see through the pane (an
    exposure pull for the exterior, like a photographer's window blend)
    while light and shadow rays pass unchanged.

    ``coating`` = {"reflect": 0.3, "tint": (r, g, b)} gives faces carrying the
    ``glass_out`` attribute (the exterior side of a facade) the look of
    coated curtain-wall glass for camera rays: a minimum reflectance and a
    tinted view into the building.  Light transport is unchanged."""
    def build(t):
        if not thin:
            return t.n("ShaderNodeBsdfGlass", Color=color, Roughness=roughness, IOR=ior)["BSDF"]
        # Reflect only on front faces: on the exit (back) face the Fresnel node
        # would see glass->air and report total internal reflection beyond
        # ~42 deg, turning grazing views of a pane into a dark mirror.
        fres = t.n("ShaderNodeFresnel", IOR=ior)["Fac"]
        back = t.n("ShaderNodeNewGeometry")["Backfacing"]
        fres = fres * (1.0 - back)
        tcol = color
        if camera_boost != 1.0:
            cam = t.n("ShaderNodeLightPath")["Is Camera Ray"]
            k = 1.0 + (camera_boost - 1.0) * cam
            tcol = t.vmath("SCALE", tuple(color[:3]), scale=k)
        fac = fres * reflect if reflect != 1.0 else fres
        if coating:
            lp = t.n("ShaderNodeLightPath")
            outside = t.n("ShaderNodeAttribute", props={"attribute_name": "glass_out",
                                                        "attribute_type": "GEOMETRY"})["Fac"]
            k = outside * lp["Is Camera Ray"] * (1.0 - back)
            fac = t.mix(k, fac, t.max(fres, coating.get("reflect", 0.3)))
            tint = coating.get("tint", (0.6, 0.7, 0.8))
            tcol = mix_color(t, k, tcol, tuple(tint[:3]))
        transp = t.n("ShaderNodeBsdfTransparent", Color=tcol)["BSDF"]
        gloss = t.n("ShaderNodeBsdfGlossy", Color=(1, 1, 1), Roughness=roughness)["BSDF"]
        return t.n("ShaderNodeMixShader", fac, transp, gloss)["Shader"]
    return material(name, build)


def mix_color(t, fac, a, b):
    """Linear mix of two colours (sockets or tuples) by ``fac``."""
    a = tuple(a) + (1.0,) if isinstance(a, tuple) and len(a) == 3 else a
    b = tuple(b) + (1.0,) if isinstance(b, tuple) and len(b) == 3 else b
    return mix_rgb(t, fac, a, b)


def new_world(name="World"):
    w = bpy.data.worlds.get(name) or bpy.data.worlds.new(name)
    try:
        w.use_nodes = True
    except (AttributeError, TypeError):
        pass
    bpy.context.scene.world = w
    return w


# --------------------------------------------------------------- textures
def tex_coord(t: Tree, kind="Object"):
    return t.n("ShaderNodeTexCoord")[kind]


def noise(t: Tree, vec, scale=5.0, detail=2.0, rough=0.5, distortion=0.0, dims="3D"):
    nd = t.n("ShaderNodeTexNoise", Vector=vec, Scale=scale, Detail=detail, Roughness=rough,
             Distortion=distortion, props={"noise_dimensions": dims})
    return nd


def ramp(t: Tree, fac, stops):
    """ColorRamp with ``stops = [(pos, (r,g,b,a)), ...]``."""
    nd = t.n("ShaderNodeValToRGB", fac)
    cr = nd.n.color_ramp
    while len(cr.elements) > len(stops):
        cr.elements.remove(cr.elements[-1])
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (pos, col) in zip(cr.elements, stops):
        el.position = pos
        el.color = col if len(col) == 4 else (*col, 1.0)
    return nd


def mix_rgb(t: Tree, fac, a, b, blend="MIX"):
    return t.mix(fac, a, b, data_type="RGBA", blend=blend)
