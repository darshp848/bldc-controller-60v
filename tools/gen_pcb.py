"""Build hardware/better-md80.kicad_pcb from the schematic netlist.

Run with KiCad's bundled Python:
  "C:/Program Files/KiCad/9.0/bin/python.exe" tools/gen_pcb.py

What it does
  * Edge.Cuts copied from MAB's MD80 v3.0 STEP outline (mech/md80_v3_mech.json)
  * 4-layer stack-up, net classes for the 60 V power nets
  * Mechanically fixed parts (connectors, phase pads, thermistor pads, encoder,
    mounting holes, MOSFETs, shunts, DC-link capacitor rows) at MD80 coordinates
  * Everything else packed into functional zones without courtyard overlap
It does not route. Placement of the packed parts is a starting point for layout.
"""
import json
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sexp import parse, find, find1  # noqa: E402

HW = os.path.normpath(os.path.join(HERE, "..", "hardware"))
STOCK = "C:/Users/darsh/AppData/Local/Programs/KiCad/10.0/share/kicad/footprints/"
MECH = json.load(open(os.path.join(HERE, "..", "mech", "md80_v3_mech.json")))
OX, OY = 150.0, 100.0  # board origin (rotor axis) in KiCad page coordinates


def kc(x, y):
    """STEP (y-up, mm) -> KiCad internal units."""
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY - y))


# ------------------------------------------------------------------ outline
def outline_points(step=0.5):
    pts = []
    for e in MECH["wires"][0]:
        if e["kind"] == "arc":
            cx, cy = e["center"]
            a0 = math.atan2(e["start"][1] - cy, e["start"][0] - cx)
            a1 = math.atan2(e["end"][1] - cy, e["end"][0] - cx)
            am = math.atan2(e["mid"][1] - cy, e["mid"][0] - cx)
            # choose sweep direction that passes through mid
            def norm(a):
                return a % (2 * math.pi)
            ccw = norm(am - a0) < norm(a1 - a0)
            sweep = norm(a1 - a0) if ccw else -norm(a0 - a1)
            n = max(2, int(abs(sweep) * e["r"] / step))
            pts += [(cx + e["r"] * math.cos(a0 + sweep * k / n), cy + e["r"] * math.sin(a0 + sweep * k / n))
                    for k in range(n)]
        else:
            pts.append(tuple(e["start"]))
    return pts


POLY = outline_points()
_GRID = {}


def ok_point(x, y):
    """Inside the outline with 0.3 mm margin, cached on a 0.05 mm grid."""
    key = (round(x * 20), round(y * 20))
    v = _GRID.get(key)
    if v is None:
        v = inside(x, y) and edge_dist(x, y) >= 0.3
        _GRID[key] = v
    return v


def inside(x, y):
    c = False
    n = len(POLY)
    for i in range(n):
        x1, y1 = POLY[i]
        x2, y2 = POLY[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def edge_dist(x, y):
    best = 1e9
    n = len(POLY)
    for i in range(n):
        x1, y1 = POLY[i]
        x2, y2 = POLY[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy or 1)))
        best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
    return best


def add_outline(board):
    for e in MECH["wires"][0]:
        s = pcbnew.PCB_SHAPE(board)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        if e["kind"] == "arc":
            s.SetShape(pcbnew.SHAPE_T_ARC)
            s.SetArcGeometry(kc(*e["start"]), kc(*e["mid"]), kc(*e["end"]))
        else:
            if math.dist(e["start"], e["end"]) < 1e-3:
                continue
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(kc(*e["start"]))
            s.SetEnd(kc(*e["end"]))
        board.Add(s)


# ------------------------------------------------------------------ netlist
def read_netlist():
    t = parse(open(os.path.join(HW, "better-md80.net"), encoding="utf8").read())
    comps = []
    for c in find(find1(t, "components"), "comp"):
        sp = find1(c, "sheetpath")
        props = {find1(p, "name")[1]: (find1(p, "value") or [None, ""])[1] for p in find(c, "property")}
        comps.append(dict(ref=find1(c, "ref")[1], value=find1(c, "value")[1], fp=find1(c, "footprint")[1],
                          path=find1(sp, "tstamps")[1] + find1(c, "tstamps")[1],
                          sheet=props.get("Sheetname", ""), sheetfile=props.get("Sheetfile", ""),
                          dnp="dnp" in props))
    pinnet = {}
    for n in find(find1(t, "nets"), "net"):
        name = find1(n, "name")[1]
        for node in find(n, "node"):
            pinnet[(find1(node, "ref")[1], find1(node, "pin")[1])] = name
    return comps, pinnet


def load_fp(fpid):
    lib, name = fpid.split(":")
    d = os.path.join(HW, "lib", "better_md80.pretty") if lib == "better_md80" else STOCK + lib + ".pretty"
    fp = pcbnew.FootprintLoad(d, name)
    if fp is None:
        raise SystemExit("footprint not found: " + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


# ------------------------------------------------------------------ placement plan (STEP coords)
PH_X = {"A": -10.0, "B": 0.0, "C": 10.0}
SHUNT_GAP_X = {"A": -5.0, "C": 5.0}   # top-side shunts stand in the gaps between the high-side FETs
SHUNT_Y = -12.6
CAP_X = [-16.5 + 3.0 * k for k in range(12)]
CAP_X_TOP = [x for x in CAP_X if abs(abs(x) - 6.0) > 2.0]  # keep the shunt gaps free

FIXED = {  # ref: (x, y, rotation_deg, side)
    "MECH1": (0, 0, 0, "F"),
    "J1": (-21.98, 7.0, 0, "F"), "J2": (-21.98, -7.0, 0, "F"),
    "J3": (3.15, 21.0, 180, "F"), "J4": (20.5, -2.6, 90, "F"),
    "J5": (15.43, -19.35, 0, "F"),
    "J10": (-5.8, -24.8, 0, "F"), "J11": (0.0, -25.0, 0, "F"), "J12": (5.8, -24.8, 0, "F"),
    "U7": (0, 0, 0, "B"),
    "D1": (-14.2, 1.0, 90, "F"),   # 5.0SMDJ60A, SMC, next to the power entry
}
for i, ph in enumerate("ABC"):
    FIXED["Q%d" % (2 * i + 1)] = (PH_X[ph], -13.5, 90, "F")   # high side, drain towards DC link
    # low side: A's sources face the A/B gap (rot 180), B and C sources face left (rot 0)
    FIXED["Q%d" % (2 * i + 2)] = (PH_X[ph], -20.1, 180 if ph == "A" else 0, "F")
for i, ph in enumerate("ABC"):
    if ph in SHUNT_GAP_X:
        FIXED["RS%d" % (i + 1)] = (SHUNT_GAP_X[ph], SHUNT_Y, 90, "F")   # pad 1 (low-side end) down
top_caps = ["C%d" % (100 + k) for k in range(12)]
for ref, x in zip(top_caps, CAP_X_TOP):
    FIXED[ref] = (x, -7.2, 90, "F")
for k, x in enumerate(CAP_X):
    FIXED["C%d" % (112 + k)] = (x, -7.2, 90, "B")
EXTRA_CAPS = top_caps[len(CAP_X_TOP):]   # the rest of the DC-link caps are packed near the bus

ZONES = [  # (refs, (x, y), side)
    (["U4", "C40", "C41", "C42", "C43", "C44", "C45", "C46", "C47", "R40", "R41", "R42"], (-8.5, 2.5), "F"),
    (["C48", "C49", "C50"], (2.0, -2.5), "F"),
    (["U5", "Y1", "C68", "C69", "C60", "C61", "C62", "C63", "C64", "C65", "C66", "C67", "R60",
      "R1", "R2", "C4"], (8.0, 5.5), "F"),
    (["R61", "R62", "D60", "D61"], (14.5, 13.0), "F"),
    (["J6"], (8.0, 13.0), "B"),
    (["U1", "C5", "C6", "R3", "R4", "R5", "C7", "L1", "R6", "R7", "R8", "C8", "C9", "C10", "C11"], (-10.0, 16.0), "F"),
    (["U2", "C12", "L2", "C13", "U3", "C14", "C15", "FB1", "C16", "C17"], (-12.0, 9.0), "B"),
    (["U6", "C70", "C71", "D70", "K1", "R70", "R71"], (-13.0, -1.0), "B"),
    (["C72", "C73", "R81"], (0.0, 4.0), "B"),
    (["R72", "R73", "R74", "R75"], (0.0, 16.5), "B"),
    (["U8", "C74", "R76", "R77", "R78"], (14.0, 3.0), "B"),
    (["R79", "R80", "C75"], (12.0, -17.0), "B"),
    (["TH1", "R33", "C32"], (-2.0, -16.5), "B"),
    (EXTRA_CAPS, (0.0, -3.8), "B"),
    (["R20", "R21", "C22", "R30", "C23"], (-10.0, -13.0), "B"),
    (["R22", "R23", "C26", "R31", "C27"], (0.0, -13.0), "B"),
    (["R24", "R25", "C30", "R32", "C31"], (9.5, -13.0), "B"),
]


FANOUT_RING = {"U4": 2.2, "U5": 2.2}


class Packer:
    def __init__(self):
        self.occ = {"F": [], "B": []}

    @staticmethod
    def rel_bbox(fp, rot, side):
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        fp.SetOrientationDegrees(rot)
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
        x1, y1 = pcbnew.ToMM(bb.GetLeft()), -pcbnew.ToMM(bb.GetBottom())
        x2, y2 = pcbnew.ToMM(bb.GetRight()), -pcbnew.ToMM(bb.GetTop())
        if side == "B":
            x1, x2 = -x2, -x1
        return x1, y1, x2, y2

    def fits(self, box, side, margin=0.4):
        x1, y1, x2, y2 = box
        for (a1, b1, a2, b2) in self.occ[side]:
            if x1 < a2 + margin and x2 > a1 - margin and y1 < b2 + margin and y2 > b1 - margin:
                return False
        for (px, py) in ((x1, y1), (x1, y2), (x2, y1), (x2, y2), ((x1 + x2) / 2, y1), ((x1 + x2) / 2, y2),
                         (x1, (y1 + y2) / 2), (x2, (y1 + y2) / 2)):
            if not ok_point(px, py):
                return False
        return True

    def occupy(self, box, side):
        self.occ[side].append(box)

    def find(self, fp, center, side, rots=(0, 90)):
        cx, cy = center
        rels = [(r, self.rel_bbox(fp, r, side)) for r in rots]
        for ring in range(0, 70):
            rad = ring * 0.5
            steps = max(1, int(2 * math.pi * rad / 0.5))
            for k in range(steps):
                a = 2 * math.pi * k / steps
                x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
                x, y = round(x * 4) / 4, round(y * 4) / 4
                for r, (a1, b1, a2, b2) in rels:
                    box = (x + a1, y + b1, x + a2, y + b2)
                    if self.fits(box, side):
                        return x, y, r, box
        return None


def put(fp, x, y, rot, side):
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    fp.SetOrientationDegrees(rot)
    if side == "B":
        fp.Flip(pcbnew.VECTOR2I(0, 0), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetPosition(kc(x, y))


def main():
    comps, pinnet = read_netlist()
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(pcbnew.FromMM(1.6))
    ds.m_CopperEdgeClearance = pcbnew.FromMM(0.3)
    add_outline(board)

    nets = {}
    for name in sorted(set(pinnet.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    fps = {}
    for c in comps:
        if c["ref"].startswith("#"):
            continue
        fp = load_fp(c["fp"])
        fp.SetReference(c["ref"])
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        try:
            fp.SetSheetname(c["sheet"])
            fp.SetSheetfile(c["sheetfile"])
        except AttributeError:
            pass
        for pad in fp.Pads():
            net = pinnet.get((c["ref"], pad.GetNumber()))
            if net and not net.startswith("unconnected-"):
                pad.SetNet(nets[net])
        board.Add(fp)
        fps[c["ref"]] = fp

    pk = Packer()
    placed = set()

    def area(r):
        b = pk.rel_bbox(fps[r], 0, "F")
        return (b[2] - b[0]) * (b[3] - b[1])
    order = sorted(fps, key=lambda r: -area(r))  # before placing: rel_bbox moves parts to the origin
    for ref, (x, y, rot, side) in FIXED.items():
        fp = fps[ref]
        rel = pk.rel_bbox(fp, rot, side)
        put(fp, x, y, rot, side)
        box = (x + rel[0], y + rel[1], x + rel[2], y + rel[3])
        placed.add(ref)
        if ref == "MECH1":  # its keep-outs are added individually below
            continue
        pk.occupy(box, side)
        if fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE or ref.startswith(("J", "MECH")):
            pk.occupy(box, "B" if side == "F" else "F")
    # mechanical keep-outs (screw heads / standoffs) on both sides
    for w in MECH["wires"][1:]:
        e = w[0]
        if len(w) == 1 and 1.55 <= e["r"] <= 1.65:
            x, y = e["center"]
            for s in "FB":
                pk.occupy((x - 2.4, y - 2.4, x + 2.4, y + 2.4), s)
    for (x, y) in ((26.56, -7.12), (-7.12, 26.57), (-19.45, -19.45)):
        for s in "FB":
            pk.occupy((x - 2.25, y - 2.25, x + 2.25, y + 2.25), s)

    failed = []
    zone_of = {}
    for refs, center, side in ZONES:
        for r in refs:
            zone_of[r] = (center, side)
    for ref in order:
        if ref in placed:
            continue
        center, side = zone_of.get(ref, ((4.0, -2.0), "F"))
        if ref in ("Y1", "C68", "C69") and "U5" in placed:
            u5 = fps["U5"]
            pins = {p.GetNumber(): p.GetPosition() for p in u5.Pads()}
            c5 = u5.GetPosition()
            hx = (pins["5"].x + pins["6"].x) / 2
            hy = (pins["5"].y + pins["6"].y) / 2
            dx, dy = hx - c5.x, hy - c5.y
            L = max(1, math.hypot(dx, dy))
            d = pcbnew.FromMM({"Y1": 5.2, "C68": 7.6, "C69": 7.6}[ref])
            px, py = hx + dx / L * d, hy + dy / L * d
            off = {"Y1": 0, "C68": -1.6, "C69": 1.6}[ref]
            px += -dy / L * pcbnew.FromMM(off)
            py += dx / L * pcbnew.FromMM(off)
            center, side = ((pcbnew.ToMM(px) - OX, OY - pcbnew.ToMM(py)), "F")
        res = pk.find(fps[ref], center, side)
        if res is None:
            side = "B" if side == "F" else "F"
            res = pk.find(fps[ref], center, side)
        if res is None:
            failed.append(ref)
            put(fps[ref], 40, 0, 0, "F")
            continue
        x, y, rot, box = res
        put(fps[ref], x, y, rot, side)
        pk.occupy(box, side)
        if any(p.GetDrillSize().x > 0 for p in fps[ref].Pads()):  # holes go through both sides
            pk.occupy(box, "B" if side == "F" else "F")
        if ref in FANOUT_RING:  # keep a via fan-out ring free on both sides
            r = FANOUT_RING[ref]
            ring = (box[0] - r, box[1] - r, box[2] + r, box[3] + r)
            pk.occupy(ring, "F")
            pk.occupy(ring, "B")
        placed.add(ref)

    # net classes: 60 V power nets get wider clearance
    ns = ds.m_NetSettings
    hv = pcbnew.NETCLASS("HV_60V")
    hv.SetClearance(pcbnew.FromMM(0.2))
    hv.SetTrackWidth(pcbnew.FromMM(0.5))
    hv.SetViaDiameter(pcbnew.FromMM(0.8))
    hv.SetViaDrill(pcbnew.FromMM(0.4))
    try:
        ns.SetNetclass("HV_60V", hv)
        for pat in ("VBUS", "PH*", "SW12", "BST12", "GH*", "CPH", "CPL", "VCP", "SNUB*"):
            ns.SetNetclassPatternAssignment(pat, "HV_60V")
    except Exception as ex:  # API differs between 9.0.x releases
        print("net class setup skipped:", ex)

    out = os.path.join(HW, "better-md80.kicad_pcb")
    board.Save(out)
    print("saved", out, "footprints:", len(fps), "unplaced:", failed)


if __name__ == "__main__":
    main()
