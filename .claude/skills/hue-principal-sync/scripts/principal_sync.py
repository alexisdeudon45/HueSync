#!/usr/bin/env python3
"""
Principal-light sync for the Home group.

Picks a random "principal" light from Home (or uses one you name), optionally
sets its color / brightness / power, then copies its FULL state (color +
brightness + on/off) onto every other Home light so the whole room matches the
principal.

Connection uses the credentials saved by the HueSync server at
~/.hue-mcp/config.json (falls back to the known bridge IP).

Examples:
    # random principal, mirror its current look to the rest
    python principal_sync.py

    # random principal, set it blue, everyone follows
    python principal_sync.py --color 0,0,255

    # specific principal, warm-ish via Kelvin, dimmed, all follow
    python principal_sync.py --principal 49 --ct 2700 --bri 120

    # turn the principal (and therefore the room) off
    python principal_sync.py --off
"""
import argparse
import json
import os
import random
import sys
import time

from phue import Bridge

HOME_LIGHTS = [43, 47, 48, 49, 50, 51, 52]
HOME_GROUP = 81
CONFIG_FILE = os.path.expanduser("~/.hue-mcp/config.json")
FALLBACK_IP = "192.168.178.37"


def connect() -> Bridge:
    ip, username = FALLBACK_IP, None
    if os.path.exists(CONFIG_FILE):
        try:
            cfg = json.load(open(CONFIG_FILE))
            ip = cfg.get("bridge_ip", ip)
            username = cfg.get("username")
        except (json.JSONDecodeError, OSError):
            pass
    b = Bridge(ip, username=username) if username else Bridge(ip)
    b.connect()
    return b


def rgb_to_xy(r: int, g: int, b: int) -> list[float]:
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    f = lambda c: pow((c + 0.055) / 1.055, 2.4) if c > 0.04045 else c / 12.92
    r, g, b = f(r), f(g), f(b)
    X = r * 0.649926 + g * 0.103455 + b * 0.197109
    Y = r * 0.234327 + g * 0.743075 + b * 0.022598
    Z = b * 1.035763 + r * 0.0 + g * 0.053077
    s = X + Y + Z
    return [0.0, 0.0] if s == 0 else [X / s, Y / s]


def run_cycle(bridge: Bridge, principal: int, name: str, args) -> int:
    """Rotate color across the whole Home group, one group command per tick.

    The principal "leads": each tick a color is chosen and applied to the entire
    group (principal + followers) in a single group call, which is the fastest
    safe way over the REST API. The bridge rate-limits group commands to roughly
    one per second, so very small intervals will be throttled and look choppy —
    smooth/strobe-fast effects need the Entertainment streaming API, which this
    REST-based tool can't use.
    """
    interval = max(0.2, args.interval)
    transition = int(interval * 10) if args.transition < 0 else args.transition
    steps = max(1, int(args.duration / interval))
    bridge.set_group(HOME_GROUP, "on", True)
    try:
        for i in range(steps):
            hue = random.randint(0, 65535) if args.random else (i * 65535 // 24) % 65536
            bridge.set_group(HOME_GROUP, {"hue": hue, "sat": 254, "bri": 254,
                                          "transitiontime": transition})
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    print(f"Cycled the Home group for ~{steps} steps at {interval}s "
          f"({'random' if args.random else 'hue-sweep'}, transition {transition}ds). "
          f"Principal was light {principal} ({name}).")
    print("Note: over the REST API the bridge throttles group updates to ~1/s; "
          "for smooth fast effects use an Entertainment area + the streaming API.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mirror Home lights to a random principal")
    ap.add_argument("--principal", type=int, help="Light ID to use as principal (default: random Home light)")
    ap.add_argument("--color", type=str, help="Set principal color first, as 'r,g,b' (0-255 each)")
    ap.add_argument("--ct", type=int, help="Set principal color temperature in Kelvin (2000-6500)")
    ap.add_argument("--bri", type=int, help="Set principal brightness first (0-254)")
    ap.add_argument("--on", action="store_true", help="Turn principal on before mirroring")
    ap.add_argument("--off", action="store_true", help="Turn principal off before mirroring")
    ap.add_argument("--cycle", action="store_true",
                    help="Rapidly rotate color through the whole room (principal leads, all follow)")
    ap.add_argument("--interval", type=float, default=0.6,
                    help="Seconds between color steps in --cycle (default 0.6; <0.5 may be throttled by the bridge)")
    ap.add_argument("--duration", type=float, default=15.0,
                    help="Total seconds to run --cycle (default 15)")
    ap.add_argument("--transition", type=int, default=-1,
                    help="Crossfade per step in deciseconds; -1 = match interval (smooth), 0 = instant/strobe")
    ap.add_argument("--random", action="store_true",
                    help="Use random colors in --cycle instead of a smooth hue sweep")
    args = ap.parse_args()

    bridge = connect()

    principal = args.principal if args.principal in HOME_LIGHTS else random.choice(HOME_LIGHTS)
    followers = [l for l in HOME_LIGHTS if l != principal]
    name = bridge.get_light(principal, "name")

    if args.cycle:
        return run_cycle(bridge, principal, name, args)

    # 1) Optionally drive the principal first.
    if args.off:
        bridge.set_light(principal, "on", False)
    if args.on or args.color or args.ct is not None or args.bri is not None:
        bridge.set_light(principal, "on", True)
    if args.bri is not None:
        bridge.set_light(principal, "bri", max(0, min(254, args.bri)))
    if args.color:
        try:
            r, g, b = (int(x) for x in args.color.split(","))
        except ValueError:
            print("Error: --color must be 'r,g,b' with three 0-255 integers", file=sys.stderr)
            return 2
        bridge.set_light(principal, "xy", rgb_to_xy(r, g, b))
    elif args.ct is not None:
        kelvin = max(2000, min(6500, args.ct))
        bridge.set_light(principal, "ct", int(1000000 / kelvin))

    # 2) Read the principal's FULL state.
    st = bridge.get_light(principal)["state"]
    target = {"on": st["on"]}
    if st["on"]:
        target["bri"] = st.get("bri", 254)
        mode = st.get("colormode")
        if mode == "xy" and "xy" in st:
            target["xy"] = st["xy"]
        elif mode == "ct" and "ct" in st:
            target["ct"] = st["ct"]
        elif mode == "hs":
            target["hue"], target["sat"] = st.get("hue", 0), st.get("sat", 0)

    # 3) Mirror onto the followers.
    bridge.set_light(followers, target)

    reachable = [str(l) for l in HOME_LIGHTS if not bridge.get_light(l, "reachable")]
    color_desc = (f"xy={target['xy']}" if "xy" in target else
                  f"ct={target['ct']} mired" if "ct" in target else
                  f"hue/sat={target.get('hue')}/{target.get('sat')}" if "hue" in target else "—")
    print(f"Principal: light {principal} ({name})")
    print(f"State mirrored to {followers}: on={target['on']}"
          + (f", bri={target.get('bri')}, color {color_desc}" if target["on"] else ""))
    if reachable:
        print(f"Note: lights {reachable} are unreachable (powered off) — they won't visibly update.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
