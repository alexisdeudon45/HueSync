---
name: hue-latency-principal
description: >-
  Benchmark whether WHICH light is chosen as the principal/master affects command
  latency — per-light timing across all Home lights, grouped by type (Hue Play vs
  color lamp). Use when the user asks if some Hue lights respond slower than
  others, whether the random principal choice has a latency cost, or wants a
  per-light latency comparison. Runs real single-light PUTs and writes a
  self-contained HTML report. Part of the hue-latency-* benchmark family.
---

# Hue latency: does the principal choice matter?

Times a single-light color change for **each Home light individually** to see
whether some lights are slower to command and whether picking a particular
principal has a latency cost.

Run it:

```
/home/tor/hue/hue-mcp/hue-mcp/.venv/bin/python scripts/bench.py
```

Writes `report.html` (+ `report.json`) to
`~/.claude/skills/hue-latency-principal-workspace/`. Usual finding: latency is
roughly uniform across lights (small spread), so the random principal in
`hue-principal-sync` carries no latency penalty — report the spread and per-type
means.
