#!/usr/bin/env python3
"""Take a single photo from a webcam using ffmpeg (no Python deps required).

This system has no fswebcam / v4l2-ctl, but it does have ffmpeg, and the camera is a
standard V4L2 device (/dev/video0). The one non-obvious thing about grabbing a still
from a webcam is exposure: the very first frame a camera delivers is usually dark or
green because auto-exposure and white balance haven't settled. So we capture a short
burst of frames and keep only the LAST one (`-update 1` overwrites the output each
frame), which gives the sensor time to adjust — a properly lit photo instead of a
murky first frame.

Usage:
    python snap.py                       # default cam, 1280x720, save to ~/Pictures/webcam/
    python snap.py -o /tmp/me.jpg        # explicit output path
    python snap.py --device /dev/video2  # a different camera
    python snap.py --size 640x480
    python snap.py --list                # list cameras and their supported formats
"""
import argparse
import datetime
import os
import subprocess
import sys


def list_devices():
    """Show each /dev/video* node and the formats/resolutions ffmpeg reports for it."""
    nodes = sorted(p for p in os.listdir("/dev") if p.startswith("video"))
    if not nodes:
        print("No /dev/video* devices found.")
        return
    for node in nodes:
        dev = f"/dev/{node}"
        print(f"\n=== {dev} ===")
        # ffmpeg prints supported formats to stderr; a capture node lists resolutions,
        # a metadata-only node (common second node of a UVC cam) lists nothing useful.
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-f", "v4l2", "-list_formats", "all", "-i", dev],
            capture_output=True, text=True,
        ).stderr
        lines = [l for l in out.splitlines() if "Raw" in l or "Compressed" in l]
        print("\n".join(lines) if lines else "  (no capture formats — likely a metadata node)")


def snap(device, size, warmup, output):
    os.makedirs(os.path.dirname(output), exist_ok=True)
    # -frames:v <warmup> with -update 1 over a single file: each captured frame
    # overwrites the previous, so when ffmpeg stops we're left with the last (settled)
    # frame. -q:v 2 keeps JPEG quality high.
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "v4l2", "-video_size", size, "-i", device,
        "-frames:v", str(warmup), "-update", "1", "-q:v", "2", "-y", output,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(output):
        err = r.stderr.strip() or "unknown error"
        # The usual culprit is the camera already being held by another app
        # (browser, video call, the screen-sync tools don't use it but a meeting might).
        print(f"capture failed on {device}:\n{err}", file=sys.stderr)
        if "Device or resource busy" in err or "Resource busy" in err:
            print("-> the camera is in use by another application; close it and retry.",
                  file=sys.stderr)
        sys.exit(1)
    return output


def main():
    ap = argparse.ArgumentParser(description="Take a photo from a webcam via ffmpeg")
    ap.add_argument("--device", default="/dev/video0", help="V4L2 device (default /dev/video0)")
    ap.add_argument("--size", default="1280x720", help="resolution WxH (default 1280x720)")
    ap.add_argument("--warmup", type=int, default=15,
                    help="frames to capture so exposure settles; the last is kept (default 15)")
    ap.add_argument("-o", "--output", default=None,
                    help="output file (default ~/Pictures/webcam/webcam_<timestamp>.jpg)")
    ap.add_argument("--list", action="store_true", help="list cameras and supported formats, then exit")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return

    output = args.output
    if output is None:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output = os.path.expanduser(f"~/Pictures/webcam/webcam_{stamp}.jpg")

    path = snap(args.device, args.size, args.warmup, output)
    size_kb = os.path.getsize(path) / 1024
    print(f"saved {path} ({size_kb:.0f} KB, {args.size})")


if __name__ == "__main__":
    main()
