"""Generate the KiCad 9 project (schematics + project library) from design.py.

Connectivity is expressed with global labels placed directly on symbol pin ends,
so every net is visible by name on every sheet. Run:  python tools/gen_sch.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from sexp import Sym, dump  # noqa: E402
import libsym  # noqa: E402
import design  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hardware"))
PROJECT = "better-md80"
NS = uuid.UUID("6f1c2b1e-58a4-4d8e-9d0c-7c1d2a3b4c5d")


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


def S(x):
    return Sym(x)


def font(size=1.27, justify=None, hide=False):
    eff = [S("effects"), [S("font"), [S("size"), size, size]]]
    if justify:
        eff.append([S("justify")] + [S(j) for j in justify.split()])
    if hide:
        eff.append([S("hide"), S("yes")])
    return eff


def snap(v, g=1.27):
    return round(round(v / g) * g, 4)


# ------------------------------------------------------------------ geometry helpers

def sym_extent(pins):
    xs = [p["x"] for p in pins] or [0]
    ys = [p["y"] for p in pins] or [0]
    return min(xs), max(xs), min(ys), max(ys)


def place_parts(parts, flats):
    """Simple shelf packing. Returns {ref: (x, y)} in schematic coords (y down)."""
    pos = {}
    x0, y0 = 25.4, 30.48
    x, y, row_h = x0, y0, 0
    maxw = 380
    for p in parts:
        pins = libsym.pins_of(flats[p.lib_id])
        l, r, b, t = sym_extent(pins)
        lab = max([len(n or "") for n in p.pins.values()] + [0]) * 1.1 + 4
        left = (-l + (lab if any(pp["rot"] == 0 for pp in pins) else 3))
        right = (r + (lab if any(pp["rot"] == 180 for pp in pins) else 3))
        top = t + (lab if any(pp["rot"] == 270 for pp in pins) else 4)
        bot = -b + (lab if any(pp["rot"] == 90 for pp in pins) else 4)
        w = max(left + right + 5, 20.32)
        h = top + bot + 10
        if x + w > maxw and x > x0:
            x, y, row_h = x0, y + row_h, 0
        pos[p.ref] = (snap(x + left), snap(y + top))
        x += w
        row_h = max(row_h, h)
    return pos, y + row_h


def paper_for(height):
    if height < 270:
        return "A3", 420, 297
    if height < 400:
        return "A2", 594, 420
    return "A1", 841, 594


# ------------------------------------------------------------------ sheet writer

def lib_symbols(flats, ids):
    return [S("lib_symbols")] + [flats[i] for i in sorted(ids)]


def symbol_instance(p, flat, x, y, sheet_path):
    props = libsym.props_of(flat)
    inst = [S("symbol"), [S("lib_id"), p.lib_id], [S("at"), x, y, 0], [S("unit"), 1],
            [S("exclude_from_sim"), S("no")], [S("in_bom"), S("no") if p.ref.startswith("#") else S("yes")],
            [S("on_board"), S("no") if p.ref.startswith("#") else S("yes")],
            [S("dnp"), S("yes") if p.dnp else S("no")], [S("uuid"), uid("sym", p.ref)]]
    values = {"Reference": p.ref, "Value": p.value, "Footprint": p.fp or "",
              "Datasheet": props["Datasheet"][2] if "Datasheet" in props else "",
              "Description": props["Description"][2] if "Description" in props else ""}
    for key in ("Reference", "Value", "Footprint", "Datasheet", "Description"):
        src = props.get(key)
        at = src and [a for a in src if isinstance(a, list) and a[0] == "at"]
        px, py = (float(at[0][1]), float(at[0][2])) if at else (0.0, 0.0)
        hide = key not in ("Reference", "Value") or p.ref.startswith("#")
        if key == "Value" and p.ref.startswith("#FLG"):
            hide = True
        inst.append([S("property"), key, values[key], [S("at"), snap(x + px, 0.01), snap(y - py, 0.01), 0],
                     font(justify=None, hide=hide)])
    for key, val in (("MPN", p.mpn), ("Note", p.note)):
        if val:
            inst.append([S("property"), key, val, [S("at"), x, y, 0], font(hide=True)])
    for pin in libsym.pins_of(flat):
        inst.append([S("pin"), pin["num"], [S("uuid"), uid("pin", p.ref, pin["num"])]])
    inst.append([S("instances"), [S("project"), PROJECT,
                                   [S("path"), sheet_path, [S("reference"), p.ref], [S("unit"), 1]]]])
    return inst


def label(net, x, y, angle, key):
    just = {0: "left", 180: "right", 90: "left", 270: "right"}[angle]
    return [S("global_label"), net, [S("shape"), S("passive")], [S("at"), x, y, angle],
            [S("fields_autoplaced"), S("yes")], font(justify=just), [S("uuid"), uid("lbl", key)],
            [S("property"), "Intersheetrefs", "${INTERSHEET_REFS}", [S("at"), x, y, 0],
             font(size=1.27, justify=just, hide=True)]]


def write_sheet(sh, root_uuid, sheet_uuid, page_no, flats):
    parts = sh["parts"]
    pos, height = place_parts(parts, flats)
    paper, pw, ph = paper_for(height)
    items = []
    used = set()
    path = "/%s/%s" % (root_uuid, sheet_uuid)
    for p in parts:
        flat = flats[p.lib_id]
        used.add(p.lib_id)
        x, y = pos[p.ref]
        items.append(symbol_instance(p, flat, x, y, path))
        pins = libsym.pins_of(flat)
        nums = {pin["num"] for pin in pins}
        unknown = set(p.pins) - nums
        if unknown:
            raise SystemExit("%s: unknown pins %s" % (p.ref, sorted(unknown)))
        for pin in pins:
            if pin["num"] not in p.pins:
                raise SystemExit("%s pin %s (%s) is not mapped" % (p.ref, pin["num"], pin["name"]))
            net = p.pins[pin["num"]]
            ex, ey = snap(x + pin["x"], 0.01), snap(y - pin["y"], 0.01)
            if net is None:
                items.append([S("no_connect"), [S("at"), ex, ey], [S("uuid"), uid("nc", p.ref, pin["num"])]])
            else:
                items.append(label(net, ex, ey, (pin["rot"] + 180) % 360, p.ref + "." + pin["num"]))
    doc = [S("kicad_sch"), [S("version"), 20250114], [S("generator"), "eeschema"],
           [S("generator_version"), "9.0"], [S("uuid"), sheet_uuid], [S("paper"), paper],
           [S("title_block"), [S("title"), sh["title"]], [S("date"), "2026-09-28"], [S("rev"), "A"],
            [S("company"), "better-md80"],
            [S("comment"), 1, "48 V nominal / 60 V max MD80-compatible BLDC controller"],
            [S("comment"), 2, "Generated by tools/gen_sch.py from tools/design.py - edit design.py, not this file"]],
           lib_symbols(flats, used)] + items + [[S("embedded_fonts"), S("no")]]
    with open(os.path.join(ROOT, sh["file"]), "w", encoding="utf8", newline="\n") as f:
        f.write(dump(doc) + "\n")
    return paper


def write_root(root_uuid, sheets):
    items = []
    x, y = 30.48, 40.64
    for i, sh in enumerate(sheets):
        su = uid("sheet", sh["file"])
        w, h = 60.96, 20.32
        items.append([S("sheet"), [S("at"), x, y], [S("size"), w, h], [S("exclude_from_sim"), S("no")],
                      [S("in_bom"), S("yes")], [S("on_board"), S("yes")], [S("dnp"), S("no")],
                      [S("fields_autoplaced"), S("yes")],
                      [S("stroke"), [S("width"), 0.1524], [S("type"), S("solid")]],
                      [S("fill"), [S("color"), 0, 0, 0, 0.0]], [S("uuid"), su],
                      [S("property"), "Sheetname", sh["title"], [S("at"), x, y - 0.7116, 0],
                       font(justify="left bottom")],
                      [S("property"), "Sheetfile", sh["file"], [S("at"), x, y + h + 0.5884, 0],
                       font(justify="left top")],
                      [S("instances"), [S("project"), PROJECT, [S("path"), "/" + root_uuid, [S("page"), str(i + 2)]]]]])
        x += 76.2
        if x > 300:
            x, y = 30.48, y + 40.64
    notes = [
        "better-md80: MD80 v3.0 form-factor BLDC controller for 48 V nominal / 60 V max buses.",
        "Voltage-limiting parts of the original (gate driver, bus caps, regulators, TVS) replaced with 100 V-class parts.",
        "Connectivity uses global labels: every net name is identical on every sheet.",
        "See ../docs/ for architecture, BOM, thermal/layout and firmware notes.",
    ]
    for k, t in enumerate(notes):
        items.append([S("text"), t, [S("exclude_from_sim"), S("no")], [S("at"), 30.48, 160 + k * 6, 0],
                      font(size=2.0, justify="left"), [S("uuid"), uid("note", str(k))]])
    doc = [S("kicad_sch"), [S("version"), 20250114], [S("generator"), "eeschema"],
           [S("generator_version"), "9.0"], [S("uuid"), root_uuid], [S("paper"), "A4"],
           [S("title_block"), [S("title"), "better-md80 - 60 V MD80-compatible motor controller"],
            [S("date"), "2026-09-28"], [S("rev"), "A"], [S("company"), "better-md80"]],
           [S("lib_symbols")]] + items + [
        [S("sheet_instances"), [S("path"), "/", [S("page"), "1"]]], [S("embedded_fonts"), S("no")]]
    with open(os.path.join(ROOT, PROJECT + ".kicad_sch"), "w", encoding="utf8", newline="\n") as f:
        f.write(dump(doc) + "\n")


def write_project_files():
    with open(os.path.join(ROOT, "sym-lib-table"), "w", newline="\n") as f:
        f.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "better_md80")(type "KiCad")'
                '(uri "${KIPRJMOD}/lib/better_md80.kicad_sym")(options "")(descr "better-md80 project symbols"))\n)\n')
    with open(os.path.join(ROOT, "fp-lib-table"), "w", newline="\n") as f:
        f.write('(fp_lib_table\n\t(version 7)\n\t(lib (name "better_md80")(type "KiCad")'
                '(uri "${KIPRJMOD}/lib/better_md80.pretty")(options "")(descr "MD80 mechanical footprints"))\n)\n')
    pro = os.path.join(ROOT, PROJECT + ".kicad_pro")
    if not os.path.exists(pro):
        import json
        json.dump({"meta": {"filename": PROJECT + ".kicad_pro", "version": 3},
                   "board": {"design_settings": {"defaults": {}, "rules": {}}},
                   "sheets": [], "text_variables": {}}, open(pro, "w"), indent=2)


def main():
    os.makedirs(os.path.join(ROOT, "lib"), exist_ok=True)
    with open(libsym.PROJECT_LIB, "w", encoding="utf8", newline="\n") as f:
        f.write(dump(libsym.custom_library()) + "\n")
    libsym._trees.pop("better_md80", None)
    flats = {}
    for sh in design.SHEETS:
        for p in sh["parts"]:
            if p.lib_id not in flats:
                lib, name = p.lib_id.split(":")
                flats[p.lib_id] = libsym.flat_symbol(lib, name)
    root_uuid = uid("root")
    for i, sh in enumerate(design.SHEETS):
        paper = write_sheet(sh, root_uuid, uid("sheet", sh["file"]), i + 2, flats)
        print("wrote", sh["file"], paper, len(sh["parts"]), "parts")
    write_root(root_uuid, design.SHEETS)
    write_project_files()


if __name__ == "__main__":
    main()
