"""
Core.render -- render settings and the compositor "look" pipeline.

Handles the compositor API change in Blender 5.0 (``scene.node_tree`` ->
``scene.compositing_node_group`` with a Group Output) and the Glare node's
properties -> sockets change, so shot files stay portable across 4.2 .. 5.x.
"""
from __future__ import annotations

import bpy

from .nodes import Tree
from .gn import set_menu

__all__ = ["setup_cycles", "color_management", "compositor", "render_still"]


def setup_cycles(samples=128, denoise=True, device="CPU", max_bounces=8, clamp_indirect=10.0,
                 caustics=False, adaptive_threshold=0.02, light_tree=True):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = device
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = adaptive_threshold
    cy.use_denoising = denoise
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    cy.max_bounces = max_bounces
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 4
    cy.transmission_bounces = 8
    cy.transparent_max_bounces = 16
    cy.sample_clamp_indirect = clamp_indirect
    cy.caustics_reflective = caustics
    cy.caustics_refractive = caustics
    try:
        cy.use_light_tree = light_tree
    except AttributeError:
        pass
    sc.render.use_persistent_data = True
    return sc


def color_management(view="AgX", look=None, exposure=0.0, gamma=1.0):
    sc = bpy.context.scene
    vs = sc.view_settings
    try:
        vs.view_transform = view
    except TypeError:
        vs.view_transform = "Standard"
    if look:
        for cand in (look, f"{view} - {look}", f"AgX - {look}"):
            try:
                vs.look = cand
                break
            except TypeError:
                continue
    vs.exposure = exposure
    vs.gamma = gamma
    sc.display_settings.display_device = "sRGB"
    sc.sequencer_colorspace_settings.name = "sRGB" if "sRGB" in [
        i.identifier for i in sc.sequencer_colorspace_settings.bl_rna.properties["name"].enum_items
    ] else sc.sequencer_colorspace_settings.name


def _set(node, name, value):
    """Set a compositor node parameter that is a property (4.x) or an input
    socket (5.x)."""
    n = node.n if hasattr(node, "n") else node
    sock = None
    for s in n.inputs:
        if s.name == name and getattr(s, "enabled", True):
            sock = s
            break
    if sock is not None and hasattr(sock, "default_value"):
        if isinstance(value, str):
            set_menu(sock, value)
        else:
            sock.default_value = value
        return
    prop = name.lower().replace(" ", "_")
    alias = {"type": "glare_type", "strength": "mix"}
    for p in (prop, alias.get(prop, prop)):
        if hasattr(n, p):
            try:
                setattr(n, p, value)
                return
            except TypeError:
                if isinstance(value, str):
                    setattr(n, p, value.upper())
                    return
    # silently ignore parameters that do not exist in this version


def compositor(look: dict | None = None):
    """Build the compositor graph from a ``look`` dict::

        {"bloom": {"threshold": 1.0, "size": 7, "strength": 0.6},
         "glow":  {"threshold": 0.8, "size": 9, "strength": 0.25},
         "exposure": 0.0,
         "lift": [r,g,b], "gamma": [r,g,b], "gain": [r,g,b],
         "hue_sat": {"hue": 0.5, "saturation": 1.0, "value": 1.0},
         "curves": {"C": [[x,y],...], "R": [...], "G": [...], "B": [...]}}
    """
    look = look or {}
    sc = bpy.context.scene
    # headless builds have no GPU context: keep the compositor on the CPU
    for attr, val in (("compositor_device", "CPU"), ("compositor_denoise_device", "CPU")):
        if hasattr(sc.render, attr):
            try:
                setattr(sc.render, attr, val)
            except TypeError:
                pass
    new_api = hasattr(sc, "compositing_node_group")
    if new_api:
        ng = sc.compositing_node_group
        if ng is None:
            ng = bpy.data.node_groups.new("Compositor", "CompositorNodeTree")
            sc.compositing_node_group = ng
        t = Tree(nodetree=ng, clear=True)
        ng.interface.clear()
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    else:
        sc.use_nodes = True
        t = Tree(nodetree=sc.node_tree, clear=True)
    rl = t.n("CompositorNodeRLayers")
    img = rl["Image"]

    if "exposure" in look and look["exposure"]:
        img = t.n("CompositorNodeExposure", img, look["exposure"]).o

    for key, gtype in (("glow", "FOG_GLOW"), ("bloom", "BLOOM"), ("streaks", "STREAKS")):
        if key in look:
            p = look[key]
            gl = t.n("CompositorNodeGlare")
            t.link(img, gl.n.inputs["Image"])
            _set(gl, "Type", "Bloom" if gtype == "BLOOM" else ("Fog Glow" if gtype == "FOG_GLOW" else "Streaks"))
            _set(gl, "Quality", p.get("quality", "Medium"))
            _set(gl, "Threshold", p.get("threshold", 1.0))
            _set(gl, "Size", p.get("size", 7) if not new_api else p.get("size_f", p.get("size", 7) / 9.0))
            _set(gl, "Strength", p.get("strength", 0.5))
            if "saturation" in p:
                _set(gl, "Saturation", p["saturation"])
            if "tint" in p:
                _set(gl, "Tint", (*p["tint"], 1.0))
            if "smoothness" in p:
                _set(gl, "Smoothness", p["smoothness"])
            if "streaks" in p:
                _set(gl, "Streaks", p["streaks"])
            img = gl["Image"]

    if look.get("grade"):
        from .grade import grade_nodes
        img = grade_nodes(t, img, look["grade"])

    if any(k in look for k in ("lift", "gamma", "gain")):
        cb = t.n("CompositorNodeColorBalance")
        t.link(img, cb.n.inputs["Image"])
        n = cb.n
        try:
            n.correction_method = "LIFT_GAMMA_GAIN"
        except (AttributeError, TypeError):
            _set(cb, "Type", "Lift/Gamma/Gain")
        for key, prop in (("lift", "lift"), ("gamma", "gamma"), ("gain", "gain")):
            if key in look:
                v = (*look[key], 1.0)
                done = False
                for s in n.inputs:
                    if s.name.lower() == key and getattr(s, "enabled", True) and s.type == "RGBA":
                        s.default_value = v
                        done = True
                        break
                if not done and hasattr(n, prop):
                    setattr(n, prop, look[key])
        img = cb.o

    if "hue_sat" in look:
        hs = look["hue_sat"]
        n = t.n("CompositorNodeHueSat")
        t.link(img, n.n.inputs["Image"])
        _set(n, "Hue", hs.get("hue", 0.5))
        _set(n, "Saturation", hs.get("saturation", 1.0))
        _set(n, "Value", hs.get("value", 1.0))
        img = n.o

    if "curves" in look:
        cv = t.n("CompositorNodeCurveRGB")
        t.link(img, cv.n.inputs["Image"])
        mapping = cv.n.mapping
        chans = {"C": 3, "R": 0, "G": 1, "B": 2}
        for ch, pts in look["curves"].items():
            curve = mapping.curves[chans[ch]]
            while len(curve.points) > 2:
                curve.points.remove(curve.points[1])
            curve.points[0].location = pts[0]
            curve.points[-1].location = pts[-1]
            for x, y in pts[1:-1]:
                curve.points.new(x, y)
        mapping.update()
        img = cv.o

    if new_api:
        out = t.n("NodeGroupOutput")
        t.link(img, out.n.inputs[0])
    else:
        comp = t.n("CompositorNodeComposite")
        t.link(img, comp.n.inputs["Image"])
    t.layout()
    return t


def lines(cfg: dict | None):
    """Freestyle ink lines (the painted-BG outline pass).

    cfg = {"thickness": px at 100 %, "color": [r,g,b], "alpha": a,
           "crease_deg": angle, "collections": [names]}"""
    sc = bpy.context.scene
    if not cfg:
        sc.render.use_freestyle = False
        return None
    sc.render.use_freestyle = True
    try:
        sc.render.line_thickness_mode = "RELATIVE"
    except TypeError:
        pass
    sc.render.line_thickness = 1.0
    vl = bpy.context.view_layer
    fs = vl.freestyle_settings
    fs.mode = "EDITOR"
    fs.crease_angle = __import__("math").radians(cfg.get("crease_deg", 140.0))
    fs.use_culling = True
    for ls in list(fs.linesets):
        fs.linesets.remove(ls)
    ls = fs.linesets.new("Ink")
    ls.select_by_visibility = True
    ls.visibility = "VISIBLE"
    ls.select_by_edge_types = True
    ls.select_silhouette = True
    ls.select_border = True
    ls.select_crease = True
    ls.select_external_contour = True
    cols = cfg.get("collections") or []
    if cols:
        ls.select_by_collection = True
        ls.collection = bpy.data.collections[cols[0]]
    st = ls.linestyle
    st.color = tuple(cfg.get("color", (0.08, 0.16, 0.3)))
    st.alpha = cfg.get("alpha", 0.5)
    st.thickness = cfg.get("thickness", 1.2)
    st.chaining = "PLAIN"
    return ls


def render_still(path, use_compositor=True):
    sc = bpy.context.scene
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    try:
        sc.render.use_compositing = use_compositor
    except AttributeError:
        pass
    bpy.ops.render.render(write_still=True)
    return path
