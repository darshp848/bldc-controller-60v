"""Extract PCB outline, holes and tall-part envelope from MAB's MD80 STEP model.

usage: python analyze_step.py MD80_V3.0_simplified.step > md80_mech.json
"""
import json
import sys

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line

shape = cq.importers.importStep(sys.argv[1])
solids = shape.solids().vals()
info = []
for i, s in enumerate(solids):
    bb = s.BoundingBox()
    info.append(dict(i=i, x=(bb.xmin, bb.xmax), y=(bb.ymin, bb.ymax), z=(bb.zmin, bb.zmax),
                     dx=bb.xlen, dy=bb.ylen, dz=bb.zlen, vol=s.Volume()))

# PCB = large, thin solid
pcb = max((d for d in info if d["dz"] < 2.5), key=lambda d: d["dx"] * d["dy"])
ps = solids[pcb["i"]]
ztop = pcb["z"][1]
edges = []
for f in ps.Faces():
    n = f.normalAt()
    if abs(n.z - 1) < 1e-6 and abs(f.Center().z - ztop) < 1e-3:
        for w in f.Wires():
            wl = []
            for e in w.Edges():
                c = BRepAdaptor_Curve(e.wrapped)
                t = c.GetType()
                a, b = e.startPoint(), e.endPoint()
                d = dict(start=[a.x, a.y], end=[b.x, b.y])
                if t == GeomAbs_Circle:
                    circ = c.Circle()
                    ctr = circ.Location()
                    d.update(kind="arc", center=[ctr.X(), ctr.Y()], r=circ.Radius(), mid=[e.positionAt(0.5).x, e.positionAt(0.5).y])
                elif t == GeomAbs_Line:
                    d.update(kind="line")
                else:
                    d.update(kind="other", mid=[e.positionAt(0.5).x, e.positionAt(0.5).y])
                wl.append(d)
            edges.append(wl)

others = [d for d in info if d["i"] != pcb["i"]]
top = [d for d in others if d["z"][0] >= ztop - 0.05]
bot = [d for d in others if d["z"][1] <= pcb["z"][0] + 0.05]
out = dict(pcb=pcb, wires=edges,
           top_max_height=max((d["z"][1] - ztop for d in top), default=0),
           bottom_max_depth=max((pcb["z"][0] - d["z"][0] for d in bot), default=0),
           top_parts=sorted(top, key=lambda d: -d["z"][1])[:40],
           bottom_parts=sorted(bot, key=lambda d: d["z"][0])[:40],
           nsolids=len(solids))
json.dump(out, sys.stdout, indent=1)
