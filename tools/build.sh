#!/usr/bin/env bash
# Regenerate the whole KiCad project from tools/design.py and check it.
# Usage (Git Bash on Windows):  bash tools/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."
KICAD="${KICAD:-/c/Program Files/KiCad/9.0/bin}"
K="$KICAD/kicad-cli.exe"
python tools/gen_fp.py
python tools/gen_sch.py
cd hardware
"$K" sch erc -o erc.rpt better-md80.kicad_sch
"$K" sch export netlist --format kicadsexpr -o better-md80.net better-md80.kicad_sch
"$KICAD/python.exe" ../tools/gen_pcb.py
"$K" pcb drc --severity-error -o drc.rpt better-md80.kicad_pcb || true
"$K" sch export pdf -o ../docs/schematic.pdf better-md80.kicad_sch
"$K" sch export bom --fields 'Reference,Value,Footprint,MPN,${QUANTITY},${DNP},Note' \
    --labels 'Refs,Value,Footprint,MPN,Qty,DNP,Note' --group-by 'Value,Footprint,MPN,${DNP}' \
    -o ../docs/bom.csv better-md80.kicad_sch
for side in top bottom; do
  "$K" pcb render --side $side --width 1400 --height 1400 --quality basic --background opaque \
      -o ../docs/img/pcb_3d_$side.png better-md80.kicad_pcb
done
grep -E "ERC messages|violations" erc.rpt drc.rpt || true
