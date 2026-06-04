#!/usr/bin/env python3
"""Lock a V4L2 webcam's auto-white-balance and auto-exposure (pure Python, no v4l2-ctl).

Why this exists: when you flood a room with one color, a webcam's auto white-balance
fights you — it sees the strong green cast and "corrects" it back toward neutral, so the
SAME green lamp setting reads as vivid green one second and washed-out teal the next.
Auto-exposure does the same to brightness. That makes the illumination eval drift and
untrustworthy. Disabling both freezes the camera so a given lamp setting always reads the
same way, which is what lets the optimization loop compare settings fairly.

This pokes the standard V4L2 controls directly with ioctl():
  AUTO_WHITE_BALANCE -> 0 (off), then a fixed WHITE_BALANCE_TEMPERATURE
  EXPOSURE_AUTO      -> 1 (manual), then a fixed EXPOSURE_ABSOLUTE
Controls a given camera doesn't support are skipped (it just prints that it couldn't set
them). Run --status to see current values.

    python lock_camera.py                 # lock with sensible defaults
    python lock_camera.py --wb 4600 --exposure 250
    python lock_camera.py --auto           # hand control back to the camera
"""
import argparse
import fcntl
import struct
import sys

DEVICE_DEFAULT = "/dev/video0"

# V4L2 control IDs
V4L2_CID_BASE = 0x00980900
AUTO_WHITE_BALANCE = V4L2_CID_BASE + 12       # 0=manual, 1=auto
WHITE_BALANCE_TEMPERATURE = V4L2_CID_BASE + 26
V4L2_CID_CAMERA_CLASS_BASE = 0x009A0900
EXPOSURE_AUTO = V4L2_CID_CAMERA_CLASS_BASE + 1     # 0=auto, 1=manual, 2/3=priority
EXPOSURE_ABSOLUTE = V4L2_CID_CAMERA_CLASS_BASE + 2

# ioctl numbers for struct v4l2_control { __u32 id; __s32 value; } (8 bytes), type 'V'(86)
#   _IOWR: (3<<30)|(8<<16)|(86<<8)|nr
VIDIOC_G_CTRL = (3 << 30) | (8 << 16) | (86 << 8) | 27
VIDIOC_S_CTRL = (3 << 30) | (8 << 16) | (86 << 8) | 28

NAMES = {AUTO_WHITE_BALANCE: "auto_white_balance", WHITE_BALANCE_TEMPERATURE: "wb_temperature",
         EXPOSURE_AUTO: "exposure_auto", EXPOSURE_ABSOLUTE: "exposure_absolute"}


def get_ctrl(fd, cid):
    buf = struct.pack("Ii", cid, 0)
    try:
        res = fcntl.ioctl(fd, VIDIOC_G_CTRL, buf)
        return struct.unpack("Ii", res)[1]
    except OSError:
        return None


def set_ctrl(fd, cid, value):
    try:
        fcntl.ioctl(fd, VIDIOC_S_CTRL, struct.pack("Ii", cid, value))
        return True
    except OSError as e:
        print(f"  could not set {NAMES.get(cid, hex(cid))} = {value}: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description="Lock webcam white-balance and exposure via V4L2")
    ap.add_argument("--device", default=DEVICE_DEFAULT)
    ap.add_argument("--wb", type=int, default=4600, help="fixed white-balance temperature (K-ish units)")
    ap.add_argument("--exposure", type=int, default=300, help="fixed exposure (device units)")
    ap.add_argument("--auto", action="store_true", help="restore auto WB + auto exposure, then exit")
    ap.add_argument("--status", action="store_true", help="print current control values, then exit")
    args = ap.parse_args()

    with open(args.device, "rb") as f:
        fd = f.fileno()
        if args.status:
            for cid in (AUTO_WHITE_BALANCE, WHITE_BALANCE_TEMPERATURE, EXPOSURE_AUTO, EXPOSURE_ABSOLUTE):
                print(f"  {NAMES[cid]:24} = {get_ctrl(fd, cid)}")
            return 0
        if args.auto:
            set_ctrl(fd, AUTO_WHITE_BALANCE, 1)
            # EXPOSURE_AUTO is a menu; cameras vary in which "auto" they expose. Many accept
            # 3 (aperture priority) but reject 0 (auto). Try the common ones in order.
            if not (set_ctrl(fd, EXPOSURE_AUTO, 3) or set_ctrl(fd, EXPOSURE_AUTO, 0)):
                print("  (could not restore auto exposure; set it in your camera app)", file=sys.stderr)
            print("camera back to auto white-balance + auto exposure")
            return 0
        # Order matters: disable the auto control before setting the manual value.
        set_ctrl(fd, AUTO_WHITE_BALANCE, 0)
        set_ctrl(fd, WHITE_BALANCE_TEMPERATURE, args.wb)
        set_ctrl(fd, EXPOSURE_AUTO, 1)
        set_ctrl(fd, EXPOSURE_ABSOLUTE, args.exposure)
        print(f"locked: wb={args.wb}, exposure={args.exposure} (device {args.device})")
        print("verify with --status; loosen/tighten with --wb / --exposure; --auto to undo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
