"""
Shanhaijing furniture kit -- geometry-node groups (``SHJ.Furn.*``).

Local frames: origin on the floor at the footprint centre.  A seat's user
faces -Y (its back is towards +Y); cabinets and shelves have their front
face on y = 0 and their body towards +Y, centred on X.

The hardwood pieces follow one family: square rosewood members with eased
edges, rows of copper studs on the outward faces of legs and posts, pale
inlay lines on tops and red silk cushions with a gold piping line.
"""
from __future__ import annotations

import math
import os

from Core import jsonio
from Core.gn import GN, asset, get_asset
from .architecture import flat_sweep, solid, STAND
from .. import FURN

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _studs(g, x, y, z0, z1, pitch, r, normal):
    """A vertical row of dome studs on a face at (x, y) from z0 to z1; the
    domes point along ``normal`` (unit tuple in XY)."""
    n = g.math("FLOOR", (z1 - z0) / pitch)
    n = g.max(n, 1.0)
    pts = g.mesh_line(n + 1.0, g.vec(x, y, z0), g.vec(0.0, 0.0, pitch))
    dome = g.n("GeometryNodeMeshUVSphere", Segments=10, Rings=6, Radius=r)["Mesh"]
    dome = g.transform(dome, s=(1.0, 1.0, 0.55))
    # sphere Z (flattened) -> the face normal
    nx, ny = normal
    rot = g.vec(0.0, math.pi * 0.5, math.atan2(ny, nx))
    dome = g.transform(dome, r=rot)
    return g.realize(g.iop(g.mesh_to_points(pts), dome))


# --------------------------------------------------------------- tea table
@asset("SHJ.Furn.TeaTable", "Furniture")
def tea_table():
    """Square hardwood tea table: pale lacquered top with a double inlay
    line, dark rim, slim apron, round stretchers just below the top and
    square legs with rows of copper studs."""
    g = GN("SHJ.Furn.TeaTable", tea_table.__doc__)
    W = g.inp("Width", default=FURN["table_size"], subtype="DISTANCE")
    D = g.inp("Depth", default=FURN["table_size"], subtype="DISTANCE")
    H = g.inp("Height", default=FURN["table_height"], subtype="DISTANCE")
    T = g.inp("Top Thickness", default=0.035, subtype="DISTANCE", panel="Details")
    s = g.inp("Leg Size", default=0.058, subtype="DISTANCE", panel="Details")
    li = g.inp("Leg Inset", default=0.012, subtype="DISTANCE", panel="Details")
    ah = g.inp("Apron Height", default=0.04, subtype="DISTANCE", panel="Details")
    sz = g.inp("Stretcher Drop", default=0.085, subtype="DISTANCE", panel="Details")
    sr = g.inp("Stretcher Radius", default=0.012, subtype="DISTANCE", panel="Details")
    i1 = g.inp("Inlay Inset", default=0.035, subtype="DISTANCE", panel="Details")
    i2 = g.inp("Inlay Gap", default=0.022, subtype="DISTANCE", panel="Details")
    iw = g.inp("Inlay Width", default=0.006, subtype="DISTANCE", panel="Details")
    pitch = g.inp("Stud Pitch", default=FURN["stud_pitch"], subtype="DISTANCE", panel="Details")
    m_top = g.inp("Top Material", "MATERIAL", panel="Materials")
    m_wood = g.inp("Frame Material", "MATERIAL", panel="Materials")
    m_inlay = g.inp("Inlay Material", "MATERIAL", panel="Materials")
    m_stud = g.inp("Stud Material", "MATERIAL", panel="Materials")
    m_rod = g.inp("Stretcher Material", "MATERIAL", panel="Materials")
    m_edge = g.inp("Edge Material", "MATERIAL", panel="Materials", desc="side faces of the top slab")
    hw, hd = W * 0.5, D * 0.5
    top = g.box(hw * -1.0, hd * -1.0, H - T, hw, hd, H)
    nz = g.sep(g.normal())[2]
    top = g.mat(top, m_wood)
    top = g.mat(top, m_edge, sel=g.compare(g.abs(nz), 0.5, "LESS_THAN"))
    top = g.mat(top, m_top, sel=g.compare(nz, 0.5, "GREATER_THAN"))
    # inlay: two concentric rectangular lines on the top surface
    r1 = g.rect(W - i1 * 2.0, D - i1 * 2.0)
    r2 = g.rect(W - (i1 + i2) * 2.0, D - (i1 + i2) * 2.0)
    inl = flat_sweep(g, g.join(r1, r2), iw, 0.001)
    inl = g.mat(g.move(inl, z=H + 0.0004), m_inlay)
    # legs
    lx, ly = hw - li - s * 0.5, hd - li - s * 0.5
    leg = g.box(s * -0.5, s * -0.5, 0.0, s * 0.5, s * 0.5, H - T)
    corners = g.join(g.points(1, g.vec(lx * -1.0, ly * -1.0, 0.0)), g.points(1, g.vec(lx, ly * -1.0, 0.0)),
                     g.points(1, g.vec(lx * -1.0, ly, 0.0)), g.points(1, g.vec(lx, ly, 0.0)))
    legs = g.realize(g.iop(corners, leg))
    # apron boards under the top, between the legs
    at = 0.02
    z0, z1 = H - T - ah, H - T
    ax, ay = lx, ly
    apron = g.join(g.box(ax * -1.0, ay * -1.0 - s * 0.5 + 0.004, z0, ax, ay * -1.0 - s * 0.5 + 0.004 + at, z1),
                   g.box(ax * -1.0, ay + s * 0.5 - 0.004 - at, z0, ax, ay + s * 0.5 - 0.004, z1),
                   g.box(ax * -1.0 - s * 0.5 + 0.004, ay * -1.0, z0, ax * -1.0 - s * 0.5 + 0.004 + at, ay, z1),
                   g.box(ax + s * 0.5 - 0.004 - at, ay * -1.0, z0, ax + s * 0.5 - 0.004, ay, z1))
    # round stretchers just below the apron on all four sides
    zs = H - T - sz
    st = g.join(g.rod(g.vec(lx * -1.0, ly * -1.0, zs), g.vec(lx, ly * -1.0, zs), sr, 10),
                g.rod(g.vec(lx * -1.0, ly, zs), g.vec(lx, ly, zs), sr, 10),
                g.rod(g.vec(lx * -1.0, ly * -1.0, zs), g.vec(lx * -1.0, ly, zs), sr, 10),
                g.rod(g.vec(lx, ly * -1.0, zs), g.vec(lx, ly, zs), sr, 10))
    frame = g.join(g.mat(g.join(legs, apron), m_wood), g.mat(st, m_rod))
    # studs on both outward faces of every leg
    rows = []
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        fx, fy = lx * sx, ly * sy
        rows.append(_studs(g, fx + s * 0.5 * sx, fy, 0.09, H - T - 0.1, pitch, 0.0065, (sx, 0.0)))
        rows.append(_studs(g, fx, fy + s * 0.5 * sy, 0.09, H - T - 0.1, pitch, 0.0065, (0.0, sy)))
    studs = g.mat(g.join(*rows), m_stud)
    g.result(g.join(g.smooth_by_angle(g.join(top, frame), 0.5), inl, g.smooth(studs, True)))
    return g


# -------------------------------------------------------------------- chair
@asset("SHJ.Furn.Chair", "Furniture")
def chair():
    """Tall-back hardwood side chair (灯挂椅): square legs, the rear legs
    rising as raked back posts, a wide central splat, crest rail, stepped
    stretchers (front lowest), copper studs on the front legs and back posts,
    and a red silk cushion with gold piping.  User faces -Y."""
    g = GN("SHJ.Furn.Chair", chair.__doc__)
    sw = g.inp("Seat Width", default=0.47, subtype="DISTANCE")
    sd = g.inp("Seat Depth", default=0.43, subtype="DISTANCE")
    sh = g.inp("Seat Height", default=0.46, subtype="DISTANCE")
    bh = g.inp("Back Height", default=FURN["chair_height"], subtype="DISTANCE")
    rake = g.inp("Back Rake", default=0.09, subtype="DISTANCE", desc="backward lean of the post tops")
    s = g.inp("Leg Size", default=0.046, subtype="DISTANCE", panel="Details")
    spw = g.inp("Splat Width", default=0.13, subtype="DISTANCE", panel="Details")
    ct = g.inp("Cushion Thickness", default=0.055, subtype="DISTANCE", panel="Details")
    pitch = g.inp("Stud Pitch", default=FURN["stud_pitch"], subtype="DISTANCE", panel="Details")
    m_wood = g.inp("Wood Material", "MATERIAL", panel="Materials")
    m_cush = g.inp("Cushion Material", "MATERIAL", panel="Materials")
    m_gold = g.inp("Piping Material", "MATERIAL", panel="Materials")
    m_stud = g.inp("Stud Material", "MATERIAL", panel="Materials")
    hw, hd = sw * 0.5, sd * 0.5
    fx, fy = hw - s * 0.5, hd - s * 0.5
    ft = 0.045                                     # seat frame height
    # front legs
    fl = g.box(s * -0.5, s * -0.5, 0.0, s * 0.5, s * 0.5, sh)
    legs = g.join(g.move(fl, fx * -1.0, fy * -1.0, 0.0), g.move(fl, fx, fy * -1.0, 0.0))
    # rear legs -> back posts: straight to the seat, then raked backwards
    def rake_shear(geo, x_in=0.0):
        """lean everything above the seat backwards (and slightly inwards)"""
        pz = g.sep(g.position())[2]
        k = g.max(pz - sh, 0.0) / (bh - sh)
        return g.set_pos(geo, offset=g.vec(x_in * k, rake * k, 0.0))

    posts = []
    for sx in (-1.0, 1.0):
        post = g.cube(g.vec(s, s * 0.92, bh), 2, 2, 8)
        post = g.move(post, fx * sx, fy, bh * 0.5)
        posts.append(rake_shear(post, fx * sx * -0.04))
    # seat frame
    frame = g.join(g.box(hw * -1.0, hd * -1.0, sh - ft, hw, hd * -1.0 + s * 0.6, sh),
                   g.box(hw * -1.0, hd - s * 0.6, sh - ft, hw, hd, sh),
                   g.box(hw * -1.0, hd * -1.0, sh - ft, hw * -1.0 + s * 0.6, hd, sh),
                   g.box(hw - s * 0.6, hd * -1.0, sh - ft, hw, hd, sh),
                   g.box(hw * -1.0 + 0.02, hd * -1.0 + 0.02, sh - 0.02, hw - 0.02, hd - 0.02, sh - 0.005))
    # crest rail and splat (follow the rake)
    crest = g.box(fx * -0.96 - s * 0.5, fy + rake - 0.02, bh - 0.05, fx * 0.96 + s * 0.5, fy + rake + 0.025, bh)
    splat = g.cube(g.vec(spw, 0.022, bh - 0.04 - sh - 0.02), 2, 2, 6)
    splat = rake_shear(g.move(splat, 0.0, fy, (bh - 0.04 + sh + 0.02) * 0.5))
    back_rail = g.box(fx * -1.0, fy - 0.012, sh + 0.02, fx, fy + 0.012, sh + 0.06)
    # stepped stretchers: front lowest, sides higher, back middle
    sr = 0.011
    stre = g.join(g.rod(g.vec(fx * -1.0, fy * -1.0, 0.09), g.vec(fx, fy * -1.0, 0.09), sr, 8),
                  g.rod(g.vec(fx * -1.0, fy * -1.0, 0.2), g.vec(fx * -1.0, fy, 0.2), sr, 8),
                  g.rod(g.vec(fx, fy * -1.0, 0.2), g.vec(fx, fy, 0.2), sr, 8),
                  g.rod(g.vec(fx * -1.0, fy, 0.15), g.vec(fx, fy, 0.15), sr, 8))
    wood = g.mat(g.join(legs, *posts, frame, crest, splat, back_rail, stre), m_wood)
    # cushion with gold piping
    cush = g.cube(g.vec(sw - 0.02, sd - 0.02, ct), 4, 4, 2)
    cush = g.subdiv(cush, 2)
    cush = g.transform(cush, t=g.vec(0.0, 0.0, sh + ct * 0.5))
    pipe = flat_sweep(g, g.fillet(g.rect(sw - 0.09, sd - 0.09), 0.02, 3), 0.005, 0.003)
    pipe = g.move(pipe, z=sh + ct + 0.0012)
    # studs: front faces of the front legs, front faces of the back posts
    rows = [_studs(g, fx * sx, fy * -1.0 - s * 0.5, 0.06, sh - 0.06, pitch, 0.006, (0.0, -1.0))
            for sx in (-1.0, 1.0)]
    stud_f = g.join(*rows)
    # back posts: studs follow the rake (sheared row)
    post_rows = []
    for sx in (-1.0, 1.0):
        r = _studs(g, fx * sx, fy - s * 0.5 - 0.001, sh + 0.08, bh - 0.08, pitch, 0.006, (0.0, -1.0))
        # shear: y offset proportional to height above the seat
        pz = g.sep(g.position())[2]
        r = g.set_pos(r, offset=g.vec(fx * sx * -0.04 * (pz - sh) / (bh - sh), rake * (pz - sh) / (bh - sh), 0.0))
        post_rows.append(r)
    studs = g.mat(g.join(stud_f, *post_rows), m_stud)
    g.result(g.join(g.smooth_by_angle(wood, 0.5), g.smooth(g.mat(cush, m_cush), True),
                    g.mat(pipe, m_gold), g.smooth(studs, True)))
    return g


# ------------------------------------------------------------ display shelf
def _load(name):
    return jsonio.load(os.path.join(DATA, name))


def keyhole_points(gx, gz, r, pw, base_z, n=64):
    """Outline of a keyhole gate (circle of radius r at (gx, gz) over a
    straight passage of width pw down to base_z), counter-clockwise, as
    (x, z) pairs."""
    h = pw * 0.5
    a0 = -math.pi * 0.5 + math.asin(min(h / r, 1.0))       # right junction
    a1 = 1.5 * math.pi - math.asin(min(h / r, 1.0))        # left junction
    pts = [(gx + h, base_z)]
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        pts.append((gx + r * math.cos(a), gz + r * math.sin(a)))
    pts.append((gx - h, base_z))
    return pts


def _board(g, x0, x1, z0, z1, y0, y1, per_m=40):
    """Box subdivided along X (so faces can be clipped finely)."""
    nx = max(2, int(abs(x1 - x0) * per_m) + 1)
    c = g.cube(g.vec(x1 - x0, y1 - y0, z1 - z0), nx, 2, 2)
    return g.move(c, (x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)


@asset("SHJ.Furn.BoguShelf", "Furniture")
def bogu_shelf():
    """Display wall (博古架) with a keyhole moon gate.

    The design (``Kit/data/bogu_shelf.json``, measured on the painting's
    shelf plane) is in metres on the shelf face (x across from the centre,
    z up); Width / Height / Depth scale it.  Black lacquered carcass and
    stepped cornice, olive-gold boards and dividers with little corner
    scrolls, a green lacquered plinth with gold fret, the keyhole gate with a
    moulded rim and a recessed plank door.  Boards that run into the gate
    are clipped by it."""
    D = _load("bogu_shelf.json")
    g = GN("SHJ.Furn.BoguShelf", bogu_shelf.__doc__)
    W = g.inp("Width", default=D["width"], subtype="DISTANCE")
    Hh = g.inp("Height", default=D["height"], subtype="DISTANCE")
    dep = g.inp("Depth", default=D["depth"], subtype="DISTANCE")
    m_frame = g.inp("Carcass Material", "MATERIAL", panel="Materials")
    m_board = g.inp("Board Material", "MATERIAL", panel="Materials")
    m_back = g.inp("Back Material", "MATERIAL", panel="Materials")
    m_base = g.inp("Plinth Material", "MATERIAL", panel="Materials")
    m_door = g.inp("Door Material", "MATERIAL", panel="Materials")
    m_rim = g.inp("Gate Rim Material", "MATERIAL", panel="Materials")
    w, H, d = D["width"], D["height"], D["depth"]
    hw = w * 0.5
    ph, ch, fw, bt = D["plinth"], D["cornice"], D["frame"], 0.035
    G = D["gate"]
    gx, gz, gr, rim, pw = G["x"], G["z"], G["radius"], G["rim"], G["passage_width"]
    top = H - ch
    # --- keyhole outline (opening) and the rim's centre line
    hole = keyhole_points(gx, gz, gr, pw, ph)
    rim_c = keyhole_points(gx, gz, gr + rim * 0.5, pw + rim, ph)

    def outline(pts, closed=True):
        return g.polyline([(x, z, 0.0) for x, z in pts], cyclic=closed)

    # --- back panel (dark planks) with the keyhole cut out
    frame_o = outline([(-hw, ph), (hw, ph), (hw, top), (-hw, top)])
    back = solid(g, g.fill(g.join(frame_o, outline(hole)), mode="NGONS"), 0.02)
    back = g.transform(back, t=(0.0, d, 0.0), r=STAND)
    # --- carcass: sides, top board, stepped cornice; plinth
    carcass = g.join(g.box(-hw, 0.0, ph, -hw + fw, d, top), g.box(hw - fw, 0.0, ph, hw, d, top),
                     g.box(-hw, 0.0, top - fw, hw, d, top),
                     g.box(-hw - 0.04, -0.04, top, hw + 0.04, d + 0.02, top + ch * 0.6),
                     g.box(-hw - 0.08, -0.08, top + ch * 0.6, hw + 0.08, d + 0.03, H))
    plinth = g.box(-hw, -0.02, 0.0, hw, d, ph)
    # --- boards, dividers and corner scrolls from the design
    parts = []
    for x0, x1, z in D["shelves"]:
        parts.append(_board(g, x0, x1, z - bt * 0.5, z + bt * 0.5, 0.0, d - 0.03))
    for x, z0, z1 in D["dividers"]:
        parts.append(_board(g, x - bt * 0.5, x + bt * 0.5, z0, z1, 0.0, d - 0.03, per_m=2))
    for x, z, sxn, szn in D.get("brackets", []):
        tri = outline([(0.0, 0.0), (0.11 * sxn, 0.0), (0.0, 0.11 * szn)])
        tri = solid(g, g.fill(tri), 0.012)
        tri = g.transform(tri, t=(x, -0.001, z), r=STAND)
        parts.append(tri)
    boards = g.join(*parts)
    # clip everything that runs into the gate (face centres inside the rim)
    px, py, pz = g.sep(g.position())
    dx, dz = px - gx, pz - gz
    inside = g.bool_or(
        g.compare(g.math("SQRT", dx * dx + dz * dz), gr + rim * 0.6, "LESS_THAN"),
        g.bool_and(g.compare(g.abs(dx), pw * 0.5 + rim * 0.6, "LESS_THAN"),
                   g.compare(pz, gz, "LESS_THAN")))
    boards = g.delete(boards, inside, "FACE")
    # --- gate rim (moulded band following the keyhole) and recessed door
    rim_g = flat_sweep(g, outline(rim_c, closed=False), rim, d - 0.03)
    rim_g = g.transform(rim_g, t=(0.0, (d - 0.03) * 0.5, 0.0), r=STAND)
    door = solid(g, g.fill(outline(hole)), 0.03)
    door = g.transform(door, t=(0.0, d - 0.005, 0.0), r=STAND)
    geo = g.join(g.mat(carcass, m_frame), g.mat(boards, m_board), g.mat(back, m_back),
                 g.mat(plinth, m_base), g.mat(rim_g, m_rim), g.mat(door, m_door))
    geo = g.smooth_by_angle(geo, 0.5)
    g.result(g.transform(geo, s=g.vec(W / w, dep / d, Hh / H)))
    return g


# ---------------------------------------------------------- display counter
@asset("SHJ.Furn.DisplayCounter", "Furniture")
def display_counter():
    """Glass display cabinet (tea shop counter): black lacquer frame whose
    plinth, shelf edge and top rail carry gold key-fret bands, clear glass
    front, ends and top, slim mullions, a low bottom shelf and a middle
    shelf.  Front on y = 0, runs along X centred."""
    g = GN("SHJ.Furn.DisplayCounter", display_counter.__doc__)
    L = g.inp("Length", default=3.0, subtype="DISTANCE")
    D = g.inp("Depth", default=0.55, subtype="DISTANCE")
    H = g.inp("Height", default=1.0, subtype="DISTANCE")
    f = g.inp("Frame Size", default=0.035, subtype="DISTANCE")
    ph = g.inp("Plinth Height", default=0.1, subtype="DISTANCE", panel="Details")
    sz = g.inp("Shelf Height", default=0.47, subtype="DISTANCE", panel="Details", desc="bottom of the middle band")
    bh = g.inp("Band Height", default=0.13, subtype="DISTANCE", panel="Details")
    th = g.inp("Top Rail", default=0.09, subtype="DISTANCE", panel="Details")
    pitch = g.inp("Mullion Pitch", default=1.2, subtype="DISTANCE", panel="Details")
    m_frame = g.inp("Frame Material", "MATERIAL", panel="Materials")
    m_glass = g.inp("Glass Material", "MATERIAL", panel="Materials")
    m_band = g.inp("Band Material", "MATERIAL", panel="Materials")
    m_shelf = g.inp("Shelf Material", "MATERIAL", panel="Materials")
    hl = L * 0.5
    # carcass: plinth block, middle shelf block, top rail, back board, end posts
    plinth = g.box(hl * -1.0, 0.0, 0.0, hl, D, ph)
    mid = g.box(hl * -1.0, 0.0, sz, hl, D, sz + bh)
    top = g.box(hl * -1.0, 0.0, H - th, hl, D, H - 0.012)
    back = g.box(hl * -1.0, D - 0.02, ph, hl, D, H - th)
    post = g.box(0.0, 0.0, 0.0, f, f, H - 0.012)
    posts = g.join(g.move(post, hl * -1.0, 0.0, 0.0), g.move(post, hl - f, 0.0, 0.0),
                   g.move(post, hl * -1.0, D - f, 0.0), g.move(post, hl - f, D - f, 0.0))
    # front mullions every ~pitch
    nm = g.max(g.math("FLOOR", L / pitch), 1.0)
    mpts = g.mesh_line(nm - 1.0, g.vec(hl * -1.0 + L / nm - f * 0.5, 0.0, 0.0), g.vec(L / nm, 0.0, 0.0))
    mull = g.realize(g.iop(g.mesh_to_points(mpts), g.box(0.0, 0.0, 0.0, f, f * 0.8, H - 0.012)))
    # key-fret bands: thin plates proud of the front and end faces
    def bands(z0, z1):
        return g.join(g.box(hl * -1.0, -0.004, z0, hl, 0.0, z1),
                      g.box(hl * -1.0 - 0.004, 0.0, z0, hl * -1.0, D, z1),
                      g.box(hl, 0.0, z0, hl + 0.004, D, z1))
    band = g.join(bands(0.012, ph - 0.012), bands(sz + 0.012, sz + bh - 0.012), bands(H - th + 0.012, H - 0.024))
    shelves = g.box(hl * -1.0 + f, f, ph, hl - f, D - 0.02, ph + 0.012)
    glass = g.join(g.box(hl * -1.0 + f, 0.006, ph, hl - f, 0.012, sz),
                   g.box(hl * -1.0 + f, 0.006, sz + bh, hl - f, 0.012, H - th),
                   g.box(hl * -1.0 + 0.006, f, ph, hl * -1.0 + 0.012, D - f, H - th),
                   g.box(hl - 0.012, f, ph, hl - 0.006, D - f, H - th),
                   g.box(hl * -1.0, 0.0, H - 0.012, hl, D, H))
    geo = g.join(g.mat(g.join(plinth, mid, top, back, posts, mull), m_frame), g.mat(band, m_band),
                 g.mat(shelves, m_shelf), g.mat(glass, m_glass))
    g.result(geo)
    return g


# ------------------------------------------------------------------ pedestal
@asset("SHJ.Furn.Pedestal", "Furniture")
def pedestal():
    """Stone pedestal for a guardian lion: plinth, recessed waist (束腰) and
    a cap slab, square in plan, centred."""
    g = GN("SHJ.Furn.Pedestal", pedestal.__doc__)
    s = g.inp("Size", default=0.55, subtype="DISTANCE")
    Hh = g.inp("Height", default=1.1, subtype="DISTANCE")
    m = g.inp("Material", "MATERIAL")
    m_cap = g.inp("Cap Material", "MATERIAL")
    hs = s * 0.5
    base = g.box(hs * -1.0, hs * -1.0, 0.0, hs, hs, 0.12)
    waist = g.box(hs * -0.86, hs * -0.86, 0.12, hs * 0.86, hs * 0.86, Hh - 0.1)
    cap = g.box(hs * -1.02, hs * -1.02, Hh - 0.1, hs * 1.02, hs * 1.02, Hh)
    g.result(g.join(g.mat(g.join(base, waist), m), g.mat(cap, m_cap)))
    return g
