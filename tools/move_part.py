"""Move one footprint to the nearest free spot around a point (checks copper and courtyards).

usage (KiCad Python): move_part.py board.kicad_pcb REF x_mm y_mm side(F|B)
"""
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hand_route as H  # noqa: E402
import gen_pcb  # noqa: E402

MM = pcbnew.FromMM


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    ref, cx, cy, side = sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    fp = board.FindFootprintByReference(ref)
    if (side == "B") != fp.IsFlipped():
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    layer = pcbnew.B_Cu if side == "B" else pcbnew.F_Cu
    cyl = pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd
    net_codes = {p.GetNetCode() for p in fp.Pads()}
    H.CLR, H.W = 0.2, 0.0
    obs = pcbnew.SHAPE_POLY_SET()
    for nc in net_codes:
        pass
    # obstacles for every net except the part's own pads' nets handled per pad
    others = [f for f in board.GetFootprints() if f.GetReference() != ref]
    crt = pcbnew.SHAPE_POLY_SET()
    for f in others:
        c = f.GetCourtyard(cyl)
        if c.OutlineCount():
            crt.BooleanAdd(c)
    per_net = {nc: H.obstacles(board, nc, layer, 0.2) for nc in net_codes}
    for ring in range(0, 80):
        r = ring * 0.25
        steps = max(1, int(2 * math.pi * r / 0.25))
        for k in range(steps):
            for rot in (0, 90):
                x, y = cx + r * math.cos(2 * math.pi * k / steps), cy + r * math.sin(2 * math.pi * k / steps)
                fp.SetOrientationDegrees(rot)
                fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
                ok = True
                for p in ([] if "--ignore-tracks" in sys.argv else fp.Pads()):
                    sh = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(sh, layer, 0, MM(0.01), pcbnew.ERROR_INSIDE)
                    t = pcbnew.SHAPE_POLY_SET(sh)
                    t.BooleanIntersection(per_net[p.GetNetCode()])
                    if t.OutlineCount():
                        ok = False
                        break
                if ok:
                    bb = fp.GetCourtyard(cyl).BBox()
                    for (kx, ky) in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                                     (bb.GetLeft(), bb.GetBottom()), (bb.GetRight(), bb.GetBottom())):
                        sx, sy = pcbnew.ToMM(kx) - gen_pcb.OX, gen_pcb.OY - pcbnew.ToMM(ky)
                        if not gen_pcb.inside(sx, sy) or gen_pcb.edge_dist(sx, sy) < 0.3:
                            ok = False
                if ok:
                    c = pcbnew.SHAPE_POLY_SET(fp.GetCourtyard(cyl))
                    c.BooleanIntersection(crt)
                    ok = c.OutlineCount() == 0
                if ok and "--ignore-tracks" in sys.argv:
                    # rip other-net copper under the new pads; hand_route.py reconnects it
                    shapes = []
                    for p in fp.Pads():
                        sh = pcbnew.SHAPE_POLY_SET()
                        p.TransformShapeToPolygon(sh, layer, MM(0.25), MM(0.01), pcbnew.ERROR_INSIDE)
                        shapes.append((p.GetNetCode(), sh))
                    doomed = []
                    for t in list(board.GetTracks()):
                        for nc, sh in shapes:
                            if t.GetNetCode() == nc:
                                continue
                            ts = pcbnew.SHAPE_POLY_SET()
                            t.TransformShapeToPolygon(ts, layer if t.Type() != pcbnew.PCB_VIA_T else layer, 0, MM(0.01),
                                                      pcbnew.ERROR_INSIDE)
                            if t.IsOnLayer(layer):
                                ts.BooleanIntersection(sh)
                                if ts.OutlineCount():
                                    doomed.append(t)
                                    break
                    for t in doomed:
                        board.Remove(t)
                    print("ripped", len(doomed), "tracks/vias under", ref)
                if ok:
                    board.Save(sys.argv[1])
                    print("moved", ref, "to %.2f %.2f rot %d" % (x, y, rot))
                    return
    print("no spot for", ref)


if __name__ == "__main__":
    main()
