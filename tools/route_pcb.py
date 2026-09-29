"""Copper pours, power vias, autorouting hand-off and silkscreen clean-up.

Run with KiCad 10's Python, in this order (tools/route.sh does it):
  route_pcb.py pours      add zones + power-stage stitching vias, export hardware/route/board.dsn
  (freerouting)           route board.dsn -> board.ses
  route_pcb.py finish     import board.ses, refill zones, fix silkscreen, save

Coordinates here are MD80 STEP coordinates (mm, y up, origin on the rotor axis).
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_pcb  # noqa: E402  (outline polygon, coordinate helper, phase positions)

HW = gen_pcb.HW
PCB = os.environ.get("BMD_PCB", os.path.join(HW, "better-md80.kicad_pcb"))
RDIR = os.environ.get("BMD_RDIR", os.path.join(HW, "route"))
kc = gen_pcb.kc
MM = pcbnew.FromMM


def netcode(board, name):
    return board.FindNet(name)


# ------------------------------------------------------------------ zones
def add_zone(board, net, layer, pts, priority=0, clearance=0.2, min_width=0.2, solid=True, name=""):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(netcode(board, net))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(MM(clearance))
    z.SetMinThickness(MM(min_width))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.25))
    z.SetThermalReliefSpokeWidth(MM(0.35))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    if name:
        z.SetZoneName(name)
    ol = z.Outline()
    ol.NewOutline()
    for (x, y) in pts:
        ol.Append(kc(x, y))
    board.Add(z)
    return z


def rect(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def board_poly():
    return gen_pcb.POLY[::3]


def add_power_pours(board):
    """Local power-stage copper. Nothing of another net lies inside these, so the
    autorouter can treat them as fixed conduction areas.

    Layout (STEP coordinates): high-side FETs at y = -13.5, low-side FETs at y = -20.1,
    top-side shunts for phases A and C standing in the gaps at x = -5 / +5, phase B's
    low side returns straight to GND (two-shunt sensing)."""
    F, B, I4 = pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In4_Cu
    add_zone(board, "GND", pcbnew.In1_Cu, board_poly(), 0, name="GND plane")
    # VBUS over the high-side drains, with notches for the two shunt gaps
    vb = [(-18.2, -7.3), (18.2, -7.3), (18.2, -12.4), (7.1, -12.4), (7.1, -7.9), (2.9, -7.9), (2.9, -12.4),
          (-2.9, -12.4), (-2.9, -7.9), (-7.1, -7.9), (-7.1, -12.4), (-18.2, -12.4)]
    add_zone(board, "VBUS", F, vb, 5, name="VBUS top")
    add_zone(board, "VBUS", B, rect(-18.2, -7.3, 18.2, -10.4), 5, name="VBUS bottom")
    for ph, x0 in gen_pcb.PH_X.items():
        hole_x = {"A": -5.8, "B": 0.0, "C": 5.8}[ph]
        s = -1 if ph == "A" else 1          # side of the low-side drain pad
        net = "PH" + ph
        add_zone(board, net, F, rect(x0 - 2.4, -15.3, x0 + 1.2, -17.9), 6, name=net + " top")
        d1, d2 = sorted((x0 + s * (1.05 - 2.35), x0 + s * (1.05 + 2.35)))
        add_zone(board, net, F, rect(d1, -17.5, d2, -22.6), 10)
        add_zone(board, net, F, rect(min(d1, hole_x - 1.9), -22.7, max(d2, hole_x + 1.9), -27.6), 11)
        lo = {"A": (-14.6, -4.6), "B": (-4.2, 4.2), "C": (4.6, 14.2)}[ph]
        add_zone(board, net, I4, rect(lo[0], -15.5, lo[1], -27.6), 6, name=net + " In4")
    # low-side sources -> shunt pad 1 (top side, around the gate pin)
    add_zone(board, "LSA", F, [(-7.6, -22.4), (-4.4, -22.4), (-4.4, -14.9), (-6.4, -14.9), (-6.4, -18.6),
                               (-7.6, -18.6)], 7, name="LSA top")
    add_zone(board, "LSC", F, rect(4.4, -21.6, 7.6, -14.9), 7, name="LSC top")


def add_general_pours(board):
    """Board-wide pours, added after routing so they flow around the tracks."""
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    full = board_poly()
    add_zone(board, "GND", F, full, 0, solid=False, name="GND top")
    add_zone(board, "GND", B, full, 0, solid=False, name="GND bottom")
    for L, nm in ((pcbnew.In2_Cu, "In2"), (pcbnew.In3_Cu, "In3"), (pcbnew.In4_Cu, "In4")):
        add_zone(board, "GND", L, full, 0, solid=True, name="GND %s fill" % nm)
    # VBUS plane: Micro-Fit strip, the TVS D1, and the power stage
    add_zone(board, "VBUS", pcbnew.In4_Cu, [(-30, 5.6), (-16.6, 5.6), (-16.6, -0.3), (-12.8, -0.3), (-12.8, -3.4),
                                            (19.5, -3.4), (19.5, -15.1),
                                 (-30, -15.1)], 5, name="VBUS plane")


# ------------------------------------------------------------------ vias
def box_dist(bb, p):
    """Distance in mm from point p (VECTOR2I) to box bb; 0 inside."""
    dx = max(bb.GetLeft() - p.x, 0, p.x - bb.GetRight())
    dy = max(bb.GetTop() - p.y, 0, p.y - bb.GetBottom())
    return pcbnew.ToMM(int(math.hypot(dx, dy)))


HV_NETS = {"VBUS", "PHA", "PHB", "PHC", "SW12", "BST12", "GHA", "GHB", "GHC", "GHA_G", "GHB_G", "GHC_G",
           "CPH", "CPL", "VCP"}


def seg_dist(p, a, b):
    ax, ay, bx, by, px, py = a.x, a.y, b.x, b.y, p.x, p.y
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return pcbnew.ToMM(int(math.hypot(px - ax - t * dx, py - ay - t * dy)))


def fix_vias_tracks(board, min_w=0.1, min_ring=0.1):
    """Make autorouter output meet fab minimums: via annular ring and neck-down widths."""
    rings = necks = 0
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            size, drill = t.GetWidth(pcbnew.F_Cu), t.GetDrillValue()
            if (size - drill) / 2 < MM(min_ring) - 10:
                t.SetDrill(size - 2 * MM(min_ring))
                rings += 1
        elif t.GetWidth() < MM(min_w) - 10:
            t.SetWidth(MM(min_w))
            necks += 1
    return rings, necks


def add_via(board, net, x, y, size=0.8, drill=0.4, clear=0.2, force=False):
    p = kc(x, y)
    n = netcode(board, net)
    if not force:
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetDrillSize().x > 0:  # hole-to-hole applies to every net
                    hd = pcbnew.ToMM(int((pad.GetPosition() - p).EuclideanNorm()))
                    if hd < pcbnew.ToMM(pad.GetDrillSize().x) / 2 + drill / 2 + 0.3:
                        return False
                if pad.GetNetCode() == n.GetNetCode():
                    continue
                hv = pad.GetNetname() in HV_NETS or net in HV_NETS
                if box_dist(pad.GetBoundingBox(), p) < size / 2 + (max(clear, 0.25) if hv and pad.GetNetCode() else clear):
                    return False
        for t in board.GetTracks():
            if t.GetNetCode() == n.GetNetCode():
                continue
            if t.Type() == pcbnew.PCB_VIA_T:
                d = pcbnew.ToMM(int((t.GetPosition() - p).EuclideanNorm())) - pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
            else:
                d = seg_dist(p, t.GetStart(), t.GetEnd()) - pcbnew.ToMM(t.GetWidth()) / 2
            if d < size / 2 + clear:
                return False
        if gen_pcb.edge_dist(x, y) < size / 2 + 0.4 or not gen_pcb.inside(x, y):
            return False
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(p)
    v.SetWidth(MM(size))
    v.SetDrill(MM(drill))
    v.SetNet(n)
    board.Add(v)
    return True


def net_unnamed_pads(board):
    """Give un-numbered copper pads (exposed-pad segments, TDSON drain leads) the net of
    the numbered pad they overlap, so they are not foreign copper to DRC or the router."""
    n = 0
    for fp in board.GetFootprints():
        named = [p for p in fp.Pads() if p.GetNumber() and p.GetNetCode()]
        for p in fp.Pads():
            if p.GetNumber() or not (p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.B_Cu)):
                continue
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            bb = p.GetBoundingBox()
            for q in named:
                qb = q.GetBoundingBox()
                qb.Inflate(pcbnew.FromMM(0.3))
                if bb.Intersects(qb):
                    p.SetNet(q.GetNet())
                    n += 1
                    break
    return n


def add_track(board, net, p1, p2, width, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(p1)
    t.SetEnd(p2)
    t.SetWidth(MM(width))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)


def fanout(board, refs=("U4", "U5"), rows=(0.95, 1.75)):
    """Hand fan-out of the fine-pitch QFNs: a short stub from every pin to a small via,
    staggered in two rows so a 0.15 mm track passes between vias. The autorouter then
    only has to connect vias on the inner layers."""
    done = skipped = 0
    for ref in refs:
        fp = board.FindFootprintByReference(ref)
        c = fp.GetPosition()
        pads = [p for p in fp.Pads() if p.GetNumber() and p.GetNetCode()]
        ep = max(pads, key=lambda p: p.GetSize().x * p.GetSize().y)
        for pad in pads:
            if pad is ep or pad.GetNetname() in ("HSE_IN", "HSE_OUT"):
                continue
            pos = pad.GetPosition()
            dx, dy = pos.x - c.x, pos.y - c.y
            ux, uy = ((1 if dx > 0 else -1), 0) if abs(dx) > abs(dy) else (0, (1 if dy > 0 else -1))
            order = rows if int(pad.GetNumber()) % 2 else rows[::-1]
            for d in order:
                # stub starts at the pad's outer end
                half = max(pad.GetSize().x, pad.GetSize().y) / 2
                x = pcbnew.ToMM(pos.x) - gen_pcb.OX + ux * d
                y = gen_pcb.OY - (pcbnew.ToMM(pos.y) + uy * d)
                if add_via(board, pad.GetNetname(), x, y, 0.45, 0.2, 0.18):
                    end = kc(x, y)
                    add_track(board, pad.GetNet(), pos, end, 0.15)
                    done += 1
                    break
            else:
                skipped += 1
        # thermal / ground vias in the exposed pad
        epc = ep.GetPosition()
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                x = pcbnew.ToMM(epc.x) - gen_pcb.OX + i * 1.2
                y = gen_pcb.OY - pcbnew.ToMM(epc.y) + j * 1.2
                add_via(board, ep.GetNetname(), x, y, 0.45, 0.2, 0.15, force=True)
    return done, skipped


def add_rule_area(board, name, box_mm):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(False)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowZoneFills(False)
    z.SetZoneName(name)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    ol = z.Outline()
    ol.NewOutline()
    x1, y1, x2, y2 = box_mm
    for (x, y) in rect(x1, y1, x2, y2):
        ol.Append(kc(x, y))
    board.Add(z)


def fanout_areas(board):
    for ref in ("U4", "U1"):
        fp = board.FindFootprintByReference(ref)
        bb = fp.GetBoundingBox(False)
        x1, x2 = pcbnew.ToMM(bb.GetLeft()) - gen_pcb.OX - 2.5, pcbnew.ToMM(bb.GetRight()) - gen_pcb.OX + 2.5
        y2, y1 = gen_pcb.OY - pcbnew.ToMM(bb.GetTop()) + 2.5, gen_pcb.OY - pcbnew.ToMM(bb.GetBottom()) - 2.5
        add_rule_area(board, "FINEPITCH_" + ref, (x1, y1, x2, y2))


def add_power_vias(board):
    placed = 0
    for ph, x0 in gen_pcb.PH_X.items():
        for dx in (-1.6, -0.4, 0.8):              # phase node to In4
            placed += add_via(board, "PH" + ph, x0 + dx, -17.3)
    # shunt ground ends (pad 4 at y ~ -10.1) straight into the In1 plane
    for (x, y) in ((-6.2, -11.0), (-6.2, -12.0), (3.8, -11.0), (3.8, -12.0)):
        placed += add_via(board, "GND", x, y, 0.6, 0.3)
    # phase B low side is GND: vias next to its source pins
    for (x, y) in ((-2.9, -17.0), (-3.9, -23.4), (-2.9, -23.6)):
        placed += add_via(board, "GND", x, y, 0.6, 0.3)
    # VBUS stitching at the ends of the high-side row
    for x in (-16.2, -15.0, -13.6, 13.6, 15.0, 16.2):
        for y in (-10.6, -11.8):
            placed += add_via(board, "VBUS", x, y)
    for k in range(12):
        x = -16.5 + 3 * k
        placed += add_via(board, "VBUS", x + 1.5, -8.6)
        placed += add_via(board, "GND", x + 1.5, -5.4)
    return placed


STITCHED = []


def prune_stitching(board):
    """Drop stitching vias that ended up touching GND copper on fewer than two layers."""
    gnd = board.FindNet("GND").GetNetCode()
    fills = []
    for z in board.Zones():
        if z.GetNetCode() == gnd and not z.GetIsRuleArea():
            for L in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu):
                if z.IsOnLayer(L):
                    f = z.GetFilledPolysList(L)
                    if f is not None:
                        fills.append(f)
    removed = 0
    for v in list(STITCHED):
        hits = sum(1 for f in fills if f.Contains(v.GetPosition()))
        if hits < 2:
            board.Remove(v)
            removed += 1
    return removed


def tvs_vias(board):
    """Tie the input TVS straight into the VBUS plane and the GND plane."""
    d1 = board.FindFootprintByReference("D1")
    n = 0
    for p in d1.Pads():
        c = p.GetPosition()
        x, y = pcbnew.ToMM(c.x) - gen_pcb.OX, gen_pcb.OY - pcbnew.ToMM(c.y)
        for dx, dy in ((-1.6, 0), (1.6, 0), (0, -1.6), (0, 1.6), (-1.6, -1.2), (1.6, 1.2)):
            n += add_via(board, p.GetNetname(), x + dx, y + dy, 0.6, 0.3, 0.2)
    print("TVS plane vias:", n)


def stitch_gnd(board, pitch=2.5):
    """Sprinkle GND vias over the board wherever there is room (plane stitching)."""
    global VIAS_NOW
    VIAS_NOW = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    n = 0
    for iy in range(-12, 13):
        for ix in range(-12, 13):
            x, y = ix * pitch, iy * pitch
            if -15.5 < y < -3.0 and abs(x) < 19:  # power stage has its own vias
                continue
            if math.hypot(x, y) < 3.5:           # keep clear under the encoder
                continue
            if x < -23.5:                        # Micro-Fit strip: pours there are islands
                continue
            if any(t.Type() == pcbnew.PCB_VIA_T and (t.GetPosition() - kc(x, y)).EuclideanNorm() < MM(0.9)
                   for t in VIAS_NOW):
                continue
            if add_via(board, "GND", x, y, 0.6, 0.3, 0.25):
                STITCHED.append(list(board.GetTracks())[-1])
                n += 1
    return n


def fill(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


# ------------------------------------------------------------------ silkscreen
def fix_silk(board):
    """Shrink reference designators and move them off copper; hide the ones with no room."""
    pads = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            bb.Inflate(MM(0.15))
            if pad.IsOnLayer(pcbnew.F_Cu):
                pads[pcbnew.F_SilkS].append(bb)
            if pad.IsOnLayer(pcbnew.B_Cu):
                pads[pcbnew.B_SilkS].append(bb)
    for v in board.GetTracks():
        if v.Type() == pcbnew.PCB_VIA_T:
            bb = v.GetBoundingBox()
            bb.Inflate(MM(0.1))
            pads[pcbnew.F_SilkS].append(bb)
            pads[pcbnew.B_SilkS].append(bb)
    texts = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    edge = [pcbnew.BOX2I(kc(x, y), pcbnew.VECTOR2I(1, 1)) for x, y in gen_pcb.POLY]
    moved = hidden = 0
    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    for fp in fps:
        ref = fp.Reference()
        layer = ref.GetLayer()
        if layer not in pads:
            continue
        if fp.GetReference().startswith("MECH"):
            ref.SetVisible(False)
            continue
        small = len(fp.Pads()) <= 4 and max(fp.GetBoundingBox(False).GetWidth(), fp.GetBoundingBox(False).GetHeight()) < MM(4)
        h = 0.8
        ref.SetTextSize(pcbnew.VECTOR2I(MM(h), MM(h)))
        ref.SetTextThickness(MM(h * 0.15))
        ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        ref.SetKeepUpright(True)
        cy = fp.GetCourtyard(pcbnew.F_CrtYd if not fp.IsFlipped() else pcbnew.B_CrtYd)
        cb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
        c = cb.GetCenter()
        hw, hh = cb.GetWidth() // 2, cb.GetHeight() // 2
        tw = MM(h * 0.75 * len(fp.GetReference()) + 0.2)
        th = MM(h * 1.3)
        cands = [(0, -hh - th // 2), (0, hh + th // 2), (-hw - tw // 2, 0), (hw + tw // 2, 0),
                 (-hw - tw // 2, -hh - th // 2), (hw + tw // 2, -hh - th // 2),
                 (-hw - tw // 2, hh + th // 2), (hw + tw // 2, hh + th // 2), (0, 0)]
        ok = False
        for dx, dy in cands:
            pos = pcbnew.VECTOR2I(c.x + dx, c.y + dy)
            box = pcbnew.BOX2I(pcbnew.VECTOR2I(pos.x - tw // 2, pos.y - th // 2), pcbnew.VECTOR2I(tw, th))
            if any(box.Intersects(b) for b in pads[layer]) or any(box.Intersects(b) for b in texts[layer]):
                continue
            if any(box.Intersects(e) for e in edge):
                continue
            xm, ym = pcbnew.ToMM(pos.x) - gen_pcb.OX, gen_pcb.OY - pcbnew.ToMM(pos.y)
            if not gen_pcb.inside(xm, ym) or gen_pcb.edge_dist(xm, ym) < 0.8:
                continue
            ref.SetPosition(pos)
            ref.SetVisible(True)
            texts[layer].append(box)
            ok = True
            moved += 1
            break
        if not ok:
            ref.SetVisible(False)
            hidden += 1
    # footprint silk lines that land on pads: remove the offending segments
    removed = 0
    for fp in board.GetFootprints():
        for item in list(fp.GraphicalItems()):
            if item.GetLayer() not in pads or item.Type() != pcbnew.PCB_SHAPE_T:
                continue
            bb = item.GetBoundingBox()
            own = [p.GetBoundingBox() for p in fp.Pads()]
            others = [b for b in pads[item.GetLayer()]]
            if any(bb.Intersects(b) for b in others) and item.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                # keep segments that only touch their own pads' clearance halo, drop the rest
                fp.Remove(item)
                removed += 1
    return moved, hidden, removed


# ------------------------------------------------------------------ main
def main():
    stage = sys.argv[1]
    os.makedirs(RDIR, exist_ok=True)
    board = pcbnew.LoadBoard(PCB)
    if stage == "pours":
        for z in list(board.Zones()):
            board.Remove(z)
        for t in list(board.GetTracks()):
            board.Remove(t)
        print("unnamed pads netted:", net_unnamed_pads(board))
        add_power_pours(board)
        n = add_power_vias(board)
        print("fan-out vias placed / skipped:", fanout(board))
        # DRC rule areas are added in "finish": Specctra export turns them into keep-outs
        m = 0  # plane stitching happens after routing so it does not block the router
        fill(board)
        board.Save(PCB)
        ok = pcbnew.ExportSpecctraDSN(board, os.path.join(RDIR, "board.dsn"))
        print("pours added, power vias %d, stitching vias %d, dsn export %s" % (n, m, ok))
    elif stage == "import":
        ok = pcbnew.ImportSpecctraSES(board, os.path.join(RDIR, "board.ses"))
        print("ses import", ok)
        print("vias fixed / tracks widened:", fix_vias_tracks(board))
        fill(board)
        board.Save(PCB)
    elif stage == "final":
        fanout_areas(board)
        add_general_pours(board)
        tvs_vias(board)
        print("GND stitching vias", stitch_gnd(board))
        fill(board)
        print("isolated stitching vias removed", prune_stitching(board))
        fill(board)
        print("silk: moved %d, hidden %d, removed %d segments" % fix_silk(board))
        board.Save(PCB)
    elif stage == "silk":
        print("silk: moved %d, hidden %d, removed %d segments" % fix_silk(board))
        board.Save(PCB)


if __name__ == "__main__":
    main()
