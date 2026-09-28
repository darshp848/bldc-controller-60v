# Re-running the layout flow

Only needed if the placement is regenerated (`REGEN_PCB=1 bash tools/build.sh`), which
discards all routing. Normal edits should be made in KiCad directly.

Tools: KiCad 10 (per-user install), Freerouting 2.4.1 (`C:/Users/darsh/tools/freerouting-2.4.1.jar`)
and the JRE 25 next to it. Commands assume Git Bash in the repo root.

```bash
K=/c/Users/darsh/AppData/Local/Programs/KiCad/10.0/bin
cd hardware
# 1. local power pours, power vias, QFN fan-out, Specctra export -> route/board.dsn
"$K/python.exe" ../tools/route_pcb.py pours
cp better-md80.kicad_pcb route/pre.kicad_pcb
# 2. keep the In1 GND plane free of signals
sed -i '/(layer In1.Cu/{n;s/(type signal)/(type power)/}' route/board.dsn
# 3. autoroute
/c/Users/darsh/tools/jdk-25.0.4.1+1-jre/bin/java.exe -jar /c/Users/darsh/tools/freerouting-2.4.1.jar \
    -de route/board.dsn -do route/board.ses -mp 8 -mt 16 --gui.enabled=false
cd ..
# 4. import, hand-route leftovers, board-wide pours + stitching, silkscreen, DRC
bash tools/route_finish.sh route
```

Lessons that shaped this flow:

- KiCad's Specctra export turns DRC rule areas into keep-outs, so rule areas are added
  after routing (`route_pcb.py final`).
- Board-wide pours exported as planes block the router on their layer; only local
  power-stage pours go in before routing.
- Freerouting routes on In1 unless the DSN marks it `(type power)`.
- In KiCad 10's Python, `board.GetTracks()` / `board.Zones()` must be read before any
  `board.Remove()`; calling them afterwards crashes or returns an unusable object.
