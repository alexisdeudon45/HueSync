---
name: hue-screen-sync
description: >-
  Ambilight: capture this computer's screen(s) and stream their colors to the Home
  Entertainment Hue lights in real time, so the lamps match what's on the monitors.
  Use when the user wants screen sync / ambilight / bias lighting / "lights match my
  screen / game / movie", or to mirror the PC display colors onto the Hue lights.
  Trigger on "screen sync", "ambilight", "bias lighting", "make the lights match my
  screen/game/video", "sync lights to my monitor", "ambiance écran". Runs on the
  live X11 session (XFCE), captures with mss, streams ~15-20 fps over the
  Entertainment API.
---

# Hue screen sync (ambilight)

Mirrors the colors on your monitors onto the lights: it captures the X11 desktop,
splits the screen **width into one zone per light channel** (left → right),
averages each zone, boosts saturation a little, smooths over time, and streams the
result to the Home Entertainment area.

## Run it
```
DISPLAY=:1.0 /home/tor/hue/hue-mcp/hue-mcp/.venv/bin/python scripts/screensync.py [opts]
```
(`DISPLAY=:1.0` is this machine's XFCE session — needed only if running detached.)

Options:
- `--monitor` — `0` = all screens combined (default; spans DP-1 + HDMI-1), or `1`/`2`
  for a single monitor (use `mss` monitor indices).
- `--sat` (default 1.6) — saturation boost so the wall isn't washed out.
- `--gamma` (default 0.8, `<1` brightens dim scenes).
- `--smooth` (0..1, default 0.5) — temporal EMA to kill jitter.
- `--fps` (default 18; it's capture-bound, ~14-20 fps for the full 3840×1080).
- `--step` — pixel subsample stride (bigger = faster, coarser).
- `--duration`.

## How it maps
The 7 entertainment channels get the 7 left-to-right screen zones in order. On this
dual-monitor desktop, the left lights follow DP-1 and the right lights follow HDMI-1.
To make it physically accurate, arrange the lights' positions in the Hue app to match
the room; the zone order is purely left→right here.

## Notes / requirements
- **X11 only** (this session is XFCE/X11 — perfect). On Wayland, mss won't work; you'd
  capture via `grim`/PipeWire portal instead.
- Dependencies: `numpy`, `mss` (`uv pip install numpy mss`).
- Streaming credentials in `~/.hue-mcp/stream.json`; DTLS via `openssl` (scripts/huestream.py).
- **Only one entertainment stream at a time** — stop `hue-gradient-noise` / huenicorn first.
- Capturing the screen reads on-screen content into this process; it stays local (nothing
  is sent anywhere except color values to the local bridge).
