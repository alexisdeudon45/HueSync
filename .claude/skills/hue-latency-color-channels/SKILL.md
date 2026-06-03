---
name: hue-latency-color-channels
description: >-
  Benchmark whether changing all three RGB channels vs only blue vs a slight
  color tweak vs re-sending the same color (no-op) affects Hue command latency.
  Use when the user thinks in RGB channels and asks if changing only one channel
  or a tiny amount is faster/cheaper, or whether the size of the color change
  matters. Also explains that Hue has no RGB channels (color is one xy command).
  Runs real single-light PUTs and writes a self-contained HTML report. Part of
  the hue-latency-* benchmark family.
---

# Hue latency: RGB channels & change magnitude

Tests a common misconception. Hue has **no RGB channels** — the client converts
the whole RGB color to a single `xy` point and sends one command. So "change only
blue" is not a smaller operation than "change all three". This experiment times:

- **full RGB change** (all channels differ, large xy jump)
- **only blue changes** (R,G fixed — still one xy)
- **slight change** (tiny xy delta)
- **repeat / no-op** (set the exact same color again)

Run it:

```
/home/tor/hue/hue-mcp/hue-mcp/.venv/bin/python scripts/bench.py
```

Writes `report.html` (+ `report.json`) to
`~/.claude/skills/hue-latency-color-channels-workspace/`. Expected finding: all
cases land within a small spread — latency is **per-command**, not per-channel and
not proportional to how far the color moved. Report that and correct the
RGB-channel mental model.
