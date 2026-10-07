"""
Overlays kit (``CIN.Overlay.*``): what a shot's camera carries in front of its lens, drawn in the
picture's units -- across from -``Aspect`` to +``Aspect``, up from -1 to +1 (``scenes`` overlays).

Every piece but the wipe is drawn in ink (``CIN.OverlayInk``): its ``Color``, brightened by its
``Glow``, coming in over ``Fade In`` and going out over ``Fade Out`` (each a start frame and a
number of frames; a length of 0 is no fade) -- stored on it as ``ink``, ``glow`` and ``alpha``.
It slides from ``Slide In`` away to its place over ``Slide Time`` (start frame, frames), slowing
as it arrives (the share of the way still to go is the share of the time left to the power
``Slide Ease``), and from that start drifts on by ``Drift`` a frame; it leaves sliding away by
``Slide Out`` over ``Slide Out Time``, gathering speed the same way; its opacity falls by
``Falloff`` from its top to its foot.  With a ``Hatch`` (period, angle in degrees, share) its ink
is laid in stripes ``period`` apart along the picture's direction ``angle``, ``share`` of each
inked, the stripes moving with it.  A piece is a picture's overlay or, in
metres, an item of a set (a title standing behind her).

``CIN.Overlay.DiamondWipe``: the picture uncovered through a lattice of diamonds.  The picture is
covered by black diamonds ``Columns`` across; from the frame ``Start`` each shrinks to nothing
over ``Duration`` frames, those on the right first and those on the left ``Sweep`` frames after,
and while it shrinks its edge glows white (``Edge``: the glowing rim's share of a diamond).

``CIN.Overlay.Text``: a line of text, ``Size`` high, drawn out ``Stretch`` times wider, its
middle at ``Position`` (``Align``: 0 left end, 0.5 middle, 1 right end), turned ``Angle``
degrees, in the design system's ``ui`` font (``Cinematics.json`` ``fonts``: a file of the
system's font folder).

``CIN.Overlay.Title``: a line of display type in the design system's ``title`` font, as the
text is.

``CIN.Overlay.Rect``: a rectangle ``Size`` (width, height) about ``Position``, turned ``Angle``.

``CIN.Overlay.Triangle``: a triangle with the corners ``A``, ``B`` and ``C``.

``CIN.Overlay.Emblems``: ``Count`` rarity emblems in a row about ``Position``, ``Spacing``
apart, each ``Size`` across: the design system's ``emblem``, three folded blades turned a third
of a turn apart round a point, the shaded face of each drawn at its ``shade_opacity``.

``CIN.Overlay.Beam``: a line of light across the picture at height ``Height``, ``Width`` thick,
its head travelling from the left edge to the right one between the frames ``Grow``
(start, frames), a soft halo ``Halo`` times as thick round it.

``CIN.Overlay.Curtain``: an aurora of ``Count`` upright streaks of light across the picture
between ``Across`` (left and right ends; 0, 0: all of it), each its own width, drifting sideways
at ``Drift``; the colours of their heads pass from ``Color A`` through ``Color B`` and
``Color C`` to ``Color D``, of their feet from ``Foot A`` to ``Foot D``, at the frames ``First``
and ``Times``, each streak a little ahead or behind (``Stagger`` frames), the colour running from
foot to head up each streak (passing from one to the other round its middle), as bright all the way
up, soft at its sides; the whole curtain comes in over ``Fade In`` and goes out over ``Fade Out``
(start frame, frames).

``CIN.Overlay.Contours``: an inverted triangle ``Size`` across about ``Position``: a landscape
with its contour lines cut out (``CIN.OverlayContours``).
"""
from __future__ import annotations

import math
import os

import bpy

from Core.gn import GN, asset
from .. import CINEMATICS
from . import materials as M


def font(key):
    """The design system's font ``key`` (``Cinematics.json`` ``fonts``), loaded from the system's font folder."""
    name = CINEMATICS["fonts"][key]
    path = os.path.join(os.environ["WINDIR"], "Fonts", name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"font '{key}': no {name} in the system's font folder")
    loaded = next((item for item in bpy.data.fonts if item.filepath and os.path.normcase(bpy.path.abspath(item.filepath)) == os.path.normcase(path)),
                  None)
    return loaded or bpy.data.fonts.load(path)


def _inked(graph, geometry):
    """Store ``ink``, ``glow``, ``alpha``, ``hatch`` and ``place`` (from the inputs Color, Glow, Fade In, Fade Out, Falloff,
    Hatch) on ``geometry``, moved as it slides in, drifts and slides out (Slide In, Slide Time, Slide Ease, Drift, Slide Out, Slide Out Time), in
    CIN.OverlayInk, at ``Opacity``.  A part of ``geometry`` carrying an ``opacity`` of its own is drawn at that share of the item's."""
    color = graph.inp("Color", "COLOR", default=(1.0, 1.0, 1.0, 1.0))
    glow = graph.inp("Glow", default=1.0, min=0.0)
    opacity_input = graph.inp("Opacity", default=1.0, min=0.0, max=1.0)
    fade_in = graph.inp("Fade In", "VECTOR", default=(0.0, 0.0, 0.0), desc="Start frame, frames")
    fade_out = graph.inp("Fade Out", "VECTOR", default=(100000.0, 0.0, 0.0), desc="Start frame, frames")
    slide = graph.inp("Slide In", "VECTOR", default=(0.0, 0.0, 0.0), desc="Where it comes in from, from its place")
    slide_time = graph.inp("Slide Time", "VECTOR", default=(0.0, 0.0, 0.0), desc="Start frame, frames")
    ease = graph.inp("Slide Ease", default=2.0, min=1.0, desc="How sharply it slows as it arrives (power of the time left)")
    drift = graph.inp("Drift", "VECTOR", default=(0.0, 0.0, 0.0), desc="How far it moves a frame from the slide's start")
    slide_out = graph.inp("Slide Out", "VECTOR", default=(0.0, 0.0, 0.0), desc="Where it leaves to, from its place")
    slide_out_time = graph.inp("Slide Out Time", "VECTOR", default=(100000.0, 0.0, 0.0), desc="Start frame, frames")
    falloff = graph.inp("Falloff", default=0.0, min=0.0, max=1.0, desc="Opacity lost from its top to its foot")
    hatch = graph.inp("Hatch", "VECTOR", default=(0.0, 0.0, 0.5), desc="Stripes: period (0: solid), angle (degrees), inked share")
    frame = graph.scene_frame()
    coming = graph.clamp01((frame - fade_in.x) / graph.max(fade_in.y, 0.001))
    going = 1.0 - graph.clamp01((frame - fade_out.x) / graph.max(fade_out.y, 0.001))
    bounds = graph.bound_box(geometry)
    low, high = bounds["Min"], bounds["Max"]
    rise = graph.clamp01((graph.position().y - low.y) / graph.max(high.y - low.y, 0.0001))
    arriving = graph.clamp01((frame - slide_time.x) / graph.max(slide_time.y, 0.001))
    remaining = graph.math("POWER", 1.0 - arriving, ease)
    geometry = graph.store(geometry, "ink", color, "FLOAT_COLOR")
    geometry = graph.store(geometry, "glow", glow)
    own = graph.n("GeometryNodeInputNamedAttribute", Name="opacity", props={"data_type": "FLOAT"})
    opacity = graph.switch(own["Exists"], 1.0, own["Attribute"], input_type="FLOAT")
    geometry = graph.store(geometry, "alpha", coming * going * (1.0 - falloff * (1.0 - rise)) * opacity * opacity_input)
    geometry = graph.store(geometry, "hatch", hatch, "FLOAT_VECTOR")
    geometry = graph.store(geometry, "place", graph.position(), "FLOAT_VECTOR")
    leaving = graph.math("POWER", graph.clamp01((frame - slide_out_time.x) / graph.max(slide_out_time.y, 0.001)), ease)
    geometry = graph.set_pos(geometry, offset=slide * remaining + drift * graph.max(frame - slide_time.x, 0.0) + slide_out * leaving)
    return graph.mat(geometry, M.get("CIN.OverlayInk"))


def _placed(graph, geometry, position, angle):
    return graph.transform(geometry, t=position, r=graph.vec(0.0, 0.0, angle))


@asset("CIN.Overlay.DiamondWipe", "Overlays")
def diamond_wipe():
    """The picture uncovered through a lattice of shrinking diamonds (see the module notes)."""
    graph = GN("CIN.Overlay.DiamondWipe", diamond_wipe.__doc__)
    aspect = graph.inp("Aspect", default=16.0 / 9.0, min=0.1)
    columns = graph.inp("Columns", "INT", default=14, min=1)
    start = graph.inp("Start", default=0.0)
    duration = graph.inp("Duration", default=4.0, min=0.01)
    sweep = graph.inp("Sweep", default=4.0, min=0.0)
    edge = graph.inp("Edge", default=0.12, min=0.0, max=1.0)
    material = graph.inp("Material", "MATERIAL", default=M.get("CIN.OverlayBlack"))
    edge_material = graph.inp("Edge Material", "MATERIAL", default=M.get("CIN.OverlayWhite"))
    cell = aspect * 2.0 / columns
    rows = graph.to_int(graph.math("CEIL", 2.0 / cell) * 2.0 + 3.0, "FLOOR")
    count = graph.to_int(graph.math("MULTIPLY", columns + 2, rows), "FLOOR")
    points = graph.new_points(count)
    index = graph.index()
    column = graph.math("MODULO", index, columns + 2)
    row = graph.math("FLOOR", index / (columns + 2))
    shift = graph.math("MODULO", row, 2.0) * 0.5
    place = graph.vec((column + shift) * cell - aspect - cell * 0.5, row * cell * 0.5 - 1.0 - cell * 0.5, 0.0)
    points = graph.set_pos(points, pos=place)
    lateness = (aspect - graph.position().x) / (aspect * 2.0) * sweep
    progress = graph.clamp01((graph.scene_frame() - start - lateness) / duration)
    size = cell * (1.0 - progress) * 0.7072 * 1.02
    diamond = graph.transform(graph.n("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=1.0, Vertices_X=2, Vertices_Y=2)["Mesh"],
                              r=graph.vec(0.0, 0.0, math.radians(45.0)))
    covers = graph.iop(points, graph.mat(diamond, material), scale=graph.vec(size, size, 1.0))
    glowing = graph.math("MULTIPLY", graph.compare(progress, 0.0, "GREATER_THAN"), graph.compare(progress, 1.0, "LESS_THAN"))
    rim = graph.iop(points, graph.mat(graph.move(diamond, z=-0.001), edge_material),
                    scale=graph.vec(size * (1.0 + edge), size * (1.0 + edge), 1.0), sel=glowing)
    graph.result(graph.realize(graph.join(covers, rim)))
    return graph


def _lettered(name, doc, key):
    """A line of letters in the design system's font ``key`` (see the module notes)."""
    graph = GN(name, doc)
    words = graph.inp("Text", "STRING", default="")
    size = graph.inp("Size", default=0.1, min=0.0)
    position = graph.inp("Position", "VECTOR", default=(0.0, 0.0, 0.0))
    align = graph.inp("Align", default=0.5, min=0.0, max=1.0)
    angle = graph.inp("Angle", default=0.0, subtype="ANGLE")
    spacing = graph.inp("Spacing", default=1.0, min=0.0)
    stretch = graph.inp("Stretch", default=1.0, min=0.01)
    letters = graph.n("GeometryNodeStringToCurves", String=words, Size=size, Character_Spacing=spacing, Font=font(key))
    face = graph.transform(graph.fill(graph.realize(letters["Curve Instances"])), s=graph.vec(stretch, 1.0, 1.0))
    bounds = graph.bound_box(face)
    low, high = bounds["Min"], bounds["Max"]
    anchor = graph.vec(low.x + (high.x - low.x) * align, (low.y + high.y) * 0.5, 0.0)
    graph.result(_inked(graph, _placed(graph, graph.set_pos(face, offset=anchor * -1.0), position, angle)))
    return graph


@asset("CIN.Overlay.Text", "Overlays")
def text():
    """A line of text in the design system's ui font (see the module notes)."""
    return _lettered("CIN.Overlay.Text", text.__doc__, "ui")


@asset("CIN.Overlay.Title", "Overlays")
def title():
    """A line of display type in the design system's title font (see the module notes)."""
    return _lettered("CIN.Overlay.Title", title.__doc__, "title")


@asset("CIN.Overlay.Rect", "Overlays")
def rect():
    """A rectangle (see the module notes)."""
    graph = GN("CIN.Overlay.Rect", rect.__doc__)
    size = graph.inp("Size", "VECTOR", default=(1.0, 0.1, 0.0))
    position = graph.inp("Position", "VECTOR", default=(0.0, 0.0, 0.0))
    angle = graph.inp("Angle", default=0.0, subtype="ANGLE")
    sheet = graph.n("GeometryNodeMeshGrid", Size_X=size.x, Size_Y=size.y, Vertices_X=2, Vertices_Y=2)["Mesh"]
    graph.result(_inked(graph, _placed(graph, sheet, position, angle)))
    return graph


@asset("CIN.Overlay.Triangle", "Overlays")
def triangle():
    """A triangle (see the module notes)."""
    graph = GN("CIN.Overlay.Triangle", triangle.__doc__)
    corners = [graph.inp(name, "VECTOR", default=default) for name, default in
               (("A", (0.0, 0.0, 0.0)), ("B", (0.1, 0.0, 0.0)), ("C", (0.0, 0.1, 0.0)))]
    graph.result(_inked(graph, graph.fill(graph.polyline(corners, cyclic=True))))
    return graph


@asset("CIN.Overlay.Emblems", "Overlays")
def emblems():
    """A row of rarity emblems (see the module notes)."""
    graph = GN("CIN.Overlay.Emblems", emblems.__doc__)
    count = graph.inp("Count", "INT", default=6, min=1)
    position = graph.inp("Position", "VECTOR", default=(0.0, 0.0, 0.0))
    spacing = graph.inp("Spacing", default=0.15, min=0.0)
    size = graph.inp("Size", default=0.13, min=0.0)
    design = CINEMATICS["emblem"]
    faces = [graph.store(graph.fill(graph.polyline([(x, y, 0.0) for x, y in design[key]], cyclic=True)), "opacity", opacity)
             for key, opacity in (("light", 1.0), ("shade", design["shade_opacity"]))]
    blade = graph.join(*faces)
    blades = graph.join(*[graph.transform(blade, r=graph.vec(0.0, 0.0, math.radians(120.0 * k))) for k in range(3)])
    row = graph.n("GeometryNodeMeshLine", Count=count, Offset=graph.vec(spacing, 0.0, 0.0)).o
    row = graph.set_pos(row, offset=graph.vec(spacing * (count - 1) * -0.5, 0.0, 0.0) + position)
    graph.result(_inked(graph, graph.realize(graph.iop(graph.n("GeometryNodeMeshToPoints", Mesh=row).o, blades,
                                                       scale=graph.vec(size, size, 1.0)))))
    return graph


@asset("CIN.Overlay.Beam", "Overlays")
def beam():
    """A line of light crossing the picture (see the module notes)."""
    graph = GN("CIN.Overlay.Beam", beam.__doc__)
    aspect = graph.inp("Aspect", default=16.0 / 9.0, min=0.1)
    height = graph.inp("Height", default=0.0)
    width = graph.inp("Width", default=0.012, min=0.0)
    halo = graph.inp("Halo", default=6.0, min=1.0)
    grow = graph.inp("Grow", "VECTOR", default=(0.0, 4.0, 0.0), desc="Start frame, frames")
    reach = graph.clamp01((graph.scene_frame() - grow.x) / graph.max(grow.y, 0.001))
    length = graph.max(reach * aspect * 2.0, 0.0001)
    core = graph.n("GeometryNodeMeshGrid", Size_X=length, Size_Y=width, Vertices_X=2, Vertices_Y=2)["Mesh"]
    glow = graph.n("GeometryNodeMeshGrid", Size_X=length, Size_Y=width * halo, Vertices_X=2, Vertices_Y=3)["Mesh"]
    glow = graph.store(glow, "edge", graph.abs(graph.position().y) / (width * halo * 0.5))
    line = graph.join(graph.move(core, z=0.0005), glow)
    graph.result(_inked(graph, graph.set_pos(line, offset=graph.vec(aspect * -1.0 + length * 0.5, height, 0.0))))
    return graph


@asset("CIN.Overlay.Curtain", "Overlays")
def curtain():
    """An aurora of upright streaks of light (see the module notes)."""
    graph = GN("CIN.Overlay.Curtain", curtain.__doc__)
    aspect = graph.inp("Aspect", default=16.0 / 9.0, min=0.1)
    count = graph.inp("Count", "INT", default=90, min=1)
    across_range = graph.inp("Across", "VECTOR", default=(0.0, 0.0, 0.0), desc="Left and right ends of the streaks (0, 0: the whole picture)")
    seed = graph.inp("Seed", "INT", default=0)
    drift = graph.inp("Drift", default=0.004, desc="Picture units a frame")
    times = graph.inp("Times", "VECTOR", default=(0.0, 10.0, 20.0), desc="Frames of colours B, C and D")
    first = graph.inp("First", default=0.0, desc="Frame of colour A")
    stagger = graph.inp("Stagger", default=3.0, min=0.0)
    colors = [graph.inp(f"Color {name}", "COLOR", default=default) for name, default in
              (("A", (0.1, 0.8, 0.3, 1.0)), ("B", (0.2, 0.8, 0.9, 1.0)), ("C", (1.0, 0.9, 0.4, 1.0)), ("D", (0.9, 0.3, 0.1, 1.0)))]
    feet = [graph.inp(f"Foot {name}", "COLOR", default=default) for name, default in
            (("A", (0.1, 0.8, 0.3, 1.0)), ("B", (0.2, 0.8, 0.9, 1.0)), ("C", (1.0, 0.9, 0.4, 1.0)), ("D", (0.9, 0.3, 0.1, 1.0)))]
    fade_in = graph.inp("Fade In", "VECTOR", default=(0.0, 0.0, 0.0), desc="Start frame, frames")
    fade_out = graph.inp("Fade Out", "VECTOR", default=(100000.0, 0.0, 0.0), desc="Start frame, frames")
    frame = graph.scene_frame()
    present = graph.clamp01((frame - fade_in.x) / graph.max(fade_in.y, 0.001)) * (1.0 - graph.clamp01((frame - fade_out.x) / graph.max(fade_out.y, 0.001)))

    def draw(salt, low=0.0, high=1.0):
        return graph.random(low, high, seed * 13 + salt, ID=graph.index())

    streaks = graph.new_points(count)
    clock = graph.scene_frame() + draw(1, -1.0, 1.0) * stagger
    whole = graph.compare(graph.abs(across_range.x) + graph.abs(across_range.y), 0.0, "EQUAL")
    left = graph.switch(whole, across_range.x, aspect * -1.2, "FLOAT")
    right = graph.switch(whole, across_range.y, aspect * 1.2, "FLOAT")
    across = left + (right - left) * draw(2) + graph.scene_frame() * drift * draw(3, 0.5, 1.5)
    streaks = graph.set_pos(streaks, pos=graph.vec(across, 0.0, draw(4, -0.01, 0.0)))
    stops = [first, times.x, times.y, times.z]

    def passing(track):
        blend = track[0]
        for k in range(1, 4):
            share = graph.clamp01((clock - stops[k - 1]) / graph.max(stops[k] - stops[k - 1], 0.001))
            blend = graph.mix(share, blend, track[k], "RGBA")
        return blend

    streak = graph.n("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=3.0, Vertices_X=5, Vertices_Y=13)["Mesh"]
    streak = graph.store(streak, "rise", (graph.position().y + 1.0) / 2.0)
    streak = graph.store(streak, "edge", graph.abs(graph.position().x) * 2.0)
    streaks = graph.store(streaks, "tint", passing(colors), "FLOAT_COLOR")
    streaks = graph.store(streaks, "foot tint", passing(feet), "FLOAT_COLOR")
    streaks = graph.store(streaks, "strength", draw(5, 0.7, 1.0))
    sheets = graph.realize(graph.iop(streaks, streak, scale=graph.vec(draw(6, 0.05, 0.4), 1.0, 1.0)))
    rise = graph.named("rise")
    turn = graph.n("ShaderNodeMapRange", Value=rise, From_Min=0.3, From_Max=0.7, To_Min=0.0, To_Max=1.0, props={"interpolation_type": "SMOOTHSTEP"})["Result"]
    sheets = graph.store(sheets, "ink", graph.mix(turn, graph.named("foot tint", "FLOAT_COLOR"), graph.named("tint", "FLOAT_COLOR"), "RGBA"),
                         "FLOAT_COLOR")
    sheets = graph.store(sheets, "glow", graph.named("strength") * present)
    sheets = graph.store(sheets, "alpha", graph.named("strength") * present)
    graph.result(graph.mat(sheets, M.get("CIN.OverlayInk")))
    return graph


@asset("CIN.Overlay.Contours", "Overlays")
def contours():
    """An inverted triangle of contour lines (see the module notes)."""
    graph = GN("CIN.Overlay.Contours", contours.__doc__)
    size = graph.inp("Size", default=1.2, min=0.0)
    position = graph.inp("Position", "VECTOR", default=(0.0, 0.0, 0.0))
    triangle = graph.fill(graph.polyline([(-0.5, 0.29, 0.0), (0.5, 0.29, 0.0), (0.0, -0.58, 0.0)], cyclic=True))
    triangle = graph.n("GeometryNodeSubdivideMesh", Mesh=triangle, Level=5).o
    triangle = graph.store(triangle, "landscape", graph.position(), "FLOAT_VECTOR")
    sheet = graph.set_pos(graph.transform(triangle, s=graph.vec(size, size, 1.0)), offset=position)
    sheet = _inked(graph, sheet)
    graph.result(graph.mat(sheet, M.get("CIN.OverlayContours")))
    return graph
