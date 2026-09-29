"""Netlist-level description of the better-md80 controller.

Every part lists its pins by pin number -> net name. Pins listed in `nc` get a
no-connect flag. The schematic generator refuses unmapped pins, so this file is
the single source of truth for connectivity.
"""

NC = None

FP = dict(
    R0402="Resistor_SMD:R_0402_1005Metric",
    R0603="Resistor_SMD:R_0603_1608Metric",
    R0805="Resistor_SMD:R_0805_2012Metric",
    R1206="Resistor_SMD:R_1206_3216Metric",
    C0402="Capacitor_SMD:C_0402_1005Metric",
    C0603="Capacitor_SMD:C_0603_1608Metric",
    C0805="Capacitor_SMD:C_0805_2012Metric",
    C1206="Capacitor_SMD:C_1206_3216Metric",
    C1210="Capacitor_SMD:C_1210_3225Metric",
    LED0603="LED_SMD:LED_0603_1608Metric",
    FET="Package_TO_SOT_SMD:TDSON-8-1",
    SHUNT="Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T2.66mm",
    GH2="Connector_JST:JST_GH_SM02B-GHS-TB_1x02-1MP_P1.25mm_Horizontal",
    GH6="Connector_JST:JST_GH_SM06B-GHS-TB_1x06-1MP_P1.25mm_Horizontal",
    GH10="Connector_JST:JST_GH_SM10B-GHS-TB_1x10-1MP_P1.25mm_Horizontal",
    MICROFIT="better_md80:MD80_MicroFit_2x03_RA",
    PHASE="better_md80:MD80_Phase_Pad",
    NTC="better_md80:MD80_NTC_Pads",
    AUX1="Connector_Molex:Molex_PicoBlade_53048-0610_1x06_P1.25mm_Horizontal",
    AUX2="Connector_Molex:Molex_PicoBlade_53048-0810_1x08_P1.25mm_Horizontal",
)


class Part:
    def __init__(self, ref, lib_id, value, pins, fp=None, mpn="", nc=(), dnp=False, note=""):
        self.ref, self.lib_id, self.value = ref, lib_id, value
        self.pins = dict(pins)
        for n in nc:
            self.pins[n] = NC
        self.fp, self.mpn, self.dnp, self.note = fp, mpn, dnp, note


def R(ref, value, a, b, size="0402", mpn="", dnp=False, note=""):
    return Part(ref, "Device:R_Small", value, {"1": a, "2": b}, FP["R" + size], mpn, dnp=dnp, note=note)


def C(ref, value, a, b, size="0402", mpn="", dnp=False, note=""):
    return Part(ref, "Device:C_Small", value, {"1": a, "2": b}, FP["C" + size], mpn, dnp=dnp, note=note)


def FLAG(ref, net):
    return Part(ref, "power:PWR_FLAG", "PWR_FLAG", {"1": net})


BULK_MPN = "TDK C3216X7S2A225K160AB"

# Micro-Fit 2x3 R/A. Pads 1-3: row nearest board edge (housing bottom row),
# 4-6: rear row. Column order CAN / GND / VBUS, per MAB's connector diagram.
MICROFIT_PINS = {"1": "CANH", "2": "GND", "3": "VBUS", "4": "CANL", "5": "GND", "6": "VBUS"}

SHEETS = []


def sheet(name, title, parts):
    SHEETS.append(dict(file=name + ".kicad_sch", title=title, parts=parts))


# --------------------------------------------------------------------------- 1. power input
sheet("power_input", "Power input, protection, bulk capacitance", [
    Part("J1", "Connector_Generic:Conn_02x03_Odd_Even", "Micro-Fit 2x3",
         MICROFIT_PINS, FP["MICROFIT"], "Molex 43045-0600 (R/A, 2x3)",
         note="Power + CAN daisy-chain, MD80 position; pinout see docs/mechanical.md"),
    Part("J2", "Connector_Generic:Conn_02x03_Odd_Even", "Micro-Fit 2x3",
         MICROFIT_PINS, FP["MICROFIT"], "Molex 43045-0600 (R/A, 2x3)"),
    Part("D1", "Device:D_Zener", "5.0SMDJ60A", {"1": "VBUS", "2": "GND"}, "Diode_SMD:D_SMC",
         "Littelfuse 5.0SMDJ60A", note="5 kW TVS, VRWM 60 V, VC 96.8 V @ 51.6 A; sized by sim/bus_surge.py"),
] + [C("C%d" % (100 + k), "2.2u 100V", "VBUS", "GND", "1206", BULK_MPN,
        note="DC-link row, 12 top + 12 bottom as on MD80" if k == 0 else "") for k in range(24)] + [
    R("R1", "100k", "VBUS", "VBUS_SENSE", "0603", note="VBUS divider 20.6:1, 68 V -> 3.30 V"),
    R("R2", "5.1k", "VBUS_SENSE", "GND", "0402"),
    C("C4", "10n", "VBUS_SENSE", "GND"),
    FLAG("#FLG01", "VBUS"),
    FLAG("#FLG02", "GND"),
])

# --------------------------------------------------------------------------- 2. regulators
sheet("regulators", "Auxiliary supplies: 60V->12V->5V->3.3V", [
    Part("U1", "Regulator_Switching:LM5164DDA", "LM5164DDAR",
         {"2": "VBUS", "3": "UVLO12", "4": "RON12", "1": "GND", "9": "GND", "7": "BST12", "8": "SW12",
          "5": "FB12"}, "Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm", "TI LM5164DDAR",
         nc=["6"], note="100 V, 1 A COT sync buck; 12 V rail for gate drive"),
    C("C5", "2.2u 100V", "VBUS", "GND", "1206", BULK_MPN),
    C("C6", "100n 100V", "VBUS", "GND", "0603", "Murata GRM188R72A104KA35D"),
    R("R3", "100k", "VBUS", "UVLO12", "0603", note="UVLO on ~10.8 V"),
    R("R4", "16.2k", "UVLO12", "GND"),
    R("R5", "75k", "RON12", "GND", note="fsw = 12*2500/75k = 400 kHz"),
    C("C7", "2.2n", "BST12", "SW12", "0402"),
    Part("L1", "Device:L", "47u", {"1": "SW12", "2": "+12V"}, "Inductor_SMD:L_Bourns-SRN4018",
         "Bourns SRN4018-470M (verify Isat)"),
    R("R6", "453k", "+12V", "FB12", note="Vout = 1.2*(1+453/49.9) = 12.1 V"),
    R("R7", "49.9k", "FB12", "GND"),
    R("R8", "453k", "SW12", "RIPL12", "0603", note="Ripple injection (Type 3), per LM5164 EVM"),
    C("C8", "3.3n", "RIPL12", "+12V"),
    C("C9", "56p", "RIPL12", "FB12"),
    C("C10", "22u 25V", "+12V", "GND", "1210", "Taiyo Yuden TMK325B7226KMHT"),
    C("C11", "1u 25V", "+12V", "GND", "0603"),
    Part("U2", "Regulator_Switching:TPS62163DSG", "TPS62163DSGR",
         {"2": "+12V", "3": "+12V", "1": "GND", "4": "GND", "9": "GND", "7": "SW5", "6": "+5V", "5": "GND"},
         "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm", "TI TPS62163DSGR",
         nc=["8"], note="Fixed 5.0 V, 1 A; FB tied to GND for fixed version"),
    C("C12", "10u 25V", "+12V", "GND", "0805"),
    Part("L2", "Device:L", "2.2u", {"1": "SW5", "2": "+5V"}, "Inductor_SMD:L_1008_2520Metric",
         "Murata DFE252012F-2R2M"),
    C("C13", "22u 10V", "+5V", "GND", "0805"),
    Part("U3", "Regulator_Linear:TLV75533PDBV", "TLV75533PDBVR",
         {"1": "+5V", "3": "+5V", "2": "GND", "5": "+3V3"}, "Package_TO_SOT_SMD:SOT-23-5", "TI TLV75533PDBVR",
         nc=["4"]),
    C("C14", "1u", "+5V", "GND"),
    C("C15", "2.2u", "+3V3", "GND", "0603"),
    Part("FB1", "Device:FerriteBead_Small", "BLM18PG221", {"1": "+3V3", "2": "+3V3A"}, "Inductor_SMD:L_0603_1608Metric",
         "Murata BLM18PG221SN1D"),
    C("C16", "1u", "+3V3A", "GND"),
    C("C17", "100n", "+3V3A", "GND"),
    FLAG("#FLG03", "+12V"),
    FLAG("#FLG04", "+5V"),
    FLAG("#FLG05", "+3V3A"),
])

# --------------------------------------------------------------------------- 3. power stage
# Two-shunt current sensing (phases A and C, the same scheme as ODrive v3): with only two
# shunts both fit on the top side in the gaps between the high-side FETs, which halves the
# commutation loop (5.0 -> ~2.7 nH, sim/loop_inductance.py). Phase B's low side goes
# straight to GND and ib = -(ia + ic).
SHUNTED = "AC"
stage = []
for i, ph in enumerate("ABC"):
    n = i * 2
    ls = "LS%s" % ph if ph in SHUNTED else "GND"
    stage += [
        Part("Q%d" % (n + 1), "Transistor_FET:Q_NMOS_SSSGD_AvalancheRated", "ISC022N10NM6",
             {"4": "GH%s_G" % ph, "5": "VBUS", "1": "PH%s" % ph, "2": "PH%s" % ph, "3": "PH%s" % ph},
             FP["FET"], "Infineon ISC022N10NM6ATMA1", note="100 V, 2.2 mOhm, SuperSO8"),
        Part("Q%d" % (n + 2), "Transistor_FET:Q_NMOS_SSSGD_AvalancheRated", "ISC022N10NM6",
             {"4": "GL%s_G" % ph, "5": "PH%s" % ph, "1": ls, "2": ls, "3": ls},
             FP["FET"], "Infineon ISC022N10NM6ATMA1"),
        R("R%d" % (20 + n), "0", "GH%s" % ph, "GH%s_G" % ph, note="Gate resistor, tune for ringing"),
        R("R%d" % (21 + n), "0", "GL%s" % ph, "GL%s_G" % ph),
        C("C%d" % (22 + i * 4), "100n 100V", "VBUS", "GND", "0603", "Murata GRM188R72A104KA35D",
          note="Place across HS drain / LS source"),
        R("R%d" % (30 + i), "2.2", "PH%s" % ph, "SNUB%s" % ph, "1206", dnp=True,
          note="RC snubber; fit on first boards (sim/double_pulse.py), 0.3 W"),
        C("C%d" % (23 + i * 4), "2.2n 100V", "SNUB%s" % ph, "GND", "0603", dnp=True),
        Part("J%d" % (10 + i), "Connector_Generic:Conn_01x01", "Phase %s" % ph, {"1": "PH%s" % ph}, FP["PHASE"],
             "", note="Motor lead solder pad"),
    ]
    if ph in SHUNTED:
        stage.append(Part("RS%d" % (i + 1), "Device:R_Shunt", "0.5m",
                          {"1": "LS%s" % ph, "4": "GND", "2": "SP%s" % ph, "3": "SN%s" % ph}, FP["SHUNT"],
                          "Vishay WSK2512 0.5 mOhm 1% (verify)", note="Kelvin 4-terminal, top side between the FETs"))
stage += [
    Part("TH1", "Device:Thermistor_NTC", "10k NTC", {"1": "TEMP_FET", "2": "GND"}, "Resistor_SMD:R_0603_1608Metric",
         "Murata NCP18XH103F03RB", note="Place between phase B FETs"),
    R("R33", "10k", "+3V3A", "TEMP_FET"),
    C("C32", "100n", "TEMP_FET", "GND"),
]
sheet("power_stage", "Three-phase bridge, shunts, motor pads", stage)

# --------------------------------------------------------------------------- 4. gate driver
sheet("gate_driver", "DRV8353S gate driver and current-sense amplifiers", [
    Part("U4", "better_md80:DRV8353SRTA", "DRV8353SRTAR",
         {"3": "+12V", "4": "VBUS", "2": "CPH", "1": "CPL", "5": "VCP", "40": "VGLS", "38": "DVDD", "24": "+3V3A",
          "32": "INHA", "33": "INLA", "34": "INHB", "35": "INLB", "36": "INHC", "37": "INLC", "31": "DRV_EN",
          "30": "DRV_nCS", "29": "DRV_SCK", "28": "DRV_MOSI", "27": "DRV_MISO", "26": "DRV_nFAULT",
          "39": "GND", "25": "GND", "41": "GND",
          "6": "GHA", "7": "PHA", "8": "GLA", "9": "SPA", "10": "SNA",
          "15": "GHB", "14": "PHB", "13": "GLB", "12": "GND", "11": "GND",
          "16": "GHC", "17": "PHC", "18": "GLC", "19": "SPC", "20": "SNC",
          "23": "SOA", "22": "SOB", "21": "SOC"},
         "Package_DFN_QFN:Texas_RHA0040B_VQFN-40-1EP_6x6mm_P0.5mm_EP4.15x4.15mm", "TI DRV8353SRTAR",
         note="VM from 12 V rail so gate-drive losses do not scale with VBUS"),
    C("C40", "10u 25V", "+12V", "GND", "0805"),
    C("C41", "100n 25V", "+12V", "GND"),
    C("C42", "100n 100V", "VBUS", "GND", "0603", "Murata GRM188R72A104KA35D", note="VDRAIN local"),
    C("C43", "47n 100V", "CPH", "CPL", "0603", "Murata GRM188R72A473KA01D (verify)"),
    C("C44", "1u 25V", "VCP", "VBUS", "0603"),
    C("C45", "1u 25V", "VGLS", "GND", "0603"),
    C("C46", "1u", "DVDD", "GND"),
    C("C47", "100n", "+3V3A", "GND", note="VREF"),
    R("R40", "10k", "+3V3", "DRV_nFAULT"),
    R("R41", "10k", "+3V3", "DRV_MISO"),
    R("R42", "100k", "DRV_EN", "GND"),
    C("C48", "470p", "SOA", "GND", note="CSA output filter, at MCU pin"),
    C("C49", "470p", "SOB", "GND"),
    C("C50", "470p", "SOC", "GND"),
])

# --------------------------------------------------------------------------- 5. MCU
mcu_pins = {
    "1": "+3V3", "23": "+3V3", "35": "+3V3", "48": "+3V3", "21": "+3V3A", "20": "+3V3A", "49": "GND",
    "8": "SOA", "9": "SOB", "10": "SOC", "11": "VBUS_SENSE",
    "12": "DRV_nCS", "13": "DRV_SCK", "14": "DRV_MISO", "15": "DRV_MOSI",
    "30": "INHA", "31": "INHB", "32": "INHC", "26": "INLA", "27": "INLB", "28": "INLC",
    "33": "CAN_RX", "34": "CAN_TX", "36": "SWDIO", "37": "SWCLK", "38": "ENC_nCS",
    "17": "TEMP_FET", "18": "TEMP_MOTOR",
    "41": "SPI3_SCK", "42": "SPI3_MISO", "43": "SPI3_MOSI",
    "44": "AUX_GPIO1", "45": "AUX_GPIO2", "46": "BOOT0", "47": "AUX_nCS",
    "22": "RS422_TX", "24": "RS422_RX", "25": "CAN_TERM_EN",
    "29": "DRV_EN", "39": "DRV_nFAULT", "40": "LED_RED", "2": "LED_GREEN",
    "5": "HSE_IN", "6": "HSE_OUT", "7": "NRST",
}
sheet("mcu", "STM32G474 MCU, clock, debug, status LEDs", [
    Part("U5", "MCU_ST_STM32G4:STM32G474CEUx", "STM32G474CEU6", mcu_pins,
         "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm", "ST STM32G474CEU6",
         nc=["3", "4", "16", "19"], note="170 MHz M4F, HRTIM, FDCAN, 5x ADC"),
    C("C60", "100n", "+3V3", "GND"),
    C("C61", "100n", "+3V3", "GND"),
    C("C62", "100n", "+3V3", "GND"),
    C("C63", "100n", "+3V3", "GND", note="VBAT"),
    C("C64", "4.7u", "+3V3", "GND", "0603"),
    C("C65", "1u", "+3V3A", "GND", note="VDDA"),
    C("C66", "100n", "+3V3A", "GND", note="VREF+"),
    C("C67", "100n", "NRST", "GND"),
    R("R60", "10k", "BOOT0", "GND"),
    Part("Y1", "Device:Crystal_GND24_Small", "8MHz", {"1": "HSE_IN", "3": "HSE_OUT", "2": "GND", "4": "GND"},
         "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", "Abracon ABM8-8.000MHZ-B2-T (verify CL)",
         note="HSE for FDCAN bit timing at 8 Mbit/s"),
    C("C68", "10p", "HSE_IN", "GND"),
    C("C69", "10p", "HSE_OUT", "GND"),
    Part("J6", "Connector:Conn_ARM_SWD_TagConnect_TC2030-NL", "TC2030-NL",
         {"1": "+3V3", "5": "GND", "3": "NRST", "4": "SWCLK", "2": "SWDIO"},
         "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", "", nc=["6"]),
    R("R61", "1k", "LED_GREEN", "LED_G_A"),
    Part("D60", "Device:LED", "Green", {"1": "GND", "2": "LED_G_A"}, FP["LED0603"], "Kingbright APTD1608LZGCK"),
    R("R62", "1k", "LED_RED", "LED_R_A"),
    Part("D61", "Device:LED", "Red", {"1": "GND", "2": "LED_R_A"}, FP["LED0603"], "Kingbright APTD1608LSURCK"),
])

# --------------------------------------------------------------------------- 6. comms and sensors
sheet("comms_sensors", "CAN-FD, onboard encoder, AUX encoder ports, motor thermistor", [
    Part("U6", "Interface_CAN_LIN:TJA1051T-3", "TCAN1044AVDR",
         {"1": "CAN_TX", "4": "CAN_RX", "5": "+3V3", "8": "GND", "3": "+5V", "2": "GND", "7": "CANH", "6": "CANL"},
         "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "TI TCAN1044AVDR",
         note="8 Mbit/s CAN-FD, VIO 3.3 V; TJA1051T/3 pinout"),
    C("C70", "100n", "+5V", "GND"),
    C("C71", "100n", "+3V3", "GND"),
    Part("D70", "Device:D_TVS_Dual_AAC", "PESD2CAN", {"1": "CANH", "2": "CANL", "3": "GND"},
         "Package_TO_SOT_SMD:SOT-23", "Nexperia PESD2CAN,215"),
    Part("K1", "Relay_SolidState:CPC1017N", "CPC1017N",
         {"1": "TERM_LED", "2": "GND", "4": "CANH", "3": "TERM_MID"}, "Package_SO:SOP-4_3.8x4.1mm_P2.54mm",
         "IXYS CPC1017NTR", note="Software termination switch (60 V PhotoMOS)"),
    R("R70", "680", "CAN_TERM_EN", "TERM_LED"),
    R("R71", "120", "TERM_MID", "CANL", "0603"),
    Part("U7", "Sensor_Magnetic:AS5047D", "AS5047P-ATSM",
         {"4": "SPI3_MOSI", "3": "SPI3_MISO", "2": "SPI3_SCK", "1": "ENC_nCS", "12": "ENC_V3", "5": "GND",
          "11": "+3V3", "13": "GND"},
         "Package_SO:TSSOP-14_4.4x5mm_P0.65mm", "ams OSRAM AS5047P-ATSM",
         nc=["7", "6", "14", "10", "9", "8"],
         note="14-bit on-axis encoder, bottom side at rotation axis, same TSSOP-14 height as MD80"),
    R("R81", "0", "+3V3", "ENC_V3", note="3.3 V mode: VDD3V3 tied to VDD"),
    C("C72", "100n", "+3V3", "GND"),
    C("C73", "1u", "+3V3", "GND"),
    Part("J3", "Connector_Generic:Conn_01x06", "AUX1 SPI enc",
         {"1": "+5V", "2": "GND", "3": "AUX_nCS_C", "4": "AUX_SCK", "5": "AUX_MOSI", "6": "AUX_MISO"},
         FP["AUX1"], "Molex 53048-0650", note="MD80 AUX1 pinout"),
    R("R72", "33", "SPI3_SCK", "AUX_SCK"),
    R("R73", "33", "SPI3_MISO", "AUX_MISO"),
    R("R74", "33", "SPI3_MOSI", "AUX_MOSI"),
    R("R75", "33", "AUX_nCS", "AUX_nCS_C"),
    Part("U8", "Interface_UART:MAX3490xSA", "MAX3490EESA+",
         {"1": "+3V3", "4": "GND", "2": "RS422_RX", "3": "RS422_TX", "8": "RS422_A", "7": "RS422_B",
          "6": "RS422_Z", "5": "RS422_Y"}, "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "Analog MAX3490EESA+",
         note="Full-duplex RS-422 for AksIM-2 / Orbis"),
    C("C74", "100n", "+3V3", "GND"),
    R("R76", "120", "RS422_A", "RS422_B", "0603", note="RX termination"),
    Part("J4", "Connector_Generic:Conn_01x08", "AUX2 RS422",
         {"1": "+5V", "2": "GND", "3": "AUX_GPIO1_C", "4": "AUX_GPIO2_C", "5": "RS422_Y", "6": "RS422_Z",
          "7": "RS422_A", "8": "RS422_B"}, FP["AUX2"], "Molex 53048-0850", note="MD80 AUX2 pinout"),
    R("R77", "100", "AUX_GPIO1", "AUX_GPIO1_C"),
    R("R78", "100", "AUX_GPIO2", "AUX_GPIO2_C"),
    Part("J5", "Connector_Generic:Conn_01x02", "Motor NTC", {"1": "TEMP_MOTOR_C", "2": "GND"}, FP["NTC"],
         "", note="Solder pads for MAB motor thermistor"),
    R("R79", "10k", "+3V3A", "TEMP_MOTOR_C"),
    R("R80", "1k", "TEMP_MOTOR_C", "TEMP_MOTOR"),
    C("C75", "100n", "TEMP_MOTOR", "GND"),
    Part("MECH1", "Mechanical:MountingHole", "MD80 v3 holes", {}, "better_md80:MD80_V3_Mechanical",
         note="4x M2.5 holes + Micro-Fit peg holes at MD80 v3.0 coordinates"),
])
