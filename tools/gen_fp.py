"""Write the project footprint library (hardware/lib/better_md80.pretty).

All MD80-specific geometry comes from mech/md80_v3_mech.json, which
tools/analyze_step.py extracted from MAB's MD80_V3.0_simplified.step.
STEP coordinates are y-up; KiCad footprints are y-down, hence the sign flips.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "hardware", "lib", "better_md80.pretty")
MECH = json.load(open(os.path.join(HERE, "..", "mech", "md80_v3_mech.json")))


def holes(r_min, r_max):
    return [(w[0]["center"][0], w[0]["center"][1], w[0]["r"]) for w in MECH["wires"][1:]
            if len(w) == 1 and r_min <= w[0]["r"] <= r_max]


# Board-edge screw notches (half holes) of the MD80 v3.0 outline
NOTCHES = [(26.56, -7.12), (-7.12, 26.57), (-19.45, -19.45)]
PEG_ODD = (-26.3, -7.0)  # non-circular Micro-Fit peg cut-out, modelled as a 3.0 mm hole


def txt(ref_y, val_y, name, layer="F"):
    return ('\t(property "Reference" "REF**" (at 0 %.3f 0) (layer "%s.SilkS")\n'
            '\t\t(effects (font (size 1 1) (thickness 0.15))))\n'
            '\t(property "Value" "%s" (at 0 %.3f 0) (layer "%s.Fab")\n'
            '\t\t(effects (font (size 1 1) (thickness 0.15))))\n') % (ref_y, layer, name, val_y, layer)


def circle(x, y, r, layer, w=0.05):
    return '\t(fp_circle (center %.3f %.3f) (end %.3f %.3f) (stroke (width %.3f) (type solid)) (fill no) (layer "%s"))\n' % (
        x, y, x + r, y, w, layer)


def rect(x1, y1, x2, y2, layer, w=0.05):
    return '\t(fp_rect (start %.3f %.3f) (end %.3f %.3f) (stroke (width %.3f) (type solid)) (fill no) (layer "%s"))\n' % (
        x1, y1, x2, y2, w, layer)


def tht(num, x, y, size, drill):
    return '\t(pad "%s" thru_hole circle (at %.3f %.3f) (size %.3f %.3f) (drill %.3f) (layers "*.Cu" "*.Mask"))\n' % (
        num, x, y, size, size, drill)


def npth(x, y, d):
    return '\t(pad "" np_thru_hole circle (at %.3f %.3f) (size %.3f %.3f) (drill %.3f) (layers "*.Cu" "*.Mask"))\n' % (
        x, y, d, d, d)


def write(name, descr, body, attr="through_hole"):
    s = ('(footprint "%s"\n\t(version 20241229)\n\t(generator "better_md80_gen")\n\t(generator_version "9.0")\n'
         '\t(layer "F.Cu")\n\t(descr "%s")\n\t(attr %s)\n') % (name, descr, attr)
    s += body + "\t(embedded_fonts no)\n)\n"
    with open(os.path.join(OUT, name + ".kicad_mod"), "w", newline="\n") as f:
        f.write(s)


def main():
    os.makedirs(OUT, exist_ok=True)

    # Micro-Fit 3.0 2x3 right-angle, pads only (pegs live in MD80_V3_Mechanical).
    b = txt(-6.2, 6.2, "MD80_MicroFit_2x03_RA")
    for i, dy in enumerate((-3, 0, 3)):
        b += tht(str(i + 1), 0, dy, 1.9, 1.07)
        b += tht(str(i + 4), 3, dy, 1.9, 1.07)
    b += rect(-7.3, -5.2, 4.3, 5.2, "F.CrtYd") + rect(-7.0, -4.95, 1.8, 4.95, "F.Fab", 0.1)
    b += rect(-1.2, -4.3, 4.2, 4.3, "B.CrtYd")
    write("MD80_MicroFit_2x03_RA",
          "Molex Micro-Fit 3.0 43045-06xx 2x3 R/A at MD80 v3.0 pin pitch; pad 1-3 edge row, origin pad 2", b)

    b = txt(-2.6, 2.6, "MD80_Phase_Pad") + tht("1", 0, 0, 3.0, 1.9)
    b += circle(0, 0, 1.75, "F.CrtYd") + circle(0, 0, 1.75, "B.CrtYd")
    write("MD80_Phase_Pad", "Motor phase wire solder hole, 1.9 mm drill as on MD80 v3.0", b)

    b = txt(-1.8, 3.6, "MD80_NTC_Pads") + tht("1", 0, 0, 1.3, 0.8) + tht("2", 0, 1.7, 1.3, 0.8)
    b += rect(-0.9, -0.9, 0.9, 2.6, "F.CrtYd") + rect(-0.9, -0.9, 0.9, 2.6, "B.CrtYd")
    write("MD80_NTC_Pads", "Motor thermistor solder pads, 1.7 mm pitch, MD80 v3.0 position", b)

    b = txt(0, 2.0, "MD80_V3_Mechanical")
    for (x, y, r) in holes(1.55, 1.65):
        b += npth(x, -y, 2 * r)
        b += circle(x, -y, 2.4, "F.CrtYd") + circle(x, -y, 2.4, "B.CrtYd")  # 4.8 mm standoff
        b += circle(x, -y, 2.4, "F.SilkS", 0.15)
    for (x, y, r) in holes(1.45, 1.52):
        b += npth(x, -y, 2 * r) + circle(x, -y, 1.7, "B.CrtYd")
    b += npth(PEG_ODD[0], -PEG_ODD[1], 3.0) + circle(PEG_ODD[0], -PEG_ODD[1], 1.7, "B.CrtYd")
    for (x, y) in NOTCHES:
        b += circle(x, -y, 2.25, "F.CrtYd") + circle(x, -y, 2.25, "B.CrtYd")  # DIN912 M2.5 head
    write("MD80_V3_Mechanical",
          "MD80 v3.0 mounting: 4x 3.2 mm holes for M2.5 DIN912, Micro-Fit peg holes, screw keep-outs; origin = rotor axis",
          b, attr="board_only exclude_from_pos_files exclude_from_bom")
    print("footprints written to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
