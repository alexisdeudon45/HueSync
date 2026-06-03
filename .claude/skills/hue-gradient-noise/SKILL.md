---
name: hue-gradient-noise
description: >-
  Drive the Home Entertainment lights with gradient noise (Perlin/Simplex) for
  smooth, organic, flowing color — and explain how gradient noise works. Variants:
  per-light noise, a spatial wave across the room, domain-warped swirls, and a
  music-reactive mode where audio modulates the noise. Use when the user wants
  ambient/organic lighting (lava-lamp, aurora, "flow"), wants to understand
  gradient noise, or wants music-reactive lighting that isn't harsh strobing.
  Trigger on "gradient noise", "perlin/simplex lighting", "organic/ambient color
  flow", "lava lamp lights", "aurora effect", "make the lights flow with the
  music", "ambiance qui ondule". Streams ~30-40 fps over the Entertainment API.
---

# Hue gradient-noise lighting

## What gradient noise is (and why it's used here)
**Gradient noise** (Perlin, 1985; **Simplex**, 2001) is a *smooth, continuous*
pseudo-random field — unlike `random`, which jumps. Key properties that make it
ideal for lighting:

- **Continuous / band-limited** → colors flow with **no flicker** (a random value
  per frame would strobe).
- **Octaves → fBm** (fractal Brownian motion): summing the noise at doubling
  frequencies and halving amplitudes adds natural detail (the "lava-lamp" look).
- **Multi-dimensional**: 1D `noise(t)` for time evolution; 2D `noise(position, t)`
  for effects that are coherent *across* the lights.

This skill maps noise to **HSV**: independent Simplex/fBm channels feed hue,
saturation and value, so each light "breathes" organically.

**Honest note on hue:** gradient noise is *centred* (values cluster near the
middle), so naively mapping noise→hue gives only a narrow green/blue band. We fix
this the pure-noise way — a **hue gain** (`--hue-gain`, default 4) so the noise
excursion wraps the whole color wheel (`mod 1`), covering the full spectrum from
noise alone. Hue, saturation and value are all genuine gradient noise. There is
also an optional `--hue-drift` (default 0) that adds a *non-noise* linear sweep of
the wheel — leave it at 0 to keep everything pure noise.

## Run it
```
/home/tor/hue/hue-mcp/hue-mcp/.venv/bin/python scripts/noisefx.py --effect <e> [opts]
```
Effects:
- **`noise`** — per-light 1D fBm over time; each light evolves independently.
- **`spatial`** — 2D fBm over (light position, time); an organic wave rolls across
  the room (the smooth cousin of `hue-principal-sync`'s rigid `wave`).
- **`warp`** — domain-warped fBm (noise feeding noise) → liquid swirls.

Options: `--duration`, `--fps` (default 40), `--speed` (flow rate), `--octaves`
(detail), `--sat`.

**Principal mode (default).** Like `hue-principal-sync`, ALL lights show **one
principal color** (sampled from channel 0) that flows over time — every light is
identical. Add **`--per-light`** to instead give each light its own noise sample
(multicolor: the `spatial`/`warp` effects then visibly differ across the room).

## Music-reactive variant
Add `--music` (optionally `--source <pulse monitor>`): audio captured from the
system output (via `parec`) **modulates** the noise instead of replacing it —
loudness → speed + brightness, treble → hue shift, onsets → a gentle "breath".
You keep noise's smoothness but it reacts to sound (no jarring flashes). See the
hue-latency / streaming notes: this must go over the Entertainment API, never REST.

## Dependencies
`numpy`, `opensimplex` (and `parec` for `--music`). Install once:
`uv pip install numpy opensimplex`. Streaming credentials live in
`~/.hue-mcp/stream.json`; transport is DTLS via `openssl` (see scripts/huestream.py).
Only one entertainment stream can run at a time (stop huenicorn / hue-screen-sync first).
