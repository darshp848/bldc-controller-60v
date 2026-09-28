"""Double-pulse test of one half-bridge in LTspice: switch-node overshoot and ringing.

Uses the commutation-loop inductance extracted by loop_inductance.py (FastHenry), an
ISC022N10NM6 VDMOS model fitted to the datasheet (Rev 2.1: Ciss 5400 pF, Coss 1200 pF
and Crss 19 pF at 50 V, Qg 73 nC, Qgd 11.9 nC, Qoss 135 nC, Qrr 70 nC, RG 1.4 Ohm,
Vth 2.8 V, RDS(on) 1.8 mOhm typ) and the DRV8353 IDRIVE setting (300 mA source /
600 mA sink, modelled as Thevenin sources at the Miller plateau).

run:  python sim/double_pulse.py [L_loop_nH]
"""
import os
import subprocess
import sys

import numpy as np
from spicelib import RawRead

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
LTSPICE = r"C:\Users\darsh\AppData\Local\Programs\ADI\LTspice\LTspice.exe"

FET = (".model ISC022 VDMOS(Rg=1.4 Vto=2.8 Rd=0.9m Rs=0.4m Rb=1.5m Kp=180 lambda=0.02 "
       "Cgdmax=2.2n Cgdmin=19p a=0.45 Cgs=5.2n Cjo=9.0n m=0.55 VJ=0.9 Is=5p N=1.05 TT=12n "
       "BV=100 mfg=fit Vds=100 Ron=2.24m Qg=73n)")


def netlist(vbus, ipk, l_loop, snubber=False, idrive=(0.3, 0.6), name="dp"):
    lload = 20e-6
    t1 = ipk * lload / vbus
    r_on = (11 - 4.4) / idrive[0]
    r_off = 4.4 / idrive[1]
    snub = "Rsn sw sn 2.2\nCsn sn 0 2.2n\n" if snubber else ""
    return f"""* better-md80 double pulse {name}
Vbus in 0 {vbus}
Lcab in dc 100n Rser=20m
Cdc dc 0 20u Rser=2m Lser=0.1n
Cloc dc 0 100n Rser=10m Lser=0.4n
Lvb dc d_hs {l_loop * 0.4}
XQH d_hs gh sw ISC022P
Lload d_hs sw {lload} Rser=5m
XQL sw gl s_ls ISC022P
Lgnd s_ls 0 {l_loop * 0.6}
{snub}* high side held off (body diode freewheels), gate referenced to its source
Vghs gh sw 0
* low side gate: DRV8353 IDRIVE modelled at the Miller plateau
Vpl drv 0 PULSE(0 11 1u 2n 2n {t1} {t1 + 5e-6} 2)
Don drv gl_a Dsw
Ron gl_a gl_t {r_on}
Doff gl_t gl_b Dsw
* routed gate trace GLx: ~25 mm over the GND plane
Lgate gl_t gl 15n
Roff gl_b drv {r_off}
.model Dsw D(Ron=0.01 Vfwd=0.05)
.subckt ISC022P D G S
Ld D di 0.15n
Ls si S 0.3n
M1 di G si si ISC022
.ends
{FET}
.tran 0 {t1 + 9e-6} {t1 - 0.5e-6} 0.1n
.options plotwinsize=0
.end
"""


def run(tag, **kw):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, tag + ".net")
    open(path, "w").write(netlist(name=tag, **kw))
    subprocess.run([LTSPICE, "-b", path], check=True, timeout=600)
    raw = RawRead(path.replace(".net", ".raw"))
    t = raw.get_trace("time").get_wave()
    vsw = raw.get_trace("V(sw)").get_wave()
    vdc = raw.get_trace("V(d_hs)").get_wave()
    t = np.abs(t)
    if t.min() < 1e-9:  # LTspice stores time relative to the .tran save start here
        t = t + kw["ipk"] * 20e-6 / kw["vbus"] - 0.5e-6
    vds_ls = vsw
    vds_hs = vdc - vsw
    i = raw.get_trace("I(Lload)").get_wave()
    return t, vds_ls, vds_hs, i


def ring_freq(t, v, t0):
    m = t > t0
    tt, vv = t[m], v[m] - np.median(v[m])
    zc = tt[1:][np.diff(np.sign(vv)) != 0]
    return 1 / (2 * np.mean(np.diff(zc[:8]))) if len(zc) > 3 else float("nan")


def main():
    l_loop = float(sys.argv[1]) * 1e-9 if len(sys.argv) > 1 else 5.0e-9
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    cases = [("60V_80A", dict(vbus=60, ipk=80)), ("60V_20A", dict(vbus=60, ipk=20)),
             ("48V_80A", dict(vbus=48, ipk=80)), ("60V_80A_snub", dict(vbus=60, ipk=80, snubber=True)),
             ("60V_80A_fast", dict(vbus=60, ipk=80, idrive=(0.7, 1.4)))]
    for k, (tag, kw) in enumerate(cases):
        t, vls, vhs, i = run(tag, l_loop=l_loop, **kw)
        t_off = kw["ipk"] * 20e-6 / kw["vbus"] + 1e-6
        off = (t > t_off) & (t < t_off + 2e-6)
        on2 = t > t_off + 5e-6
        pk_ls = vls[off].max()
        pk_hs = vhs[on2].max() if on2.any() else float("nan")
        f = ring_freq(t, vls, t[off][np.argmax(vls[off])])
        rows.append((tag, kw["vbus"], kw["ipk"], pk_ls, pk_hs, f / 1e6))
        panels = {"60V_80A": 0, "60V_80A_fast": 2, "60V_80A_snub": 3}
        if tag in panels:
            ax = axes.flat[panels[tag]]
            t_on = t_off + 5e-6
            m = (t > t_on - 0.05e-6) & (t < t_on + 0.4e-6)
            ax.plot((t[m] - t_on) * 1e9, vhs[m], label="VDS high side (diode recovery)")
            ax.axhline(100, color="r", ls="--", lw=0.8, label="100 V rating")
            ax.set_title("%s, low-side turn-on: peak %.1f V" % (tag, pk_hs))
            ax.set_xlabel("ns after turn-on command"); ax.set_ylabel("V"); ax.legend(loc="lower right", fontsize=8)
        if tag == "60V_80A":
            ax = axes.flat[1]
            m = (t > t_off - 0.05e-6) & (t < t_off + 0.4e-6)
            ax.plot((t[m] - t_off) * 1e9, vls[m], label="VDS low side")
            ax.axhline(100, color="r", ls="--", lw=0.8, label="100 V rating")
            ax.set_title("%s, low-side turn-off: peak %.1f V" % (tag, pk_ls))
            ax.set_xlabel("ns after turn-off command"); ax.set_ylabel("V"); ax.legend(loc="lower right", fontsize=8)
    fig.suptitle("Double pulse, L_loop = %.1f nH (FastHenry), DRV8353 IDRIVE 300/600 mA" % (l_loop * 1e9))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "double_pulse.png"), dpi=110)
    with open(os.path.join(OUT, "double_pulse.txt"), "w") as fo:
        fo.write("case\tVbus\tI_pk\tVDS_LS_peak_turnoff\tVDS_HS_peak_recovery\tring_MHz\n")
        for r in rows:
            fo.write("%s\t%d\t%d\t%.1f\t%.1f\t%.0f\n" % r)
            print("%-14s Vbus=%2d I=%2d  LS turn-off peak %.1f V  HS peak at LS turn-on %.1f V  ring %.0f MHz" % r)


if __name__ == "__main__":
    main()
