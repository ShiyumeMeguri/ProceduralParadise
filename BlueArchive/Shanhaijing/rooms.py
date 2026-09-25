"""
Shanhaijing room builder.

``build_room(room_dir, parent_matrix)`` reads ``room.json`` from a room folder
and assembles the room from the Shanhaijing kit.  Everything is parented to a
room root empty (``ROOM_<id>``), so the same definition can later be dropped
into a campus scene by giving the root a transform.

``room.json`` is pure data:

* ``parts``      -- explicit kit instances ``{"asset", "name", "loc", "rot",
                    "inputs", "mat"}`` (``rot`` in degrees, ``mat`` maps GN
                    material inputs to library names);
* ``structure``  -- the timber frame as grids (longitudinal beams, cross
                    beams, hanging posts, plaster and timber ceilings);
* ``columns``, ``tables`` (each with its chairs and table-top props),
  ``lanterns``, ``downlights``, ``lights`` ... -- repeated elements described
  once and expanded here.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Matrix, Vector

from Core import jsonio, scene as SC
from Core.gn import get_asset
from . import LEVELS, TIMBER
from .Kit import materials as M


def load_room(room_dir):
    return jsonio.load(os.path.join(room_dir, "room.json"))


def _rot(r):
    if r is None:
        return (0.0, 0.0, 0.0)
    if isinstance(r, (int, float)):
        return (0.0, 0.0, math.radians(r))
    return tuple(math.radians(a) for a in r)


class RoomBuilder:
    def __init__(self, room_dir, parent_matrix=None, collection=None):
        self.dir = room_dir
        self.R = load_room(room_dir)
        self.id = self.R["id"]
        self.col = collection or SC.collection(f"ROOM_{self.id}")
        self.root = SC.empty(f"ROOM_{self.id}", collection=self.col, display="ARROWS", size=1.0)
        self.root.matrix_world = parent_matrix or Matrix.Identity(4)
        self.sub = {}
        self.count = {}

    # ------------------------------------------------------------ helpers
    def c(self, name):
        if name not in self.sub:
            self.sub[name] = SC.collection(f"{self.id}.{name}", parent=self.col)
        return self.sub[name]

    def _name(self, base):
        n = self.count.get(base, 0)
        self.count[base] = n + 1
        return base if n == 0 else f"{base}.{n:03d}"

    def obj(self, name, asset, inputs=None, mat=None, loc=(0, 0, 0), rot=None, col="Architecture",
            parent=None, scale=(1, 1, 1)):
        ins = dict(inputs or {})
        for k, v in (mat or {}).items():
            ins[k] = M.get(v)
        ob = SC.gn_object(f"{self.id}.{self._name(name)}", get_asset(asset), ins,
                          location=loc, rotation=_rot(rot), scale=scale,
                          collection=self.c(col), parent=parent or self.root)
        return ob

    def part(self, p, col=None, parent=None):
        return self.obj(p.get("name", p["asset"].split(".")[-1]), p["asset"], p.get("inputs"),
                        p.get("mat"), p.get("loc", (0, 0, 0)), p.get("rot"),
                        col or p.get("col", "Architecture"), parent, p.get("scale", (1, 1, 1)))

    # ------------------------------------------------------------ build
    def build(self):
        R = self.R
        self.structure()
        for p in R.get("parts", []):
            self.part(p)
        self.columns()
        self.tables()
        self.lanterns()
        self.downlights()
        self.lights()
        return self

    # ------------------------------------------------------------ frame
    def structure(self):
        S = self.R.get("structure")
        if not S:
            return
        bw, bd = TIMBER["beam_width"], TIMBER["beam_depth"]
        zb = S.get("beam_bottom", LEVELS["beam_bottom"])
        tz = S.get("timber_ceiling", LEVELS["timber_ceiling"])
        pz = S.get("plaster_ceiling", LEVELS["plaster_ceiling"])
        mat_y = S.get("y_beam_material", "SHJ.TimberRed")
        mat_x = S.get("x_beam_material", "SHJ.TimberDark")
        # longitudinal (Y) beams
        yb = S["y_beams"]
        for x in yb["x"]:
            self.obj("BeamY", "SHJ.Arch.Beam", {"Length": yb["y1"] - yb["y0"], "Width": bw,
                                               "Height": tz - zb},
                     {"Material": mat_y}, (x, yb["y0"], zb), 90.0, "Structure")
        # cross (X) beams under the timber ceiling
        xb = S["x_beams"]
        for y in xb["y"]:
            self.obj("BeamX", "SHJ.Arch.Beam", {"Length": xb["x1"] - xb["x0"], "Width": bw,
                                               "Height": tz - zb},
                     {"Material": mat_x}, (xb["x0"], y, zb), 0.0, "Structure")
        # hanging blocks between the plaster ceiling and the Y beams
        hp = S.get("plaster_posts")
        if hp:
            for x in hp.get("on", yb["x"]):
                self.obj("HangBlock", "SHJ.Arch.HangingPost",
                         {"Length": pz - hp["bottom"], "Size": hp.get("size", 0.2), "Disc Radius": 0.0},
                         {"Material": mat_y, "Disc Material": mat_y}, (x, hp["y"], pz), None, "Structure")
        # hanging posts with discs at the timber grid intersections
        tp = S.get("timber_posts")
        if tp:
            skip = {tuple(v) for v in tp.get("skip", [])}
            for x in tp.get("x", yb["x"]):
                for y in tp.get("y", xb["y"]):
                    if (x, y) in skip:
                        continue
                    self.obj("HangPost", "SHJ.Arch.HangingPost",
                             {"Length": tz - tp["bottom"], "Size": tp.get("size", 0.2),
                              "Disc Radius": tp.get("disc", TIMBER["hanging_disc_radius"])},
                             {"Material": mat_x, "Disc Material": tp.get("disc_material", "SHJ.TimberDark")},
                             (x, y, tz), None, "Structure")
            # free-standing hanging posts between the grid lines: [x, y, bottom(, disc)]
            for e in tp.get("extra", []):
                self.obj("HangPost", "SHJ.Arch.HangingPost",
                         {"Length": tz - e[2], "Size": tp.get("size", 0.2),
                          "Disc Radius": e[3] if len(e) > 3 else 0.0},
                         {"Material": mat_x, "Disc Material": tp.get("disc_material", "SHJ.TimberDark")},
                         (e[0], e[1], tz), None, "Structure")

    # ------------------------------------------------------------ columns
    def columns(self):
        types = self.R.get("column_types", {})
        for c in self.R.get("columns", []):
            t = dict(types.get(c.get("type", ""), {}))
            ins = dict(t.get("inputs", {}))
            ins.update(c.get("inputs", {}))
            mat = dict(t.get("mat", {}))
            mat.update(c.get("mat", {}))
            self.obj(c.get("name", "Column"), "SHJ.Arch.Column", ins, mat,
                     (c["x"], c["y"], c.get("z", 0.0)), None, "Structure")

    # ------------------------------------------------------------ furniture
    def tables(self):
        T = self.R.get("tables")
        if not T:
            return
        types = T.get("types", {})
        for t in T["items"]:
            base = dict(types.get(t.get("type", "tea"), {}))
            rot = t.get("rot", 0.0)
            tab = self.obj(t.get("id", "Table"), base.get("asset", "SHJ.Furn.TeaTable"),
                           {**base.get("inputs", {}), **t.get("inputs", {})},
                           {**base.get("mat", {}), **t.get("mat", {})},
                           (t["x"], t["y"], 0.0), rot, "Furniture")
            H = t.get("inputs", {}).get("Height", base.get("inputs", {}).get("Height", 0.754))
            # chairs: placed in the table frame; "side" = W/E/N/S of the table
            ctype = dict(T.get("chair", {}))
            for ch in t.get("chairs", []):
                side = ch.get("side", "W")
                dist = ch.get("dist", ctype.get("dist", 0.62))
                ang = {"W": 90.0, "E": -90.0, "S": 180.0, "N": 0.0}[side]   # chairs face -Y
                dx, dy = {"W": (-dist, 0.0), "E": (dist, 0.0), "S": (0.0, -dist), "N": (0.0, dist)}[side]
                dx += ch.get("dx", 0.0)
                dy += ch.get("dy", 0.0)
                ob = self.obj(ch.get("id", "Chair"), ctype.get("asset", "SHJ.Furn.Chair"),
                              {**ctype.get("inputs", {}), **ch.get("inputs", {})},
                              {**ctype.get("mat", {}), **ch.get("mat", {})},
                              (dx, dy, 0.0), ang + ch.get("rot", 0.0), "Furniture", parent=tab)
            for p in t.get("props", []):
                q = dict(p)
                loc = list(q.get("loc", (0, 0, 0)))
                if len(loc) == 2:
                    loc = [loc[0], loc[1], H + 0.001]
                q["loc"] = loc
                self.part(q, col="Props", parent=tab)

    # ------------------------------------------------------------ lighting
    def lanterns(self):
        L = self.R.get("lanterns")
        if not L:
            return
        base = L.get("defaults", {})
        for s in L["strings"]:
            ins = {**base.get("inputs", {}), **s.get("inputs", {})}
            ob = self.obj(s.get("id", "Lanterns"), "SHJ.Prop.LanternString", ins,
                          {"Paper Material": "SHJ.LanternPaper", "Gold Material": "SHJ.LanternGold",
                           "Cord Material": "SHJ.Tassel"},
                          (s["x"], s["y"], s["z"]), s.get("rot"), "Lanterns")
            # a warm point light inside every lantern
            n = int(ins.get("Count", 3))
            D = ins.get("Diameter", 0.6)
            for i in range(n):
                z = s["z"] - ins.get("Drop", 0.6) - ins.get("Pitch", 0.7) * i - D * 0.16 - D * 0.41
                self.point_light(f"LanternLight", (s["x"], s["y"], z),
                                 L.get("light_power", 12.0) * (D / 0.6) ** 2,
                                 L.get("light_color", (1.0, 0.35, 0.18)), D * 0.35)

    def downlights(self):
        Dl = self.R.get("downlights")
        if not Dl:
            return
        sets = Dl["sets"] if "sets" in Dl else [Dl]
        for d in sets:
            hidden = d.get("hidden", False)       # concealed: light only, no visible fixture
            for x, y, z in d["at"]:
                if not hidden:
                    self.obj("Downlight", "SHJ.Arch.Downlight", {"Radius": d.get("radius", 0.06)},
                             {"Emitter Material": "SHJ.Downlight", "Trim Material": "SHJ.DownlightTrim"},
                             (x, y, z), None, "Lights")
                ob = self.spot_light("DownlightSpot", (x, y, z - 0.02), d.get("power", 60.0),
                                     d.get("color", (1.0, 0.82, 0.6)), d.get("angle", 70.0),
                                     d.get("blend", 0.6), d.get("radius", 0.06))
                if hidden:
                    self._conceal(ob)

    def lights(self):
        """Explicit lights.  ``"hidden": true`` marks a concealed fixture
        (a cove or wall-washer tucked behind a beam): it lights the room but
        is not seen directly by the camera or in reflections."""
        for l in self.R.get("lights", []):
            kind = l["type"]
            if kind == "POINT":
                ob = self.point_light(l.get("name", "Point"), l["loc"], l["power"], l.get("color", (1, 1, 1)),
                                      l.get("radius", 0.1))
            elif kind == "AREA":
                ob = self.area_light(l.get("name", "Area"), l["loc"], l.get("rot", (0, 0, 0)), l["power"],
                                     l.get("color", (1, 1, 1)), l.get("size", (1.0, 1.0)))
            elif kind == "SPOT":
                ob = self.spot_light(l.get("name", "Spot"), l["loc"], l["power"], l.get("color", (1, 1, 1)),
                                     l.get("angle", 60.0), l.get("blend", 0.5), l.get("radius", 0.05),
                                     l.get("rot"))
            if l.get("hidden"):
                self._conceal(ob)

    @staticmethod
    def _conceal(ob):
        for attr in ("visible_camera", "visible_glossy"):
            if hasattr(ob, attr):
                setattr(ob, attr, False)

    def _light(self, name, data, loc, rot=None):
        ob = bpy.data.objects.new(f"{self.id}.{self._name(name)}", data)
        self.c("Lights").objects.link(ob)
        ob.parent = self.root
        ob.location = loc
        if rot is not None:
            ob.rotation_euler = _rot(rot)
        return ob

    def point_light(self, name, loc, power, color, radius=0.1):
        d = bpy.data.lights.new(name, "POINT")
        d.energy = power
        d.color = color[:3]
        d.shadow_soft_size = radius
        return self._light(name, d, loc)

    def spot_light(self, name, loc, power, color, angle=60.0, blend=0.5, radius=0.05, rot=None):
        d = bpy.data.lights.new(name, "SPOT")
        d.energy = power
        d.color = color[:3]
        d.spot_size = math.radians(angle)
        d.spot_blend = blend
        d.shadow_soft_size = radius
        return self._light(name, d, loc, rot)

    def area_light(self, name, loc, rot, power, color, size):
        d = bpy.data.lights.new(name, "AREA")
        d.energy = power
        d.color = color[:3]
        d.shape = "RECTANGLE"
        d.size, d.size_y = size
        return self._light(name, d, loc, rot)


def build_room(room_dir, parent_matrix=None, in_tower=False):
    """Build the room in ``room_dir``.  ``in_tower`` is accepted for API
    compatibility with campus-based academies (Shanhaijing rooms stand
    alone)."""
    return RoomBuilder(room_dir, parent_matrix).build()
