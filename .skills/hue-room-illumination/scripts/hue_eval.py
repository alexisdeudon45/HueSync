#!/usr/bin/env python3
"""EVAL for room illumination: how much of the room is lit, and is it the target color?

This is the scoring half of the hue-room-illumination loop. It takes a webcam frame of
the room (captured here, or an existing --image) and a target color, then reports, as
plain numbers you can optimize against:

  illuminated_pct   - % of the frame bright enough to count as "lit" (value >= --v-thresh)
  lit_in_color_pct  - % of the frame that is BOTH lit AND the target color
                      (this is the headline metric: "the room, illuminated, in this color")
  color_purity_pct  - of the lit pixels, what fraction match the target color
  mean_lit_rgb/hue  - the actual average color of the lit area (so you can see which way
                      it's off: too white, wrong hue, too dim...)

Why these: the goal is "the whole room illuminated in the chosen color". Two things can be
wrong — not enough light (raise brightness) or the wrong color (the lit area is white or
the wrong hue → push saturation / fix the lamp color). Splitting the score into an
illumination part and a color part tells the optimizer WHICH knob to turn.

Targets: a name (red orange yellow green cyan blue purple magenta white warm) or "r,g,b".
Neutral targets (white/warm) are matched by low saturation instead of a hue.

Only ffmpeg + numpy are used (no PIL/OpenCV). Run with the hue venv python, which has both:
    /home/tor/hue-mcp/.venv/bin/python hue_eval.py --target green --json
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

# name -> (representative RGB, target hue in degrees or None for neutral)
NAMED = {
    "red": ((255, 0, 0), 0), "orange": ((255, 110, 0), 30), "yellow": ((255, 220, 0), 55),
    "green": ((0, 255, 0), 120), "cyan": ((0, 255, 255), 180), "blue": ((0, 60, 255), 225),
    "purple": ((150, 0, 255), 275), "magenta": ((255, 0, 200), 320),
    "white": ((255, 255, 255), None), "warm": ((255, 180, 90), None),
}


def capture(device, w, h, warmup):
    """One settled webcam frame as (h, w, 3) uint8 via ffmpeg raw RGB (keep last frame)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2",
           "-video_size", f"{w}x{h}", "-i", device, "-frames:v", str(warmup),
           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    r = subprocess.run(cmd, capture_output=True)
    fb = w * h * 3
    if r.returncode != 0 or len(r.stdout) < fb:
        print(r.stderr.decode(errors="replace").strip(), file=sys.stderr)
        sys.exit(1)
    return np.frombuffer(r.stdout[-fb:], dtype=np.uint8).reshape(h, w, 3)


def load_image(path):
    """Decode any image file to (h, w, 3) uint8 using ffprobe (size) + ffmpeg (pixels)."""
    dims = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True).stdout.strip()
    w, h = (int(x) for x in dims.split("x"))
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
         "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw[: w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def rgb_to_hsv(rgb):
    """Vectorized RGB->HSV. rgb float (...,3) in [0,1]. Returns h[0,360), s,v in [0,1]."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    df = mx - mn
    h = np.zeros_like(mx)
    nz = df > 1e-6
    rmax = nz & (mx == r); h[rmax] = (60 * ((g - b)[rmax] / df[rmax])) % 360
    gmax = nz & (mx == g) & ~rmax; h[gmax] = (60 * ((b - r)[gmax] / df[gmax]) + 120) % 360
    bmax = nz & (mx == b) & ~rmax & ~gmax; h[bmax] = (60 * ((r - g)[bmax] / df[bmax]) + 240) % 360
    s = np.where(mx > 1e-6, df / np.where(mx > 1e-6, mx, 1), 0.0)
    return h, s, mx


def evaluate(img, target_hue, v_thresh, s_min, hue_tol):
    rgb = img.astype(np.float32) / 255.0
    h, s, v = rgb_to_hsv(rgb)
    lit = v >= v_thresh                                   # bright enough to be "illuminated"
    if target_hue is None:                                # neutral target: lit + low saturation
        color_ok = lit & (s < 0.25)
    else:                                                 # chromatic: lit + saturated + hue near target
        dh = np.abs(h - target_hue)
        dh = np.minimum(dh, 360 - dh)                     # shortest arc on the hue wheel
        color_ok = lit & (s >= s_min) & (dh <= hue_tol)
    total = img.shape[0] * img.shape[1]
    lit_rgb = img.reshape(-1, 3)[lit.reshape(-1)]
    mean_lit = lit_rgb.mean(0).astype(int).tolist() if lit_rgb.size else [0, 0, 0]
    mh, _, _ = rgb_to_hsv(np.array(mean_lit, np.float32) / 255.0) if lit_rgb.size else (0, 0, 0)
    return {
        "illuminated_pct": round(float(lit.mean()) * 100, 1),
        "lit_in_color_pct": round(float(color_ok.mean()) * 100, 1),
        "color_purity_pct": round(float(color_ok.sum()) / max(1, int(lit.sum())) * 100, 1),
        "mean_brightness": round(float(v.mean()), 3),
        "mean_lit_rgb": mean_lit,
        "mean_lit_hue": round(float(mh), 0) if lit_rgb.size else None,
    }


def verdict(m, target_hue):
    """Plain-language hint about which knob to turn, for the optimizer loop."""
    if m["illuminated_pct"] < 45:
        return "TOO DIM — raise brightness (and/or the room has dark zones the lamp can't reach)."
    if target_hue is not None and m["color_purity_pct"] < 60:
        if m["mean_lit_hue"] is not None:
            return (f"LIT BUT WRONG COLOR — lit area averages hue {m['mean_lit_hue']:.0f}°, "
                    f"target {target_hue}°. Push saturation up / kill competing light.")
        return "LIT BUT WRONG COLOR — push saturation up."
    if m["lit_in_color_pct"] >= 70:
        return "GOOD — room is broadly lit in the target color."
    return "PARTIAL — increase brightness or saturation to cover more of the room."


def main():
    ap = argparse.ArgumentParser(description="Eval: % of room illuminated, and in the target color")
    ap.add_argument("--target", default="white", help="color name or 'r,g,b' (default white)")
    ap.add_argument("--image", help="evaluate an existing image instead of capturing")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--size", default="640x480")
    ap.add_argument("--warmup", type=int, default=12)
    ap.add_argument("--v-thresh", type=float, default=0.30, help="brightness to count a pixel as lit")
    ap.add_argument("--s-min", type=float, default=0.18, help="min saturation for a chromatic match")
    ap.add_argument("--hue-tol", type=float, default=35, help="hue tolerance in degrees")
    ap.add_argument("-o", "--save", help="save the captured frame to this path")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON only")
    args = ap.parse_args()

    if args.target.lower() in NAMED:
        _, target_hue = NAMED[args.target.lower()]
    else:
        try:
            r, g, b = (int(x) for x in args.target.split(","))
            th, ts, _ = rgb_to_hsv(np.array([r, g, b], np.float32) / 255.0)
            target_hue = None if ts < 0.15 else float(th)
        except ValueError:
            print(f"bad --target '{args.target}': use a name or 'r,g,b'", file=sys.stderr)
            return 2

    if args.image:
        img = load_image(args.image)
    else:
        w, h = (int(x) for x in args.size.lower().split("x"))
        img = capture(args.device, w, h, args.warmup)
        if args.save:
            os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-", "-y", args.save],
                           input=img.tobytes())

    m = evaluate(img, target_hue, args.v_thresh, args.s_min, args.hue_tol)
    m["target"] = args.target
    m["verdict"] = verdict(m, target_hue)

    if args.json:
        print(json.dumps(m))
    else:
        print(f"target={args.target}  illuminated={m['illuminated_pct']}%  "
              f"lit_in_color={m['lit_in_color_pct']}%  purity={m['color_purity_pct']}%")
        print(f"lit area avg RGB={m['mean_lit_rgb']} (hue {m['mean_lit_hue']}°), "
              f"mean brightness={m['mean_brightness']}")
        print(f"-> {m['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
