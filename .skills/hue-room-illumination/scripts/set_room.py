#!/usr/bin/env python3
"""Set the whole Home room (the principal light + all followers) to a color & brightness.

This is the actuator half of the hue-room-illumination loop: the optimizer calls it to
try a setting, then captures the room and scores it with hue_eval.py. We drive the whole
Home group in one command (the principal leads, every light follows) because the goal is
to illuminate the ROOM, not one lamp.

Color is given as 'r,g,b' (0-255). Saturation is implied by the RGB: pure 0,255,0 is
vivid green; 120,255,120 is a paler, brighter green. That trade-off — vivid but dim vs
pale but bright — is exactly what the loop explores, so it tweaks both the RGB and --bri.

Run with the hue venv python (it has phue):
    /home/tor/hue-mcp/.venv/bin/python set_room.py --rgb 0,255,0 --bri 254
"""
import argparse
import json
import os
import sys

from phue import Bridge

HOME_GROUP = 81
HOME_LIGHTS = [43, 47, 48, 49, 50, 51, 52]
CONFIG_FILE = os.path.expanduser("~/.hue-mcp/config.json")
FALLBACK_IP = "192.168.178.37"


def connect():
    ip, username = FALLBACK_IP, None
    if os.path.exists(CONFIG_FILE):
        try:
            cfg = json.load(open(CONFIG_FILE))
            ip, username = cfg.get("bridge_ip", ip), cfg.get("username")
        except (json.JSONDecodeError, OSError):
            pass
    b = Bridge(ip, username=username) if username else Bridge(ip)
    b.connect()
    return b


def rgb_to_xy(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    f = lambda c: pow((c + 0.055) / 1.055, 2.4) if c > 0.04045 else c / 12.92
    r, g, b = f(r), f(g), f(b)
    X = r * 0.649926 + g * 0.103455 + b * 0.197109
    Y = r * 0.234327 + g * 0.743075 + b * 0.022598
    Z = b * 1.035763 + g * 0.053077
    s = X + Y + Z
    return [0.0, 0.0] if s == 0 else [X / s, Y / s]


def main():
    ap = argparse.ArgumentParser(description="Set the whole Home room to a color & brightness")
    ap.add_argument("--rgb", required=True, help="target color 'r,g,b' (0-255)")
    ap.add_argument("--bri", type=int, default=254, help="brightness 0-254 (default 254 = max)")
    ap.add_argument("--transition", type=int, default=4, help="crossfade in deciseconds (default 0.4s)")
    ap.add_argument("--off", action="store_true", help="turn the room off and exit")
    args = ap.parse_args()

    b = connect()
    if args.off:
        b.set_group(HOME_GROUP, "on", False)
        print("room off")
        return 0
    try:
        r, g, bl = (int(x) for x in args.rgb.split(","))
    except ValueError:
        print("--rgb must be 'r,g,b' with three 0-255 integers", file=sys.stderr)
        return 2

    bri = max(0, min(254, args.bri))
    b.set_group(HOME_GROUP, {"on": True, "bri": bri, "xy": rgb_to_xy(r, g, bl),
                             "transitiontime": args.transition})
    unreachable = [l for l in HOME_LIGHTS if not b.get_light(l, "reachable")]
    print(f"room set: rgb={r},{g},{bl} xy={rgb_to_xy(r, g, bl)} bri={bri}")
    if unreachable:
        print(f"note: lights {unreachable} are powered off / unreachable — they won't light up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
