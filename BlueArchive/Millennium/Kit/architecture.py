"""
Millennium architecture kit -- geometry-node groups (``MIL.Arch.*``).

Local-frame conventions (all assets):
    * metres, Z up, Z = 0 is finished floor level of the storey
    * linear elements run along +Y (curtain wall) or +X (wall panels)
    * rooms use a "room frame": origin at the inner glass line / front wall
      corner, +X into the room, +Y along the facade.
"""
from __future__ import annotations

from Core.gn import GN, asset
from .. import CW, LEVELS, MOD
from . import materials as M


# --------------------------------------------------------------- curtain wall
@asset("MIL.Arch.CurtainWall", "Architecture")
def curtain_wall():
    """Unitised curtain wall bay row as seen from the interior.

    Runs along +Y from 0 to Length.  The glass plane is x = 0, the interior is
    +x.  Mullions sit every ``Module`` metres starting at ``First Mullion``.
    Heights (sill, low rail, transom, head) default to the academy standard.
    """
    g = GN("MIL.Arch.CurtainWall", curtain_wall.__doc__)
    L = g.inp("Length", default=12.0, min=0.1, subtype="DISTANCE")
    H = g.inp("Head Height", default=CW["head_height"], subtype="DISTANCE")
    mod = g.inp("Module", default=CW["module"], min=0.3, subtype="DISTANCE", panel="Grid")
    first = g.inp("First Mullion", default=0.0, subtype="DISTANCE", panel="Grid")
    count = g.inp("Mullion Count", "INT", default=9, min=0, panel="Grid",
                  desc="Number of mullions (computed by the builder from Length/Module)")
    mw = g.inp("Mullion Width", default=CW["mullion_width"], subtype="DISTANCE", panel="Profile")
    md = g.inp("Mullion Depth", default=CW["mullion_depth"], subtype="DISTANCE", panel="Profile")
    ext = g.inp("Exterior Cap", default=CW.get("exterior_cap", 0.06), subtype="DISTANCE", panel="Profile")
    sill_h = g.inp("Sill Height", default=CW["sill_height"], subtype="DISTANCE", panel="Rails")
    sill_d = g.inp("Sill Depth", default=0.2, subtype="DISTANCE", panel="Rails")
    rail_z = g.inp("Rail Height", default=CW["rail_height"], subtype="DISTANCE", panel="Rails")
    rail_t = g.inp("Rail Thickness", default=CW["rail_thickness"], subtype="DISTANCE", panel="Rails")
    rail_d = g.inp("Rail Depth", default=0.07, subtype="DISTANCE", panel="Rails")
    tr_z = g.inp("Transom Height", default=CW["transom_height"], subtype="DISTANCE", panel="Rails")
    tr_t = g.inp("Transom Thickness", default=CW["transom_thickness"], subtype="DISTANCE", panel="Rails")
    tr_d = g.inp("Transom Depth", default=0.1, subtype="DISTANCE", panel="Rails")
    hd = g.inp("Head Frame Depth", default=CW["head_frame_depth"], subtype="DISTANCE", panel="Rails")
    hh = g.inp("Head Frame Height", default=0.06, subtype="DISTANCE", panel="Rails")
    gt = g.inp("Glass Thickness", default=CW["glass_thickness"], subtype="DISTANCE", panel="Profile")
    m_frame = g.inp("Frame Material", "MATERIAL", panel="Materials")
    m_glass = g.inp("Glass Material", "MATERIAL", panel="Materials")
    m_sill = g.inp("Sill Material", "MATERIAL", panel="Materials")

    # glass (one continuous pane per bay row; joints hidden by mullions)
    glass = g.box(-gt * 0.5, 0.0, sill_h, gt * 0.5, L, H)
    # mark the exterior face so the glass shader can give it a reflective coating
    nx = g.sep(g.normal())[0]
    glass = g.store(glass, "glass_out", g.compare(nx, -0.5, "LESS_THAN"), domain="FACE")
    glass = g.mat(glass, m_glass)

    # mullions: instanced boxes along +Y
    mull = g.box(-ext, -mw * 0.5, 0.0, md, mw * 0.5, H)
    pts = g.mesh_line(count, g.vec(0.0, first, 0.0), g.vec(0.0, mod, 0.0))
    mulls = g.iop(g.mesh_to_points(pts), mull)

    sill = g.box(-ext, 0.0, 0.0, sill_d, L, sill_h)
    rail = g.box(0.0, 0.0, rail_z - rail_t * 0.5, rail_d, L, rail_z + rail_t * 0.5)
    trans = g.box(-ext, 0.0, tr_z - tr_t * 0.5, tr_d, L, tr_z + tr_t * 0.5)
    head = g.box(-ext, 0.0, H - hh, hd, L, H + 0.02)
    frame = g.join(g.realize(mulls), rail, trans, head)
    frame = g.mat(frame, m_frame)
    sill = g.mat(sill, m_sill)
    g.result(g.join(glass, frame, sill))
    return g


# ------------------------------------------------------------------ wall
@asset("MIL.Arch.WallPanel", "Architecture")
def wall_panel():
    """Straight partition wall: runs along +X from 0 to Length; its finished
    face is y = 0 (thickness grows towards -Y, i.e. behind the face)."""
    g = GN("MIL.Arch.WallPanel", wall_panel.__doc__)
    L = g.inp("Length", default=4.0, subtype="DISTANCE")
    H = g.inp("Height", default=LEVELS["ceiling_datum"], subtype="DISTANCE")
    T = g.inp("Thickness", default=0.2, subtype="DISTANCE")
    z0 = g.inp("Base Z", default=0.0, subtype="DISTANCE")
    bb_h = g.inp("Baseboard Height", default=0.0, subtype="DISTANCE", panel="Trim")
    bb_d = g.inp("Baseboard Depth", default=0.012, subtype="DISTANCE", panel="Trim")
    m = g.inp("Material", "MATERIAL", panel="Materials")
    m_bb = g.inp("Baseboard Material", "MATERIAL", panel="Materials")
    wall = g.mat(g.box(0.0, -T, z0, L, 0.0, z0 + H), m)
    bb = g.box(0.0, -0.001, z0, L, bb_d, z0 + bb_h)
    bb = g.mat(bb, m_bb)
    has_bb = g.compare(bb_h, 0.001, "GREATER_THAN")
    g.result(g.join(wall, g.switch(has_bb, None, bb)))
    return g


@asset("MIL.Arch.Column", "Architecture")
def column():
    """Rectangular column / pilaster centred on the origin in XY."""
    g = GN("MIL.Arch.Column", column.__doc__)
    sx = g.inp("Width X", default=0.4, subtype="DISTANCE")
    sy = g.inp("Width Y", default=0.4, subtype="DISTANCE")
    H = g.inp("Height", default=LEVELS["ceiling_datum"], subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    g.result(g.mat(g.box(sx * -0.5, sy * -0.5, 0.0, sx * 0.5, sy * 0.5, H), m))
    return g


@asset("MIL.Arch.FloorSlab", "Architecture")
def floor_slab():
    """Finished floor slab over [0,SizeX]x[0,SizeY]; top face at z = 0."""
    g = GN("MIL.Arch.FloorSlab", floor_slab.__doc__)
    sx = g.inp("Size X", default=10.0, subtype="DISTANCE")
    sy = g.inp("Size Y", default=10.0, subtype="DISTANCE")
    t = g.inp("Thickness", default=LEVELS["slab_thickness"], subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    g.result(g.mat(g.box(0.0, 0.0, -t, sx, sy, 0.0), m))
    return g


# --------------------------------------------------------------- ceiling
@asset("MIL.Arch.CeilingSystem", "Architecture")
def ceiling_system():
    """Room ceiling: perimeter soffits at the datum, main ceiling plane, and a
    recessed central coffer with a light trim.  The window-side soffit (x = 0
    edge) carries an extra small step as in the Millennium standard section.

    Coordinates are in the room frame ([0,SizeX] x [0,SizeY]).
    """
    g = GN("MIL.Arch.CeilingSystem", ceiling_system.__doc__)
    SX = g.inp("Size X", default=10.5, subtype="DISTANCE")
    SY = g.inp("Size Y", default=24.0, subtype="DISTANCE")
    zd = g.inp("Datum Z", default=LEVELS["ceiling_datum"], subtype="DISTANCE", panel="Heights")
    zm = g.inp("Main Z", default=LEVELS["ceiling_coffer"], subtype="DISTANCE", panel="Heights")
    zc = g.inp("Coffer Z", default=4.4, subtype="DISTANCE", panel="Heights")
    zt = g.inp("Void Top Z", default=LEVELS["ceiling_void_top"], subtype="DISTANCE", panel="Heights")
    sw = g.inp("Soffit Window", default=1.11, subtype="DISTANCE", panel="Soffits")
    sr = g.inp("Soffit Right", default=1.2, subtype="DISTANCE", panel="Soffits")
    sf = g.inp("Soffit Front", default=1.2, subtype="DISTANCE", panel="Soffits")
    sb = g.inp("Soffit Back", default=1.5, subtype="DISTANCE", panel="Soffits")
    st_h = g.inp("Window Step Height", default=0.06, subtype="DISTANCE", panel="Soffits")
    st_d = g.inp("Window Step Depth", default=0.17, subtype="DISTANCE", panel="Soffits")
    cx0 = g.inp("Coffer X0", default=2.45, subtype="DISTANCE", panel="Coffer")
    cx1 = g.inp("Coffer X1", default=7.5, subtype="DISTANCE", panel="Coffer")
    cy0 = g.inp("Coffer Y0", default=6.0, subtype="DISTANCE", panel="Coffer")
    cy1 = g.inp("Coffer Y1", default=18.2, subtype="DISTANCE", panel="Coffer")
    tw = g.inp("Trim Width", default=0.06, subtype="DISTANCE", panel="Coffer")
    m_panel = g.inp("Panel Material", "MATERIAL", panel="Materials")
    m_soffit = g.inp("Soffit Material", "MATERIAL", panel="Materials")
    m_trim = g.inp("Trim Material", "MATERIAL", panel="Materials")

    th = 0.03  # skin thickness of plates
    # --- perimeter soffits (solid bulkheads from datum up to main ceiling)
    wx = sw - st_d
    s_win1 = g.box(0.0, 0.0, zd, wx, SY, zm)
    s_win2 = g.box(wx, 0.0, zd + st_h, sw, SY, zm)
    s_right = g.box(SX - sr, 0.0, zd, SX, SY, zm)
    s_front = g.box(sw, 0.0, zd, SX - sr, sf, zm)
    s_back = g.box(sw, SY - sb, zd, SX - sr, SY, zm)
    soffits = g.mat(g.join(s_win1, s_win2, s_right, s_front, s_back), m_soffit)

    # --- main ceiling plate with a hole for the coffer (4 plates)
    ix0, ix1, iy0, iy1 = sw, SX - sr, sf, SY - sb
    p1 = g.box(ix0, iy0, zm, cx0, iy1, zm + th)
    p2 = g.box(cx1, iy0, zm, ix1, iy1, zm + th)
    p3 = g.box(cx0, iy0, zm, cx1, cy0, zm + th)
    p4 = g.box(cx0, cy1, zm, cx1, iy1, zm + th)
    # coffer lid
    lid = g.box(cx0, cy0, zc, cx1, cy1, zc + th)
    panels = g.mat(g.join(p1, p2, p3, p4, lid), m_panel)

    # --- coffer trim: vertical faces + a flat reveal lip at the main ceiling
    t1 = g.box(cx0, cy0, zm, cx0 + tw, cy1, zc)
    t2 = g.box(cx1 - tw, cy0, zm, cx1, cy1, zc)
    t3 = g.box(cx0, cy0, zm, cx1, cy0 + tw, zc)
    t4 = g.box(cx0, cy1 - tw, zm, cx1, cy1, zc)
    trim = g.mat(g.join(t1, t2, t3, t4), m_trim)

    # --- plenum top (keeps light from leaking between storeys)
    top = g.box(0.0, 0.0, zt, SX, SY, zt + th)
    top = g.mat(top, m_soffit)
    g.result(g.join(soffits, panels, trim, top))
    return g


# ------------------------------------------------------------------- doors
@asset("MIL.Arch.GlassDoor", "Architecture")
def glass_door():
    """Double glass door in a portal frame with Millennium's chamfered top
    corner.  Runs along +X from 0 to Width in the wall plane y = 0."""
    g = GN("MIL.Arch.GlassDoor", glass_door.__doc__)
    W = g.inp("Width", default=1.8, subtype="DISTANCE")
    H = g.inp("Height", default=2.7, subtype="DISTANCE")
    fw = g.inp("Frame Width", default=0.08, subtype="DISTANCE")
    fd = g.inp("Frame Depth", default=0.24, subtype="DISTANCE")
    ch = g.inp("Chamfer", default=0.35, subtype="DISTANCE")
    m_f = g.inp("Frame Material", "MATERIAL", panel="Materials")
    m_g = g.inp("Glass Material", "MATERIAL", panel="Materials")
    # outer outline (chamfered top-right) and inner outline -> frame ring
    outer = g.polyline([(0, 0, 0), (W, 0, 0), (W, H - ch, 0), (W - ch, H, 0), (0, H, 0)], cyclic=True)
    inner = g.polyline([(fw, 0, 0), (W - fw, 0, 0), (W - fw, H - ch - fw * 0.4, 0),
                        (W - ch - fw * 0.4, H - fw, 0), (fw, H - fw, 0)], cyclic=True)
    ring = g.fill(g.join(outer, inner), mode="TRIANGLES")
    ring = g.extrude(ring, fd, direction=(0, 0, 1))
    # stand the XY outline up into the XZ wall plane (rotate +90 about X)
    ring = g.transform(ring, t=g.vec(0.0, fd * 0.5, 0.0), r=(1.5707963, 0, 0))
    glass = g.fill(inner)
    glass = g.extrude(glass, 0.02, direction=(0, 0, 1))
    glass = g.transform(glass, t=(0.0, 0.01, 0.0), r=(1.5707963, 0, 0))
    # centre stile between the two leaves
    stile = g.box(W * 0.5 - 0.025, -0.03, 0.0, W * 0.5 + 0.025, 0.03, H - fw)
    handle1 = g.box(W * 0.5 - 0.09, -0.07, 0.95, W * 0.5 - 0.07, 0.07, 1.25)
    handle2 = g.box(W * 0.5 + 0.07, -0.07, 0.95, W * 0.5 + 0.09, 0.07, 1.25)
    frame = g.mat(g.join(ring, stile, handle1, handle2), m_f)
    g.result(g.join(frame, g.mat(glass, m_g)))
    return g
