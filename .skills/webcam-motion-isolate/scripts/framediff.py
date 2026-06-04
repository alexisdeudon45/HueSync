#!/usr/bin/env python3
"""Capture N webcam frames 1s apart, find the pixels COMMON to all of them
(the static background), and remove them — keeping only what changed.

The idea: over a few seconds the background (wall, desk, chair) barely moves, so a
pixel that shows the background reads almost the same value in every frame. Anything
that moved — a person, a hand, a passing object — lands on different pixels at
different times, so those pixels vary between frames. So "common across all frames"
is a good proxy for "background", and removing it isolates the motion.

For each pixel we measure how much it varies across the N frames (the range,
max minus min, taken over the worst color channel). If that variation is below a
threshold the pixel is judged COMMON/static and removed (made transparent); otherwise
it's kept from the last frame. Output is a PNG with an alpha channel so the removed
background is genuinely gone (transparent), not just painted black.

Only ffmpeg + numpy are needed — frames are grabbed as raw RGB (no JPEG decode) and
the result is encoded to PNG by piping raw RGBA back through ffmpeg, so there's no
dependency on PIL/OpenCV.

Usage:
    python framediff.py                      # 5 frames, 1s apart, 640x480
    python framediff.py --frames 8 --interval 0.5
    python framediff.py --threshold 40       # higher = remove more (more counts as common)
    python framediff.py -o /tmp/moved.png --keep-frames
"""
import argparse
import datetime
import os
import subprocess
import sys
import time

import numpy as np


def capture_frame(device, w, h, warmup):
    """Grab one settled frame as an (h, w, 3) uint8 array via ffmpeg raw RGB.

    We capture `warmup` frames and keep the last one: a freshly opened camera needs a
    few frames for auto-exposure/white-balance to converge, and each ffmpeg call
    reopens the device, so we warm up on every capture."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "v4l2", "-video_size", f"{w}x{h}", "-i", device,
        "-frames:v", str(warmup), "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
    ]
    r = subprocess.run(cmd, capture_output=True)
    frame_bytes = w * h * 3
    if r.returncode != 0 or len(r.stdout) < frame_bytes:
        err = r.stderr.decode(errors="replace").strip() or "unknown error"
        print(f"capture failed on {device}:\n{err}", file=sys.stderr)
        if "usy" in err:  # "Device or resource busy"
            print("-> camera is in use by another app; close it and retry.", file=sys.stderr)
        sys.exit(1)
    last = r.stdout[-frame_bytes:]                       # keep the settled frame
    return np.frombuffer(last, dtype=np.uint8).reshape(h, w, 3)


def encode_png(rgba, out_path):
    """Write an (h, w, 4) uint8 RGBA array to a PNG by piping it through ffmpeg."""
    h, w = rgba.shape[:2]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-i", "-",
        "-y", out_path,
    ]
    p = subprocess.run(cmd, input=rgba.tobytes(), capture_output=True)
    if p.returncode != 0 or not os.path.exists(out_path):
        print(p.stderr.decode(errors="replace"), file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Remove pixels common to N webcam frames (isolate motion)")
    ap.add_argument("--frames", type=int, default=5, help="how many frames to capture (default 5)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between captures (default 1.0)")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--size", default="640x480", help="WxH (default 640x480)")
    ap.add_argument("--warmup", type=int, default=12, help="exposure warm-up frames per capture")
    ap.add_argument("--threshold", type=int, default=30,
                    help="a pixel is 'common' (removed) if its variation across frames is <= this "
                         "(0-255). Higher removes more; lower keeps more.")
    ap.add_argument("-o", "--output", default=None,
                    help="output PNG (default ~/Pictures/webcam/isolated_<timestamp>.png)")
    ap.add_argument("--keep-frames", action="store_true",
                    help="also save the individual captured frames next to the output")
    args = ap.parse_args()

    w, h = (int(x) for x in args.size.lower().split("x"))

    print(f"capturing {args.frames} frames, {args.interval}s apart, {w}x{h}...")
    frames = []
    for i in range(args.frames):
        frames.append(capture_frame(args.device, w, h, args.warmup))
        print(f"  frame {i + 1}/{args.frames}")
        if i < args.frames - 1:
            time.sleep(args.interval)

    stack = np.stack(frames).astype(np.int16)            # (N, h, w, 3)
    # Variation per pixel = range across frames, worst channel. Small => same in every
    # frame => background/common. This is cheap and intuitive; a person who moved leaves
    # a high-variation trail everywhere they were, which is exactly what we keep.
    variation = (stack.max(0) - stack.min(0)).max(2)     # (h, w)
    common = variation <= args.threshold                 # True where static/common

    ref = frames[-1]                                     # keep the most recent look of moved pixels
    alpha = np.where(common, 0, 255).astype(np.uint8)    # transparent where common
    rgba = np.dstack([ref, alpha])

    out = args.output
    if out is None:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.expanduser(f"~/Pictures/webcam/isolated_{stamp}.png")
    encode_png(rgba, out)

    removed = float(common.mean()) * 100
    print(f"saved {out}  ({100 - removed:.1f}% of pixels kept, {removed:.1f}% removed as common)")

    if args.keep_frames:
        base = os.path.splitext(out)[0]
        for i, f in enumerate(frames):
            encode_png(np.dstack([f, np.full((h, w), 255, np.uint8)]), f"{base}_frame{i + 1}.png")
        print(f"  saved {args.frames} source frames as {base}_frame*.png")


if __name__ == "__main__":
    main()
