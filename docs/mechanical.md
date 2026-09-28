# Mechanical compatibility with MD80 v3.0

The board has to drop into the same actuators MAB sells with the MD80 (their CubeMars /
T-Motor based actuators and MA series). Every mechanical feature is taken from MAB's
`MD80_V3.0_simplified.step` (public 3D-model folder linked from the MD80 docs page).

## How the geometry was extracted

`tools/analyze_step.py` loads the STEP with CadQuery, picks the 1.6 mm PCB solid, and
dumps its top-face outline and every circular hole to `mech/md80_v3_mech.json`. From that:

- `tools/gen_pcb.py` copies the outline (lines and arcs) to Edge.Cuts unchanged.
- `tools/gen_fp.py` builds `MD80_V3_Mechanical` (holes + keep-outs) from the hole list.
- `tools/check_fit.py` compares every drilled hole on our board with every round hole in
  the STEP. Result (`mech/fit_check.txt`): **36 holes, worst position error 0.000 mm,
  all diameters equal.**

Coordinates below are STEP coordinates, origin on the rotor axis, +Y towards AUX1.

| Feature | Position (mm) | Size |
|---|---|---|
| Mounting holes (4) | (+/-15.5, +/-15.5) | 3.2 mm, M2.5 DIN912; 4.8 mm standoff keep-out both sides |
| Edge screw notches (3) | (26.56, -7.12), (-7.12, 26.57), (-19.45, -19.45) | R1.6 half-holes, 4.5 mm head keep-out |
| Micro-Fit pegs | (-26.3, +7.0), (-26.3, -7.0) | 3.0 mm (the lower one is a non-round cut-out in the STEP; modelled as 3.0 mm) |
| Micro-Fit J1 / J2 pins | x = -21.98 / -18.98, y = 4, 7, 10 and -4, -7, -10 | 1.07 mm drill, 3.0 mm pitch |
| AUX1 (PicoBlade 6) | y = 21.0, x = +3.15 ... -3.10 | 0.5 mm drill, 1.25 mm pitch, pin 1 at +x |
| AUX2 (PicoBlade 8) | x = 20.5, y = -2.60 ... +6.15 | 0.5 mm drill, pin 1 at -y |
| Phase wire holes | (-5.8, -24.8), (0, -25.0), (5.8, -24.8) | 1.9 mm drill |
| Motor thermistor pads | (15.43, -19.35), (15.43, -21.05) | 0.8 mm drill |
| Encoder IC | (0, 0), bottom side | TSSOP-14, 1.2 mm tall (MD80 part is also 1.2 mm) |

Height envelope measured from the STEP: components reach **4.0 mm above** the top copper
(excluding connectors) and **2.3 mm below** the bottom. The tallest top parts here are the
SMB TVS (2.3 mm), the 1210 capacitor (2.5 mm) and L1 (1.8 mm); the tallest bottom parts
are SOIC-8 (1.75 mm) and SOP-4 (2.1 mm). All fit inside the MD80 envelope.

## Things to verify before the first build

1. **Micro-Fit pin assignment.** MAB's diagram shows columns CAN / GND / VCC with CAN H on the
   row nearest the board, but the picture does not say which way round it is drawn. The
   board uses: edge row (x = -21.98) CAN H / GND / VBUS at y = +10 / +7 / +4, rear row
   CAN L / GND / VBUS. Check continuity against a genuine MD80 or a MAB cable before power-up;
   getting this wrong puts 60 V on CAN. The mapping is one line (`MICROFIT_PINS` in
   `tools/design.py`).
2. **AUX pin order.** Pin 1 = +5 V is assumed at the end shown on MAB's AUX photos
   (+x end for AUX1, -y end for AUX2). Same check with a MAB encoder cable.
3. **Screw notch next to AUX1.** The only remaining DRC error is J3's courtyard touching the
   screw-head keep-out of the notch at (-7.12, 26.57). The MD80 has the connector in the same
   place, so it fits in practice, but look at it with the real screw.
4. **3D models.** The Micro-Fit, phase-pad and mechanical footprints have no 3D model yet, so
   the KiCad 3D view does not show the connector bodies.
