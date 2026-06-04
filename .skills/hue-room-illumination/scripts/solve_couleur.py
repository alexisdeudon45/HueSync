#!/usr/bin/env python3
"""solve_couleur — desired ROOM color -> the RGB to COMMAND the Hue lamps (+ expected result).

Closed-loop calibration (hue_eval + set_room, camera locked) showed the room does NOT
render the color you command 1:1. This script encodes what we measured so you can go
straight to the right lamp setting instead of iterating every time:

  * Law 0 (magnitude invariance): the lamp uses chromaticity (xy) + a separate brightness,
    so only the RGB *ratio* sets the color and `bri` sets the light. We therefore solve for
    a full-saturation hue and hand brightness to `bri`. Scaling a single channel is a no-op.
  * Law 1 (hue transfer T): room_hue = T(commanded_hue) — near-identity but with a strong
    "green attractor" (commanded ~75-130 all collapse to ~140-150) and a warm pull (oranges
    drift toward red). We invert T so you get the hue you actually want.
  * Law 2 (brightness gain g): at full saturation the room's lit fraction depends on hue —
    red/orange/blue bright (~0.5-0.6), green/cyan dim (~0.22). We report the expected
    illuminated_pct so you know up front whether a hue can fill the room.

The calibration is specific to THIS room + webcam at the locked settings used to measure it
(WB 4600 / exposure 6000). If the room, camera, or lock changes, re-measure (sweep the hue
wheel with hue_eval) and update ANCHORS. Numbers, not magic — re-fit when reality moves.

    PY=/home/tor/hue-mcp/.venv/bin/python
    $PY solve_couleur.py green                 # what to send to make the room green
    $PY solve_couleur.py 30                    # a target room HUE in degrees
    $PY solve_couleur.py 255,120,0 --apply     # solve from an RGB target and set the room
    $PY solve_couleur.py blue --verify         # set it, then capture+score to confirm
"""
import argparse
import colorsys
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# Measured anchors from the hue-wheel sweep (camera locked WB4600/exp6000):
#   commanded_hue°, resulting room_hue°, illuminated_pct at full saturation & bri 254
ANCHORS = [
    (0, 0, 60), (30, 3, 57), (60, 48, 27), (90, 143, 22), (120, 143, 22), (150, 149, 23),
    (180, 187, 22), (210, 225, 42), (240, 243, 49), (270, 269, 42), (300, 319, 48), (330, 354, 56),
]
CMD = np.array([a[0] for a in ANCHORS], float)
ROOM = np.array([a[1] for a in ANCHORS], float)
GAIN = np.array([a[2] for a in ANCHORS], float)

NAMED_TARGET_HUE = {  # desired ROOM hue for common names
    "red": 0, "orange": 30, "yellow": 60, "green": 120, "cyan": 180,
    "blue": 240, "azure": 210, "purple": 280, "violet": 270, "magenta": 300, "pink": 330, "rose": 335,
}


def circdist(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def forward_room_hue(cmd):
    """T: commanded hue -> predicted room hue, by interpolating the measured anchors."""
    return float(np.interp(cmd % 360, CMD, ROOM))


def forward_gain(cmd):
    return float(np.interp(cmd % 360, CMD, GAIN))


# Commanded hues in this band don't render — they collapse into the green attractor
# (measured: cmd 90 -> room 143 at ~1% purity). Excluding them from the inversion stops the
# solver from "finding" a fake faithful green by interpolating across that discontinuity, so
# unrenderable targets honestly report a large residual instead of false confidence.
UNSTABLE_CMD = (65, 115)


def invert(target_room_hue):
    """T^-1: scan the *stable* commanded hues, pick the one whose predicted room hue is
    closest to target. Returns (best_cmd_hue, residual_deg). A big residual means the room
    can't render that hue (e.g. true yellow-greens — everything there lands near 143°)."""
    cands = [c for c in np.arange(0, 360, 1.0) if not (UNSTABLE_CMD[0] <= c <= UNSTABLE_CMD[1])]
    errs = [circdist(forward_room_hue(c), target_room_hue) for c in cands]
    i = int(np.argmin(errs))
    return float(cands[i]), float(errs[i])


def target_hue_from_arg(arg):
    """Accept a color name, a hue in degrees, or 'r,g,b' -> desired room hue (or None=neutral)."""
    a = arg.lower().strip()
    if a in NAMED_TARGET_HUE:
        return float(NAMED_TARGET_HUE[a])
    if a in ("white", "warm", "neutral"):
        return None
    if "," in a:
        r, g, b = (int(x) for x in a.split(","))
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return None if s < 0.12 else h * 360
    return float(a)  # bare number = hue in degrees


def solve(target_hue, sat):
    cmd_hue, resid = invert(target_hue)
    r, g, b = colorsys.hsv_to_rgb(cmd_hue / 360.0, sat, 1.0)
    rgb = (round(r * 255), round(g * 255), round(b * 255))
    return cmd_hue, resid, rgb, forward_gain(cmd_hue)


def main():
    ap = argparse.ArgumentParser(description="Desired room color -> RGB to command the Hue lamps")
    ap.add_argument("color", help="room color you want: name | hue degrees | 'r,g,b'")
    ap.add_argument("--sat", type=float, default=1.0, help="saturation 0..1 (1=faithful color; lower=brighter but washed)")
    ap.add_argument("--bri", type=int, default=254, help="brightness 0-254 (default max)")
    ap.add_argument("--apply", action="store_true", help="send the solved setting to the room (set_room.py)")
    ap.add_argument("--verify", action="store_true", help="apply, then capture+score to confirm (hue_eval.py)")
    args = ap.parse_args()

    target = target_hue_from_arg(args.color)
    if target is None:  # neutral / white: hue transfer doesn't apply
        rgb, cmd_hue, resid, gain = (255, 255, 255), None, 0.0, None
        print(f"neutral target -> command rgb=255,255,255 bri={args.bri} (no hue calibration needed)")
    else:
        cmd_hue, resid, rgb, gain = solve(target, args.sat)
        print(f"target room hue = {target:.0f}°")
        print(f"-> command hue  = {cmd_hue:.0f}°   rgb={rgb[0]},{rgb[1]},{rgb[2]}   bri={args.bri}")
        print(f"   predicted room hue = {forward_room_hue(cmd_hue):.0f}°  (residual {resid:.0f}°)")
        print(f"   expected illuminated ≈ {gain:.0f}% of view at full saturation")
        if resid > 20:
            print("   ⚠ this hue is poorly renderable here (green/yellow-green band) — closest match shown")
        if gain < 30:
            print("   ⚠ low-gain hue: room will stay dim if kept saturated; desaturating brightens but washes the color")

    rgb_str = f"{rgb[0]},{rgb[1]},{rgb[2]}"
    if args.apply or args.verify:
        subprocess.run([sys.executable, os.path.join(HERE, "set_room.py"),
                        "--rgb", rgb_str, "--bri", str(args.bri)], check=True)
    if args.verify:
        import time
        time.sleep(2.5)
        tgt = args.color if ("," in args.color or args.color.lower() in NAMED_TARGET_HUE) else rgb_str
        out = subprocess.run([sys.executable, os.path.join(HERE, "hue_eval.py"),
                              "--target", tgt], capture_output=True, text=True)
        print("verify:\n" + out.stdout.strip())
    else:
        print(f"\nto apply:  python set_room.py --rgb {rgb_str} --bri {args.bri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
