"""
Millennium furniture kit -- geometry-node groups (``MIL.Furn.*``).

Local frames: origin on the floor at the footprint centre, the *user* of a
piece of furniture faces -Y (so its back is towards +Y).  Layout code rotates
pieces by 180 deg for seats on the far side of a desk.
"""
from __future__ import annotations

import math

from Core.gn import GN, asset, get_asset


# ------------------------------------------------------------------ desk
@asset("MIL.Furn.Desk", "Furniture")
def desk():
    """Lab/seminar desk unit: laminate top with dark edge band, slim apron and
    four round steel legs.  Units are designed to butt together side by side
    into clusters (see ``MIL.Furn.DeskCluster``)."""
    g = GN("MIL.Furn.Desk", desk.__doc__)
    W = g.inp("Width", default=0.72, subtype="DISTANCE")
    D = g.inp("Depth", default=1.2, subtype="DISTANCE")
    H = g.inp("Height", default=0.845, subtype="DISTANCE")
    T = g.inp("Top Thickness", default=0.025, subtype="DISTANCE", panel="Details")
    ah = g.inp("Apron Height", default=0.045, subtype="DISTANCE", panel="Details")
    ai = g.inp("Apron Inset", default=0.035, subtype="DISTANCE", panel="Details")
    lr = g.inp("Leg Radius", default=0.017, subtype="DISTANCE", panel="Details")
    lix = g.inp("Leg Inset X", default=0.05, subtype="DISTANCE", panel="Details")
    liy = g.inp("Leg Inset Y", default=0.05, subtype="DISTANCE", panel="Details")
    m_top = g.inp("Top Material", "MATERIAL", panel="Materials")
    m_edge = g.inp("Edge Material", "MATERIAL", panel="Materials")
    m_frame = g.inp("Frame Material", "MATERIAL", panel="Materials")

    hw, hd = W * 0.5, D * 0.5
    top = g.box(-hw, -hd, H - T, hw, hd, H)
    nz = g.sep(g.normal())[2]
    top = g.mat(top, m_edge)
    top = g.mat(top, m_top, sel=g.compare(g.abs(nz), 0.5, "GREATER_THAN"))

    # apron frame (4 bars) just below the top
    ax, ay = hw - ai, hd - ai
    z0, z1 = H - T - ah, H - T
    at = 0.018
    apron = g.join(
        g.box(-ax, -ay, z0, ax, -ay + at, z1),
        g.box(-ax, ay - at, z0, ax, ay, z1),
        g.box(-ax, -ay, z0, -ax + at, ay, z1),
        g.box(ax - at, -ay, z0, ax, ay, z1),
    )
    # legs at the four corners
    leg = g.cylinder(lr, H - T, 16)
    leg = g.move(leg, z=(H - T) * 0.5)
    lx, ly = hw - lix, hd - liy
    pts = g.join(g.points(1, g.vec(-lx, -ly, 0.0)), g.points(1, g.vec(lx, -ly, 0.0)),
                 g.points(1, g.vec(-lx, ly, 0.0)), g.points(1, g.vec(lx, ly, 0.0)))
    legs = g.realize(g.iop(pts, leg))
    frame = g.mat(g.smooth(g.join(apron, legs), False), m_frame)
    legs_s = g.smooth(frame, True)
    g.result(g.join(top, legs_s))
    return g


# ------------------------------------------------------------------ chair
@asset("MIL.Furn.ChairShell", "Furniture")
def chair_shell():
    """One-piece polypropylene shell: seat + hourglass back with the rounded
    triangular handle cut-out.  Built flat from curves, then bent and tilted."""
    g = GN("MIL.Furn.ChairShell", chair_shell.__doc__)
    sw = g.inp("Seat Width", default=0.44, subtype="DISTANCE")
    sd = g.inp("Seat Depth", default=0.42, subtype="DISTANCE")
    sh = g.inp("Seat Height", default=0.465, subtype="DISTANCE")
    bw = g.inp("Back Width", default=0.44, subtype="DISTANCE")
    bh = g.inp("Back Height", default=0.56, subtype="DISTANCE")
    tilt = g.inp("Back Tilt", default=0.2, subtype="ANGLE")
    th = g.inp("Shell Thickness", default=0.02, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")

    # seat: rounded rectangle slab (front edge at -Y)
    seat = g.fillet(g.rect(sw, sd), 0.035, 5)
    seat = g.slab(seat, th * 1.25)
    seat = g.move(seat, 0.0, 0.0, sh - th * 1.25)

    # back outline in its own plane (x = width, y = up along the back):
    # flared foot -> narrow spine -> trapezoid panel (wider at the top)
    s = bw / 0.44
    half = [(0.20, 0.0), (0.125, 0.03), (0.085, 0.08), (0.068, 0.15), (0.068, 0.345),
            (0.205, 0.365), (0.23, bh / s)]
    pts_r = [(x * s, y * s, 0.0) for x, y in half]
    pts_l = [(-x, y, 0.0) for x, y, _ in reversed(pts_r)]
    outline = g.polyline(pts_r + pts_l, cyclic=True)
    outline = g.fillet(outline, 0.012, 4)
    # rounded triangular handle, apex down
    ty = (bh - 0.075) * 1.0
    tri = g.polyline([(-0.085 * s, ty + 0.03, 0), (0.085 * s, ty + 0.03, 0),
                      (0.0, ty - 0.035, 0)], cyclic=True)
    tri = g.fillet(tri, 0.009, 4)
    back = g.fill(g.join(outline, tri), mode="TRIANGLES")
    back = g.extrude(back, th, direction=(0, 0, 1))
    # gentle curvature of the panel: push the sides forward with x^2
    P = g.position()
    px, py, pz = g.sep(P)
    bend = px * px * 0.3
    back = g.set_pos(back, offset=g.vec(0.0, 0.0, bend))
    # stand up: local +y -> world +Z, local +z (thickness) -> world -Y (front)
    back = g.transform(back, r=(1.5707963, 0, 0))
    back = g.transform(back, r=g.vec(g.math("MULTIPLY", tilt, -1.0), 0.0, 0.0))
    back = g.move(back, 0.0, sd * 0.5 - 0.01, sh - th * 0.6)
    shell = g.join(seat, back)
    g.result(g.smooth_by_angle(g.mat(shell, m), 0.5))
    return g


@asset("MIL.Furn.SledBase", "Furniture")
def sled_base():
    """Bent steel-tube sled base (two side loops + two cross bars)."""
    g = GN("MIL.Furn.SledBase", sled_base.__doc__)
    w = g.inp("Width", default=0.40, subtype="DISTANCE")
    d = g.inp("Seat Depth", default=0.42, subtype="DISTANCE")
    h = g.inp("Seat Height", default=0.445, subtype="DISTANCE")
    r = g.inp("Tube Radius", default=0.0095, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    hw = w * 0.5
    loops = []
    for sx in (-1.0, 1.0):
        x = hw * sx
        path = g.polyline([
            (x * 0.96, -d * 0.40, h),       # under seat, front
            (x, -d * 0.62, 0.012),          # floor, front (legs splay forward)
            (x, d * 0.48, 0.012),           # floor, rear
            (x * 0.96, d * 0.40, h),        # under seat, rear
        ])
        path = g.fillet(path, 0.05, 6)
        loops.append(g.tube(path, r, 10))
    cross1 = g.rod(g.vec(-hw * 0.96, -d * 0.40, h), g.vec(hw * 0.96, -d * 0.40, h), r, 10)
    cross2 = g.rod(g.vec(-hw * 0.96, d * 0.40, h), g.vec(hw * 0.96, d * 0.40, h), r, 10)
    base = g.join(*loops, cross1, cross2)
    g.result(g.smooth(g.mat(base, m), True))
    return g


@asset("MIL.Furn.Cushion", "Furniture")
def cushion():
    """Soft square seat cushion (rounded, slightly puffy)."""
    g = GN("MIL.Furn.Cushion", cushion.__doc__)
    s = g.inp("Size", default=0.37, subtype="DISTANCE")
    t = g.inp("Thickness", default=0.06, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    c = g.cube(g.vec(s, s, t), 6, 6, 3)
    c = g.subdiv(c, 2)
    # puff: bulge the top/bottom towards the centre
    P = g.position()
    px, py, pz = g.sep(P)
    k = 1.0 - (px * px + py * py) / (s * s * 0.25)
    c = g.set_pos(c, offset=g.vec(0.0, 0.0, pz * g.max(k, 0.0) * 0.6))
    c = g.move(c, z=t * 0.5)
    g.result(g.smooth(g.mat(c, m), True))
    return g


@asset("MIL.Furn.Chair", "Furniture")
def chair():
    """Stacking chair: shell + sled base, optional cushions on the seat."""
    g = GN("MIL.Furn.Chair", chair.__doc__)
    m_shell = g.inp("Shell Material", "MATERIAL", panel="Materials")
    m_base = g.inp("Base Material", "MATERIAL", panel="Materials")
    m_cush = g.inp("Cushion Material", "MATERIAL", panel="Materials")
    ncush = g.inp("Cushions", "INT", default=0, min=0, max=3)
    cush_rot = g.inp("Cushion Twist", default=0.12, subtype="ANGLE")
    sh = g.inp("Seat Height", default=0.465, subtype="DISTANCE")
    shell = g.group(get_asset("MIL.Furn.ChairShell"), Material=m_shell, Seat_Height=sh)
    base = g.group(get_asset("MIL.Furn.SledBase"), Material=m_base,
                   Seat_Height=sh - 0.02)
    c = g.group(get_asset("MIL.Furn.Cushion"), Material=m_cush).o
    pts = g.mesh_line(ncush, g.vec(0.0, -0.035, sh), (0.0, 0.0, 0.06))
    rot = g.vec(0.0, 0.0, g.index() * cush_rot + g.math("MULTIPLY", cush_rot, -0.5))
    cushions = g.realize(g.iop(g.mesh_to_points(pts), c, rot=rot))
    g.result(g.join(shell.o, base.o, cushions))
    return g


# ------------------------------------------------------------------ props
@asset("MIL.Furn.Laptop", "Props")
def laptop():
    """Thin laptop, user at -Y, lid hinged on the +Y edge.  The lid back
    carries the Millennium emblem."""
    g = GN("MIL.Furn.Laptop", laptop.__doc__)
    W = g.inp("Width", default=0.31, subtype="DISTANCE")
    D = g.inp("Depth", default=0.215, subtype="DISTANCE")
    ang = g.inp("Lid Angle", default=1.85, subtype="ANGLE")
    m_body = g.inp("Body Material", "MATERIAL", panel="Materials")
    m_scr = g.inp("Screen Material", "MATERIAL", panel="Materials")
    m_logo = g.inp("Logo Material", "MATERIAL", panel="Materials")
    emblem = g.group(get_asset("MIL.Emblem"), Material=m_logo).o
    hw, hd = W * 0.5, D * 0.5
    base = g.fillet(g.rect(W, D), 0.012, 3)
    base = g.slab(base, 0.014)
    lid = g.fillet(g.rect(W, D * 0.97), 0.012, 3)
    lid = g.slab(lid, 0.006)
    # lid local: hinge edge at y = -D/2 (move so hinge is at origin), then rotate
    lid = g.move(lid, 0.0, D * 0.485, 0.0)
    screen = g.box(-hw + 0.012, 0.012, 0.0061, hw - 0.012, D * 0.97 - 0.012, 0.0065)
    # emblem on the lid back (-z face before opening), mirrored in x so it
    # reads correctly from behind
    logo = g.transform(emblem, t=g.vec(0.0, D * 0.485, -0.0004), s=(-0.055, 0.055, 1.0))
    lidg = g.join(g.mat(lid, m_body), g.mat(screen, m_scr), g.mat(logo, m_logo))
    # hinge at y = 0: rotate about X by (pi - angle); the lid leans back to +Y
    # and the screen (+z face) turns to face the user at -Y
    rx = g.math("SUBTRACT", 3.14159265, ang)
    lidg = g.transform(lidg, r=g.vec(rx, 0.0, 0.0))
    lidg = g.move(lidg, 0.0, hd, 0.014)
    g.result(g.join(g.mat(base, m_body), lidg))
    return g


@asset("MIL.Furn.PenCup", "Props")
def pen_cup():
    """Desk pen cup with a few pens and scissors handles."""
    g = GN("MIL.Furn.PenCup", pen_cup.__doc__)
    m_cup = g.inp("Cup Material", "MATERIAL")
    m_pen = g.inp("Pen Material", "MATERIAL")
    cup = g.move(g.cylinder(0.035, 0.1, 24), z=0.05)
    pens = []
    for i, (dx, dy, tx, ty) in enumerate([(0.01, 0.0, 0.2, 0.05), (-0.012, 0.008, -0.15, 0.12),
                                          (0.0, -0.012, 0.05, -0.2), (-0.006, -0.004, -0.25, -0.1)]):
        p = g.cylinder(0.0045, 0.15, 8)
        p = g.transform(p, t=g.vec(dx, dy, 0.1), r=(tx, ty, 0.0))
        pens.append(p)
    g.result(g.join(g.mat(g.smooth(cup), m_cup), g.mat(g.join(*pens), m_pen)))
    return g


@asset("MIL.Furn.BookRow", "Props")
def book_row():
    """Row of standing books with randomised heights/thickness/colours
    (colour picked per book from three materials)."""
    g = GN("MIL.Furn.BookRow", book_row.__doc__)
    n = g.inp("Count", "INT", default=6, min=0)
    seed = g.inp("Seed", "INT", default=0)
    lean = g.inp("Lean", default=0.0, subtype="ANGLE")
    m0 = g.inp("Material A", "MATERIAL")
    m1 = g.inp("Material B", "MATERIAL")
    m2 = g.inp("Material C", "MATERIAL")
    pts = g.mesh_to_points(g.mesh_line(n, (0, 0, 0), (0.03, 0, 0)))
    idx = g.index()
    pts = g.store(pts, "book_id", idx, dtype="INT", domain="POINT")
    book = g.box(-0.012, -0.08, 0.0, 0.012, 0.08, 1.0)
    hgt = g.random(0.17, 0.25, seed, idx)
    thick = g.random(0.8, 1.2, g.math("ADD", seed, 7), idx)
    inst = g.iop(pts, book, scale=g.vec(thick, 1.0, hgt), rot=g.vec(0.0, lean, 0.0))
    books = g.realize(inst)
    bid = g.n("GeometryNodeInputNamedAttribute", Name="book_id", props={"data_type": "INT"}).o
    r = g.random(0.0, 1.0, g.math("ADD", seed, 3), bid)
    books = g.mat(books, m0)
    books = g.mat(books, m1, sel=g.compare(r, 0.45, "LESS_THAN"))
    books = g.mat(books, m2, sel=g.compare(r, 0.15, "LESS_THAN"))
    g.result(books)
    return g


# ---------------------------------------------------------------- shelving
@asset("MIL.Furn.WingShelf", "Furniture")
def wing_shelf():
    """Display shelf: a narrow bookcase 'tower' with cantilevered trapezoid
    display trays ('wings') on both sides at two levels, optional top rail.

    Faces -Y; centred on x = 0; floor at z = 0.  Wing trays tilt towards the
    viewer and carry a raised rim, as on the Millennium club-room shelves.
    """
    g = GN("MIL.Furn.WingShelf", wing_shelf.__doc__)
    tw = g.inp("Tower Width", default=0.62, subtype="DISTANCE", panel="Tower")
    th = g.inp("Tower Height", default=2.36, subtype="DISTANCE", panel="Tower")
    td = g.inp("Tower Depth", default=0.36, subtype="DISTANCE", panel="Tower")
    bt = g.inp("Board Thickness", default=0.045, subtype="DISTANCE", panel="Tower")
    z1 = g.inp("Wing 1 Z", default=1.32, subtype="DISTANCE", panel="Wings")
    l1 = g.inp("Wing 1 Length", default=0.95, subtype="DISTANCE", panel="Wings")
    z2 = g.inp("Wing 2 Z", default=1.78, subtype="DISTANCE", panel="Wings")
    l2 = g.inp("Wing 2 Length", default=0.7, subtype="DISTANCE", panel="Wings")
    wd = g.inp("Wing Depth", default=0.34, subtype="DISTANCE", panel="Wings")
    wt = g.inp("Wing Tilt", default=0.35, subtype="ANGLE", panel="Wings")
    tt = g.inp("Tray Thickness", default=0.03, subtype="DISTANCE", panel="Wings")
    nbooks = g.inp("Books per Shelf", "INT", default=8, min=0, panel="Tower")
    rail = g.inp("Top Rail", "BOOL", default=False, panel="Tower")
    rail_len = g.inp("Top Rail Length", default=2.2, subtype="DISTANCE", panel="Tower")
    m_b = g.inp("Board Material", "MATERIAL", panel="Materials")
    m_t = g.inp("Tray Material", "MATERIAL", panel="Materials")
    m_k = g.inp("Book Material A", "MATERIAL", panel="Materials")
    m_k2 = g.inp("Book Material B", "MATERIAL", panel="Materials")
    m_k3 = g.inp("Book Material C", "MATERIAL", panel="Materials")

    hw = tw * 0.5
    hd = td * 0.5
    # tower: side boards, back rails, internal shelves, cap
    left = g.box(g.math("MULTIPLY", hw, -1.0), -hd, 0.0, bt - hw, hd, th)
    right = g.box(hw - bt, -hd, 0.0, hw, hd, th)
    shelves = []
    for f in (0.02, 0.3, 0.56, 0.78):
        z = th * f
        shelves.append(g.box(bt - hw, -hd, z, hw - bt, hd, z + 0.025))
    back_rail = g.box(bt - hw, hd - 0.03, th * 0.4, hw - bt, hd, th * 0.4 + 0.05)
    tower = g.mat(g.join(left, right, back_rail, *shelves), m_b)

    # books inside the tower (two rows)
    books = []
    for i, (f, seed) in enumerate(((0.3, 3), (0.56, 9), (0.02, 4))):
        br = g.group(get_asset("MIL.Furn.BookRow"), Count=nbooks, Seed=seed,
                     Material_A=m_k, Material_B=m_k2, Material_C=m_k3).o
        br = g.move(br, g.math("ADD", g.math("MULTIPLY", hw, -1.0), bt + 0.03), 0.0, th * f + 0.025)
        books.append(br)
    books = g.join(*books)

    def tray(length, z, side):
        # trapezoid in XY: inner edge at x = 0, outer end slanted
        L = length
        d = wd
        outline = g.polyline([(0.0, -d * 0.5, 0), (L, -d * 0.5, 0), (L - d * 0.55, d * 0.5, 0),
                              (0.0, d * 0.5, 0)], cyclic=True)
        outline = g.fillet(outline, 0.02, 3)
        slab = g.slab(outline, tt)
        rim = g.sweep(outline, g.rect(0.025, 0.05), True)
        rim = g.move(rim, z=g.math("ADD", tt, 0.005))
        tr = g.join(slab, rim)
        # tilt towards the viewer (-Y): rotate about X so the back edge rises
        tr = g.transform(tr, r=g.vec(wt, 0.0, 0.0))
        if side < 0:
            tr = g.transform(tr, s=(-1.0, 1.0, 1.0))
            tr = g.n("GeometryNodeFlipFaces", tr).o
            tr = g.move(tr, g.math("MULTIPLY", hw, -1.0), 0.0, z)
        else:
            tr = g.move(tr, hw, 0.0, z)
        return tr

    trays = g.join(tray(l1, z1, 1), tray(l1, z1, -1), tray(l2, z2, 1), tray(l2, z2, -1))
    # slim support posts under the outer ends of the lower wings
    post = g.cylinder(0.018, z1, 12)
    post = g.move(post, z=z1 * 0.5)
    px = hw + l1 - wd * 0.3
    pts = g.join(g.points(1, g.vec(px, 0.0, 0.0)),
                 g.points(1, g.vec(g.math("MULTIPLY", px, -1.0), 0.0, 0.0)))
    posts = g.realize(g.iop(pts, post))
    trays = g.mat(g.join(trays, posts), m_t)

    # optional top rail (two round bars spanning over the wings)
    rl = rail_len * 0.5
    bars = g.join(g.rod(g.vec(g.math("MULTIPLY", rl, -1.0), -hd * 0.6, th + 0.04), g.vec(rl, -hd * 0.6, th + 0.04), 0.016, 10),
                  g.rod(g.vec(g.math("MULTIPLY", rl, -1.0), hd * 0.6, th + 0.04), g.vec(rl, hd * 0.6, th + 0.04), 0.016, 10))
    bars = g.mat(bars, m_b)
    g.result(g.join(tower, books, trays, g.switch(rail, None, bars)))
    return g
