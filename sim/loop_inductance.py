"""Commutation-loop inductance of one half-bridge (phase B) with FastHenry2.

The loop follows the routed copper: DC-link capacitor -> VBUS pour (F.Cu) -> high-side
MOSFET -> phase pour -> low-side MOSFET -> low-side pour and vias -> Kelvin shunt on
B.Cu -> ground vias -> In1 GND plane -> capacitor ground pad. Coordinates are the
MD80/STEP board coordinates in mm (see tools/gen_pcb.py). The MOSFET packages are
modelled as 0.6 mm-high straps; their datasheet-level parasitics are added in the
LTspice model instead of here.

run:  python sim/loop_inductance.py      (needs FastHenry2 from FastFieldSolvers)
"""
import os
import time

import win32com.client

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

ZF, ZI1, ZB = 0.0, -0.2, -1.6      # F.Cu, In1.Cu, B.Cu heights (6-layer, 1.6 mm)
T_OUT, T_IN = 0.07, 0.035           # 2 oz outer (plated), 1 oz inner
ZPKG = 0.6                          # die / clip height inside the SuperSO8

nodes, edges = [], []


def N(name, x, y, z):
    nodes.append("N%s x=%.3f y=%.3f z=%.3f" % (name, x, y, z))
    return "N" + name


def E(a, b, w, h, sub=(5, 1)):
    edges.append("E%d %s %s w=%.3f h=%.3f nwinc=%d nhinc=%d" % (len(edges), a, b, w, h, sub[0], sub[1]))


def build(n_vias_ls=5, n_vias_gnd=3, plane=True, local_cap=False):
    """local_cap: port at a 100 nF 0603 on B.Cu right under the high-side drain (C26)
    instead of at the DC-link row; this is the loop that sets the switching overshoot."""
    nodes.clear()
    edges.clear()
    if local_cap:
        ca = N("capP", 0.8, -13.3, ZB)
        cb = N("capN", -0.8, -13.3, ZB)
        hd = N("hsD", 0.8, -13.3, ZF)
        E(ca, hd, 0.5, 0.5)                 # via up into the HS drain pad
    else:
        ca = N("capP", 0, -8.67, ZF)        # capacitor VBUS pad
        cb = N("capN", 0, -5.72, ZF)        # capacitor GND pad (port = the capacitor)
        hd = N("hsD", 0, -12.45, ZF)
        E(ca, hd, 6.0, T_OUT)               # VBUS pour
    hd_up = N("hsDu", 0, -12.45, ZPKG)
    hs_up = N("hsSu", 0, -16.4, ZPKG)
    hs = N("hsS", 0, -16.4, ZF)
    E(hd, hd_up, 4.0, 0.2)
    E(hd_up, hs_up, 4.0, 0.2)               # HS package strap
    E(hs_up, hs, 3.0, 0.2)
    ld = N("lsD", 1.05, -18.5, ZF)
    E(hs, ld, 3.5, T_OUT)                   # phase pour
    ld_up = N("lsDu", 1.05, -19.5, ZPKG)
    ls_up = N("lsSu", -2.9, -19.5, ZPKG)
    ls = N("lsS", -2.9, -19.5, ZF)
    E(ld, ld_up, 4.0, 0.2)
    E(ld_up, ls_up, 4.0, 0.2)               # LS package strap
    E(ls_up, ls, 3.0, 0.2)
    vt = N("lsVt", -4.5, -20.3, ZF)
    E(ls, vt, 3.0, T_OUT)                   # LS pour top
    vb = N("lsVb", -4.5, -20.3, ZB)
    E(vt, vb, 0.4 * n_vias_ls ** 0.5 * 1.6, 0.4 * n_vias_ls ** 0.5 * 1.6)  # via cluster
    s1 = N("sh1", -2.48, -20.1, ZB)
    E(vb, s1, 3.0, T_OUT)                   # LS pour bottom
    s4 = N("sh4", 2.48, -20.1, ZB)
    E(s1, s4, 3.0, 0.6)                     # shunt element
    gb = N("gVb", 3.1, -20.6, ZB)
    E(s4, gb, 2.0, T_OUT)
    gi = N("gVi", 3.1, -20.6, ZI1)
    E(gb, gi, 0.4 * n_vias_gnd ** 0.5 * 1.6, 0.4 * n_vias_gnd ** 0.5 * 1.6)
    ci = N("cVi", -0.8, -13.3, ZI1) if local_cap else N("cVi", 1.5, -5.4, ZI1)
    if plane:
        # In1 GND plane under the power stage, meshed so the return current can spread
        plane_txt = ("G1 x1=-12 y1=-24 z1=%.3f x2=12 y2=-24 z2=%.3f x3=12 y3=-3 z3=%.3f thick=%.3f "
                     "seg1=24 seg2=21\n+ Nnin (3.1,-20.6,%.3f)\n+ Nnout (%.3f,%.3f,%.3f)\n") % (
            ZI1, ZI1, ZI1, T_IN, ZI1, (-0.8 if local_cap else 1.5), (-13.3 if local_cap else -5.4), ZI1)
        edges.append(plane_txt.strip())
        edges.append(".equiv %s Nnin" % gi)
        edges.append(".equiv %s Nnout" % ci)
    else:
        E(gi, ci, 10.0, T_IN)
    if local_cap:
        E(ci, cb, 0.3, 0.3)                 # ground via down to the local cap
    else:
        ct = N("cVt", 1.5, -5.4, ZF)
        E(ci, ct, 0.3, 0.3)                 # capacitor ground via
        E(ct, cb, 1.0, T_OUT)
    txt = ["* better-md80 phase B commutation loop", ".Units mm", ".Default sigma=5.8e4", ""]
    txt += nodes + [""] + edges + ["", ".external %s %s" % (ca, cb), ".freq fmin=1e7 fmax=1e8 ndec=1", ".end"]
    return "\n".join(txt) + "\n"


def run(inp_path):
    fh = win32com.client.Dispatch("FastHenry2.Document")
    ok = fh.Run('"%s" -S loop' % inp_path)
    while fh.IsRunning:
        time.sleep(0.5)
    L = fh.GetInductance
    R = fh.GetResistance
    f = fh.GetFrequencies
    fh.Quit
    return ok, list(f), [row[0][0] for row in L], [row[0][0] for row in R]


def main():
    results = []
    for label, kw in (("baseline (5 LS vias, 3 GND vias, meshed In1)", {}),
                      ("more vias (10 LS, 8 GND)", dict(n_vias_ls=10, n_vias_gnd=8)),
                      ("HF loop via local 100 nF (C26)", dict(local_cap=True))):
        path = os.path.join(OUT, "loop_%d.inp" % len(results))
        open(path, "w").write(build(**kw))
        ok, f, L, R = run(path)
        results.append((label, f, L, R))
        for fi, li, ri in zip(f, L, R):
            print("%-45s f=%6.1f MHz  L=%.2f nH  R=%.2f mOhm" % (label, fi / 1e6, li * 1e9, ri * 1e3))
    with open(os.path.join(OUT, "loop_inductance.txt"), "w") as fo:
        for label, f, L, R in results:
            for fi, li, ri in zip(f, L, R):
                fo.write("%s\t%.3g Hz\tL=%.3f nH\tR=%.3f mOhm\n" % (label, fi, li * 1e9, ri * 1e3))


if __name__ == "__main__":
    main()
