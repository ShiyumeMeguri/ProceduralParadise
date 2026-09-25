"""
Shanhaijing architecture kit -- geometry-node groups (``SHJ.Arch.*``).

Local frames (all lengths in metres):

* linear members (beams, walls, bands) run along local +X from the origin,
  are centred on Y (walls: finished face at y = 0, body towards +Y) and sit
  on z = 0 unless stated otherwise;
* windows are centred on the origin in the XZ plane, looking along -Y;
* columns and posts stand on (or hang from) the origin along Z.

Rooms place and rotate the parts; the parts themselves carry the
dimensions and details of the Shanhaijing design system (Academy.json).
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset, set_mode
from .. import LEVELS, TIMBER

SQ2 = math.sqrt(2.0)
STAND = (math.pi * 0.5, 0.0, 0.0)          # XY plane -> XZ plane (face towards -Y)
PROFILE_X = (math.pi * 0.5, 0.0, math.pi * 0.5)   # XY profile -> YZ plane, normal +X


def flat_sweep(g, curve, w, d):
    """Sweep a planar XY curve with a w (in plane) x d (along Z) bar."""
    nd = g.n("GeometryNodeSetCurveNormal", curve)
    set_mode(nd, "Z_UP")
    return g.sweep(nd.o, g.rect(w, d), True)


def solid(g, face, depth, direction=(0.0, 0.0, 1.0)):
    """Closed prism: extrude a face along ``direction`` and keep the
    (flipped) original face as the back cap."""
    ext = g.extrude(face, depth, direction=direction)
    back = g.n("GeometryNodeFlipFaces", face).o
    return g.merge(g.join(ext, back), 0.0001)


# ------------------------------------------------------------------ basics
@asset("SHJ.Arch.Slab", "Architecture")
def slab():
    """Axis-aligned box from (0, 0, 0) to (Size X, Size Y, Thickness):
    floors, ceilings, bands, boards."""
    g = GN("SHJ.Arch.Slab", slab.__doc__)
    sx = g.inp("Size X", default=4.0, subtype="DISTANCE")
    sy = g.inp("Size Y", default=4.0, subtype="DISTANCE")
    t = g.inp("Thickness", default=0.2, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    g.result(g.mat(g.box(0.0, 0.0, 0.0, sx, sy, t), m))
    return g


def _rounded_rect_profile(g, w, h, r):
    """Closed rectangle curve (w x h, centred) with filleted corners, in XY."""
    return g.fillet(g.rect(w, h), r, 3)


@asset("SHJ.Arch.Beam", "Architecture")
def beam():
    """Timber beam with eased (rounded) arrises so its edges catch the light
    like the painted beams.  Runs along +X from the origin, centred on Y,
    bottom on z = 0."""
    g = GN("SHJ.Arch.Beam", beam.__doc__)
    L = g.inp("Length", default=4.0, subtype="DISTANCE")
    W = g.inp("Width", default=TIMBER["beam_width"], subtype="DISTANCE")
    H = g.inp("Height", default=TIMBER["beam_depth"], subtype="DISTANCE")
    r = g.inp("Edge Radius", default=0.012, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    prof = g.fill(_rounded_rect_profile(g, W, H, r))
    prof = g.transform(prof, r=PROFILE_X)
    body = solid(g, prof, L, (1.0, 0.0, 0.0))
    body = g.move(body, z=H * 0.5)
    g.result(g.smooth_by_angle(g.mat(body, m), 0.6))
    return g


@asset("SHJ.Arch.HangingPost", "Architecture")
def hanging_post():
    """Hanging post (垂柱): square timber post hanging from the origin down
    by Length, finished with a turned disc (and a small knob) at the foot."""
    g = GN("SHJ.Arch.HangingPost", hanging_post.__doc__)
    L = g.inp("Length", default=0.85, subtype="DISTANCE")
    s = g.inp("Size", default=TIMBER["hanging_post"], subtype="DISTANCE")
    dr = g.inp("Disc Radius", default=TIMBER["hanging_disc_radius"], subtype="DISTANCE")
    dt = g.inp("Disc Thickness", default=0.05, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    md = g.inp("Disc Material", "MATERIAL")
    post = g.box(s * -0.5, s * -0.5, L * -1.0, s * 0.5, s * 0.5, 0.0)
    post = g.mat(g.smooth(post, False), m)
    disc = g.cylinder(dr, dt, 32)
    disc = g.move(disc, z=L * -1.0 - dt * 0.5 + 0.01)
    rim = g.cylinder(dr * 0.8, dt * 0.6, 32)
    rim = g.move(rim, z=L * -1.0 - dt - dt * 0.3 + 0.01)
    feet = g.join(disc, rim)
    has = g.compare(dr, 0.001, "GREATER_THAN")
    feet = g.switch(has, None, feet)
    g.result(g.join(post, g.smooth_by_angle(g.mat(feet, md), 0.5)))
    return g


# ----------------------------------------------------------------- columns
@asset("SHJ.Arch.Column", "Architecture")
def column():
    """Round lacquered column on a stone drum base.  An optional sleeve
    (e.g. red lacquer between Sleeve Bottom and Sleeve Top) with gold rings
    at both ends, and a gold capital band below the top."""
    g = GN("SHJ.Arch.Column", column.__doc__)
    R = g.inp("Radius", default=TIMBER["column_diameter"] * 0.5, subtype="DISTANCE")
    Hh = g.inp("Height", default=5.27, subtype="DISTANCE")
    bh = g.inp("Base Height", default=0.12, subtype="DISTANCE", panel="Base")
    br = g.inp("Base Radius", default=0.2, subtype="DISTANCE", panel="Base")
    dh = g.inp("Dado Height", default=0.0, subtype="DISTANCE", panel="Base",
               desc="dark lower section above the base (0 = none)")
    s0 = g.inp("Sleeve Bottom", default=0.47, subtype="DISTANCE", panel="Sleeve")
    s1 = g.inp("Sleeve Top", default=0.0, subtype="DISTANCE", panel="Sleeve",
               desc="0 = no sleeve")
    sd = g.inp("Sleeve Offset", default=0.01, subtype="DISTANCE", panel="Sleeve")
    rw = g.inp("Ring Width", default=0.035, subtype="DISTANCE", panel="Sleeve")
    ch = g.inp("Capital Height", default=0.0, subtype="DISTANCE", panel="Top",
               desc="gold band this far below the top (0 = none)")
    m_shaft = g.inp("Shaft Material", "MATERIAL", panel="Materials")
    m_sleeve = g.inp("Sleeve Material", "MATERIAL", panel="Materials")
    m_base = g.inp("Base Material", "MATERIAL", panel="Materials")
    m_gold = g.inp("Gold Material", "MATERIAL", panel="Materials")
    m_dado = g.inp("Dado Material", "MATERIAL", panel="Materials")

    def cyl(r, z0, z1, verts=48):
        c = g.cylinder(r, z1 - z0, verts)
        return g.move(c, z=(z0 + z1) * 0.5)

    shaft = g.mat(cyl(R, bh, Hh), m_shaft)
    base = g.mat(cyl(br, 0.0, bh), m_base)
    # base drum: slightly swelling top chamfer
    base_top = g.mat(cyl(br * 0.88, bh, bh + 0.03), m_base)
    has_dado = g.compare(dh, 0.001, "GREATER_THAN")
    dado = g.switch(has_dado, None, g.mat(cyl(R + sd * 0.5, bh, dh), m_dado))
    has_sleeve = g.compare(s1, 0.001, "GREATER_THAN")
    sleeve = g.join(
        g.mat(cyl(R + sd, s0, s1), m_sleeve),
        g.mat(cyl(R + sd * 1.8, s0, s0 + rw), m_gold),
        g.mat(cyl(R + sd * 1.8, s1 - rw, s1), m_gold),
    )
    sleeve = g.switch(has_sleeve, None, sleeve)
    has_cap = g.compare(ch, 0.001, "GREATER_THAN")
    cap = g.join(g.mat(cyl(R + 0.012, Hh - ch - rw, Hh - ch), m_gold),
                 g.mat(cyl(R + 0.02, Hh - ch - rw * 2.5, Hh - ch - rw * 1.6), m_gold))
    cap = g.switch(has_cap, None, cap)
    g.result(g.smooth_by_angle(g.join(shaft, base, base_top, dado, sleeve, cap), 0.5))
    return g


# ------------------------------------------------------------------- walls
@asset("SHJ.Arch.Wall", "Architecture")
def wall():
    """Wall or panel segment: finished face at y = 0 (facing -Y), body
    towards +Y, running along +X from the origin, from z = 0 up.  One
    optional opening (Hole: 0 none, 1 round, 2 rectangle) with its reveal."""
    g = GN("SHJ.Arch.Wall", wall.__doc__)
    L = g.inp("Length", default=4.0, subtype="DISTANCE")
    H = g.inp("Height", default=3.0, subtype="DISTANCE")
    T = g.inp("Thickness", default=0.2, subtype="DISTANCE")
    hole = g.inp("Hole", "INT", default=0, min=0, max=2, panel="Opening")
    hx = g.inp("Hole X", default=2.0, subtype="DISTANCE", panel="Opening")
    hz = g.inp("Hole Z", default=1.5, subtype="DISTANCE", panel="Opening")
    hr = g.inp("Hole Radius", default=0.8, subtype="DISTANCE", panel="Opening")
    hw = g.inp("Hole Width", default=1.0, subtype="DISTANCE", panel="Opening")
    hh = g.inp("Hole Height", default=1.0, subtype="DISTANCE", panel="Opening")
    m = g.inp("Material", "MATERIAL")
    m_rev = g.inp("Reveal Material", "MATERIAL")
    outline = g.transform(g.rect(L, H), t=g.vec(L * 0.5, H * 0.5, 0.0))
    circ = g.transform(g.circle(hr, 96), t=g.vec(hx, hz, 0.0))
    rect = g.transform(g.rect(hw, hh), t=g.vec(hx, hz, 0.0))
    inner = g.index_switch(hole, [None, circ, rect], "GEOMETRY")
    face = g.fill(g.join(outline, inner), mode="NGONS")
    body = solid(g, face, T)
    # the reveal = faces whose normal lies in the wall plane and which are
    # inside the outline (not the outer border)
    P = g.position()
    px, py, pz = g.sep(P)
    inside = g.bool_and(g.bool_and(g.compare(px, 0.002, "GREATER_THAN"),
                                   g.compare(px, L - 0.002, "LESS_THAN")),
                        g.bool_and(g.compare(py, 0.002, "GREATER_THAN"),
                                   g.compare(py, H - 0.002, "LESS_THAN")))
    nz = g.sep(g.normal())[2]
    reveal = g.bool_and(inside, g.compare(g.abs(nz), 0.5, "LESS_THAN"))
    body = g.mat(body, m)
    body = g.mat(body, m_rev, sel=reveal)
    # stand up: local XY (length, height) -> world XZ, extrusion +Z -> +Y
    body = g.transform(body, r=STAND)
    body = g.transform(body, s=(1.0, -1.0, 1.0))
    g.result(g.n("GeometryNodeFlipFaces", body).o)
    return g


@asset("SHJ.Arch.PanelFrame", "Architecture")
def panel_frame():
    """Flat rectangular frame (border strips) in the XZ plane at y = 0,
    projecting towards -Y: panel edging, dado rails, plaque borders."""
    g = GN("SHJ.Arch.PanelFrame", panel_frame.__doc__)
    L = g.inp("Length", default=2.6, subtype="DISTANCE")
    H = g.inp("Height", default=3.0, subtype="DISTANCE")
    w = g.inp("Border", default=0.06, subtype="DISTANCE")
    d = g.inp("Depth", default=0.03, subtype="DISTANCE")
    top = g.inp("Top", "BOOL", default=True)
    bottom = g.inp("Bottom", "BOOL", default=True)
    sides = g.inp("Sides", "BOOL", default=True)
    m = g.inp("Material", "MATERIAL")
    t_ = g.box(0.0, d * -1.0, H - w, L, 0.0, H)
    b_ = g.box(0.0, d * -1.0, 0.0, L, 0.0, w)
    l_ = g.box(0.0, d * -1.0, 0.0, w, 0.0, H)
    r_ = g.box(L - w, d * -1.0, 0.0, L, 0.0, H)
    geo = g.join(g.switch(top, None, t_), g.switch(bottom, None, b_),
                 g.switch(sides, None, g.join(l_, r_)))
    g.result(g.mat(geo, m))
    return g


# ----------------------------------------------------------------- windows
@asset("SHJ.Arch.OctagonLattice", "Architecture")
def octagon_lattice():
    """八角景 lattice: truncated-square tiling (octagons + small squares) of
    square-section bars, clipped to a disc of Radius; an octagon sits on the
    centre.  Built without duplicated edges: every unit cell contributes the
    diamond between four octagons plus one horizontal and one vertical
    shared octagon edge.  XZ plane, centred, face towards -Y."""
    g = GN("SHJ.Arch.OctagonLattice", octagon_lattice.__doc__)
    R = g.inp("Radius", default=0.9, subtype="DISTANCE")
    a = g.inp("Edge", default=0.17, subtype="DISTANCE", desc="octagon edge length")
    bw = g.inp("Bar Width", default=0.028, subtype="DISTANCE")
    bd = g.inp("Bar Depth", default=0.035, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    p = a * (1.0 + SQ2)                  # octagon pitch (= width across flats)
    h = p * 0.5
    ha = a * 0.5
    diamond = g.polyline([g.vec(ha, h, 0.0), g.vec(h, ha, 0.0), g.vec(p - ha, h, 0.0),
                          g.vec(h, p - ha, 0.0)], cyclic=True)
    seg_h = g.curve_line(g.vec(ha * -1.0, h, 0.0), g.vec(ha, h, 0.0))
    seg_v = g.curve_line(g.vec(h, ha * -1.0, 0.0), g.vec(h, ha, 0.0))
    unit = g.join(diamond, seg_h, seg_v)
    n = 9
    pts = g.grid_points(n, n, p, p, g.vec(p * -(n // 2), p * -(n // 2), 0.0))
    tiles = g.realize(g.iop(pts, unit))
    tiles = g.resample(tiles, 24)
    bars = flat_sweep(g, tiles, bw, bd)
    # clip to the disc (face centres); the ring frame covers the cut ends
    far = g.compare(g.vmath("LENGTH", g.position()), R, "GREATER_THAN")
    bars = g.delete(bars, far, "FACE")
    bars = g.transform(bars, r=STAND)
    g.result(g.mat(bars, m))
    return g


def haitang_points(cx, cy, q, rc, n=5):
    """Square of half-size q with concave (inward) quarter-arc corners of
    radius rc -- the small 'begonia' flower of the lattice -- as a closed
    list of (x, y) points."""
    pts = []
    for kx, ky, a0 in ((1, 1, 270.0), (-1, 1, 0.0), (-1, -1, 90.0), (1, -1, 180.0)):
        ox, oy = cx + kx * q, cy + ky * q
        for i in range(n + 1):
            a = math.radians(a0 - 90.0 * i / n)
            pts.append((ox + rc * math.cos(a), oy + rc * math.sin(a)))
    pts.append(pts[0])
    return pts


def four_octagon_segments(c=0.46, a=0.29, e=0.04, q=0.1, rc=0.045, dia=0.18):
    """Line work of the tea house round windows on the unit circle: a
    doubled central cross, four upright octagons (flats on the axes) each with
    a cross running out to the central bars and to the rim and a lozenge at
    its centre, and splayed 'Y' arms where the cross meets the rim.
    Returns {group: [polyline, ...]}; the groups get slightly different bar
    depths so that crossing bars never share a face plane."""
    G = {"central_v": [], "central_h": [], "cross_v": [], "cross_h": [], "arms": [], "octagons": [],
         "flowers": []}
    for s in (-1.0, 1.0):
        G["central_v"].append([(s * e, -1.2), (s * e, 1.2)])
        G["central_h"].append([(-1.2, s * e), (1.2, s * e)])
    h = a * math.tan(math.pi / 8.0)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            cx, cy = sx * c, sy * c
            V = [(cx + a, cy - h), (cx + a, cy + h), (cx + h, cy + a), (cx - h, cy + a),
                 (cx - a, cy + h), (cx - a, cy - h), (cx - h, cy - a), (cx + h, cy - a)]
            G["octagons"].append(V + [V[0]])
            G["cross_h"].append([(sx * e, cy), (sx * 1.2, cy)])
            G["cross_v"].append([(cx, sy * e), (cx, sy * 1.2)])
            # the flower: a lozenge (square on its corner) centred on the octagon's cross
            G["flowers"].append([(cx + dia, cy), (cx, cy + dia), (cx - dia, cy), (cx, cy - dia), (cx + dia, cy)])
    for k in range(4):
        ca, sa = math.cos(k * math.pi / 2.0), math.sin(k * math.pi / 2.0)
        for s in (-1.0, 1.0):
            p0, p1 = (s * 0.28, 0.92), (s * e, 0.74)
            G["arms"].append([(p0[0] * ca - p0[1] * sa, p0[0] * sa + p0[1] * ca),
                              (p1[0] * ca - p1[1] * sa, p1[0] * sa + p1[1] * ca)])
    return G


@asset("SHJ.Arch.FourOctagonLattice", "Architecture")
def four_octagon_lattice():
    """Round-window lattice of the Shan tea house (八方锦): four upright
    octagons, each with a lozenge on a cross that runs out to the
    doubled central cross and to the rim, and splayed 'Y' arms at the four
    ends of the central cross.  Built on the unit circle and scaled to Radius
    (bar width is absolute).  XZ plane, centred, face towards -Y."""
    g = GN("SHJ.Arch.FourOctagonLattice", four_octagon_lattice.__doc__)
    R = g.inp("Radius", default=0.9, subtype="DISTANCE")
    bw = g.inp("Bar Width", default=0.045, subtype="DISTANCE")
    bd = g.inp("Bar Depth", default=0.04, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    depth = {"central_v": 1.1, "central_h": 1.06, "cross_v": 1.02, "cross_h": 1.0, "arms": 0.97,
             "octagons": 1.04, "flowers": 1.13}
    parts = []
    for name, lines in four_octagon_segments().items():
        cur = g.join(*[g.polyline([(x, y, 0.0) for x, y in p]) for p in lines])
        if name != "flowers":
            cur = g.resample(cur, 48)
        cur = g.transform(cur, s=g.vec(R, R, 1.0))
        parts.append(flat_sweep(g, cur, bw, bd * depth[name]))
    bars = g.join(*parts)
    far = g.compare(g.vmath("LENGTH", g.position()), R, "GREATER_THAN")
    bars = g.delete(bars, far, "FACE")
    bars = g.transform(bars, r=STAND)
    g.result(g.smooth_by_angle(g.mat(bars, m), 0.5))
    return g


@asset("SHJ.Arch.RoundWindow", "Architecture")
def round_window():
    """Round lattice window: moulded timber ring, lattice (Pattern 0 octagon
    tiling, 1 the tea house's four-octagon motif) and a glass pane, centred
    on the origin in the XZ plane (face towards -Y)."""
    g = GN("SHJ.Arch.RoundWindow", round_window.__doc__)
    R = g.inp("Radius", default=0.92, subtype="DISTANCE")
    rw = g.inp("Ring Width", default=0.07, subtype="DISTANCE")
    rd = g.inp("Ring Depth", default=0.12, subtype="DISTANCE")
    pat = g.inp("Pattern", "INT", default=1, min=0, max=1)
    a = g.inp("Lattice Edge", default=0.17, subtype="DISTANCE")
    bw = g.inp("Bar Width", default=0.045, subtype="DISTANCE")
    gy = g.inp("Glass Offset", default=0.05, subtype="DISTANCE")
    m_ring = g.inp("Ring Material", "MATERIAL", panel="Materials")
    m_lat = g.inp("Lattice Material", "MATERIAL", panel="Materials")
    m_glass = g.inp("Glass Material", "MATERIAL", panel="Materials")
    ring = flat_sweep(g, g.circle(R - rw * 0.5, 128), rw, rd)
    ring = g.transform(ring, r=STAND)
    lat0 = g.group(get_asset("SHJ.Arch.OctagonLattice"), Radius=R - rw * 0.6, Edge=a,
                   Bar_Width=bw, Material=m_lat).o
    lat1 = g.group(get_asset("SHJ.Arch.FourOctagonLattice"), Radius=R - rw * 0.6,
                   Bar_Width=bw, Material=m_lat).o
    lat = g.index_switch(pat, [lat0, lat1], "GEOMETRY")
    glass = g.fill(g.circle(R - rw * 0.5, 96))
    glass = g.transform(glass, t=g.vec(0.0, gy, 0.0), r=STAND)
    g.result(g.join(g.smooth_by_angle(g.mat(ring, m_ring), 0.6), lat, g.mat(glass, m_glass)))
    return g


@asset("SHJ.Arch.GridLattice", "Architecture")
def grid_lattice():
    """Rectangular window with a fine square grid lattice, frame and glass.
    Width along X, Height along Z from z = 0, face towards -Y."""
    g = GN("SHJ.Arch.GridLattice", grid_lattice.__doc__)
    W = g.inp("Width", default=2.0, subtype="DISTANCE")
    H = g.inp("Height", default=3.0, subtype="DISTANCE")
    p = g.inp("Pitch", default=0.1, subtype="DISTANCE")
    bw = g.inp("Bar Width", default=0.018, subtype="DISTANCE")
    bd = g.inp("Bar Depth", default=0.03, subtype="DISTANCE")
    fw = g.inp("Frame Width", default=0.08, subtype="DISTANCE")
    gy = g.inp("Glass Offset", default=0.05, subtype="DISTANCE")
    m_lat = g.inp("Lattice Material", "MATERIAL", panel="Materials")
    m_glass = g.inp("Glass Material", "MATERIAL", panel="Materials")
    nx = g.math("CEIL", W / p)
    nz = g.math("CEIL", H / p)
    vbar = g.box(bw * -0.5, bd * -0.5, 0.0, bw * 0.5, bd * 0.5, H)
    hbar = g.box(0.0, bd * -0.5, bw * -0.5, W, bd * 0.5, bw * 0.5)
    v = g.array(vbar, nx, g.vec(p, 0.0, 0.0), g.vec(0.0, 0.0, 0.0))
    h = g.array(hbar, nz, g.vec(0.0, 0.0, p), g.vec(0.0, 0.0, 0.0))
    frame = g.join(g.box(0.0, bd * -0.8, 0.0, W, bd * 0.8, fw),
                   g.box(0.0, bd * -0.8, H - fw, W, bd * 0.8, H),
                   g.box(0.0, bd * -0.8, 0.0, fw, bd * 0.8, H),
                   g.box(W - fw, bd * -0.8, 0.0, W, bd * 0.8, H))
    lat = g.mat(g.join(g.realize(v), g.realize(h), frame), m_lat)
    glass = g.mat(g.box(0.0, gy, 0.0, W, gy + 0.006, H), m_glass)
    g.result(g.join(lat, glass))
    return g


# ------------------------------------------------------------------ lights
@asset("SHJ.Arch.Downlight", "Fixtures")
def downlight():
    """Recessed round downlight: warm emitter disc inside a satin trim ring,
    face at z = 0 looking down."""
    g = GN("SHJ.Arch.Downlight", downlight.__doc__)
    r = g.inp("Radius", default=0.06, subtype="DISTANCE")
    m_e = g.inp("Emitter Material", "MATERIAL")
    m_t = g.inp("Trim Material", "MATERIAL")
    # satin trim ring (an annulus 12 mm deep) around a slightly recessed glowing disc
    ring = g.move(flat_sweep(g, g.circle(r + 0.009, 32), 0.018, 0.012), z=-0.006)
    em = g.move(g.fill(g.circle(r, 32)), z=-0.004)
    g.result(g.join(g.mat(ring, m_t), g.mat(em, m_e)))
    return g


# ------------------------------------------------------------- decoration
@asset("SHJ.Arch.WaveBand", "Decoration")
def wave_band():
    """Gold scalloped band (a row of semicircular waves) with a straight
    fillet above and a thin line below, laid along +X on the plane y = 0
    facing -Y; waves rise from z = 0."""
    g = GN("SHJ.Arch.WaveBand", wave_band.__doc__)
    L = g.inp("Length", default=5.0, subtype="DISTANCE")
    wl = g.inp("Wavelength", default=0.16, subtype="DISTANCE")
    amp = g.inp("Amplitude", default=0.045, subtype="DISTANCE")
    lw = g.inp("Line Width", default=0.012, subtype="DISTANCE")
    gap = g.inp("Fillet Gap", default=0.03, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    n = g.math("CEIL", L / wl * 12.0)
    line = g.mesh_line(n, (0, 0, 0), g.vec(L / n, 0.0, 0.0))
    px = g.sep(g.position())[0]
    yv = g.abs(g.sin(px / wl * math.pi)) * amp
    line = g.set_pos(line, offset=g.vec(0.0, yv, 0.0))
    crv = g.n("GeometryNodeMeshToCurve", line).o
    waves = flat_sweep(g, crv, lw, 0.008)
    fil = g.box(0.0, amp + gap, -0.004, L, amp + gap + lw, 0.004)
    base = g.box(0.0, lw * -1.6, -0.004, L, lw * -0.6, 0.004)
    band = g.join(waves, fil, base)
    band = g.transform(band, t=(0.0, -0.004, 0.0), r=STAND)
    g.result(g.mat(band, m))
    return g


@asset("SHJ.Arch.Medallions", "Decoration")
def medallions():
    """Row of carved gold medallion panels (square frame, inner lozenge and
    a small ring), XZ plane facing -Y, from the origin along +X."""
    g = GN("SHJ.Arch.Medallions", medallions.__doc__)
    cnt = g.inp("Count", "INT", default=3, min=1)
    s = g.inp("Size", default=0.2, subtype="DISTANCE")
    gap = g.inp("Gap", default=0.03, subtype="DISTANCE")
    lw = g.inp("Line Width", default=0.012, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    sq = flat_sweep(g, g.rect(s, s), lw, 0.01)
    dia = flat_sweep(g, g.transform(g.rect(s * 0.55, s * 0.55), r=(0.0, 0.0, math.pi / 4.0)),
                     lw, 0.01)
    ring = flat_sweep(g, g.circle(s * 0.16, 24), lw, 0.01)
    unit = g.join(sq, dia, ring)
    unit = g.move(unit, s * 0.5, s * 0.5, 0.0)
    row = g.array(unit, cnt, g.vec(s + gap, 0.0, 0.0), (0, 0, 0), realize=True)
    row = g.transform(row, t=(0.0, -0.005, 0.0), r=STAND)
    g.result(g.mat(row, m))
    return g


@asset("SHJ.Arch.Brace", "Decoration")
def brace():
    """Carved knee brace (雀替/斜撑) in the XZ plane: a board from the origin
    (on the column) rising to (Reach, Rise) (under the beam), with a gold
    carved zig-zag and border on both faces."""
    g = GN("SHJ.Arch.Brace", brace.__doc__)
    reach = g.inp("Reach", default=0.7, subtype="DISTANCE")
    rise = g.inp("Rise", default=0.8, subtype="DISTANCE")
    w = g.inp("Width", default=0.18, subtype="DISTANCE")
    t = g.inp("Thickness", default=0.08, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    m_gold = g.inp("Gold Material", "MATERIAL")
    Ln = g.math("SQRT", reach * reach + rise * rise)
    ang = g.math("ARCTAN2", rise, reach)
    board = g.box(0.0, w * -0.5, t * -0.5, Ln, w * 0.5, t * 0.5)
    zig = g.polyline([(0.06, -0.05, 0), (0.18, 0.05, 0), (0.3, -0.05, 0), (0.42, 0.05, 0),
                      (0.54, -0.05, 0), (0.66, 0.05, 0), (0.74, -0.05, 0)])
    zig = g.transform(zig, s=g.vec(Ln / 0.8, w / 0.14, 1.0))
    carving = flat_sweep(g, zig, 0.012, 0.01)
    border = flat_sweep(g, g.transform(g.rect(Ln - 0.05, w - 0.045), t=g.vec(Ln * 0.5, 0.0, 0.0)),
                        0.012, 0.01)
    face = g.join(carving, border)
    gold = g.join(g.move(face, z=t * 0.5), g.move(face, z=t * -0.5))    # carved on both faces
    geo = g.join(g.mat(board, m), g.mat(gold, m_gold))
    # board plane XY -> XZ with the carved face towards -Y, then tilt
    geo = g.transform(geo, r=(math.pi * -0.5, 0.0, 0.0))
    geo = g.transform(geo, r=g.vec(0.0, g.math("MULTIPLY", ang, -1.0), 0.0))
    g.result(geo)
    return g


@asset("SHJ.Arch.Plaque", "Decoration")
def plaque():
    """Long lacquered plaque board with a moulded gold frame, face at
    y = 0 (towards -Y), from the origin along +X, bottom on z = 0."""
    g = GN("SHJ.Arch.Plaque", plaque.__doc__)
    L = g.inp("Length", default=9.0, subtype="DISTANCE")
    H = g.inp("Height", default=0.53, subtype="DISTANCE")
    T = g.inp("Thickness", default=0.06, subtype="DISTANCE")
    fw = g.inp("Frame Width", default=0.035, subtype="DISTANCE")
    m = g.inp("Board Material", "MATERIAL")
    m_f = g.inp("Frame Material", "MATERIAL")
    board = g.mat(g.box(0.0, 0.0, 0.0, L, T, H), m)
    fr = g.group(get_asset("SHJ.Arch.PanelFrame"), Length=L, Height=H, Border=fw, Depth=0.015,
                 Material=m_f).o
    inner = g.group(get_asset("SHJ.Arch.PanelFrame"), Length=L - fw * 4.0, Height=H - fw * 4.0,
                    Border=fw * 0.35, Depth=0.01, Material=m_f).o
    inner = g.move(inner, fw * 2.0, 0.0, fw * 2.0)
    g.result(g.join(board, fr, inner))
    return g


# --------------------------------------------------------------- feature wall
@asset("SHJ.Arch.LogoWall", "Architecture")
def logo_wall():
    """Feature wall with the tea house emblem: a warm paper panel carrying the
    emblem between two lacquered cloud-pattern panels (each split by a slim
    divider), lacquered frame and plinth, and a deep lintel with inlaid gold
    lines; dark boarding above.  Runs along +X from the origin, face at
    y = 0 towards -Y, body towards +Y."""
    g = GN("SHJ.Arch.LogoWall", logo_wall.__doc__)
    L = g.inp("Length", default=4.39, subtype="DISTANCE")
    wl = g.inp("Left Panel", default=1.31, subtype="DISTANCE")
    wc = g.inp("Centre Panel", default=1.82, subtype="DISTANCE")
    lb = g.inp("Lintel Bottom", default=3.22, subtype="DISTANCE")
    lh = g.inp("Lintel Height", default=0.34, subtype="DISTANCE")
    top = g.inp("Top", default=4.3, subtype="DISTANCE")
    T = g.inp("Thickness", default=0.25, subtype="DISTANCE")
    pl = g.inp("Plinth", default=0.1, subtype="DISTANCE")
    fw = g.inp("Frame Width", default=0.045, subtype="DISTANCE")
    ex = g.inp("Emblem X", default=2.236, subtype="DISTANCE", panel="Emblem")
    ez = g.inp("Emblem Z", default=1.885, subtype="DISTANCE", panel="Emblem")
    ed = g.inp("Emblem Diameter", default=1.5616, subtype="DISTANCE", panel="Emblem")
    m_frame = g.inp("Frame Material", "MATERIAL", panel="Materials")
    m_cloud = g.inp("Cloud Material", "MATERIAL", panel="Materials")
    m_paper = g.inp("Paper Material", "MATERIAL", panel="Materials")
    m_ink = g.inp("Ink Material", "MATERIAL", panel="Materials")
    m_gold = g.inp("Gold Material", "MATERIAL", panel="Materials")
    m_board = g.inp("Boarding Material", "MATERIAL", panel="Materials")
    x1 = wl
    x2 = wl + wc
    core = g.box(0.0, 0.02, 0.0, L, T, top)                  # wall body (boarded)
    panels = g.join(g.mat(g.box(0.0, 0.0, pl, x1, 0.02, lb), m_cloud),
                    g.mat(g.box(x1, 0.0, pl, x2, 0.02, lb), m_paper),
                    g.mat(g.box(x2, 0.0, pl, L, 0.02, lb), m_cloud))
    # frame: plinth, outer stiles, stiles between panels, sub-panel dividers
    d = 0.018

    def stile(x, w):
        return g.box(x - w * 0.5, d * -1.0, pl, x + w * 0.5, 0.02, lb)

    frame = g.join(g.box(0.0, -0.03, 0.0, L, 0.02, pl),
                   stile(fw * 0.5, fw), stile(L - fw * 0.5, fw), stile(x1, fw), stile(x2, fw),
                   stile(x1 * 0.5, fw * 0.5), stile((x2 + L) * 0.5, fw * 0.5))
    lintel = g.box(-0.04, -0.06, lb, L + 0.04, T + 0.02, lb + lh)
    gold = g.join(g.box(0.0, -0.064, lb + 0.05, L, -0.058, lb + 0.062),
                  g.box(0.0, -0.064, lb + lh - 0.062, L, -0.058, lb + lh - 0.05))
    emb = g.group(get_asset("SHJ.Emblem"), Diameter=ed, Depth=0.003, Material=m_ink).o
    emb = g.move(emb, ex, -0.0005, ez)
    geo = g.join(g.mat(core, m_board), panels, g.mat(frame, m_frame), g.mat(lintel, m_frame),
                 g.mat(gold, m_gold), emb)
    g.result(geo)
    return g
