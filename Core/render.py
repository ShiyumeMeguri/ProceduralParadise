"""
Core.render -- render settings and the compositor "look" pipeline.

Handles the compositor API change in Blender 5.0 (``scene.node_tree`` ->
``scene.compositing_node_group`` with a Group Output) and the Glare node's
properties -> sockets change, so shot files stay portable across 4.4 .. 5.x.

Animations render to a PNG frame sequence that survives interruption
(:func:`frame_output`, :func:`unfinished_frames`) and is assembled into the
video by a sequencer scene (:func:`video_scene`).
"""
from __future__ import annotations

import math
import os

import bpy

from .nodes import Tree
from .gn import set_menu

__all__ = ["ENGINES", "setup_cycles", "setup_eevee", "set_samples", "color_management", "compositor", "lines", "LINES_LAYER",
           "ink", "INK_LAYER", "INK_SKIP", "INK_ID", "INK_QUIET",
           "frame_output", "frame_paths", "unfinished_frames", "video_scene",
           "use_gpu_if_available", "render_still"]

LINES_LAYER = "Lines"
INK_LAYER = "Ink"
INK_SKIP = "ink_skip"
INK_ID = "ink_id"
INK_QUIET = "ink_quiet"
SOBEL_WIDTH = 2.0
_PNG_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def setup_cycles(samples=128, denoise=True, device="CPU", max_bounces=8, clamp_indirect=10.0,
                 caustics=False, adaptive_threshold=0.02, light_tree=True, diffuse_bounces=4, glossy_bounces=4,
                 transmission_bounces=8):
    """Cycles with per-kind bounce limits.  Light carried inside thin glass
    -- a blown shell, a pane's edge -- travels by total internal reflection,
    and Cycles counts every such reflection as a glossy bounce: glass-heavy
    shots need ``glossy_bounces`` and ``transmission_bounces`` in the tens,
    or the paths are cut off and the glass edges render black."""
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
    cy.diffuse_bounces = diffuse_bounces
    cy.glossy_bounces = glossy_bounces
    cy.transmission_bounces = transmission_bounces
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


def setup_eevee(samples=64, viewport_samples=32, raytracing=True, trace_resolution="1", trace_quality=0.75,
                trace_max_roughness=0.5, fast_gi=True, volume_range=None, volume_tile="8", volume_samples=64,
                volume_distribution=0.8, volume_shadows=False, shadow_pool="512", reflection_resolution="512",
                light_threshold=0.01, shadow_resolution=1.0):
    """EEVEE with screen-space ray tracing (reflections and refraction) at
    full resolution and fast global illumination.  Volumes are evaluated on
    froxels from the camera out to ``volume_range`` ([start, end] metres;
    the camera's clip range without one), ``volume_tile`` pixels wide,
    ``volume_samples`` slices spread towards the camera by
    ``volume_distribution``; ``volume_shadows`` lets the lights cast shadows
    inside them (sun shafts through the leaves).  ``shadow_pool`` (MB) holds
    the shadow maps -- a dense garden under a sun overflows a small pool and
    loses shadows; ``reflection_resolution`` is the size of every reflection
    probe's capture.  A light reaches only as far as its light falls to
    ``light_threshold``: a studio of many faint lights, each fitted as if it
    reached everywhere, needs it near zero.  ``shadow_resolution`` scales
    every shadow map: a studio of hundreds of soft boxes casts soft shadows
    that coarse maps hold, and fine ones would overflow the shadow pages."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    ee = sc.eevee
    ee.taa_render_samples = samples
    ee.taa_samples = viewport_samples
    ee.use_raytracing = raytracing
    ee.ray_tracing_method = "SCREEN"
    tracing = ee.ray_tracing_options
    tracing.resolution_scale = trace_resolution
    tracing.screen_trace_quality = trace_quality
    tracing.trace_max_roughness = trace_max_roughness
    ee.use_shadows = True
    ee.use_fast_gi = fast_gi
    ee.fast_gi_method = "GLOBAL_ILLUMINATION"
    ee.use_volume_custom_range = volume_range is not None
    if volume_range is not None:
        ee.volumetric_start, ee.volumetric_end = volume_range
    ee.volumetric_tile_size = volume_tile
    ee.volumetric_samples = volume_samples
    ee.volumetric_sample_distribution = volume_distribution
    ee.use_volumetric_shadows = volume_shadows
    ee.shadow_pool_size = shadow_pool
    ee.gi_cubemap_resolution = reflection_resolution
    ee.light_threshold = light_threshold
    ee.shadow_resolution_scale = shadow_resolution
    return sc


ENGINES = {"CYCLES": setup_cycles, "EEVEE": setup_eevee}


def set_samples(engine, samples, scene=None):
    sc = scene or bpy.context.scene
    if engine == "CYCLES":
        sc.cycles.samples = samples
    else:
        sc.eevee.taa_render_samples = samples


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
    # Blender 4.x: node properties instead of input sockets.  Aliases first:
    # every node has a read-only ``type`` (its identifier), and the 4.x glare
    # has no strength -- its ``mix`` runs from -1 (original) to +1 (glare only).
    prop = name.lower().replace(" ", "_")
    alias = {"type": "glare_type", "strength": "mix"}
    if prop == "strength" and hasattr(n, "mix") and not isinstance(value, str):
        value = max(-1.0, min(1.0, 2.0 * float(value) - 1.0))
    for p in dict.fromkeys((alias.get(prop, prop), prop)):
        if not hasattr(n, p):
            continue
        try:
            setattr(n, p, value)
            return
        except (TypeError, AttributeError):
            if isinstance(value, str):
                try:
                    setattr(n, p, value.upper().replace(" ", "_").replace("/", "_"))
                    return
                except (TypeError, AttributeError):
                    pass
    # silently ignore parameters that do not exist in this version


def vignette_gain(r2, v):
    """Lens vignetting factor for squared radius ``r2`` (distance from the
    frame centre, half the image width = 1): 1 - strength * r2 ** power,
    never below 0.  ``r2`` may be a number, a numpy array or a node socket."""
    k = float(v.get("strength", 0.2))
    p = float(v.get("power", 2.0))
    if hasattr(r2, "shape") or isinstance(r2, (int, float)):
        import numpy as np
        return np.maximum(1.0 - k * np.power(r2, p), 0.0)
    return None


def vignette_nodes(t, img, v):
    """Multiply the (scene-linear) image by :func:`vignette_gain`, the radius
    taken from the Image Coordinates node ('Uniform': zero-centred, the
    larger image dimension spans -1..1)."""
    k = float(v.get("strength", 0.2))
    p = float(v.get("power", 2.0))
    ic = t.n("CompositorNodeImageCoordinates")
    t.link(img, ic.n.inputs[0])
    x, y, _ = t.sep(ic["Uniform"])
    r2 = x * x + y * y
    gain = t.math("MAXIMUM", 1.0 - t.math("POWER", r2, p) * k, 0.0)
    sep = t.n("CompositorNodeSeparateColor", img)
    return t.n("CompositorNodeCombineColor", sep[0] * gain, sep[1] * gain, sep[2] * gain, 1.0).o


def compositor(look: dict | None = None, lines_layer: str | None = None, ink_layer: str | None = None):
    """Build the compositor graph from a ``look`` dict::

        {"bloom": {"threshold": 1.0, "size": 7, "strength": 0.6},
         "glow":  {"threshold": 0.8, "size": 9, "strength": 0.25},
         "exposure": 0.0,
         "vignette": {"strength": 0.2, "power": 2.0},
         "lift": [r,g,b], "gamma": [r,g,b], "gain": [r,g,b],
         "hue_sat": {"hue": 0.5, "saturation": 1.0, "value": 1.0},
         "curves": {"C": [[x,y],...], "R": [...], "G": [...], "B": [...]},
         "grade": {...}, "engine_transfer": {...},   (Core.grade dicts)
         "backdrop": [r, g, b]}

    The ``grade`` carries the look of the scene; the ``engine_transfer``
    after it carries the render engine's own response onto the look the
    grade was made for (a shot fitted on another engine's renders).

    A ``backdrop`` is the sheet a transparent render is laid on (the shot's
    ``render.transparent``), last of all: a drawing's paper, which must not
    light the subject -- a world showing it to the camera would, since
    screen-space light and reflections take whatever the camera sees
    behind the subject for light.

    ``lines_layer`` (from :func:`lines`) is laid over the render first, with
    the premultiplied over Freestyle itself uses on a combined pass, so the
    exposure and grade see the ink lines as part of the image.  An
    ``ink_layer`` (from :func:`ink`) is drawn the same way, from the edges
    of its identity, normal and depth images (``look["ink"]``).
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
    rl.n.layer = sc.view_layers[0].name
    img = rl["Image"]

    if lines_layer:
        ink = t.n("CompositorNodeRLayers")
        ink.n.layer = lines_layer
        over = t.n("CompositorNodeAlphaOver")
        background, foreground = [s for s in over.n.inputs if s.type == "RGBA"][:2]
        t.link(img, background)
        t.link(ink["Freestyle"], foreground)
        _set(over, "Straight Alpha", False)
        _set(over, "premul", 1.0)
        img = over.o

    if ink_layer:
        img = ink_nodes(t, img, ink_layer, look["ink"])

    if "exposure" in look:
        ex = t.n("CompositorNodeExposure", img, look["exposure"])
        ex.n.name = ex.n.label = "Exposure"          # animation looks it up by name
        img = ex.o

    if look.get("vignette"):
        img = vignette_nodes(t, img, look["vignette"])

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

    if look.get("engine_transfer"):
        from .grade import grade_nodes
        img = grade_nodes(t, img, look["engine_transfer"])

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

    if look.get("backdrop"):
        over = t.n("CompositorNodeAlphaOver")
        background, foreground = [s for s in over.n.inputs if s.type == "RGBA"][:2]
        background.default_value = (*look["backdrop"], 1.0)
        t.link(img, foreground)
        _set(over, "Straight Alpha", False)
        img = over.o

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
           "crease_deg": angle, "collections": [names], "occluders": [names]}

    Freestyle builds its view map from every mesh of the view layer it runs
    on and only then picks the line set's ``collections``; on the main layer
    it would trace the whole city behind the windows every frame.  The lines
    get a view layer of their own instead, holding the ``collections`` and
    the ``occluders`` that can hide them and rendering no surfaces; its
    strokes come out as the layer's Freestyle pass, which :func:`compositor`
    lays over the image.  Returns the layer name (None without lines)."""
    sc = bpy.context.scene
    sc.view_layers[0].use_freestyle = False
    if not cfg:
        sc.render.use_freestyle = False
        return None
    sc.render.use_freestyle = True
    try:
        sc.render.line_thickness_mode = "RELATIVE"
    except TypeError:
        pass
    sc.render.line_thickness = 1.0
    cols = cfg.get("collections") or []
    keep = set(cols) | set(cfg.get("occluders") or [])
    vl = sc.view_layers.get(LINES_LAYER) or sc.view_layers.new(LINES_LAYER)
    missing = keep - _keep_only(vl.layer_collection, keep)
    if missing:
        raise KeyError(f"lines: no collection {sorted(missing)} in the scene")
    for flag in ("use_solid", "use_sky", "use_strand", "use_volumes"):
        setattr(vl, flag, False)
    vl.samples = 1
    vl.cycles.use_denoising = False
    fs = vl.freestyle_settings
    fs.mode = "EDITOR"
    fs.crease_angle = math.radians(cfg.get("crease_deg", 140.0))
    fs.use_culling = True
    fs.as_render_pass = True
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
    if cols:
        ls.select_by_collection = True
        ls.collection = bpy.data.collections[cols[0]]
    st = ls.linestyle
    st.color = tuple(cfg.get("color", (0.08, 0.16, 0.3)))
    st.alpha = cfg.get("alpha", 0.5)
    st.thickness = cfg.get("thickness", 1.2)
    st.chaining = "PLAIN"
    return vl.name


def ink(cfg: dict | None):
    """Screen-space ink lines: the painted line art for any camera, drawn
    wherever surfaces part -- one object from another, one leaf from the
    next (``ink_id``), a crease, a jump in depth -- and seen through glass.

    cfg = {"color": [r,g,b], "alpha": a, "width": px at 100 %,
           "id": threshold, "normal": threshold, "depth": threshold (optional),
           "rim": facing, "samples": n, "exclude": [collection names],
           "fade": [near, far] (optional, metres)}

    A view layer of its own renders every surface of the main layer (minus
    ``exclude``, e.g. volumes) with one override material: an emission of
    the object's random value mixed with the element's ``ink_id``, so every
    object -- and every leaf that stores an ``ink_id`` -- has its own
    colour.  Surfaces marked ``ink_skip`` (glass) are transparent to it
    except where seen edge-on (facing beyond ``rim``): lines of whatever
    lies behind glass are drawn, and the glass still gets its outline.
    Surfaces marked ``ink_quiet`` (foliage) share one identity and are never
    inked: the painter draws line art on the architecture and the
    glassware, and lets plants cut those lines without outlining them.
    With a ``fade`` the line art keeps to the aerial perspective: lines
    thin out from ``near`` to ``far`` away from the camera (the layer's mist
    pass, through glass as the lines are), so a skyline dissolving into the
    haze is not outlined against the sky.  :func:`compositor` turns the
    layer's colour, normal, depth and mist images into lines.  Returns the
    layer name (None without ink)."""
    sc = bpy.context.scene
    if not cfg:
        return None
    main = sc.view_layers[0]
    layer = sc.view_layers.get(INK_LAYER) or sc.view_layers.new(INK_LAYER)
    excluded = set(cfg.get("exclude") or [])

    def mirror(source, target):
        for child_source, child_target in zip(source.children, target.children):
            child_target.exclude = child_source.exclude or child_source.name in excluded
            if not child_target.exclude:
                mirror(child_source, child_target)

    mirror(main.layer_collection, layer.layer_collection)
    layer.use_pass_z = True
    layer.use_pass_normal = True
    layer.use_volumes = False
    layer.use_sky = False
    layer.samples = cfg.get("samples", 4)
    layer.use_freestyle = False
    layer.material_override = _ink_material(cfg.get("rim", 0.82))
    fade = cfg.get("fade")
    if fade:
        layer.use_pass_mist = True
        mist = sc.world.mist_settings
        mist.start, mist.depth, mist.falloff = fade[0], fade[1] - fade[0], "LINEAR"
    return layer.name


def _ink_material(rim):
    from . import shaders as S

    def build(t: Tree):
        random = t.n("ShaderNodeObjectInfo")["Random"]
        element = t.n("ShaderNodeAttribute", props={"attribute_name": INK_ID, "attribute_type": "GEOMETRY"})["Fac"]
        identity = t.n("ShaderNodeCombineColor", random, t.math("FRACT", random * 7.13 + element * 3.71),
                       t.math("FRACT", element * 13.7 + random * 1.37) * 0.9).o
        quiet = t.n("ShaderNodeAttribute", props={"attribute_name": INK_QUIET, "attribute_type": "GEOMETRY"})["Fac"]
        identity = t.mix(quiet, identity, (0.5, 0.5, 1.0, 1.0), data_type="RGBA")
        emission = t.n("ShaderNodeEmission", identity, 1.0)["Emission"]
        skip = t.n("ShaderNodeAttribute", props={"attribute_name": INK_SKIP, "attribute_type": "GEOMETRY"})["Fac"]
        facing = t.n("ShaderNodeLayerWeight", Blend=0.5)["Facing"]
        edge_on = t.map_range(facing, rim, rim + 0.02, 0.0, 1.0)
        see_through = skip * (1.0 - edge_on)
        clear = t.n("ShaderNodeBsdfTransparent")["BSDF"]
        return t.n("ShaderNodeMixShader", see_through, emission, clear)["Shader"]
    return S.material("__ink", build)


def ink_nodes(t, img, layer, cfg):
    """Lay the ink of ``layer`` over ``img``: Sobel edges of its identity
    colours (a unit step gives 4) and normals (a crease of angle a gives
    8 sin(a / 2)), and -- with a ``depth`` threshold -- of its inverse depth
    under a Laplace kernel (planes have a linear inverse depth, so only
    steps and creases in depth remain), scaled by the depth to make the
    threshold relative.  Each passes a soft threshold (full ink at 1.5 x).
    No ink lies within ``quiet_margin`` px of a quiet surface (identity blue
    1): plants cut the lines behind them and carry none.

    Widths are pixels of the frame at the scene's resolution, and a line
    keeps its width on the frame whatever size is rendered: the size is read
    from the rendered image itself, so a preview at any percentage, set
    before or after this is built, gets the same lines.  The edge filters
    draw a line ``SOBEL_WIDTH`` pixels wide; a line due fewer pixels is laid
    at the fraction of them it covers, one due more is grown to it."""
    sc = bpy.context.scene
    rl = t.n("CompositorNodeRLayers")
    rl.n.layer = layer
    rendered = t.n("ShaderNodeSeparateXYZ", t.n("CompositorNodeImageInfo", rl["Image"])["Dimensions"])["X"]
    scale = t.math("DIVIDE", rendered, float(sc.render.resolution_x))

    def filtered(image, kind):
        node = t.n("CompositorNodeFilter")
        t.link(image, node.n.inputs["Image"])
        _set(node, "Type", kind)
        _set(node, "Factor", 1.0)
        return node.o

    def strongest(image):
        parts = t.n("CompositorNodeSeparateColor", image)
        return t.math("MAXIMUM", t.math("MAXIMUM", t.math("ABSOLUTE", parts[0]), t.math("ABSOLUTE", parts[1])),
                      t.math("ABSOLUTE", parts[2]))

    def over(value, threshold):
        return t.math("MULTIPLY", t.math("SUBTRACT", value, threshold), 1.0 / max(threshold * 0.5, 1e-4), clamp=True)

    mask = t.math("MAXIMUM", over(strongest(filtered(rl["Image"], "Sobel")), cfg.get("id", 0.1)),
                  over(strongest(filtered(rl["Normal"], "Sobel")), cfg.get("normal", 2.0)))
    quiet = t.math("GREATER_THAN", t.n("CompositorNodeSeparateColor", rl["Image"])[2], 0.95)
    margin = t.n("CompositorNodeDilateErode")
    t.link(quiet, margin.n.inputs["Mask"])
    _set(margin, "Type", "Distance")
    t.link(t.math("MAXIMUM", t.math("ROUND", t.math("MULTIPLY", scale, float(cfg.get("quiet_margin", 2)))), 1.0), margin.n.inputs["Size"])
    mask = t.math("MULTIPLY", mask, t.math("SUBTRACT", 1.0, margin.o, clamp=True))
    if cfg.get("depth"):
        depth = rl["Depth"]
        inverse = t.math("DIVIDE", 1.0, t.math("MAXIMUM", depth, 1e-3))
        inverse_image = t.n("CompositorNodeCombineColor", inverse, inverse, inverse, 1.0).o
        jumps = t.math("MULTIPLY", strongest(filtered(inverse_image, "Laplace")), depth)
        mask = t.math("MAXIMUM", mask, over(jumps, cfg["depth"]))
    due = t.math("MULTIPLY", scale, SOBEL_WIDTH + 2.0 * cfg.get("width", 0.0))
    grow = t.n("CompositorNodeDilateErode")
    t.link(mask, grow.n.inputs["Mask"])
    _set(grow, "Type", "Distance")
    t.link(t.math("ROUND", t.math("MULTIPLY", t.math("MAXIMUM", t.math("SUBTRACT", due, SOBEL_WIDTH), 0.0), 0.5)), grow.n.inputs["Size"])
    coverage = t.math("MINIMUM", t.math("DIVIDE", due, SOBEL_WIDTH), 1.0)
    factor = t.math("MULTIPLY", grow.o, t.math("MULTIPLY", coverage, cfg.get("alpha", 1.0)), clamp=True)
    if cfg.get("fade"):
        factor = t.math("MULTIPLY", factor, t.math("SUBTRACT", 1.0, rl["Mist"], clamp=True))
    line = tuple(cfg.get("color", (0.005, 0.03, 0.03))) + (1.0,)
    return t.mix(factor, img, line, data_type="RGBA")


def _keep_only(layer_collection, keep):
    """Exclude every child layer collection that neither is in ``keep`` nor
    leads to one, top-down (Blender applies an exclude change to the whole
    subtree); returns the names from ``keep`` found below."""
    found = set()
    for child in layer_collection.children:
        below = {c.name for c in child.collection.children_recursive} & keep
        child.exclude = child.name not in keep and not below
        if child.name in keep:
            found |= {child.name} | below
        elif below:
            found |= _keep_only(child, keep)
    return found


def _output_kind(kind, scene=None):
    """Image settings for 'IMAGE' or 'VIDEO' output (Blender 5.x splits the
    file formats by ``media_type``; 4.x has one flat list)."""
    im = (scene or bpy.context.scene).render.image_settings
    if hasattr(im, "media_type"):
        im.media_type = "VIDEO" if kind == "VIDEO" else "IMAGE"
    return im


def frame_output(prefix, fps=30):
    """Render the frame range as the PNG sequence ``<prefix>####.png``.
    Frames already on disk are kept, so a stopped animation render carries
    on where it stopped; the caller keeps frames of different inputs apart
    by giving each its own ``prefix`` folder.  Returns ``prefix``."""
    sc = bpy.context.scene
    sc.render.fps = int(round(fps))
    sc.render.fps_base = 1.0
    sc.render.filepath = prefix
    sc.render.use_overwrite = False
    sc.render.use_placeholder = False
    im = _output_kind("IMAGE")
    im.file_format = "PNG"
    im.color_depth = "8"
    return prefix


def frame_paths(scene=None):
    """{frame: absolute file path} of the scene's frame range."""
    sc = scene or bpy.context.scene
    return {f: sc.render.frame_path(frame=f) for f in range(sc.frame_start, sc.frame_end + 1)}


def _frame_complete(path):
    try:
        with open(path, "rb") as f:
            f.seek(-len(_PNG_END), os.SEEK_END)
            return f.read() == _PNG_END
    except OSError:
        return False


def unfinished_frames(scene=None):
    """Frames of the scene's range not on disk yet.  A frame file cut short
    by an interrupted render is deleted, so the next render redoes it
    instead of skipping it."""
    sc = scene or bpy.context.scene
    missing = []
    for frame, path in frame_paths(sc).items():
        if not _frame_complete(path):
            if os.path.exists(path):
                os.remove(path)
            missing.append(frame)
    return missing


def video_scene(video, name, scene=None):
    """Scene ``name`` that assembles ``scene``'s frame sequence into an H.264
    MP4 at ``video`` in the sequencer; rendering it (Ctrl+F12 with the scene
    active) writes the video.  The frames are display-referred, so the
    Standard view transform passes their colours through unchanged."""
    sc = scene or bpy.context.scene
    vs = bpy.data.scenes.get(name) or bpy.data.scenes.new(name)
    r = vs.render
    pct = sc.render.resolution_percentage
    r.resolution_x = sc.render.resolution_x * pct // 100
    r.resolution_y = sc.render.resolution_y * pct // 100
    r.resolution_percentage = 100
    r.fps, r.fps_base = sc.render.fps, sc.render.fps_base
    vs.frame_start, vs.frame_end = 1, sc.frame_end - sc.frame_start + 1
    vs.view_settings.view_transform = "Standard"
    vs.view_settings.look = "None"
    vs.view_settings.exposure = 0.0
    vs.view_settings.gamma = 1.0
    vs.display_settings.display_device = "sRGB"
    se = vs.sequence_editor_create()
    for strip in list(se.strips):
        se.strips.remove(strip)
    prefix = sc.render.filepath
    folder = prefix[:len(prefix) - len(bpy.path.basename(prefix))]
    names = [os.path.basename(p) for p in frame_paths(sc).values()]
    strip = se.strips.new_image("Frames", folder + names[0], channel=1, frame_start=1)
    for n in names[1:]:
        strip.elements.append(n)
    strip.colorspace_settings.name = "sRGB"
    r.use_sequencer = True
    r.use_compositing = False
    r.filepath = video
    im = _output_kind("VIDEO", vs)
    im.file_format = "FFMPEG"
    ff = r.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    for attr, val in (("constant_rate_factor", "HIGH"), ("ffmpeg_preset", "GOOD"),
                      ("audio_codec", "NONE"), ("gopsize", r.fps)):
        try:
            setattr(ff, attr, val)
        except (AttributeError, TypeError):
            pass
    return vs


def use_gpu_if_available():
    """Render Cycles on the GPU when this machine has one, and denoise there
    too (OpenImageDenoise on the CPU costs a GPU render ~6 s per 1080p frame,
    and again for the Freestyle strokes).  Only touches the Cycles
    preferences when no compute backend is configured yet; returns the
    backend in use or None (CPU)."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except (KeyError, AttributeError):
        return None
    sc = bpy.context.scene
    if getattr(prefs, "compute_device_type", "NONE") == "NONE":
        for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            try:
                prefs.get_devices()
            except Exception:
                pass
            devs = [d for d in prefs.devices if d.type == backend]
            if devs:
                for d in devs:
                    d.use = True
                break
            prefs.compute_device_type = "NONE"
    backend = getattr(prefs, "compute_device_type", "NONE")
    if backend != "NONE":
        sc.cycles.device = "GPU"
        sc.cycles.denoising_use_gpu = True
        return backend
    return None


def render_still(path, use_compositor=True):
    sc = bpy.context.scene
    sc.render.filepath = path
    _output_kind("IMAGE").file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    try:
        sc.render.use_compositing = use_compositor
    except AttributeError:
        pass
    bpy.ops.render.render(write_still=True)
    return path
