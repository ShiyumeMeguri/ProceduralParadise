"""
Millennium fixtures -- lighting and signage (``MIL.Fix.*``).
"""
from __future__ import annotations

from Core.gn import GN, asset, get_asset
from .emblem import EMBLEM_ASPECT, WORDMARK_WIDTH


@asset("MIL.Fix.LinearPendant", "Lighting")
def linear_pendant():
    """Suspended linear LED luminaire.  Centred on the origin along X; the
    diffuser (bottom face) sits at z = 0; two cables rise to ``Cable Length``
    above the housing top."""
    g = GN("MIL.Fix.LinearPendant", linear_pendant.__doc__)
    L = g.inp("Length", default=5.7, subtype="DISTANCE")
    W = g.inp("Width", default=0.25, subtype="DISTANCE")
    T = g.inp("Housing Height", default=0.1, subtype="DISTANCE")
    lip = g.inp("Diffuser Inset", default=0.018, subtype="DISTANCE")
    cl = g.inp("Cable Length", default=0.9, subtype="DISTANCE", panel="Suspension")
    ci = g.inp("Cable Inset", default=0.3, subtype="DISTANCE", panel="Suspension")
    cr = g.inp("Cable Radius", default=0.0025, subtype="DISTANCE", panel="Suspension")
    m_h = g.inp("Housing Material", "MATERIAL", panel="Materials")
    m_d = g.inp("Diffuser Material", "MATERIAL", panel="Materials")
    m_c = g.inp("Cable Material", "MATERIAL", panel="Materials")
    hl, hw = L * 0.5, W * 0.5
    housing = g.box(-hl, -hw, 0.004, hl, hw, T)
    diff = g.box(-hl + lip, -hw + lip, 0.0, hl - lip, hw - lip, 0.0045)
    c1 = g.cylinder(cr, cl, 6)
    pts = g.join(g.points(1, g.vec(-hl + ci, 0.0, T + cl * 0.5)),
                 g.points(1, g.vec(hl - ci, 0.0, T + cl * 0.5)))
    cables = g.realize(g.iop(pts, c1))
    canopy = g.cylinder(0.03, 0.02, 16)
    cpts = g.join(g.points(1, g.vec(-hl + ci, 0.0, T + cl - 0.01)),
                  g.points(1, g.vec(hl - ci, 0.0, T + cl - 0.01)))
    canopies = g.realize(g.iop(cpts, canopy))
    g.result(g.join(g.mat(housing, m_h), g.mat(diff, m_d),
                    g.mat(g.join(cables, canopies), m_c)))
    return g


@asset("MIL.Fix.HoloSign", "Signage")
def holo_sign():
    """Wall sign: frosted panel shaped as an inverted trapezoid with rounded
    corners and a glowing cyan rim, carrying the emblem and wordmark.

    Local frame: the sign lies in the XZ plane facing -Y (mount it on a wall
    whose face is y = 0); x is centred, z = 0 is the panel bottom.
    """
    g = GN("MIL.Fix.HoloSign", holo_sign.__doc__)
    Wt = g.inp("Top Width", default=7.6, subtype="DISTANCE")
    Wb = g.inp("Bottom Width", default=7.0, subtype="DISTANCE")
    H = g.inp("Height", default=2.95, subtype="DISTANCE")
    R = g.inp("Corner Radius", default=0.28, subtype="DISTANCE")
    rim = g.inp("Rim Width", default=0.07, subtype="DISTANCE")
    stand = g.inp("Standoff", default=0.06, subtype="DISTANCE")
    th = g.inp("Panel Thickness", default=0.03, subtype="DISTANCE")
    eh = g.inp("Emblem Height", default=1.2, subtype="DISTANCE", panel="Artwork")
    ex = g.inp("Emblem X", default=0.0, subtype="DISTANCE", panel="Artwork")
    ez = g.inp("Emblem Z", default=1.75, subtype="DISTANCE", panel="Artwork")
    th_ = g.inp("Text Height", default=0.22, subtype="DISTANCE", panel="Artwork")
    tz = g.inp("Text Z", default=0.78, subtype="DISTANCE", panel="Artwork")
    m_p = g.inp("Panel Material", "MATERIAL", panel="Materials")
    m_r = g.inp("Rim Material", "MATERIAL", panel="Materials")
    m_a = g.inp("Artwork Material", "MATERIAL", panel="Materials")

    ht, hb = Wt * 0.5, Wb * 0.5
    outline = g.polyline([(-hb, 0, 0), (hb, 0, 0), (ht, H, 0), (-ht, H, 0)], cyclic=True)
    outline = g.fillet(outline, R, 8)
    panel = g.fill(outline, mode="TRIANGLES")
    panel = g.extrude(panel, th, direction=(0, 0, 1))
    # rim: sweep a small rectangle along the outline
    rim_m = g.sweep(outline, g.rect(rim, th + 0.03), True)
    rim_m = g.move(rim_m, z=th * 0.5)
    # artwork (emblem + wordmark), slightly proud of the panel front
    emb = g.group(get_asset("MIL.Emblem"), Material=m_a).o
    emb = g.transform(emb, t=g.vec(ex, ez, th + 0.004), s=g.vec(eh, eh, 1.0))
    word = g.group(get_asset("MIL.Wordmark"), Material=m_a).o
    word = g.transform(word, t=g.vec(ex, tz, th + 0.004), s=g.vec(th_, th_, 1.0))  # shares Emblem X
    sign = g.join(g.mat(panel, m_p), g.mat(rim_m, m_r), emb, word)
    # XY (drawing) -> XZ wall plane facing -Y: rotate +90 deg about X maps
    # +Y -> +Z and +Z (front) -> -Y
    sign = g.transform(sign, r=(1.5707963, 0, 0))
    sign = g.move(sign, 0.0, g.math("MULTIPLY", stand, -1.0), 0.0)
    g.result(sign)
    return g
