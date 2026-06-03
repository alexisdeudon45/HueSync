---
name: hue-latency-params
description: >-
  Benchmark whether the KIND of light change affects latency — brightness only
  vs color (xy) vs color (hue+sat) vs both. Use when the user asks if changing
  color is slower than changing brightness on Hue, whether some parameters are
  cheaper to set, or wants a per-parameter latency comparison. Runs real
  single-light PUTs and writes a self-contained HTML report. Part of the
  hue-latency-* benchmark family.
---

# Hue latency: parameter type (brightness vs color)

Times a single-light PUT for different payloads — `bri` only, `xy` color,
`hue+sat` color, and both together — to see whether color costs more than
brightness over the bridge's per-command Zigbee path.

Run it:

```
/home/tor/hue/hue-mcp/hue-mcp/.venv/bin/python scripts/bench.py
```

Writes `report.html` (+ `report.json`) to
`~/.claude/skills/hue-latency-params-workspace/`. Usual finding: all kinds land
within a small spread because the per-command overhead dominates the payload —
report the spread and the table.
