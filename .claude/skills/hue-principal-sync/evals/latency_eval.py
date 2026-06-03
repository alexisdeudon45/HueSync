#!/usr/bin/env python3
"""
Latency eval for principal-sync over the REST API.

Measures L = time from issuing a principal color-change order (set the principal,
then mirror to the 6 followers = 7 light PUTs) until the bridge has confirmed all
7 changes (every PUT returns a response = the bridge accepted/applied it).

We issue a series of orders at a commanded inter-order interval `th`, sweeping th
from 2.0s downward. For each th we record the per-order confirmation latency L.
The point: when orders come faster than the bridge can service them
(~10 light-cmds/s, and each order = 7 cmds), the bridge throttles and L rises.

Output: a table (th, mean L, ...) + JSON, so a formula can be fit.
"""
import colorsys
import json
import os
import statistics
import sys
import time

from phue import Bridge

HOME = [43, 47, 48, 49, 50, 51, 52]   # principal = HOME[0], followers = rest
PRINCIPAL, FOLLOWERS = HOME[0], HOME[1:]
TH_SWEEP = [2.0, 1.5, 1.0, 0.7, 0.5, 0.35, 0.25, 0.15, 0.10, 0.05]
ORDERS_PER_TH = 8         # first 2 dropped as warm-up
WARMUP = 2
OUT = os.path.expanduser("~/.claude/skills/hue-principal-sync-workspace/latency_results.json")


def xy_for(i: int):
    r, g, b = colorsys.hsv_to_rgb((i * 0.137) % 1.0, 1.0, 1.0)
    r, g, b = r / 1, g / 1, b / 1
    X = r * 0.649926 + g * 0.103455 + b * 0.197109
    Y = r * 0.234327 + g * 0.743075 + b * 0.022598
    Z = b * 1.035763 + g * 0.053077
    s = X + Y + Z or 1.0
    return [round(X / s, 4), round(Y / s, 4)]


def issue_order(bridge, xy) -> float:
    """Set principal then followers; return wall time until all 7 confirmed."""
    t0 = time.monotonic()
    bridge.set_light(PRINCIPAL, {"on": True, "xy": xy, "transitiontime": 0})
    bridge.set_light(FOLLOWERS, {"on": True, "xy": xy, "transitiontime": 0})
    return time.monotonic() - t0


def main() -> int:
    b = Bridge("192.168.178.37")
    b.connect()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    results = []
    counter = 0
    print(f"{'th(s)':>7} {'meanL(s)':>9} {'medL':>7} {'minL':>7} {'maxL':>7} {'std':>7} {'orders/s':>9}")
    for th in TH_SWEEP:
        samples = []
        for k in range(ORDERS_PER_TH):
            counter += 1
            L = issue_order(b, xy_for(counter))
            if k >= WARMUP:
                samples.append(L)
            gap = th - L
            if gap > 0:
                time.sleep(gap)
        mean = statistics.mean(samples)
        med = statistics.median(samples)
        std = statistics.pstdev(samples)
        eff_rate = 1.0 / max(mean, th)   # achievable confirmed-orders per second
        row = {"th": th, "mean_L": round(mean, 4), "median_L": round(med, 4),
               "min_L": round(min(samples), 4), "max_L": round(max(samples), 4),
               "std_L": round(std, 4), "n": len(samples), "eff_orders_per_s": round(eff_rate, 3)}
        results.append(row)
        print(f"{th:>7.2f} {mean:>9.3f} {med:>7.3f} {min(samples):>7.3f} "
              f"{max(samples):>7.3f} {std:>7.3f} {eff_rate:>9.2f}")

    json.dump({"home_lights": HOME, "orders_per_th": ORDERS_PER_TH, "warmup": WARMUP,
               "puts_per_order": len(HOME), "results": results}, open(OUT, "w"), indent=2)
    print(f"\nSaved {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
