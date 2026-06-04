---
name: hue-latency-decompose
description: >-
  Decompose a single Hue light command's latency into where the time actually
  goes — what percentage is the network (LAN round-trip), what percentage is the
  bridge processing it (request handling + Zigbee transmission), and what
  percentage is receiving the acknowledgement. Use when the user asks why a
  command takes ~38 ms, whether the network or the bridge is the bottleneck, or
  wants a percentage breakdown of Hue command latency. Runs curl-timed PUTs plus
  an ICMP reference and writes a self-contained HTML report. Part of the
  hue-latency-* benchmark family.
---

# Hue latency: decomposition

Breaks one `set_light` PUT into **network vs bridge vs ack** using curl's timing
counters, and compares against pure ICMP RTT so you can see how little is the LAN.

Run it:

```
/home/tor/hue-mcp/.venv/bin/python scripts/bench.py
```

Components reported (mean ms + % of total):
- **Network (TCP connect)** — one LAN round-trip to open the socket.
- **Bridge processing** — request in → bridge handles it and transmits over Zigbee
  to the bulb → first response byte. This is expected to dominate.
- **Ack / transfer** — receiving the small JSON response.

Writes `report.html` (+ `report.json`) to
`~/.claude/skills/hue-latency-decompose-workspace/`. The headline finding is
usually that the network is a few percent and the bridge is the rest — i.e. the
floor is the device's per-command Zigbee path, not your LAN.
