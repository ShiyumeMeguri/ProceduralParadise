"""
Millennium room builder.

``build_room(room_dir, parent_matrix)`` reads ``room.json`` from a room folder
and assembles the room from the Millennium kit.  Every object is parented to a
room root empty whose transform places the room inside its tower (see
:mod:`Millennium.Campus.campus`), so the same room definition drops into the
full-academy scene unchanged.
"""
from __future__ import annotations

import json
import math
import os

import bpy
from mathutils import Matrix, Vector

from Core import scene as SC
from Core.gn import get_asset
from . import CW, LEVELS, MOD
from .Kit import materials as M


def load_room(room_dir):
    with open(os.path.join(room_dir, "room.json"), encoding="utf-8") as f:
        return json.load(f)


class RoomBuilder:
    def __init__(self, room_dir, parent_matrix=None, collection=None, in_tower=False):
        self.dir = room_dir
        self.in_tower = in_tower
        self.R = load_room(room_dir)
        self.id = self.R["id"]
        self.col = collection or SC.collection(f"ROOM_{self.id}")
        self.root = SC.empty(f"ROOM_{self.id}", collection=self.col, display="ARROWS", size=1.0)
        self.root.matrix_world = parent_matrix or Matrix.Identity(4)
        self.sub = {}

    # ------------------------------------------------------------ helpers
    def c(self, name):
        if name not in self.sub:
            self.sub[name] = SC.collection(f"{self.id}.{name}", parent=self.col)
        return self.sub[name]

    def obj(self, name, asset, inputs, loc=(0, 0, 0), rot_z=0.0, col="Architecture", rot=None):
        ob = SC.gn_object(f"{self.id}.{name}", get_asset(asset), inputs,
                          location=loc, rotation=rot or (0.0, 0.0, math.radians(rot_z)),
                          collection=self.c(col), parent=self.root)
        return ob

    # ------------------------------------------------------------ parts
    def build(self):
        self.floor()
        if not self.in_tower:          # inside a tower the facade is the tower's
            self.curtain_wall()
        self.ceiling()
        self.walls()
        self.closures()
        self.columns()
        self.lights()
        self.sign()
        self.shelves()
        self.desks()
        return self

    def floor(self):
        sx, sy = self.R["size"]
        self.obj("Floor", "MIL.Arch.FloorSlab",
                 {"Size X": sx, "Size Y": sy, "Material": M.get("MIL.Marble")})

    def curtain_wall(self):
        sx, sy = self.R["size"]
        cw = self.R.get("curtain_wall", {})
        mod = cw.get("module", CW["module"])
        first = cw.get("first_mullion", 0.0)
        count = int(math.floor((sy - first) / mod + 1e-6)) + 1
        self.obj("CurtainWall", "MIL.Arch.CurtainWall",
                 {"Length": sy, "Module": mod, "First Mullion": first, "Mullion Count": count,
                  "Frame Material": M.get("MIL.Mullion"), "Glass Material": M.get("MIL.Glass"),
                  "Sill Material": M.get("MIL.Mullion")})

    def ceiling(self):
        sx, sy = self.R["size"]
        C = self.R["ceiling"]
        so = C["soffit"]
        x0, y0, x1, y1 = C["coffer_rect"]
        self.obj("Ceiling", "MIL.Arch.CeilingSystem", {
            "Size X": sx, "Size Y": sy, "Datum Z": C["datum"], "Main Z": C["main"],
            "Coffer Z": C["coffer"], "Void Top Z": C["void_top"],
            "Soffit Window": so["window"], "Soffit Right": so["right"],
            "Soffit Front": so["front"], "Soffit Back": so["back"],
            "Window Step Height": C["window_step"]["height"],
            "Window Step Depth": C["window_step"]["depth"],
            "Coffer X0": x0, "Coffer Y0": y0, "Coffer X1": x1, "Coffer Y1": y1,
            "Trim Width": C["trim_width"],
            "Panel Material": M.get("MIL.CeilingPanel"), "Soffit Material": M.get("MIL.Soffit"),
            "Trim Material": M.get("MIL.TrimWhite")})

    def walls(self):
        H = self.R["ceiling"]["datum"]
        T = self.R.get("wall_thickness", 0.2)
        for w in self.R["walls"]:
            a, b = Vector((*w["from"], 0)), Vector((*w["to"], 0))
            d = b - a
            L = d.length
            ang = math.atan2(d.y, d.x)
            # wall panel local: runs +X, face at y=0, body towards -Y.
            # choose the rotation so the finished face points into the room.
            face = w["face"]
            want = {"+Y": Vector((0, 1, 0)), "-Y": Vector((0, -1, 0)),
                    "+X": Vector((1, 0, 0)), "-X": Vector((-1, 0, 0))}[face]
            # local +Y normal after rotation
            n = Vector((-math.sin(ang), math.cos(ang), 0))
            flip = n.dot(want) < 0
            if flip:
                a, b = b, a
                ang = ang + math.pi
            # segments between openings
            ops = sorted(w.get("openings", []), key=lambda o: o["x0"])
            # openings are specified from the wall's 'from' point in json order
            cuts = []
            for o in ops:
                s0 = o["x0"]
                s1 = o["x0"] + o["width"]
                if flip:
                    s0, s1 = L - s1, L - s0
                cuts.append((s0, s1, o))
            cuts.sort(key=lambda c: c[0])
            pos = 0.0
            dirv = Vector((math.cos(ang), math.sin(ang), 0))
            k = 0
            for s0, s1, o in cuts + [(L, L, None)]:
                if s0 - pos > 1e-4:
                    p = a + dirv * pos
                    self.obj(f"Wall_{w['id']}_{k}", "MIL.Arch.WallPanel",
                             {"Length": s0 - pos, "Height": H, "Thickness": T,
                              "Material": M.get("MIL.WallPaint")},
                             loc=p, rot_z=math.degrees(ang))
                    k += 1
                if o is not None:
                    oh = o["height"]
                    p = a + dirv * s0
                    self.obj(f"Wall_{w['id']}_{k}_lintel", "MIL.Arch.WallPanel",
                             {"Length": s1 - s0, "Height": H - oh, "Base Z": oh, "Thickness": T,
                              "Material": M.get("MIL.WallPaint")},
                             loc=p, rot_z=math.degrees(ang))
                    k += 1
                    # door sits in the wall; its local -Y face must face the room
                    door_ang = ang
                    dp = p - Vector((-math.sin(ang), math.cos(ang), 0)) * (T * 0.5)
                    self.obj(f"Door_{w['id']}_{k}", "MIL.Arch.GlassDoor",
                             {"Width": s1 - s0, "Height": oh, "Frame Depth": T + 0.04,
                              "Frame Material": M.get("MIL.TrimWhite"),
                              "Glass Material": M.get("MIL.DoorGlass")},
                             loc=dp, rot_z=math.degrees(door_ang))
                pos = s1

    def closures(self):
        """Partition closures: where a wall meets the glass line between two
        facade mullions, a closure profile (wall thickness + one mullion)
        seals the joint -- the standard curtain-wall detail that lets a room
        sit at any 0.3 m offset along the facade.  Skipped where a column
        already covers the junction."""
        T = self.R.get("wall_thickness", 0.2)
        md, mw = CW["mullion_depth"], CW["mullion_width"]
        ext = CW.get("exterior_cap", 0.06)
        cols = self.R.get("columns", [])
        for w in self.R["walls"]:
            side = {"+Y": 1.0, "-Y": -1.0}.get(w["face"])
            if side is None:
                continue
            for px, py in (w["from"], w["to"]):
                if abs(px) > 1e-3:
                    continue
                yc = py - side * T * 0.5          # centre of the wall body
                if any(c["center"][0] - c["size"][0] * 0.5 <= 0.01
                       and abs(c["center"][1] - yc) <= (c["size"][1] + T) * 0.5 + 1e-3
                       for c in cols):
                    continue
                self.obj(f"Closure_{w['id']}", "MIL.Arch.Column",
                         {"Width X": md + ext, "Width Y": T + mw, "Height": CW["head_height"],
                          "Material": M.get("MIL.Mullion")},
                         loc=((md - ext) * 0.5, yc, 0.0))

    def columns(self):
        H = self.R["ceiling"]["datum"]
        for cdef in self.R.get("columns", []):
            self.obj(f"Column_{cdef['id']}", "MIL.Arch.Column",
                     {"Width X": cdef["size"][0], "Width Y": cdef["size"][1], "Height": H,
                      "Material": M.get("MIL.TrimWhite")},
                     loc=(cdef["center"][0], cdef["center"][1], 0.0))

    def lights(self):
        Ld = self.R["lights"]
        z = Ld["z"]
        cof = self.R["ceiling"]["coffer"]
        for i, y in enumerate(Ld["rows_y"]):
            self.obj(f"Pendant_{i}", "MIL.Fix.LinearPendant",
                     {"Length": Ld["length"], "Width": Ld["width"], "Housing Height": Ld["housing"],
                      "Cable Length": cof - z - Ld["housing"],
                      "Housing Material": M.get("MIL.Mullion"), "Diffuser Material": M.get("MIL.LED"),
                      "Cable Material": M.get("MIL.MetalFrame")},
                     loc=(Ld["center_x"], y + Ld["width"] * 0.5, z), col="Lighting")
            # area light doing the actual illumination (clean sampling)
            ld = bpy.data.lights.new(f"{self.id}.PendantLight_{i}", "AREA")
            ld.shape = "RECTANGLE"
            ld.size = Ld["length"] - 0.05
            ld.size_y = Ld["width"] - 0.05
            ld.energy = Ld.get("watts", 260.0)
            ld.color = (0.93, 0.97, 1.0)
            try:
                ld.spread = math.radians(150)
            except AttributeError:
                pass
            lo = bpy.data.objects.new(ld.name, ld)
            self.c("Lighting").objects.link(lo)
            lo.parent = self.root
            lo.location = (Ld["center_x"], y + Ld["width"] * 0.5, z - 0.005)
            lo.visible_camera = False
            lo.visible_glossy = False
            # indirect component: the pendants also throw light up onto the ceiling
            up_w = Ld.get("uplight_watts", 0.0)
            if up_w > 0:
                ud = bpy.data.lights.new(f"{self.id}.PendantUplight_{i}", "AREA")
                ud.shape = "RECTANGLE"
                ud.size, ud.size_y = Ld["length"] - 0.05, Ld["width"] - 0.05
                ud.energy = up_w
                ud.color = (0.93, 0.97, 1.0)
                uo = bpy.data.objects.new(ud.name, ud)
                self.c("Lighting").objects.link(uo)
                uo.parent = self.root
                uo.location = (Ld["center_x"], y + Ld["width"] * 0.5, z + Ld["housing"] + 0.01)
                uo.rotation_euler = (math.pi, 0.0, 0.0)
                uo.visible_camera = False
                uo.visible_glossy = False
        # wall washers: linear LED coves in the soffits, grazing the walls
        for ww in self.R.get("wall_washers", []):
            wd = bpy.data.lights.new(f"{self.id}.WallWasher_{ww['id']}", "AREA")
            wd.shape = "RECTANGLE"
            wd.size, wd.size_y = ww["length"], 0.08
            wd.energy = ww["watts"]
            wd.color = tuple(ww.get("color", (0.92, 0.96, 1.0)))
            try:
                wd.spread = math.radians(ww.get("spread_deg", 120))
            except AttributeError:
                pass
            wo = bpy.data.objects.new(wd.name, wd)
            self.c("Lighting").objects.link(wo)
            wo.parent = self.root
            wo.location = tuple(ww["location"])
            wo.rotation_euler = tuple(math.radians(a) for a in ww.get("rotation_deg", (0, 0, 0)))
            wo.visible_camera = False
            wo.visible_glossy = False

    def sign(self):
        S = self.R.get("sign")
        if not S:
            return
        sy = self.R["size"][1]
        self.obj("HoloSign", "MIL.Fix.HoloSign", {
            "Top Width": S["top_width"], "Bottom Width": S["bottom_width"], "Height": S["height"],
            "Emblem Height": S["emblem_height"], "Emblem Z": S["emblem_z"],
            "Emblem X": S.get("artwork_x", 0.0),
            "Text Height": S["text_height"], "Text Z": S["text_z"],
            "Panel Material": M.get("MIL.HoloPanel"), "Rim Material": M.get("MIL.HoloEdge"),
            "Artwork Material": M.get("MIL.LogoBlue")},
            loc=(S["center_x"], sy, S["bottom_z"]), col="Fixtures")

    def shelves(self):
        for s in self.R.get("shelves", []):
            self.obj(f"Shelf_{s['id']}", "MIL.Furn.WingShelf", {
                "Tower Width": s.get("tower_width", 0.62), "Tower Height": s.get("height", 2.36),
                "Wing 1 Length": s.get("wing1", 0.95), "Wing 2 Length": s.get("wing2", 0.7),
                "Wing 1 Z": s.get("wing1_z", 1.32), "Wing 2 Z": s.get("wing2_z", 1.78),
                "Top Rail": s.get("top_rail", False), "Top Rail Length": s.get("rail_length", 2.2),
                "Board Material": M.get("MIL.TrimWhite"), "Tray Material": M.get("MIL.TrimWhite"),
                "Book Material A": M.get("MIL.BookBlue"), "Book Material B": M.get("MIL.BookTeal"),
                "Book Material C": M.get("MIL.Paper")},
                loc=(s["center"][0], s["center"][1], 0.0), rot_z=s.get("rotation", 0),
                col="Furniture")

    def desks(self):
        D = self.R["desks"]
        U = D["unit"]
        W, Dp, H = U["width"], U["depth"], U["height"]
        tuck = D.get("chair_tuck", 0.33)
        mf = M.get("MIL.MetalFrame")
        chair_mat = {"white": M.get("MIL.ChairWhite"), "blue": M.get("MIL.ChairBlue")}
        for cl in D["clusters"]:
            ox, oy = cl["origin"]
            W = cl.get("unit_width", U["width"])
            for u in range(cl["units"]):
                cx = ox + W * (u + 0.5)
                cy = oy + Dp * 0.5
                self.obj(f"Desk_{cl['id']}_{u}", "MIL.Furn.Desk",
                         {"Width": W, "Depth": Dp, "Height": H,
                          "Top Material": M.get("MIL.DeskTop"), "Edge Material": M.get("MIL.DeskEdge"),
                          "Frame Material": mf},
                         loc=(cx, cy, 0.0), col="Furniture")
                seats = cl.get("seats", [])
                if u < len(seats) and seats[u]:
                    st = seats[u]
                    # far side, facing -Y (towards the front of the room)
                    chy = oy + Dp - tuck + 0.26
                    self.obj(f"Chair_{cl['id']}_{u}", "MIL.Furn.Chair",
                             {"Shell Material": chair_mat[st.get("chair", "white")],
                              "Base Material": mf, "Cushion Material": M.get("MIL.CushionBlue"),
                              "Cushions": st.get("cushions", 0)},
                             loc=(cx + st.get("dx", 0.0), chy + st.get("dy", 0.0), 0.0),
                             rot_z=st.get("rot", 0.0), col="Furniture")
            for p in cl.get("props", []):
                u = p["unit"]
                px = ox + W * (u + 0.5) + p["offset"][0]
                py = oy + Dp * 0.5 + p["offset"][1]
                if p["type"] == "laptop":
                    self.obj(f"Laptop_{cl['id']}_{u}", "MIL.Furn.Laptop",
                             {"Body Material": M.get("MIL.Aluminium"), "Screen Material": M.get("MIL.Screen"),
                              "Logo Material": M.get("MIL.LogoBlue")},
                             loc=(px, py, H), rot_z=180.0 + p.get("rot", 0.0), col="Props")
                elif p["type"] == "pencup":
                    self.obj(f"PenCup_{cl['id']}_{u}", "MIL.Furn.PenCup",
                             {"Cup Material": M.get("MIL.Aluminium"), "Pen Material": M.get("MIL.BookBlue")},
                             loc=(px, py, H), col="Props")


def build_room(room_dir, parent_matrix=None, collection=None, in_tower=False):
    return RoomBuilder(room_dir, parent_matrix, collection, in_tower).build()
