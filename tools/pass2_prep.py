"""Layout pass 2 preparation on the routed board.

  - strip the board-wide pours and DRC rule areas (they are re-added by route_pcb.py final)
  - rip the crystal nets and the copper around D1
  - swap D1 to the SMC footprint for the 5.0SMDJ60A
usage (KiCad Python): pass2_prep.py board.kicad_pcb
"""
import os
import sys

import pcbnew

GENERAL = {"GND top", "GND bottom", "GND In2 fill", "GND In3 fill", "GND In4 fill", "VBUS plane"}
STOCK = "C:/Users/darsh/AppData/Local/Programs/KiCad/10.0/share/kicad/footprints/"


def main():
    path = sys.argv[1]
    board = pcbnew.LoadBoard(path)
    tracks = list(board.GetTracks())
    zones = list(board.Zones())
    fps = list(board.GetFootprints())
    gone = []
    for z in zones:
        if z.GetZoneName() in GENERAL or z.GetZoneName().startswith("FINEPITCH_"):
            gone.append(z)
    d1 = [f for f in fps if f.GetReference() == "D1"][0]
    c = d1.GetPosition()
    rip = []
    for t in tracks:
        if t.GetNetname() in ("HSE_IN", "HSE_OUT"):
            rip.append(t)
        elif t.GetNetname() in ("VBUS", "GND") and t.Type() != pcbnew.PCB_VIA_T:
            for p in (t.GetStart(), t.GetEnd()):
                if (p - c).EuclideanNorm() < pcbnew.FromMM(4.5):
                    rip.append(t)
                    break
    for item in gone + rip:
        board.Remove(item)
    # swap D1 footprint, keep reference, value, path, nets and position
    new = pcbnew.FootprintLoad(STOCK + "Diode_SMD.pretty", "D_SMC")
    new.SetFPID(pcbnew.LIB_ID("Diode_SMD", "D_SMC"))
    new.SetReference("D1")
    new.SetValue("5.0SMDJ60A")
    new.SetPath(d1.GetPath())
    nets = {p.GetNumber(): p.GetNet() for p in d1.Pads()}
    for p in new.Pads():
        if p.GetNumber() in nets:
            p.SetNet(nets[p.GetNumber()])
    new.SetPosition(d1.GetPosition())
    new.SetOrientation(d1.GetOrientation())
    board.Remove(d1)
    board.Add(new)
    board.Save(path)
    print("removed %d zones/rule areas, ripped %d tracks, D1 -> D_SMC" % (len(gone), len(rip)))


if __name__ == "__main__":
    main()
