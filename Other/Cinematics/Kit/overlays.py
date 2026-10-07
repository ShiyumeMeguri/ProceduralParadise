"""
Overlays kit (``CIN.Overlay.*``): what a shot's camera carries in front of its lens, drawn in the
picture's units -- across from -``Aspect`` to +``Aspect``, up from -1 to +1 (``scenes`` overlays).

Every piece but the wipe is drawn in ink (``CIN.OverlayInk``): its ``Color``, brightened by its
``Glow``, at ``Opacity``, coming in over ``Fade In`` and going out over ``Fade Out`` (each a start
frame and a number of frames; a length of 0 is no fade) -- stored on it as ``ink``, ``glow`` and
``alpha``.
It slides from ``Slide In`` away to its place over ``Slide Time`` (start frame, frames), slowing
as it arrives (the share of the way still to go is the share of the time left to the power
``Slide Ease``), and from that start drifts on by ``Drift`` a frame; it leaves sliding away by
``Slide Out`` over ``Slide Out Time``, gathering speed the same way; its opacity falls by
``Falloff`` from its top to its foot.  A light front may cross it along ``Sweep Angle`` (degrees,
0 rightwards) over ``Sweep`` (start frame, frames, soft width), the share of it lit going from
``Sweep Span.x`` to ``Sweep Span.y`` and slowing as it stops as a slide does (``Sweep Span.z``):
what the front has not reached is unlit, and behind it the light fades over ``Trail`` (0: it
does not fade).  With a ``Hatch`` (period, angle in degrees, share) its ink
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
its head travelling from the left edge to the right one over ``Grow`` (start frame, frames) and
its tail after it over ``Retract`` (start frame, frames, gathering speed as the power ``z`` of the
time gone), a soft halo ``Halo`` times as thick round it; its ends curl up towards the picture's
edges (``Curl``: the rise at an edge, the distance in which it falls to 1/e of that).

``CIN.Overlay.Curtain``: a curtain of light hanging across the picture between ``Across`` (left
and right ends; 0, 0: all of it), fading out over ``Feather`` at its left end and at its right
(a curtain laid over a neighbour fades in over it alone, the one beneath staying whole) -- upright streaks,
the brightness of every column a noise across the picture (``Streaks``: streaks to a unit across,
octaves of finer ones, their roughness), the spread of the brightness's logarithm its ``Contrast``
at the head and at the foot, the noise drifting sideways by ``Drift`` and changing by ``Evolve`` a
frame.  Up every column the colour passes from
the ``Foot`` colour to the ``Head`` colour about a height (``Turn``: its mean as a share of the
picture's height from the foot, the spread of the height across the picture, how softly it
passes), each colour's alpha the curtain's opacity there.  The median column is drawn in the
colours themselves.  With a ``Coverage`` (threshold, softness, both in spreads of the noise; a
softness of 0: every streak) only the streaks the threshold passes are drawn.  A film keys the
colours and the turn frame by frame (``scenes``: an overlay's ``keys``).

``CIN.Overlay.Drawing``: a drawing (its mesh handed to it: ``drawings``) ``Size`` times its own
size about ``Position``, each point inked at its ``tone`` to the power ``Contrast`` of the
piece's opacity, its lettering at ``Lettering`` times that.

``CIN.Overlay.Haze``: a haze across the picture, its ink's opacity a noise of ``Scale`` (to a
unit) and ``Detail`` octaves to the power ``Contrast``, drifting by ``Drift`` a frame.
"""
from __future__ import annotations

import math
import os

import bpy

from Core.gn import GN, asset
from .. import CINEMATICS
from . import materials as M

BEAM_COLUMNS = 241
CURTAIN_COLUMNS = 280
CURTAIN_ROWS = 49
HAZE_COLUMNS = 97
HAZE_ROWS = 55


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
    sweep = graph.inp("Sweep", "VECTOR", default=(0.0, 0.0, 0.1), desc="A light front crossing it: start frame, frames, soft width")
    sweep_span = graph.inp("Sweep Span", "VECTOR", default=(1.0, 1.0, 2.0), desc="Share of it lit as the front sets out and as it stops, ease")
    sweep_angle = graph.inp("Sweep Angle", default=0.0, desc="Direction the front travels in, degrees (0: rightwards)")
    trail = graph.inp("Trail", default=0.0, min=0.0, desc="Distance the light fades over behind the front (0: no fading)")
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
    lit = _swept(graph, low, high, sweep, sweep_span, sweep_angle, trail)
    geometry = graph.store(geometry, "alpha", coming * going * (1.0 - falloff * (1.0 - rise)) * opacity * opacity_input * lit)
    geometry = graph.store(geometry, "hatch", hatch, "FLOAT_VECTOR")
    geometry = graph.store(geometry, "place", graph.position(), "FLOAT_VECTOR")
    leaving = graph.math("POWER", graph.clamp01((frame - slide_out_time.x) / graph.max(slide_out_time.y, 0.001)), ease)
    geometry = graph.set_pos(geometry, offset=slide * remaining + drift * graph.max(frame - slide_time.x, 0.0) + slide_out * leaving)
    return graph.mat(geometry, M.get("CIN.OverlayInk"))


def _swept(graph, low, high, sweep, span, angle, trail):
    """The share of the light a light front crossing the piece (bounds ``low``, ``high``) leaves at each point."""
    turn = graph.math("RADIANS", angle)
    cosine, sine = graph.math("COSINE", turn), graph.math("SINE", turn)
    along = graph.position().x * cosine + graph.position().y * sine
    nearest = graph.min(low.x * cosine, high.x * cosine) + graph.min(low.y * sine, high.y * sine)
    farthest = graph.max(low.x * cosine, high.x * cosine) + graph.max(low.y * sine, high.y * sine)
    progress = graph.clamp01((graph.scene_frame() - sweep.x) / graph.max(sweep.y, 0.001))
    share = span.x + (span.y - span.x) * (1.0 - graph.math("POWER", 1.0 - progress, span.z))
    soft = graph.max(sweep.z, 0.0001)
    front = nearest + share * (farthest - nearest + soft)
    fading = graph.math("EXPONENT", graph.max(front - soft - along, 0.0) * -1.0 / graph.max(trail, 0.0001))
    fading = graph.switch(graph.compare(trail, 0.0, "GREATER_THAN"), 1.0, fading, "FLOAT")
    return graph.clamp01((front - along) / soft) * fading


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
    retract = graph.inp("Retract", "VECTOR", default=(100000.0, 4.0, 1.0), desc="Start frame, frames, gathering (power of the time gone)")
    curl = graph.inp("Curl", "VECTOR", default=(0.0, 0.1, 0.0), desc="Rise at the picture's edges, distance it falls to 1/e in")
    frame = graph.scene_frame()
    head = graph.clamp01((frame - grow.x) / graph.max(grow.y, 0.001))
    tail = graph.math("POWER", graph.clamp01((frame - retract.x) / graph.max(retract.y, 0.001)), retract.z)
    start = aspect * -1.0 + tail * aspect * 2.0
    length = graph.max((head - tail) * aspect * 2.0, 0.0001)
    core = graph.n("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=width, Vertices_X=BEAM_COLUMNS, Vertices_Y=2)["Mesh"]
    glow = graph.n("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=width * halo, Vertices_X=BEAM_COLUMNS, Vertices_Y=3)["Mesh"]
    glow = graph.store(glow, "edge", graph.abs(graph.position().y) / (width * halo * 0.5))
    line = graph.join(graph.move(core, z=0.0005), glow)
    across = start + (graph.position().x + 0.5) * length
    to_edge = graph.min(across + aspect, aspect - across)
    rise = curl.x * graph.math("EXPONENT", to_edge * -1.0 / graph.max(curl.y, 0.0001))
    line = graph.set_pos(line, pos=graph.vec(across, graph.position().y + height + rise, graph.position().z))
    graph.result(_inked(graph, line))
    return graph


@asset("CIN.Overlay.Curtain", "Overlays")
def curtain():
    """A curtain of light hanging across the picture (see the module notes)."""
    graph = GN("CIN.Overlay.Curtain", curtain.__doc__)
    aspect = graph.inp("Aspect", default=16.0 / 9.0, min=0.1)
    across_range = graph.inp("Across", "VECTOR", default=(0.0, 0.0, 0.0), desc="Left and right ends (0, 0: the whole picture)")
    feather = graph.inp("Feather", "VECTOR", default=(0.0, 0.0, 0.0), desc="Picture units its left and right ends fade out over")
    seed = graph.inp("Seed", default=0.0)
    streaks = graph.inp("Streaks", "VECTOR", default=(6.0, 4.0, 0.6), desc="Streaks to a unit across, octaves of finer ones, roughness")
    contrast = graph.inp("Contrast", "VECTOR", default=(1.0, 1.0, 0.0), desc="Spread of log brightness at the head and at the foot")
    drift = graph.inp("Drift", default=0.004, desc="Picture units a frame")
    evolve = graph.inp("Evolve", default=0.02, desc="How fast the streaks change, a frame")
    turn = graph.inp("Turn", "VECTOR", default=(0.5, 0.0, 0.1), desc="Height the foot's colour passes to the head's at, its spread across, softness")
    coverage = graph.inp("Coverage", "VECTOR", default=(0.0, 0.0, 0.0), desc="Threshold and softness of the streaks drawn (softness 0: all)")
    head = graph.inp("Head", "COLOR", default=(0.2, 0.8, 0.4, 1.0))
    foot = graph.inp("Foot", "COLOR", default=(0.2, 0.8, 0.4, 1.0))
    frame = graph.scene_frame()
    whole = graph.compare(graph.abs(across_range.x) + graph.abs(across_range.y), 0.0, "EQUAL")
    left = graph.switch(whole, across_range.x, aspect * -1.0, "FLOAT")
    right = graph.switch(whole, across_range.y, aspect, "FLOAT")
    columns = graph.to_int((right - left) * CURTAIN_COLUMNS + 2.0, "CEILING")
    sheet = graph.n("GeometryNodeMeshGrid", Size_X=1.0, Size_Y=2.0, Vertices_X=columns, Vertices_Y=CURTAIN_ROWS)["Mesh"]
    sheet = graph.set_pos(sheet, pos=graph.vec(left + (graph.position().x + 0.5) * (right - left), graph.position().y, 0.0))
    across = graph.position().x
    rise = (graph.position().y + 1.0) * 0.5

    def noise(salt, scale):
        place = graph.vec((across + frame * drift) * scale, frame * evolve, seed * 7.31 + salt)
        raw = graph.n("ShaderNodeTexNoise", Vector=place, Scale=1.0, Detail=streaks.y, Roughness=streaks.z, props={"noise_dimensions": "3D"})["Fac"]
        spread = graph.statistic(sheet, raw)
        return (raw - spread["Mean"]) / graph.max(spread["Standard Deviation"], 0.0001)

    shine = noise(0.0, streaks.x)
    height = turn.x + turn.y * graph.max(graph.min(noise(31.7, streaks.x * 0.5), 2.5), -2.5)
    passing_up = graph.map_range(rise, height - turn.z, height + turn.z, 0.0, 1.0, interp="SMOOTHSTEP")
    brightness = graph.math("EXPONENT", shine * graph.mix(passing_up, contrast.y, contrast.x))
    head_parts = graph.n("FunctionNodeSeparateColor", Color=head)
    foot_parts = graph.n("FunctionNodeSeparateColor", Color=foot)
    opacity = graph.mix(passing_up, foot_parts["Alpha"], head_parts["Alpha"])
    covered = graph.clamp01((shine - coverage.x) / graph.max(coverage.y, 0.0001))
    covered = graph.switch(graph.compare(coverage.y, 0.0, "GREATER_THAN"), 1.0, covered, "FLOAT")
    ends = graph.clamp01((across - left) / graph.max(feather.x, 0.0001)) * graph.clamp01((right - across) / graph.max(feather.y, 0.0001))
    sheet = graph.store(sheet, "ink", graph.mix(passing_up, foot, head, "RGBA"), "FLOAT_COLOR")
    sheet = graph.store(sheet, "glow", brightness)
    sheet = graph.store(sheet, "alpha", opacity * ends * covered)
    graph.result(graph.mat(sheet, M.get("CIN.OverlayInk")))
    return graph


@asset("CIN.Overlay.Drawing", "Overlays")
def drawing():
    """A drawing (see the module notes)."""
    graph = GN("CIN.Overlay.Drawing", drawing.__doc__)
    sheet = graph.inp("Geometry", "GEOMETRY")
    size = graph.inp("Size", default=1.0, min=0.0)
    position = graph.inp("Position", "VECTOR", default=(0.0, 0.0, 0.0))
    contrast = graph.inp("Contrast", default=1.0, min=0.01, desc="Power its tones are raised to")
    lettering = graph.inp("Lettering", default=1.0, min=0.0, desc="Its lettering's opacity against the rest's")
    strength = graph.mix(graph.named("lettering"), 1.0, lettering)
    sheet = graph.store(sheet, "opacity", graph.math("POWER", graph.named("tone"), contrast) * strength)
    sheet = graph.set_pos(graph.transform(sheet, s=graph.vec(size, size, 1.0)), offset=position)
    graph.result(_inked(graph, sheet))
    return graph


@asset("CIN.Overlay.Haze", "Overlays")
def haze():
    """A haze across the picture (see the module notes)."""
    graph = GN("CIN.Overlay.Haze", haze.__doc__)
    aspect = graph.inp("Aspect", default=16.0 / 9.0, min=0.1)
    scale = graph.inp("Scale", default=1.5, min=0.0)
    detail = graph.inp("Detail", default=2.0, min=0.0)
    contrast = graph.inp("Contrast", default=2.0, min=0.01)
    seed = graph.inp("Seed", default=0.0)
    drift = graph.inp("Drift", "VECTOR", default=(0.0, 0.0, 0.0), desc="Picture units a frame")
    sheet = graph.n("GeometryNodeMeshGrid", Size_X=aspect * 2.0, Size_Y=2.0, Vertices_X=HAZE_COLUMNS, Vertices_Y=HAZE_ROWS)["Mesh"]
    place = graph.position() - drift * graph.scene_frame()
    density = graph.n("ShaderNodeTexNoise", Vector=place, W=seed, Scale=scale, Detail=detail, Roughness=0.5,
                      props={"noise_dimensions": "4D"})["Fac"]
    sheet = graph.store(sheet, "opacity", graph.math("POWER", graph.clamp01(density), contrast))
    graph.result(_inked(graph, sheet))
    return graph
