# Architecture and component selection

A drop-in replacement for the MAB Robotics MD80 v3.0 BLDC controller that runs from a
**48 V nominal bus (60 V maximum)** while keeping the MD80's board outline, mounting,
connectors, encoder position and its **20 A continuous / 80 A peak** phase current.

## Target specification

| Parameter | MD80 v3.0 | MD80 v3.0 60 V (MAB) | This design |
|---|---|---|---|
| Nominal input | 24-42 V | 48 V | 48 V (12S-13S Li-ion) |
| Operating range | 10-48 V | 12-60 V | 12-60 V |
| Transient withstand | not published | not published | 100 V parts, TVS clamps at 96.8 V @ 6.2 A |
| Continuous phase current (no cooling) | 20 A | 12 A | 20 A (see thermal notes) |
| Peak phase current (2 s) | 80 A | 40 A | 80 A |
| Max input current (connector) | 10 A RMS | 10 A RMS | 10 A RMS (same connector) |
| Outline / holes / connectors | 55 mm, 7 holes | same | identical, checked to 0.000 mm against MAB's STEP |
| Encoder | 14-bit on-axis | same | AS5047P, 14-bit, same TSSOP-14 height |
| Bus | CAN-FD 1/2/5/8 Mbit/s | same | CAN-FD up to 8 Mbit/s, switchable 120 Ohm termination |
| Aux ports | AUX1 SPI, AUX2 RS-422 + 2 GPIO, 5 V 150 mA | same | same pinout and connectors |

Sources: MAB documentation pages for [MD80](https://mabrobotics.github.io/MD80-x-CANdle-Documentation/MD/MD80.html)
and [MD80 60V](https://mabrobotics.github.io/MD80-x-CANdle-Documentation/MD/MD80HV.html), and MAB's
`MD80_V3.0_simplified.step` from their public 3D-model folder.

MAB's own 60 V variant already exists, but it halves the current rating. Keeping 80 A peak
at 60 V in the same 55 mm board is the actual engineering goal of this design.

## What limits the original to 48 V

MAB does not publish MD80 schematics, so this list is inferred from the published ratings,
photos and the STEP model rather than read from a schematic:

1. **Gate driver / pre-driver supply.** 48 V max with 24-42 V nominal matches the 60-65 V class
   of integrated three-phase drivers (e.g. the DRV832x family, 60 V abs max). Regen pumping
   the bus above ~50 V is what that margin protects.
2. **DC-link capacitors.** The MD80 uses a row of 1206 MLCCs top and bottom. At 42 V these are
   50 V parts; they are the cheapest place a 48 V limit comes from.
3. **Auxiliary buck regulator** feeding 5 V / 3.3 V, typically a 60 V-class part.
4. **MOSFETs.** The 60 V MAB variant keeps the footprint but drops to 40 A peak, which is the
   signature of moving to 100 V MOSFETs with higher R_DS(on) in the same package.

## What this design changes

| Function | Part used here | Rating | Why |
|---|---|---|---|
| Gate driver + CSA | TI **DRV8353SRTAR** (WQFN-40 6x6) | VDRAIN 100 V (102 V abs), VM 9-75 V | 100 V class, SPI-programmable IDRIVE, 3 low-side CSAs (gain 5/10/20/40), VDS and VGS monitoring |
| MOSFETs (x6) | Infineon **ISC022N10NM6ATMA1** (SuperSO8 5x6) | 100 V, 2.24 mOhm max @ 10 V | Lowest R_DS(on) 100 V part in the MD80's 5x6 footprint; this is what keeps 80 A peak |
| Shunts (x2, phases A and C) | 0.5 mOhm 2512 Kelvin (Vishay WSK2512), top side between the FETs | 3 W class | 10 mV/A; with CSA gain 20 gives +/-140 A range, 80 mA/LSB at 12 bit. Two-shunt sensing keeps the commutation loop at about 3 nH (docs/simulation.md) |
| DC-link | 24x **TDK C3216X7S2A225K160AB** 2.2 uF 100 V X7S 1206 | 100 V | Same 1206 rows as MD80 (12 top + 12 bottom), 53 uF nominal, ~20 uF at 48 V bias |
| Input TVS | Littelfuse **5.0SMDJ60A** (SMC) | VRWM 60 V, VC 96.8 V at 51.6 A | Holds a 60 V hot-plug through a 2 m cable below 100 V (the SMBJ60A reached 106 V in simulation) |
| 60 V -> 12 V | TI **LM5164DDAR** | 6-100 V in, 1 A | Feeds gate drive (DRV8353 VM) and the 5 V buck |
| 12 V -> 5 V | TI **TPS62163DSGR** | 3-17 V in, 1 A, fixed 5 V | CAN transceiver, AUX 5 V (150 mA), LDO input |
| 5 V -> 3.3 V | TI **TLV75533PDBVR** | 500 mA LDO | MCU, encoder, RS-422; ferrite-filtered +3V3A for analog/VREF |
| MCU | ST **STM32G474CEU6** (QFN-48) | 170 MHz M4F | TIM1 complementary PWM, 5 ADCs, 3 FDCAN, CORDIC/FMAC for FOC |
| CAN-FD | TI **TCAN1044AVDR** + Nexperia PESD2CAN | 8 Mbit/s, VIO 3.3 V, +/-58 V bus fault | Bus-fault rating matters now that the power pins carry 60 V next to CAN |
| Termination | IXYS **CPC1017N** PhotoMOS + 120 Ohm | 60 V | Software-switched termination like the MD80 |
| Encoder | ams **AS5047P-ATSM** (TSSOP-14) | 14 bit | Same package height as the MD80 encoder, so the 1 mm magnet gap is unchanged |
| RS-422 | **MAX3490EESA+** | 3.3 V full duplex | AUX2 for RLS AksIM-2 / Orbis |

### Why the gate driver runs from 12 V instead of the bus

DRV835x allows VM (gate-drive supply) to be separate from VDRAIN. Feeding VM from the 12 V
rail means the charge pump and low-side regulator dissipate `I_gate x 12 V` instead of
`I_gate x 60 V`. With six ~70 nC gates at 40 kHz plus ~9 mA quiescent, that is roughly
0.3 W instead of ~1.5 W inside a 6x6 QFN at 60 V. The cost is one 100 V buck (LM5164),
which is needed anyway for the logic rails.

## Power tree

```
VBUS 12-60 V --+-- 6x ISC022N10NM6 half-bridges -- motor
               +-- DRV8353 VDRAIN (HS drain sense + charge-pump reference)
               +-- 5.0SMDJ60A, 24x 2.2 uF/100 V, 100k/5.1k VBUS sense
               +-- LM5164 (400 kHz, UVLO ~10.8 V) --> +12V
                        +-- DRV8353 VM (gate drive)
                        +-- TPS62163 --> +5V --+-- TCAN1044 VCC, AUX1/AUX2 5 V out
                                               +-- TLV75533 --> +3V3 --+-- MCU, AS5047P, MAX3490, CAN VIO
                                                                        +-- ferrite --> +3V3A (VDDA, VREF+, DRV VREF, NTC bias)
```

## Schematic organisation

`hardware/better-md80.kicad_sch` is a hierarchical root with six sheets:

1. `power_input` - Micro-Fit connectors, TVS, DC-link rows, VBUS sense
2. `regulators` - LM5164, TPS62163, TLV75533, analog filter
3. `power_stage` - bridge, gate resistors (0 Ohm placeholders), Kelvin shunts, DNP RC snubbers, MOSFET NTC, phase pads
4. `gate_driver` - DRV8353S and its charge-pump/regulator capacitors, CSA output filters
5. `mcu` - STM32G474, 8 MHz HSE, Tag-Connect SWD, status LEDs
6. `comms_sensors` - CAN-FD, switchable termination, AS5047P, AUX1/AUX2, motor thermistor

Nets are connected with global labels on every pin, so a net has the same name on every
sheet. The schematic is generated from `tools/design.py`; edit that file and run
`bash tools/build.sh` rather than hand-editing the `.kicad_sch` files, or switch to editing
in KiCad and stop using the generator. Pick one; mixing them loses edits.

## BOM

`docs/bom.csv` is exported from the schematic (grouped, with MPN and notes, DNP marked).
Parts without an MPN are generic passives: use X7R/X7S, and at least 16 V for anything on
3.3 V/5 V nets, 25 V on the 12 V rail, 100 V on VBUS/phase nets (those already carry an MPN).
Items marked "verify" in the MPN column were chosen from memory of the product line and
have not been checked against a distributor listing yet:

- Vishay WSK2512 at 0.5 mOhm (if unavailable, a 0.5 mOhm 2512 Kelvin shunt from another series needs a footprint change)
- Bourns SRN4018-470M saturation current (needs >= 0.8 A; the 12 V rail draws ~0.25 A)
- Murata GRM188R72A473KA01D (47 nF 100 V 0603 charge-pump capacitor)
- Abracon ABM8-8.000MHZ-B2-T load capacitance vs the 10 pF load caps
