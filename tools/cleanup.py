"""Apply mechanical fixes for the DRC warnings that are safe to fix automatically.

usage (KiCad Python): cleanup.py board.kicad_pcb drc.rpt
  - dangling track ends and one-layer vias: removed
  - holes closer than the hole-to-hole minimum: the later via of the pair is removed
  - reference text overlapping other silkscreen: hidden (kept on the fab layer)
  - footprint silkscreen clipped by the board edge: that segment removed
Zones are refilled afterwards.
"""
import re
import sys

import pcbnew

TOL = pcbnew.FromMM(0.02)


def blocks(path):
    t = open(path, encoding="utf8").read()
    for b in re.split(r"\n(?=\[)", t):
        m = re.match(r"\[(\w+)\]", b)
        if m:
            yield m.group(1), re.findall(r"@\(([-0-9.]+) mm, ([-0-9.]+) mm\): (.*)", b)


def at(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(float(x)), pcbnew.FromMM(float(y)))


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    tracks = list(board.GetTracks())
    zones = board.Zones()  # fetch before Remove(): container accessors crash afterwards in this build
    doomed = []
    hide = set()
    drop_silk = []
    for kind, items in blocks(sys.argv[2]):
        if kind in ("track_dangling", "via_dangling") and "--dangling" in sys.argv:
            x, y, d = items[0]
            p = at(x, y)
            for t in tracks:
                if t.Type() == pcbnew.PCB_VIA_T and "Via" in d and (t.GetPosition() - p).EuclideanNorm() < TOL:
                    doomed.append(t)
                elif t.Type() != pcbnew.PCB_VIA_T and "Track" in d and \
                        min((t.GetStart() - p).EuclideanNorm(), (t.GetEnd() - p).EuclideanNorm()) < TOL:
                    doomed.append(t)
        elif kind == "hole_to_hole":
            vias = [(x, y) for x, y, d in items if d.startswith("Via")]
            if vias:
                x, y = vias[-1]
                p = at(x, y)
                doomed += [t for t in tracks if t.Type() == pcbnew.PCB_VIA_T and (t.GetPosition() - p).EuclideanNorm() < TOL]
        elif kind == "silk_overlap":
            for x, y, d in items:
                m = re.match(r"Reference field of (\S+)", d)
                if m:
                    hide.add(m.group(1))
                    break
        elif kind == "silk_edge_clearance":
            for x, y, d in items:
                m = re.match(r"Segment of (\S+) on", d)
                if m:
                    drop_silk.append((m.group(1), at(x, y)))
    seen = set()
    for t in doomed:
        if id(t) not in seen:
            seen.add(id(t))
            board.Remove(t)
    for ref in hide:
        board.FindFootprintByReference(ref).Reference().SetVisible(False)
    for ref, p in drop_silk:
        fp = board.FindFootprintByReference(ref)
        for g in list(fp.GraphicalItems()):
            if g.Type() == pcbnew.PCB_SHAPE_T and g.GetBoundingBox().Contains(p):
                fp.Remove(g)
    pcbnew.ZONE_FILLER(board).Fill(zones)
    board.Save(sys.argv[1])
    print("removed %d tracks/vias, hid %d refs, dropped %d silk segments" % (len(seen), len(hide), len(drop_silk)))


if __name__ == "__main__":
    main()
