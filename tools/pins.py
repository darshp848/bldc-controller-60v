"""Print pin number/name/position of a stock KiCad symbol: pins.py Lib Name"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sexp import parse, find, find1

LIBDIR = r"C:/Program Files/KiCad/9.0/share/kicad/symbols/"
_cache = {}


def load_lib(lib):
    if lib not in _cache:
        path = lib if os.path.isabs(lib) else LIBDIR + lib + ".kicad_sym"
        _cache[lib] = parse(open(path, encoding="utf8").read())
    return _cache[lib]


def get_symbol(lib, name):
    tree = load_lib(lib)
    for s in find(tree, "symbol"):
        if s[1] == name:
            return s
    raise KeyError(name)


def symbol_pins(sym):
    pins = []
    for unit in find(sym, "symbol"):
        for p in find(unit, "pin"):
            at = find1(p, "at")
            name = find1(p, "name")[1]
            num = find1(p, "number")[1]
            pins.append(dict(type=str(p[1]), name=name, num=num, x=float(at[1]), y=float(at[2]), rot=float(at[3]) if len(at) > 3 else 0.0))
    return pins


if __name__ == "__main__":
    s = get_symbol(sys.argv[1], sys.argv[2])
    ext = find1(s, "extends")
    if ext:
        print("extends", ext[1]); s = get_symbol(sys.argv[1], ext[1])
    for p in symbol_pins(s):
        print(p["num"], p["name"], p["type"], p["x"], p["y"], p["rot"])
