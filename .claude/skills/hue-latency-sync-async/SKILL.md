---
name: hue-latency-sync-async
description: >-
  Benchmark whether sending Hue light commands concurrently (asynchronously) is
  any faster than sending them one at a time (synchronously), across N lights.
  Use when the user asks if parallel/async requests speed up Hue control, whether
  the latency floor is a client limit or a bridge limit, or wants a sync-vs-async
  comparison for the Home lights. Runs a real experiment against the bridge and
  writes a self-contained HTML report. Part of the hue-latency-* benchmark family.
---

# Hue latency: sync vs async

Answers one question: **does firing commands in parallel beat firing them
sequentially?** If yes, the client is the bottleneck; if not, the bridge
serializes commands internally and the floor is the device.

Run it:

```
/home/tor/hue-mcp/.venv/bin/python scripts/bench.py
```

For N = 1, 3, 5, 7 lights it times an all-lights color change two ways
(sequential PUTs vs a concurrent thread pool), reports mean ms, speed-up, and
errors, and writes `report.html` (+ `report.json`) to
`~/.claude/skills/hue-latency-sync-async-workspace/`.

Interpretation: a speed-up near 1.0× means the bridge serializes Zigbee commands
(~38 ms/light) regardless of how they arrive — concurrency just queues inside the
bridge. Relay the verdict and the table; open the HTML for the chart.
