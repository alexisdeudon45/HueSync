#!/usr/bin/env python3
"""Ambilight: stream the colors of your PC screens to the Home Entertainment lights.

Captures the X11 desktop with mss, splits the screen width into one zone per light
channel (left -> right), averages each zone's color, optionally boosts saturation
and smooths over time, then streams to the Hue Entertainment area.

Runs on the live X11 session (XFCE here). Set DISPLAY if running detached, e.g.
DISPLAY=:1.0 python screensync.py
"""
import argparse
import colorsys
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from huestream import HueStream, CHANNELS  # noqa

import numpy as np  # noqa
import mss  # noqa


def boost_sat(rgb, factor, gamma):
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, s * factor)
    v = pow(v, gamma)               # gamma <1 brightens dim scenes
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def main():
    ap = argparse.ArgumentParser(description="Screen ambilight -> Hue")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--fps", type=float, default=18.0, help="target capture rate (capture-bound, ~14-20)")
    ap.add_argument("--monitor", type=int, default=0, help="0=all screens, 1/2=a specific monitor")
    ap.add_argument("--sat", type=float, default=1.6, help="saturation boost (1=raw)")
    ap.add_argument("--gamma", type=float, default=0.8, help="<1 brightens dim screens")
    ap.add_argument("--smooth", type=float, default=0.5, help="EMA factor 0..1 (higher=smoother/slower)")
    ap.add_argument("--step", type=int, default=8, help="pixel subsample stride (bigger=faster, coarser)")
    ap.add_argument("--zones", action="store_true",
                    help="per-light left->right zones (default: one principal/average color on ALL lights)")
    args = ap.parse_args()

    n = len(CHANNELS)
    dt = 1.0 / args.fps
    prev = None
    with mss.MSS() as sct, HueStream() as s:
        mon = sct.monitors[args.monitor]
        mode = f"{n} left->right zones" if args.zones else "whole-screen average (1 principal color on all lights)"
        print(f"capturing monitor[{args.monitor}] {mon['width']}x{mon['height']} -> {mode}")
        t0 = time.monotonic(); frames = 0
        try:
            while True:
                t = time.monotonic() - t0
                if t >= args.duration:
                    break
                shot = sct.grab(mon)
                img = np.frombuffer(shot.rgb, dtype=np.uint8).reshape(shot.height, shot.width, 3)
                img = img[::args.step, ::args.step]            # subsample for speed
                w = img.shape[1]
                if args.zones:
                    colors = []
                    for i in range(n):
                        zone = img[:, w * i // n: max(w * i // n + 1, w * (i + 1) // n)]
                        avg = tuple(int(c) for c in zone.reshape(-1, 3).mean(axis=0))
                        colors.append(boost_sat(avg, args.sat, args.gamma))
                else:
                    # Default: one principal color = whole-screen average, on every light.
                    avg = tuple(int(c) for c in img.reshape(-1, 3).mean(axis=0))
                    colors = [boost_sat(avg, args.sat, args.gamma)] * n
                if prev is not None:
                    a = args.smooth
                    colors = [tuple(int(a * p + (1 - a) * c) for p, c in zip(pc, cc))
                              for pc, cc in zip(prev, colors)]
                prev = colors
                if not s.send(colors):
                    print("stream closed early; see /tmp/huestream_openssl.log", file=sys.stderr)
                    break
                frames += 1
                time.sleep(max(0, dt - (time.monotonic() - t0 - t)))
        except KeyboardInterrupt:
            print("\nstopped.")
    el = time.monotonic() - t0
    print(f"ambilight: {frames} frames in {el:.1f}s (~{frames/el:.0f} fps)")


if __name__ == "__main__":
    main()
