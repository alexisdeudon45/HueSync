#!/usr/bin/env python3
"""Validate the latency formula L0(N) = 0.0384*N + 0.0024 s against the live bridge.

Auto-detects the currently REACHABLE lights in the Home (81) and Bedroom Ishan (84)
groups, then sweeps N = 1..(#reachable), measuring sequential set-color latency for N
lights and comparing to the formula. Refits a line and reports R^2.

Validated 2026-06-03 across 11 reachable lights (Home 7 + Bedroom 4): error within
+/-3.5% at every N, refit L0(N) = 0.0395*N - 0.004 s, R^2 = 0.9994.
"""
import colorsys
import statistics
import time

from phue import Bridge

BRIDGE_IP = "192.168.178.37"
GROUPS = [81, 84]                 # Home + Bedroom Ishan
A, B = 0.0384, 0.0024             # formula from the original N=1..7 fit
TRIALS, WARMUP = 6, 2


def xy(i):
    r, g, b = colorsys.hsv_to_rgb((i * 0.137) % 1, 1, 1)
    X = r*0.6499+g*0.1035+b*0.1971; Y = r*0.2343+g*0.7431+b*0.0226; Z = b*1.0358+g*0.0531
    s = X+Y+Z or 1
    return [round(X/s, 4), round(Y/s, 4)]


def main():
    b = Bridge(BRIDGE_IP)
    b.connect()
    ls = b.get_light()
    lights = []
    for g in GROUPS:
        for lid in b.get_group(g)["lights"]:
            if ls[lid]["state"]["reachable"] and int(lid) not in lights:
                lights.append(int(lid))
    print(f"Reachable lights ({len(lights)}): {lights}")
    if len(lights) < 2:
        print("Need >=2 reachable lights; power on more and retry.")
        return

    c = 0
    rows = []
    print(f"{'N':>3} {'meas(ms)':>9} {'pred(ms)':>9} {'err%':>6}")
    for N in range(1, len(lights) + 1):
        sub = lights[:N]
        samples = []
        for k in range(TRIALS):
            t0 = time.monotonic()
            for l in sub:
                c += 1
                b.set_light(l, {"on": True, "xy": xy(c), "transitiontime": 0})
            dt = (time.monotonic() - t0) * 1000
            if k >= WARMUP:
                samples.append(dt)
            time.sleep(0.3)
        meas = statistics.mean(samples); pred = (A * N + B) * 1000
        rows.append((N, meas, pred))
        print(f"{N:>3} {meas:>9.1f} {pred:>9.1f} {100*(meas-pred)/pred:>6.1f}")

    n = len(rows); sx = sum(r[0] for r in rows); sy = sum(r[1] for r in rows)
    sxx = sum(r[0]**2 for r in rows); sxy = sum(r[0]*r[1] for r in rows)
    a = (n*sxy - sx*sy) / (n*sxx - sx*sx); bb = (sy - a*sx) / n
    ybar = sy/n; sst = sum((r[1]-ybar)**2 for r in rows); ssr = sum((r[1]-(a*r[0]+bb))**2 for r in rows)
    print(f"\nRefit (N=1..{len(lights)}): L0(N) = {a/1000:.4f}*N + {bb/1000:.4f} s  "
          f"(per-light {a:.1f} ms, R^2={1-ssr/sst:.4f})")
    print(f"Formula           : L0(N) = {A}*N + {B} s")


if __name__ == "__main__":
    main()
