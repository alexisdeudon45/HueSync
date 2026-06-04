#!/usr/bin/env python3
"""solve_couleur — desired ROOM color -> the RGB to COMMAND the Hue lamps (+ expected result).

The room doesn't render the color you command 1:1 (lamp gamut + camera bend it). This turns
a desired room color straight into the lamp setting using the measured calibration in
color_calib.py (REST/xy path), so you skip the closed loop once the room is characterized.

    PY=/home/tor/hue-mcp/.venv/bin/python
    $PY solve_couleur.py green                 # what to send to make the room green
    $PY solve_couleur.py 30                    # a target room HUE in degrees
    $PY solve_couleur.py 255,120,0 --apply     # solve from an RGB target and set the room
    $PY solve_couleur.py blue --verify         # set it, then capture+score to confirm

The calibration is specific to THIS room + webcam at the locked WB/exposure used to measure
it. If the room, camera, or lock changes, re-sweep the hue wheel with hue_eval and update
REST_ANCHORS in color_calib.py. Numbers, not magic — re-fit when reality moves.
"""
import argparse
import colorsys
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from color_calib import REST  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))

NAMED_TARGET_HUE = {  # desired ROOM hue for common names
    "red": 0, "orange": 30, "yellow": 60, "green": 120, "cyan": 180,
    "blue": 240, "azure": 210, "purple": 280, "violet": 270, "magenta": 300, "pink": 330, "rose": 335,
}


def target_hue_from_arg(arg):
    """Color name, a hue in degrees, or 'r,g,b' -> desired room hue (or None = neutral)."""
    a = arg.lower().strip()
    if a in NAMED_TARGET_HUE:
        return float(NAMED_TARGET_HUE[a])
    if a in ("white", "warm", "neutral"):
        return None
    if "," in a:
        r, g, b = (int(x) for x in a.split(","))
        h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return None if s < 0.12 else h * 360
    return float(a)


def main():
    ap = argparse.ArgumentParser(description="Desired room color -> RGB to command the Hue lamps")
    ap.add_argument("color", help="room color you want: name | hue degrees | 'r,g,b'")
    ap.add_argument("--sat", type=float, default=1.0, help="saturation 0..1 (1=faithful; lower=brighter but washed)")
    ap.add_argument("--bri", type=int, default=254, help="brightness 0-254 (default max)")
    ap.add_argument("--apply", action="store_true", help="send the solved setting (set_room.py)")
    ap.add_argument("--verify", action="store_true", help="apply, then capture+score to confirm (hue_eval.py)")
    args = ap.parse_args()

    target = target_hue_from_arg(args.color)
    if target is None:
        rgb = (255, 255, 255)
        print(f"neutral target -> command rgb=255,255,255 bri={args.bri} (no hue calibration needed)")
    else:
        rgb, cmd_hue, resid, gain = REST.command_rgb(target, sat=args.sat)
        print(f"target room hue = {target:.0f}°")
        print(f"-> command hue  = {cmd_hue:.0f}°   rgb={rgb[0]},{rgb[1]},{rgb[2]}   bri={args.bri}")
        print(f"   predicted room hue = {REST.room_hue(cmd_hue):.0f}°  (residual {resid:.0f}°)")
        print(f"   expected illuminated ≈ {gain:.0f}% of view at full saturation")
        if resid > 20:
            print("   ⚠ this hue is poorly renderable here (green/yellow-green band) — closest match shown")
        if gain < 30:
            print("   ⚠ low-gain hue: stays dim if kept saturated; desaturating brightens but washes the color")

    rgb_str = f"{rgb[0]},{rgb[1]},{rgb[2]}"
    if args.apply or args.verify:
        subprocess.run([sys.executable, os.path.join(HERE, "set_room.py"),
                        "--rgb", rgb_str, "--bri", str(args.bri)], check=True)
    if args.verify:
        time.sleep(2.5)
        tgt = args.color if ("," in args.color or args.color.lower() in NAMED_TARGET_HUE) else rgb_str
        out = subprocess.run([sys.executable, os.path.join(HERE, "hue_eval.py"), "--target", tgt],
                             capture_output=True, text=True)
        print("verify:\n" + out.stdout.strip())
    else:
        print(f"\nto apply:  python set_room.py --rgb {rgb_str} --bri {args.bri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
