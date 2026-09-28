"""Route the connections the autorouter left open (grid A* over the signal layers).

usage (KiCad Python):  hand_route.py board.kicad_pcb drc.rpt
Reads the "unconnected_items" pairs from a kicad-cli DRC report, routes each pair with
0.15 mm tracks and 0.45/0.25 mm vias, keeping 0.2 mm from every other net, and saves.
In1 (the GND reference plane) is never used for routing.
"""
import heapq
import math
import re
import sys

import os

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_pcb  # noqa: E402  board outline

MARGIN = 0.04  # grid discretisation allowance

GRID = 0.05  # mm
W = 0.15
VIA, DRILL = 0.45, 0.25
CLR = 0.2
LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu]
LNAME = {pcbnew.F_Cu: "F.Cu", pcbnew.In2_Cu: "In2.Cu", pcbnew.In3_Cu: "In3.Cu", pcbnew.In4_Cu: "In4.Cu",
         pcbnew.B_Cu: "B.Cu"}
MM = pcbnew.FromMM


def parse_unconnected(path):
    t = open(path, encoding="utf8").read()
    out = []
    for blk in re.split(r"\n(?=\[)", t):
        if not blk.startswith("[unconnected_items]"):
            continue
        items = re.findall(r"@\(([-0-9.]+) mm, ([-0-9.]+) mm\): (.*)", blk)
        if len(items) == 2:
            out.append([(float(x), float(y), d) for x, y, d in items])
    return out


def _clr(item):
    return 0.2 if item.GetNetname() in HV else 0.15


def obstacles(board, net, layer, inflate):
    """inflate = own half-width + own clearance; items of 60 V nets get at least 0.2 mm."""
    base = inflate - CLR
    ps = pcbnew.SHAPE_POLY_SET()
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == net or not p.IsOnLayer(layer):
                continue
            p.TransformShapeToPolygon(ps, layer, MM(base + max(CLR, _clr(p))), MM(0.01), pcbnew.ERROR_INSIDE)
    for t in board.GetTracks():
        if t.GetNetCode() == net or not t.IsOnLayer(layer):
            continue
        t.TransformShapeToPolygon(ps, layer, MM(base + max(CLR, _clr(t))), MM(0.01), pcbnew.ERROR_INSIDE)
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() == net or not z.IsOnLayer(layer):
            continue
        fill = z.GetFilledPolysList(layer)
        if fill is not None and fill.OutlineCount():
            f = pcbnew.SHAPE_POLY_SET(fill)
            f.Inflate(MM(inflate), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.01))
            ps.BooleanAdd(f)
    # holes block every layer
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSize().x > 0 and p.GetNetCode() != net:
                c = p.GetPosition()
                r = p.GetDrillSize().x / 2 + MM(inflate + 0.1)
                circ = pcbnew.SHAPE_POLY_SET()
                circ.NewOutline()
                for k in range(16):
                    a = 2 * math.pi * k / 16
                    circ.Append(int(c.x + r * math.cos(a)), int(c.y + r * math.sin(a)))
                ps.BooleanAdd(circ)
    return ps


HV = ("VBUS", "PHA", "PHB", "PHC", "SW12", "BST12", "GHA", "GHB", "GHC", "GHA_G", "GHB_G", "GHC_G", "CPH", "CPL", "VCP")


def route_pair(board, pair):
    global CLR, W
    m = re.search(r"\[([^\]]+)\]", pair[0][2]) or re.search(r"\[([^\]]+)\]", pair[1][2])
    hv = m.group(1) in HV
    for clr, w in ((0.2 if hv else 0.15, 0.15), (0.2 if hv else 0.15, 0.1)):
        CLR, W = clr, w
        res = _route_pair(board, pair)
        if res[1]:
            return res + (w,)
    return res


def _route_pair(board, pair):
    (x1, y1, d1), (x2, y2, d2) = pair
    m = re.search(r"\[([^\]]+)\]", d1) or re.search(r"\[([^\]]+)\]", d2)
    netname = m.group(1)
    net = board.FindNet(netname)
    nc = net.GetNetCode()

    def layers_of(desc):
        for L, n in LNAME.items():
            if "on " + n in desc:
                return [L]
        return list(LAYERS)  # vias, PTH pads, zones: any layer
    la, lb = layers_of(d1), layers_of(d2)
    pad = 6.0
    x0, y0 = min(x1, x2) - pad, min(y1, y2) - pad
    nx = int((abs(x2 - x1) + 2 * pad) / GRID) + 1
    ny = int((abs(y2 - y1) + 2 * pad) / GRID) + 1
    free = {}
    for L in LAYERS:
        obs = obstacles(board, nc, L, CLR + W / 2 + MARGIN)
        grid = bytearray(nx * ny)
        for j in range(ny):
            for i in range(nx):
                x, y = x0 + i * GRID, y0 + j * GRID
                pt = pcbnew.VECTOR2I(MM(x), MM(y))
                sx, sy = x - gen_pcb.OX, gen_pcb.OY - y
                ok = gen_pcb.inside(sx, sy) and gen_pcb.edge_dist(sx, sy) > 0.3 + W / 2 + MARGIN
                grid[j * nx + i] = 1 if ok and not obs.Contains(pt) else 0
        free[L] = grid
    vobs = [obstacles(board, nc, L, CLR + VIA / 2 + MARGIN) for L in LAYERS + [pcbnew.In1_Cu]]
    edge = board.GetBoardEdgesBoundingBox()

    def via_ok(i, j):
        x, y = x0 + i * GRID, y0 + j * GRID
        sx, sy = x - gen_pcb.OX, gen_pcb.OY - y
        if not gen_pcb.inside(sx, sy) or gen_pcb.edge_dist(sx, sy) < 0.3 + VIA / 2 + MARGIN:
            return False
        pt = pcbnew.VECTOR2I(MM(x), MM(y))
        return all(not o.Contains(pt) for o in vobs)

    def cell(x, y):
        return int(round((x - x0) / GRID)), int(round((y - y0) / GRID))
    s, g = cell(x1, y1), cell(x2, y2)
    start = [(0.0, (s[0], s[1], L)) for L in la]
    goal = set((g[0], g[1], L) for L in lb)
    # endpoints sit on own-net copper, so force them free
    for L in LAYERS:
        for (ci, cj) in (s, g):
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    ii, jj = ci + di, cj + dj
                    if 0 <= ii < nx and 0 <= jj < ny:
                        free[L][jj * nx + ii] = 1
    dist = {}
    prev = {}
    heap = []
    for c, st in start:
        dist[st] = 0
        heapq.heappush(heap, (0, st))
    viacache = {}
    closed = set()
    moves = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    found = None
    while heap:
        _, st = heapq.heappop(heap)
        if st in goal:
            found = st
            break
        if st in closed:
            continue
        closed.add(st)
        dcur = dist[st]
        i, j, L = st
        for di, dj, c in moves:
            ii, jj = i + di, j + dj
            if 0 <= ii < nx and 0 <= jj < ny and free[L][jj * nx + ii]:
                nd = dcur + c + (0.5 if L != pcbnew.F_Cu and L != pcbnew.B_Cu else 0)
                ns = (ii, jj, L)
                if nd < dist.get(ns, 1e18):
                    dist[ns] = nd
                    prev[ns] = st
                    h = math.hypot(g[0] - ii, g[1] - jj)
                    heapq.heappush(heap, (nd + h, ns))
        key = (i, j)
        if key not in viacache:
            viacache[key] = via_ok(i, j)
        if viacache[key]:
            for L2 in LAYERS:
                if L2 != L and free[L2][j * nx + i]:
                    ns = (i, j, L2)
                    nd = dcur + 40
                    if nd < dist.get(ns, 1e18):
                        dist[ns] = nd
                        prev[ns] = st
                        heapq.heappush(heap, (nd + math.hypot(g[0] - i, g[1] - j), ns))
    if not found:
        best = min((math.hypot(g[0] - k[0], g[1] - k[1]) * GRID, k) for k in dist)
        print("  no path for", netname, "explored", len(dist), "closest %.2f mm at" % best[0], best[1],
              "start free:", [free[L][s[1] * nx + s[0]] for L in LAYERS], "vias ok cells:", sum(viacache.values()))
        return netname, False
    path = [found]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    # emit: merge collinear steps
    pts = [path[0]]
    for a, b in zip(path, path[1:]):
        pts.append(b)
    seg_start = pts[0]
    last_dir = None
    for a, b in zip(pts, pts[1:]):
        if a[2] != b[2]:
            if (seg_start[0], seg_start[1]) != (a[0], a[1]):
                add_track(board, net, seg_start, a, x0, y0)
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(MM(x0 + a[0] * GRID), MM(y0 + a[1] * GRID)))
            v.SetWidth(MM(VIA))
            v.SetDrill(MM(DRILL))
            v.SetNet(net)
            board.Add(v)
            seg_start = b
            last_dir = None
            continue
        d = (b[0] - a[0], b[1] - a[1])
        if last_dir is not None and d != last_dir:
            add_track(board, net, seg_start, a, x0, y0)
            seg_start = a
        last_dir = d
    if (seg_start[0], seg_start[1]) != (pts[-1][0], pts[-1][1]):
        add_track(board, net, seg_start, pts[-1], x0, y0)
    return netname, True


def add_track(board, net, a, b, x0, y0):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(MM(x0 + a[0] * GRID), MM(y0 + a[1] * GRID)))
    t.SetEnd(pcbnew.VECTOR2I(MM(x0 + b[0] * GRID), MM(y0 + b[1] * GRID)))
    t.SetWidth(MM(W))
    t.SetLayer(a[2])
    t.SetNet(net)
    board.Add(t)


def rip_near(board, specs):
    """specs: NET:x:y:r (mm, KiCad coordinates). Removes that net's tracks/vias within r."""
    n = 0
    tracks = list(board.GetTracks())  # read once: GetTracks() breaks after Remove() in this build
    doomed = []
    for spec in specs:
        name, x, y, r = spec.split(":")
        p = pcbnew.VECTOR2I(MM(float(x)), MM(float(y)))
        for t in tracks:
            if t.GetNetname() != name:
                continue
            if t.Type() == pcbnew.PCB_VIA_T:
                d = pcbnew.ToMM(int((t.GetPosition() - p).EuclideanNorm()))
            else:
                a, b = t.GetStart(), t.GetEnd()
                dx, dy = b.x - a.x, b.y - a.y
                L = dx * dx + dy * dy
                u = 0 if L == 0 else max(0, min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L))
                d = pcbnew.ToMM(int(math.hypot(p.x - a.x - u * dx, p.y - a.y - u * dy)))
            if d < float(r) and t not in doomed:
                doomed.append(t)
    for t in doomed:
        board.Remove(t)
    return len(doomed)


def rip(board, names):
    n = 0
    for t in list(board.GetTracks()):
        if t.GetNetname() in names:
            board.Remove(t)
            n += 1
    return n


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    if len(sys.argv) > 3 and sys.argv[3] == "--rip-near":
        print("ripped items:", rip_near(board, sys.argv[4].split(",")))
        board.Save(sys.argv[1])
        return
    if len(sys.argv) > 3 and sys.argv[3] == "--rip":
        print("ripped items:", rip(board, sys.argv[4].split(",")))
        board.Save(sys.argv[1])
        return
    pairs = parse_unconnected(sys.argv[2])
    for p in pairs:
        if "[GND]" in p[0][2] or "[GND]" in p[1][2]:
            continue  # GND is joined by the pours
        print(route_pair(board, p))
    board.Save(sys.argv[1])


if __name__ == "__main__":
    main()
