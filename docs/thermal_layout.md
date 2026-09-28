# Thermal and layout notes

## Loss budget (estimate, not measured)

Assumptions: 48 V bus, 20 A RMS phase current, 40 kHz centre-aligned PWM (the MD80's
torque-loop rate), MOSFET R_DS(on) 2.24 mOhm max at 25 C, taken as 3.4 mOhm hot (x1.5),
~30 ns rise and fall with DRV8353 IDRIVE at 300 mA source / 600 mA sink.

| Loss | Formula | Per phase | Total |
|---|---|---|---|
| Conduction | I_rms^2 x R_hot | 1.36 W | 4.1 W |
| Switching | 0.5 x V x I_avg x (tr + tf) x f, I_avg = 0.9 x I_rms | 1.0 W | 3.1 W |
| Output charge + dead-time diode | Qoss x V x f + Vf x I x 2 t_dead x f | ~0.35 W | ~1 W |
| Shunts | I^2 x R x duty (LS share ~0.5) | 0.1 W | 0.3 W |
| Gate drive + DRV quiescent (12 V) | | | 0.3 W |
| LM5164 + TPS62163 | ~85 % at ~2.6 W out | | 0.5 W |
| **Total** | | | **~9 W** |

At 60 V the switching term rises to ~3.9 W (total ~10 W). The MD80 at 42 V and 20 A lands
around 8 W with the same method, so 48 V costs roughly 10-15 % more heat for the same
current. Options if bench testing shows the FETs run hot:

- drop PWM to 20-25 kHz above 48 V (halves switching loss; still above audible range at 25 kHz)
- raise IDRIVE after checking ringing (faster edges, less switching loss)
- use MAB's thermal bridge / heat-sink pad under the power stage as on the MD80

The firmware MOSFET limit stays at the MD80's 100 C shutdown with 20 C hysteresis (NTC TH1
sits under the phase B FETs on the bottom side, as on the MD80).

At 80 A for 2 s: conduction ~22 W per phase pair is carried by thermal mass. The
ISC022N10NM6 pulse rating (920 A) and SuperSO8 junction-to-case (~0.5 K/W class) are far
from the limit; the limiting factor is copper temperature rise in the phase and VBUS pours,
which is why the power stage copper should be poured on all four layers.

## Stack-up

4 layers, 1.6 mm, 2 oz outer / 1 oz inner minimum (2 oz inner preferred for 80 A peak):

| Layer | Use |
|---|---|
| F.Cu | MOSFETs, DRV8353, MCU, regulators; VBUS and phase pours |
| In1.Cu | Solid GND (return for everything, reference for gate loops and CAN) |
| In2.Cu | VBUS pour under the bridge and DC-link; +12 V / +3V3 islands elsewhere |
| B.Cu | Shunts, DC-link second row, encoder, CAN, RS-422; GND pour |

## Layout rules

1. **Commutation loop first.** Each half-bridge's HS drain, LS source/shunt and the DC-link
   capacitors must form the smallest possible loop: HS FETs sit directly under the top
   capacitor row, the bottom capacitor row mirrors it, and the 100 nF 100 V caps (C22, C26,
   C30) go on the bottom straddling each HS drain / shunt ground. Via-stitch the VBUS pad
   of every HS FET to In2 and the shunt ground end to In1 with at least 8 vias each.
2. **Kelvin sensing.** SPx / SNx run as a differential pair from the inner shunt pads
   (pads 2 and 3 of the WSK2512 footprint) straight to the DRV8353, away from phase nodes.
   Do not tie SNx to the GND plane anywhere else.
3. **Gate loops.** GHx and SHx run as a pair, GLx paired with its LS source; keep under
   ~15 mm. The 0 Ohm gate resistors (R20-R25) are there to add 2-5 Ohm if ringing needs it.
4. **Snubbers.** R30-R32 / C23, C27, C31 are DNP; fit only if the phase-node ringing on the
   first board exceeds ~15 V overshoot at 60 V.
5. **60 V clearance.** Net class `HV_60V` (VBUS, PH*, LS*, gate nets, charge pump, LM5164
   switch node) has 0.2 mm base clearance for fine-pitch pins, and the custom rule file
   `hardware/better-md80.kicad_dru` enforces 0.5 mm on outer layers between HV and non-HV
   copper everywhere except at the DRV8353, LM5164 and MOSFET pins. IPC-2221B asks 0.6 mm
   (B2, uncoated external) for 51-100 V; conformal coating the power area (B4, 0.13 mm) is the
   cleaner fix if routing gets tight.
6. **CAN next to 60 V.** The Micro-Fit puts CAN H one pin from VBUS. Keep CANH/CANL routed
   as a 120 Ohm differential pair on the side away from VBUS, and keep the TCAN1044 and
   PESD2CAN close to the connector. The TCAN1044A survives +/-58 V bus faults, not 60 V; the
   PESD2CAN clamps the rest.
7. **Encoder.** Keep a 3 mm radius around U7 free of vias carrying switching current and
   keep phase and VBUS pours out of the region directly under the magnet.
8. **Buck layout.** LM5164 input caps (C5, C6) within 2 mm of VIN/GND; the SW node
   (SW12) small; the ripple-injection network (R8, C8, C9) next to FB.
9. **Screw keep-outs.** Silkscreen rings mark the 4.8 mm standoff / screw-head area at every
   mounting hole. No copper other than GND inside them (the MD80 docs warn about screw
   heads shorting to planes).

## Placement status

`tools/gen_pcb.py` places all 145 footprints: mechanically fixed parts at the MD80 coordinates,
the bridge, shunts and DC-link rows in the MD80 arrangement, and the rest packed into
functional zones with no courtyard overlap. The board is **not routed**. The placement of
the packed small parts (decoupling, dividers) is a starting point; expect to move them
toward their pins when routing.
