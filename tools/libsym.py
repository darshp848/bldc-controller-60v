"""Load, flatten and build KiCad schematic symbols."""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sexp import Sym, parse, find, find1  # noqa: E402

STOCK = r"C:/Users/darsh/AppData/Local/Programs/KiCad/10.0/share/kicad/symbols/"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_LIB = os.path.join(HERE, "..", "hardware", "lib", "better_md80.kicad_sym")

_trees = {}


def _tree(lib):
    if lib not in _trees:
        if lib == "better_md80":
            path = PROJECT_LIB
        else:
            path = STOCK + lib + ".kicad_sym"
        _trees[lib] = parse(open(path, encoding="utf8").read())
    return _trees[lib]


def _raw(lib, name):
    for s in find(_tree(lib), "symbol"):
        if s[1] == name:
            return s
    raise KeyError("%s:%s" % (lib, name))


def flat_symbol(lib, name):
    """Return the symbol as it must appear in a schematic's lib_symbols block."""
    s = copy.deepcopy(_raw(lib, name))
    ext = find1(s, "extends")
    if ext:
        parent = flat_symbol(lib, ext[1])
        pname = ext[1]
        out = [Sym("symbol"), "%s:%s" % (lib, name)]
        child_props = {p[1]: p for p in find(s, "property")}
        for item in parent[2:]:
            if isinstance(item, list) and item and item[0] == "property" and item[1] in child_props:
                out.append(child_props.pop(item[1]))
            elif isinstance(item, list) and item and item[0] == "symbol":
                sub = copy.deepcopy(item)
                sub[1] = sub[1].replace(pname, name, 1)
                out.append(sub)
            else:
                out.append(item)
        # properties the child adds that the parent lacks
        idx = max(i for i, x in enumerate(out) if isinstance(x, list) and x and x[0] == "property") + 1
        for p in child_props.values():
            out.insert(idx, p)
            idx += 1
        return out
    s[1] = "%s:%s" % (lib, name)
    return s


def pins_of(flat):
    pins = []
    for unit in find(flat, "symbol"):
        for p in find(unit, "pin"):
            at = find1(p, "at")
            pins.append(dict(type=str(p[1]), name=find1(p, "name")[1], num=find1(p, "number")[1],
                             x=float(at[1]), y=float(at[2]), rot=int(float(at[3])) if len(at) > 3 else 0))
    return pins


def props_of(flat):
    return {p[1]: p for p in find(flat, "property")}


# ---------------------------------------------------------------- custom symbols

def _font():
    return [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]


def _prop(key, val, x, y, hide=False, justify=None):
    eff = _font()
    if justify:
        eff.append([Sym("justify"), Sym(justify)])
    if hide:
        eff.append([Sym("hide"), Sym("yes")])
    return [Sym("property"), key, val, [Sym("at"), x, y, 0], eff]


def _pin(ptype, x, y, rot, name, num, length=2.54):
    return [Sym("pin"), Sym(ptype), Sym("line"), [Sym("at"), x, y, rot], [Sym("length"), length],
            [Sym("name"), name, _font()], [Sym("number"), num, _font()]]


def make_ic(name, left, right, ref="U", value=None, footprint="", datasheet="", description="", width=30.48):
    """left/right: lists of (num, name, type) or None for a gap, top to bottom."""
    rows = max(len(left), len(right))
    h = (rows + 1) * 2.54
    top = round(h / 2 / 2.54) * 2.54
    w2 = width / 2
    body = [Sym("symbol"), name + "_0_1",
            [Sym("rectangle"), [Sym("start"), -w2, top], [Sym("end"), w2, top - h],
             [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]],
             [Sym("fill"), [Sym("type"), Sym("background")]]]]
    pins = [Sym("symbol"), name + "_1_1"]
    for side, lst in ((-1, left), (1, right)):
        y = top - 2.54
        for item in lst:
            if item:
                num, pname, ptype = item
                x = side * (w2 + 2.54)
                pins.append(_pin(ptype, x, y, 0 if side < 0 else 180, pname, num))
            y -= 2.54
    return [Sym("symbol"), name,
            [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            _prop("Reference", ref, -w2, top + 1.27, justify="left"),
            _prop("Value", value or name, w2, top + 1.27, justify="right"),
            _prop("Footprint", footprint, 0, top - h - 2.54, hide=True),
            _prop("Datasheet", datasheet, 0, top - h - 5.08, hide=True),
            _prop("Description", description, 0, top - h - 7.62, hide=True),
            body, pins, [Sym("embedded_fonts"), Sym("no")]]


def custom_library():
    drv = make_ic(
        "DRV8353SRTA",
        left=[("3", "VM", "power_in"), ("4", "VDRAIN", "power_in"), ("2", "CPH", "passive"), ("1", "CPL", "passive"),
              ("5", "VCP", "passive"), ("40", "VGLS", "passive"), ("38", "DVDD", "passive"), ("24", "VREF", "power_in"),
              None,
              ("32", "INHA", "input"), ("33", "INLA", "input"), ("34", "INHB", "input"), ("35", "INLB", "input"),
              ("36", "INHC", "input"), ("37", "INLC", "input"), ("31", "ENABLE", "input"), None,
              ("30", "~{SCS}", "input"), ("29", "SCLK", "input"), ("28", "SDI", "input"), ("27", "SDO", "open_collector"),
              ("26", "~{FAULT}", "open_collector"), None,
              ("39", "GND", "power_in"), ("25", "AGND", "power_in"), ("41", "PAD", "power_in")],
        right=[("6", "GHA", "output"), ("7", "SHA", "input"), ("8", "GLA", "output"), ("9", "SPA", "input"),
               ("10", "SNA", "input"), None,
               ("15", "GHB", "output"), ("14", "SHB", "input"), ("13", "GLB", "output"), ("12", "SPB", "input"),
               ("11", "SNB", "input"), None,
               ("16", "GHC", "output"), ("17", "SHC", "input"), ("18", "GLC", "output"), ("19", "SPC", "input"),
               ("20", "SNC", "input"), None,
               ("23", "SOA", "output"), ("22", "SOB", "output"), ("21", "SOC", "output")],
        value="DRV8353SRTAR",
        footprint="Package_DFN_QFN:Texas_RHA0040B_VQFN-40-1EP_6x6mm_P0.5mm_EP4.15x4.15mm",
        datasheet="https://www.ti.com/lit/ds/symlink/drv8353.pdf",
        description="100V three-phase smart gate driver, 3 CSAs, SPI, WQFN-40 6x6 (RTA)")
    return [Sym("kicad_symbol_lib"), [Sym("version"), 20241209], [Sym("generator"), "better_md80_gen"],
            [Sym("generator_version"), "9.0"], drv]
