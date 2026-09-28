"""DC-bus transients in LTspice: hot-plug overshoot and regenerative pump-up.

Bus capacitance: 24x TDK C3216X7S2A225K160AB (2.2 uF 100 V X7S 1206). X7S at 60 V bias
keeps roughly 35-40 % (derated here to 0.85 uF each, about 20 uF total). TVS: SMBJ60A,
modelled as a zener with 70 V knee and 4.3 Ohm dynamic resistance so that it reaches the
datasheet 96.8 V at 6.2 A.

run:  python sim/bus_surge.py
"""
import os
import subprocess

import numpy as np
from spicelib import RawRead

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
LTSPICE = r"C:\Users\darsh\AppData\Local\Programs\ADI\LTspice\LTspice.exe"
TVS = "\n".join([
    ".model SMBJ60A D(BV=70 IBV=1m Rs=4.3 Cjo=1.2n Is=1p)",   # 96.8 V @ 6.2 A
    ".model SMCJ60A D(BV=70 IBV=1m Rs=1.73 Cjo=3n Is=1p)",    # 96.8 V @ 15.5 A
    ".model SMDJ60A5K D(BV=70 IBV=1m Rs=0.52 Cjo=9n Is=1p)",  # 5.0SMDJ60A: 96.8 V @ 51.6 A
])


def run(tag, body, tstop):
    path = os.path.join(OUT, tag + ".net")
    open(path, "w").write("* %s\n%s\n%s\n.tran 0 %g 0 5n\n.options plotwinsize=0\n.end\n" % (tag, body, TVS, tstop))
    subprocess.run([LTSPICE, "-b", path], check=True, timeout=600)
    raw = RawRead(path.replace(".net", ".raw"))
    return raw


def hotplug(l_cable, cbulk_ext=0.0, tvs=True, part="SMBJ60A"):
    body = f"""V1 src 0 PWL(0 0 10n 60)
Lc src a {l_cable} Rser=40m
Rc a bus 1m
Cbus bus 0 20u Rser=3m Lser=0.2n
{f"Dtvs 0 bus {part}" if tvs else ""}
{f"Cext bus 0 {cbulk_ext} Rser=150m" if cbulk_ext else ""}
Rload bus 0 1k
"""
    return body


def regen(i_regen, c_ext=0.0, part="SMBJ60A"):
    """Supply that cannot sink current (diode), motor braking pushes current into the bus."""
    body = f"""V1 src 0 60
Ds src a Dideal
.model Dideal D(Ron=5m)
Lc a bus 1u Rser=40m
Cbus bus 0 20u Rser=3m
Dtvs 0 bus {part}
{f"Cext bus 0 {c_ext} Rser=150m" if c_ext else ""}
Ireg 0 bus PULSE(0 {i_regen} 10u 1u 1u 200u 1)
"""
    return body


def main():
    os.makedirs(OUT, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lines = []
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for label, body in (("hot-plug, 0.5 m cable (0.5 uH), TVS", hotplug(0.5e-6)),
                        ("hot-plug, 2 m cable (2 uH), TVS", hotplug(2e-6)),
                        ("hot-plug, 2 m cable, no TVS", hotplug(2e-6, tvs=False)),
                        ("hot-plug, 2 m cable, TVS + 100 uF / 150 mOhm electrolytic at supply", hotplug(2e-6, 100e-6)),
                        ("hot-plug, 2 m cable, SMCJ60A instead", hotplug(2e-6, part="SMCJ60A")),
                        ("hot-plug, 2 m cable, 5.0SMDJ60A instead", hotplug(2e-6, part="SMDJ60A5K"))):
        raw = run("surge_%d" % len(lines), body, 60e-6)
        t = np.abs(raw.get_trace("time").get_wave())
        v = raw.get_trace("V(bus)").get_wave()
        itvs = raw.get_trace("I(Dtvs)").get_wave() if "no TVS" not in label else np.zeros_like(v)
        lines.append("%-70s peak %.1f V, TVS peak %.1f A" % (label, v.max(), -itvs.min() if itvs.size else 0))
        a1.plot(t * 1e6, v, label=label.replace("hot-plug, ", ""))
    a1.axhline(100, color="r", ls="--", lw=0.8)
    a1.set_xlabel("us")
    a1.set_ylabel("V(bus)")
    a1.set_title("Hot-plug onto 60 V")
    a1.legend(fontsize=7)
    for label, i_r, cext in (("regen 5 A, board caps only", 5, 0), ("regen 20 A, board caps only", 20, 0),
                             ("regen 20 A, + 470 uF external", 20, 470e-6),
                             ("regen 20 A, board caps, 5.0SMDJ60A", 20, 0)):
        raw = run("regen_%d" % len(lines), regen(i_r, cext, "SMDJ60A5K" if "SMDJ" in label else "SMBJ60A"), 250e-6)
        t = np.abs(raw.get_trace("time").get_wave())
        v = raw.get_trace("V(bus)").get_wave()
        i66 = t[np.argmax(v > 63)] if (v > 63).any() else float("nan")
        lines.append("%-70s peak %.1f V, reaches 63 V after %.1f us" % (label, v.max(), (i66 - 10e-6) * 1e6))
        a2.plot(t * 1e6, v, label=label)
    a2.axhline(63, color="orange", ls="--", lw=0.8, label="63 V firmware OV trip")
    a2.axhline(100, color="r", ls="--", lw=0.8)
    a2.set_xlabel("us")
    a2.set_title("Regenerative braking into a source that cannot sink")
    a2.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "bus_surge.png"), dpi=110)
    open(os.path.join(OUT, "bus_surge.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
