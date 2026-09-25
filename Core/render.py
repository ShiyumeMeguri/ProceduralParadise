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

__all__ = ["setup_cycles", "color_management", "compositor", "lines", "LINES_LAYER",
           "frame_output", "frame_paths", "unfinished_frames", "video_scene",
           "use_gpu_if_available", "render_still"]

LINES_LAYER = "Lines"
_PNG_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"


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


def compositor(look: dict | None = None, lines_layer: str | None = None):
    """Build the compositor graph from a ``look`` dict::

        {"bloom": {"threshold": 1.0, "size": 7, "strength": 0.6},
         "glow":  {"threshold": 0.8, "size": 9, "strength": 0.25},
         "exposure": 0.0,
         "lift": [r,g,b], "gamma": [r,g,b], "gain": [r,g,b],
         "hue_sat": {"hue": 0.5, "saturation": 1.0, "value": 1.0},
         "curves": {"C": [[x,y],...], "R": [...], "G": [...], "B": [...]}}

    ``lines_layer`` (from :func:`lines`) is laid over the render first, with
    the premultiplied over Freestyle itself uses on a combined pass, so the
    exposure and grade see the ink lines as part of the image.
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

    if "exposure" in look:
        ex = t.n("CompositorNodeExposure", img, look["exposure"])
        ex.n.name = ex.n.label = "Exposure"          # animation looks it up by name
        img = ex.o

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
