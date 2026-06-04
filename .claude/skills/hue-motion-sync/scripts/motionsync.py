#!/usr/bin/env python3
"""Motion-color ambilight: drive the principal Hue light from the pixels that *changed*.

Instead of averaging the whole screen (that's hue-screen-sync), this looks at two
consecutive frames, finds the pixels that changed between them, averages the current
color of just those changed pixels, and streams that single "dominant motion color"
to every light (the principal color leads the room).

Why changed pixels? On a mostly-static screen the moving content (a video, a game,
a scrolling page) is what your eye is drawn to, so its color is the one that should
drive the lights. A whole-screen average gets muddied by static chrome/wallpaper;
the changed-pixel average tracks the action.

Brightness is pushed to maximum by default (the dominant hue is kept but its value
is maxed in HSV) so the room stays bright and saturated rather than dim.

Runs on the live X11 session (XFCE here). Set DISPLAY if running detached, e.g.
    DISPLAY=:1.0 python motionsync.py
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


def to_max_bright(rgb, sat, max_bright):
    """Keep the hue of the dominant color but push value to max (and tweak saturation)."""
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, s * sat)
    if max_bright:
        v = 1.0                       # brightness at maximum (user default)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def main():
    ap = argparse.ArgumentParser(description="Motion-color ambilight -> Hue principal light")
    ap.add_argument("--duration", type=float, default=0.0, help="seconds; 0 = run until stopped")
    ap.add_argument("--fps", type=float, default=18.0, help="target capture rate (capture-bound, ~14-20)")
    ap.add_argument("--monitor", type=int, default=0, help="0=all screens, 1/2=a specific monitor")
    ap.add_argument("--threshold", type=int, default=25,
                    help="per-pixel change threshold (0-255); a pixel counts as 'changed' if any "
                         "channel moves more than this between two frames")
    ap.add_argument("--min-frac", type=float, default=0.001,
                    help="if fewer than this fraction of pixels changed, keep the last color "
                         "(stops a static screen from going black)")
    ap.add_argument("--sat", type=float, default=1.4, help="saturation boost (1=raw)")
    ap.add_argument("--no-max-bright", action="store_true",
                    help="keep the dominant color's own brightness instead of forcing max")
    ap.add_argument("--smooth", type=float, default=0.6,
                    help="EMA factor 0..1 (higher=smoother/slower); the changed-pixel color is "
                         "jumpy frame-to-frame, so some smoothing keeps the room calm")
    ap.add_argument("--step", type=int, default=8, help="pixel subsample stride (bigger=faster, coarser)")
    args = ap.parse_args()

    n = len(CHANNELS)
    dt = 1.0 / args.fps
    max_bright = not args.no_max_bright
    prev_frame = None        # last captured frame (for the diff)
    color = None             # last dominant color sent (smoothed, persists on static screens)

    with mss.MSS() as sct, HueStream() as s:
        mon = sct.monitors[args.monitor]
        print(f"capturing monitor[{args.monitor}] {mon['width']}x{mon['height']} -> "
              f"changed-pixel dominant color on all lights "
              f"(threshold={args.threshold}, max_bright={max_bright})")
        t0 = time.monotonic(); frames = 0; still = 0
        try:
            while True:
                t = time.monotonic() - t0
                if args.duration and t >= args.duration:
                    break
                shot = sct.grab(mon)
                img = np.frombuffer(shot.rgb, dtype=np.uint8).reshape(shot.height, shot.width, 3)
                img = img[::args.step, ::args.step].astype(np.int16)   # subsample for speed

                if prev_frame is not None and prev_frame.shape == img.shape:
                    diff = np.abs(img - prev_frame).max(axis=2)        # biggest channel move per pixel
                    mask = diff > args.threshold
                    changed = mask.sum()
                    if changed >= args.min_frac * mask.size:
                        avg = tuple(int(c) for c in img[mask].mean(axis=0))
                        target = to_max_bright(avg, args.sat, max_bright)
                        if color is None:
                            color = target
                        else:                                          # temporal smoothing
                            a = args.smooth
                            color = tuple(int(a * p + (1 - a) * c) for p, c in zip(color, target))
                    else:
                        still += 1                                     # too static; keep last color
                prev_frame = img

                if color is not None:
                    if not s.send([color] * n):
                        print("stream closed early; see /tmp/huestream_openssl.log", file=sys.stderr)
                        break
                frames += 1
                time.sleep(max(0, dt - (time.monotonic() - t0 - t)))
        except KeyboardInterrupt:
            print("\nstopped.")
    el = time.monotonic() - t0
    print(f"motion-sync: {frames} frames in {el:.1f}s (~{frames/max(el,1e-9):.0f} fps), "
          f"{still} static frames held the previous color")


if __name__ == "__main__":
    main()
