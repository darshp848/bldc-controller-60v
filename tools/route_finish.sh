#!/usr/bin/env bash
# After Freerouting: import the session, hand-route what is left, add the board-wide
# pours and stitching, clean up silkscreen, and report DRC.
# usage: bash tools/route_finish.sh <route_dir with pre.kicad_pcb + board.ses>
set -uo pipefail
cd "$(dirname "$0")/../hardware"
KICAD="${KICAD:-/c/Users/darsh/AppData/Local/Programs/KiCad/10.0/bin}"
K="$KICAD/kicad-cli.exe"; PY="$KICAD/python.exe"
RD="$1"
cp "$RD/pre.kicad_pcb" better-md80.kicad_pcb
B="$(cygpath -w "$PWD/better-md80.kicad_pcb")"
BMD_RDIR="$(cygpath -w "$PWD/$RD")" "$PY" ../tools/route_pcb.py import 2>&1 | grep -E "^ses|^vias"
for pass in 1 2 3; do
  "$K" pcb drc --severity-error -o "$RD/drc_$pass.rpt" better-md80.kicad_pcb >/dev/null
  n=$(grep -A3 "^\[unconnected_items\]" "$RD/drc_$pass.rpt" | grep "@" | grep -vc "\[GND\]")
  echo "pass $pass: $n open non-GND endpoints"
  [ "$n" = "0" ] && break
  "$PY" ../tools/hand_route.py "$B" "$(cygpath -w "$PWD/$RD/drc_$pass.rpt")" 2>&1 | grep "^('"
done
cp better-md80.kicad_pcb "$RD/hand_routed.kicad_pcb"
"$PY" ../tools/route_pcb.py final 2>&1 | grep -E "^silk|^GND|^isolated"
"$K" pcb drc --severity-all -o drc.rpt better-md80.kicad_pcb >/dev/null
"$PY" ../tools/cleanup.py "$B" "$(cygpath -w "$PWD/drc.rpt")" 2>&1 | grep removed
"$K" pcb drc --severity-all -o drc.rpt better-md80.kicad_pcb >/dev/null
grep -E "^\[" drc.rpt | sed 's/\].*/]/' | sort | uniq -c
