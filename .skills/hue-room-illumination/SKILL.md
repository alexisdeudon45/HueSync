---
name: hue-room-illumination
description: >-
  Closed-loop auto-calibration of the Philips Hue lights so the WHOLE room is illuminated
  in a chosen color, judged by the webcam. It scores a camera shot of the room (how much
  is lit, and whether the lit area is the target color), then adjusts the principal/Home
  lamp color and brightness and re-measures, iterating until the room is as fully and
  correctly lit as the lamps allow. Use when the user wants the room lighting tuned/optimized
  by actually looking at the room — e.g. "make the whole room green and check it with the
  camera", "find the best Hue settings to light up the room in red", "tune the lamps until
  the room is properly blue", "configure the principal light so the room is fully lit",
  "optimise l'éclairage pour que toute la pièce soit verte", "règle les Hue jusqu'à ce que
  la pièce soit bien illuminée", "trouve les meilleurs paramètres de la lampe principale".
  Also provides a standalone EVAL that reports the percentage of the room illuminated and
  in-color. Needs the webcam (V4L2) + the Hue bridge; distinct from hue-screen-sync/
  hue-motion-sync (which mirror the SCREEN, with no feedback) and from plain hue-lighting
  (one-shot control with no measurement).
---

# Hue room illumination (closed loop)

Tune the Hue lights so the room is as fully illuminated as possible **in a target color**,
using the webcam as the sensor. The skill is a perception→action loop: set the lamps,
photograph the room, score it, adjust, repeat.

Scripts (run all with the hue venv python — it has both `numpy` and `phue`):
```
PY=/home/tor/hue-mcp/.venv/bin/python
```
- `scripts/hue_eval.py`   — **the eval**: capture the room + score it against a target color
- `scripts/set_room.py`   — set the whole Home group (principal + followers) to an RGB + brightness
- `scripts/lock_camera.py`— freeze the webcam's auto white-balance & exposure (do this first!)
- `scripts/solve_couleur.py` — **the calibrated shortcut**: desired room color → the RGB to command

## Shortcut: solve_couleur (skip the loop once calibrated)
Once you've characterized the room (see "Deriving the formula" below), `solve_couleur.py`
turns a desired room color straight into the lamp command, so you don't re-run the loop
every time. It encodes the measured hue-transfer (inverted) and per-hue brightness gain:
```
$PY scripts/solve_couleur.py green            # prints the RGB to send + predicted result
$PY scripts/solve_couleur.py 30               # target room HUE in degrees
$PY scripts/solve_couleur.py blue --apply     # also set the room
$PY scripts/solve_couleur.py orange --verify  # set it, then capture+score to confirm
```
The calibration math lives in the shared `scripts/color_calib.py` (REST anchors here; the
same module with STREAM anchors is used by `hue-motion-sync` to correct its streamed colors).
It reports the predicted room hue, a **residual** (how faithfully that hue can be rendered —
a big residual flags unrenderable targets like true yellow-greens, which collapse into the
"green attractor"), and the **expected illuminated %** so you know up front if a hue can fill
the room (red/orange/blue ≈ 0.5–0.6; green/cyan ≈ 0.22). The calibration constants
(`ANCHORS`) are specific to this room + webcam at the locked WB/exposure — re-measure and
update them if any of those change.

## Step 0 — lock the camera (this is not optional)
A webcam constantly re-adjusts auto-white-balance and auto-exposure. When you flood the
room with one color, white-balance "corrects" the cast back toward neutral, so the *same*
green setting reads as vivid green one moment and washed-out teal the next — the eval
becomes unrepeatable and the loop chases noise. Lock the camera so it behaves as a fixed
instrument:
```
$PY scripts/lock_camera.py --wb 4600 --exposure 6000     # freeze WB + exposure
$PY scripts/lock_camera.py --status                      # confirm auto_white_balance=0, exposure_auto=1
```
Pick the exposure once so a normally-lit room reads at a sensible brightness (≈6000–9000
on this camera; lower = darker). Keep it FIXED for the rest of the session — changing it
moves the `illuminated_pct` goalposts. Hand control back when done with `--auto`.

## Step 1 — the eval
```
$PY scripts/hue_eval.py --target green                 # capture now and score
$PY scripts/hue_eval.py --target 0,255,0 --json        # RGB target, machine-readable
$PY scripts/hue_eval.py --target blue --image room.png # score an existing photo
```
It reports:
- **illuminated_pct** — % of the frame bright enough to be "lit"
- **lit_in_color_pct** — % of the frame that is *both* lit *and* the target color (the headline number)
- **color_purity_pct** — of the lit pixels, how many match the target color
- **mean_lit_rgb / mean_lit_hue** — the lit area's actual average color (shows which way it's off)
- **verdict** — which knob to turn (too dim → brightness; lit-but-wrong-color → saturation)

Targets: a name (`red orange yellow green cyan blue purple magenta white warm`) or `r,g,b`.
Neutral targets (white/warm) are matched by low saturation instead of a hue.

## Step 2 — the optimization loop
Repeat until the verdict is GOOD or the score stops improving (a handful of steps):
1. `set_room.py --rgb <r,g,b> --bri <0-254>` to try a setting.
2. Wait ~2.5 s (lamp crossfade + capture settle), then run `hue_eval.py --target <color> --json`.
3. **Read both the number and the saved image** (`--save /tmp/iterN.png`) — the eye catches
   things the metric misses.
4. Adjust from the verdict and re-run:
   - **TOO DIM / low illuminated_pct** → raise `--bri` (max is 254); if already maxed, the only
     way to light more of the room is to desaturate the color (see below).
   - **LIT BUT WRONG COLOR / low purity** → the lit area drifted off-hue (often because the
     color is too pale and other light competes). Use a *more saturated* RGB.
5. Keep the setting with the highest `lit_in_color_pct` that still reads as the right color
   (purity ≳ 80%).

### The core trade-off (what the loop is really searching)
Brightness vs color purity. A fully saturated color (e.g. `0,255,0`) is unambiguously the
right hue but the lamps emit less total light, so less of the room clears the "lit"
threshold. Adding white (`150,255,150`) brightens the room and lights more of it — up to a
point, then it washes out and the eval flags it as the wrong color. The optimum is the
palest version that still passes the color check. Measured here (camera locked):
- **Green** benefits from *slight* desaturation: `150,255,150` reached ~85% lit-in-color at
  ~95% purity, beating pure green's ~77%. Past ~`200,255,200` purity collapsed.
- **Blue** is best left **pure** (`0,0,255`): ~51% lit-in-color at ~99% purity. Blue Hue
  output is dim so the room caps around half-lit, and any desaturation just turns it
  purple/white — coverage went up but the color check failed.
So the right answer is color-dependent; that's exactly why you measure instead of guessing.

## Deriving the formula (how solve_couleur's constants were measured)
The lamp is driven by chromaticity (xy) + a separate `bri`, so `rgb_to_xy` throws away RGB
magnitude — scaling a single channel of a pure color does nothing (verified: sweeping one
channel 255→20 left illumination/hue/purity flat). Only the RGB *ratio* (hue+saturation) and
`bri` matter. To characterize the room, lock the camera, then sweep the hue wheel at full
saturation / `bri` 254 and record, per commanded hue, the resulting `mean_lit_hue` and
`illuminated_pct`:
```
for h in 0 30 60 ... 330: set_room.py --rgb <hsv(h,1,1)>; hue_eval.py --target <same> --json
```
That gives two curves: the **hue transfer** room=T(commanded) and the **gain** g(commanded).
Findings here: T is near-identity except a "green attractor" (commanded ~75–115 collapse to
~143°, so true yellow-greens are unrenderable) and a warm pull (oranges drift toward red);
g is high for red/orange/blue (~0.5–0.6) and low for green/cyan (~0.22). `solve_couleur.py`
stores these as `ANCHORS`, inverts T (skipping the unstable band), and reports g. Re-run this
sweep and update `ANCHORS` whenever the room, camera, or lock changes — it's fitted data, not
a universal constant.

## Notes
- `set_room.py` drives the whole Home group (`HOME_GROUP=81`, lights `43,47–52`) in one
  command — the principal leads, all follow — because the goal is the ROOM, not one lamp.
  Powered-off/unreachable lights are reported and simply won't light up.
- Only what the **camera sees** is optimized; aim it at the area that matters, and expect
  zones the lamps can't reach to stay dark (that caps `illuminated_pct`).
- **One app owns the camera at a time**, and **one Entertainment stream at a time** — stop
  `hue-motion-sync`/`hue-screen-sync` (`pkill -f motionsync.py`) before running this, or
  their stream will override `set_room.py`'s REST commands.
- Restore afterwards: `lock_camera.py --auto` (camera) and set a normal white via
  `set_room.py --rgb 255,255,255 --bri 254` or relaunch your ambilight.
- Everything is local (camera frames + LAN light commands); nothing is uploaded.
