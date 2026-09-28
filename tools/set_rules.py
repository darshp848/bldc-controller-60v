"""Write board design rules and net classes into hardware/better-md80.kicad_pro.

KiCad keeps these in the project file, not the board, so pcbnew's Python API
changes made while the project is not loaded do not stick.
"""
import json
import os

PRO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "better-md80.kicad_pro")
HV = ["VBUS", "PH*", "SW12", "BST12", "GH*", "CPH", "CPL", "VCP", "SNUB*"]

d = json.load(open(PRO))
rules = d.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
rules.update({"min_copper_edge_clearance": 0.3, "min_text_height": 0.8, "min_text_thickness": 0.12,
              "min_hole_to_hole": 0.25, "min_through_hole_diameter": 0.2, "min_via_diameter": 0.45, "min_track_width": 0.1, "min_clearance": 0.15})
ns = d.setdefault("net_settings", {})
classes = {c["name"]: c for c in ns.get("classes", [])}
base = dict(classes.get("Default", {}))
base.update(name="Default", clearance=0.15, track_width=0.15, via_diameter=0.45, via_drill=0.2)
classes["Default"] = base
hv = dict(base, name="HV_60V", clearance=0.2, track_width=0.4, via_diameter=0.6, via_drill=0.3, priority=0)
classes["HV_60V"] = hv
ns["classes"] = list(classes.values())
ns["netclass_patterns"] = [{"netclass": "HV_60V", "pattern": p} for p in HV]
json.dump(d, open(PRO, "w"), indent=2)
print("rules written:", PRO)
