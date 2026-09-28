"""Check every drilled hole on the board against MAB's MD80 v3.0 STEP model.

Run with KiCad's Python after gen_pcb.py. Prints, for every round hole in the
STEP board, the nearest hole on our board and the position/diameter error.
"""
import json
import math
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
MECH = json.load(open(os.path.join(HERE, "..", "mech", "md80_v3_mech.json")))
board = pcbnew.LoadBoard(os.path.join(HERE, "..", "hardware", "better-md80.kicad_pcb"))

ours = []
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.GetDrillSize().x > 0:
            pos = p.GetPosition()
            ours.append((fp.GetReference(), p.GetNumber(), pcbnew.ToMM(pos.x) - 150, 100 - pcbnew.ToMM(pos.y),
                         pcbnew.ToMM(p.GetDrillSize().x)))

rows, worst = [], 0.0
for w in MECH["wires"][1:]:
    if len(w) != 1:
        continue
    (x, y), r = w[0]["center"], w[0]["r"]
    ref, num, ox, oy, d = min(ours, key=lambda o: math.hypot(o[2] - x, o[3] - y))
    err = math.hypot(ox - x, oy - y)
    worst = max(worst, err)
    rows.append("%-6s pad %-2s  STEP (%7.2f,%7.2f) d=%.2f   ours d=%.2f   offset %.3f mm" % (ref, num, x, y, 2 * r, d, err))
for r in sorted(rows):
    print(r)
print("holes checked: %d, worst position error: %.3f mm" % (len(rows), worst))
print("note: the non-circular Micro-Fit peg cut-out at (-26.3, -7.0) is modelled as a 3.0 mm hole")
