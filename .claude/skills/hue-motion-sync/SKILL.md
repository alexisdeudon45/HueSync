---
name: hue-motion-sync
description: >-
  Motion-color ambilight for the Home Hue lights: instead of averaging the whole
  screen, it diffs two consecutive frames, finds the pixels that CHANGED, averages
  only those changed pixels, and streams that single dominant "motion color" to the
  principal light (all Home lights follow it). Brightness is pushed to maximum by
  default. Use when the user wants the lights to follow what's MOVING/changing on
  screen rather than the overall screen average — e.g. "sync the lights to the pixels
  that change", "dominant color from what moves on screen", "ambilight based on motion
  / on changed pixels", "lampe principale = couleur des pixels qui bougent", "ambilight
  basé sur le mouvement / les pixels qui changent". For a plain whole-screen-average
  ambilight use hue-screen-sync instead; for a static leader-light copy use
  hue-principal-sync.
---

# Hue motion-color sync

Drives the **principal** Home light from the **pixels that changed between two frames**,
not from the whole-screen average.

Each tick it captures the X11 desktop, compares it to the previous frame, builds a mask
of pixels whose color moved by more than a threshold, averages the **current** color of
just those changed pixels, and streams that one dominant color to every Home light over
the Entertainment API. Brightness is maxed by default so the room stays bright.

## Run it
```
DISPLAY=:1.0 /home/tor/hue/hue-mcp/hue-mcp/.venv/bin/python scripts/motionsync.py [opts]
```
(`DISPLAY=:1.0` is this machine's XFCE session — needed when running detached.)

By default it runs until stopped (`--duration 0`). Launch it in the background and stop
it with `pkill -f motionsync.py`.

## Why changed pixels
On a mostly-static screen the moving content — a video, a game, a scrolling feed — is what
the eye tracks, so its color is the one that should drive the lights. A whole-screen
average gets muddied by static chrome and wallpaper; the changed-pixel average follows the
action. When almost nothing moves, the script **holds the last color** instead of sending
black, so a paused screen doesn't kill the lights.

## Options
- `--threshold` (default 25) — a pixel counts as "changed" if any RGB channel moves more
  than this (0-255) between two frames. Lower = more sensitive (subtle motion counts),
  higher = only big changes drive the color.
- `--min-frac` (default 0.001) — if fewer than this fraction of pixels changed, keep the
  last color (the static-screen guard).
- `--no-max-bright` — keep the dominant color's own brightness instead of forcing it to
  max. By default brightness is maxed (the dominant hue is kept, its HSV value set to 1.0).
- `--sat` (default 1.4) — saturation boost so the lights show color, not washed-out white.
- `--smooth` (0..1, default 0.6) — temporal EMA. The changed-pixel color is jumpy
  frame-to-frame; smoothing keeps the room calm. Higher = smoother/slower.
- `--fps` (default 18; capture-bound, ~14-20 for the full 3840×1080).
- `--monitor` — `0` = all screens combined (default), or `1`/`2` for a single monitor
  (mss indices).
- `--step` — pixel subsample stride (bigger = faster, coarser).
- `--duration` — seconds; `0` (default) = run until stopped.

## How it maps
One dominant color (the changed-pixel average) goes to **every** light — the principal
color leads the whole room, consistent with `hue-principal-sync` / `hue-screen-sync`'s
principal mode. This skill does not do per-light left→right zones; if you want true
left/right ambilight, use `hue-screen-sync --zones`.

## Notes / requirements
- **X11 only** (this session is XFCE/X11). On Wayland, mss won't work; capture via
  `grim`/PipeWire portal instead.
- Dependencies: `numpy`, `mss`. Use the venv at
  `/home/tor/hue/hue-mcp/hue-mcp/.venv/bin/python` (already has them), or
  `uv pip install numpy mss`.
- Streaming credentials in `~/.hue-mcp/stream.json`; DTLS via `openssl`
  (`scripts/huestream.py`).
- **Only one Entertainment stream at a time** — stop `hue-screen-sync`,
  `hue-gradient-noise`, or huenicorn first (`pkill -f screensync.py` etc.).
- Capturing the screen reads on-screen content into this process; it stays local
  (only color values go to the local bridge).
