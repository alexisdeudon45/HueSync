#!/usr/bin/env python3
"""
Real Hue Entertainment streaming for smooth, fast color effects on the Home
Entertainment area — far faster than the rate-limited REST API.

How it works:
  1. Starts the v2 entertainment_configuration ("Home Entertainment") via the
     CLIP v2 API (action=start).
  2. Opens a DTLS-PSK connection to the bridge on UDP 2100 using openssl
     s_client as the transport (PSK identity = application key, PSK = clientkey).
  3. Streams HueStream 2.0 packets at ~50 Hz, cycling color across all channels.
  4. On exit, stops the entertainment_configuration and tears down DTLS.

Credentials (application key + clientkey) are required for DTLS. They are read
from ~/.hue-mcp/stream.json, falling back to huenicorn's config. A clientkey is
only issued at registration time with generateclientkey=true; we reuse an
existing one rather than re-pairing.

Examples:
    python hue_stream.py                       # 20s rainbow sweep, ~50 Hz
    python hue_stream.py --effect rainbow --duration 30 --hz 50
    python hue_stream.py --effect strobe --color 255,0,0
    python hue_stream.py --effect pulse --color 0,80,255
"""
import argparse
import colorsys
import json
import math
import os
import ssl
import subprocess
import sys
import time
import urllib.request

BRIDGE_IP = "192.168.178.37"
CONFIG_ID = "c108aaae-b53c-4780-b902-5a0e7e6232b6"  # v2 "Home Entertainment", channels 0-6
CHANNELS = [0, 1, 2, 3, 4, 5, 6]
STREAM_CREDS = os.path.expanduser("~/.hue-mcp/stream.json")
HUENICORN_CFG = os.path.expanduser("~/.config/huenicorn/config.json")


def load_creds() -> tuple[str, str]:
    for path, getter in (
        (STREAM_CREDS, lambda d: (d["username"], d["clientkey"])),
        (HUENICORN_CFG, lambda d: (d["credentials"]["username"], d["credentials"]["clientkey"])),
    ):
        if os.path.exists(path):
            try:
                return getter(json.load(open(path)))
            except (KeyError, json.JSONDecodeError, OSError):
                continue
    sys.exit("No streaming credentials (username+clientkey) found. Need a clientkey "
             "from a generateclientkey registration.")


def clip(method: str, username: str, body: dict | None = None):
    url = f"https://{BRIDGE_IP}/clip/v2/resource/entertainment_configuration/{CONFIG_ID}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"hue-application-key": username,
                                          "Content-Type": "application/json"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=6) as r:
        return json.loads(r.read())


def hue_stream_packet(rgb16_per_channel: list[tuple[int, int, int]]) -> bytes:
    p = bytearray(b"HueStream")
    p += bytes([0x02, 0x00])          # protocol version 2.0
    p += bytes([0x00])                # sequence id (ignored)
    p += bytes([0x00, 0x00])          # reserved
    p += bytes([0x00])                # color space: 0 = RGB
    p += bytes([0x00])                # reserved
    p += CONFIG_ID.encode("ascii")    # 36-byte entertainment config id
    for ch, (r, g, b) in zip(CHANNELS, rgb16_per_channel):
        p += bytes([ch])
        p += r.to_bytes(2, "big") + g.to_bytes(2, "big") + b.to_bytes(2, "big")
    return bytes(p)


def rgb16(r8: int, g8: int, b8: int) -> tuple[int, int, int]:
    return (r8 * 257, g8 * 257, b8 * 257)


def color_for(effect: str, t: float, base: tuple[int, int, int],
              phase: float = 0.0) -> tuple[int, int, int]:
    """Return an 8-bit RGB for a given effect at time t (seconds).

    `phase` shifts the effect per channel (0..1 of a cycle) — used by the
    principal-driven 'wave' effect so followers lag the principal.
    """
    if effect in ("rainbow", "wave"):
        r, g, b = colorsys.hsv_to_rgb((t * 0.3 + phase) % 1.0, 1.0, 1.0)
        return (int(r * 255), int(g * 255), int(b * 255))
    if effect == "strobe":
        on = int(t * 12) % 2 == 0  # ~6 Hz on/off
        return base if on else (0, 0, 0)
    if effect == "pulse":
        k = (math.sin((t * 0.5 - phase) * 2 * math.pi) + 1) / 2  # 0.5 Hz breathe
        return tuple(int(c * k) for c in base)
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Smooth Hue Entertainment streaming on Home")
    ap.add_argument("--effect", choices=["rainbow", "wave", "strobe", "pulse", "solid"], default="rainbow")
    ap.add_argument("--color", default="255,0,0", help="Base color 'r,g,b' for strobe/pulse/solid")
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--hz", type=float, default=50.0, help="Update rate (Hz), up to ~50-60")
    ap.add_argument("--principal", type=int, default=0,
                    help="Channel that leads the 'wave' effect (0-6); others phase-lag it")
    ap.add_argument("--spread", type=float, default=0.14,
                    help="Per-channel phase offset for 'wave'/'pulse' (fraction of a cycle)")
    ap.add_argument("--debug", action="store_true", help="Show openssl handshake output")
    args = ap.parse_args()

    # Order channels so the principal leads; each subsequent channel lags by --spread.
    principal = args.principal if args.principal in CHANNELS else CHANNELS[0]
    order = [principal] + [c for c in CHANNELS if c != principal]
    phase = {ch: i * args.spread for i, ch in enumerate(order)}

    try:
        base = tuple(int(x) for x in args.color.split(","))
        assert len(base) == 3
    except (ValueError, AssertionError):
        return print("Error: --color must be 'r,g,b'", file=sys.stderr) or 2

    username, clientkey = load_creds()

    print(f"Starting entertainment stream on '{CONFIG_ID}' ...")
    clip("PUT", username, {"action": "start"})
    time.sleep(0.4)

    cmd = ["openssl", "s_client", "-dtls1_2", "-connect", f"{BRIDGE_IP}:2100",
           "-cipher", "PSK-AES128-GCM-SHA256",
           "-psk_identity", username, "-psk", clientkey, "-quiet"]
    errlog = open("/tmp/hue_stream_openssl.log", "w")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=(None if args.debug else subprocess.DEVNULL),
                            stderr=(None if args.debug else errlog))
    time.sleep(1.5)  # let the DTLS handshake complete
    if proc.poll() is not None:
        clip("PUT", username, {"action": "stop"})
        return print("DTLS handshake failed; see /tmp/hue_stream_openssl.log", file=sys.stderr) or 1

    interval = 1.0 / args.hz
    t0 = time.monotonic()
    frames = 0
    try:
        while True:
            t = time.monotonic() - t0
            if t >= args.duration:
                break
            if args.effect in ("wave", "pulse"):
                # principal-driven: each channel gets the effect shifted by its phase
                colors = [rgb16(*color_for(args.effect, t, base, phase[ch])) for ch in CHANNELS]
            else:
                colors = [rgb16(*color_for(args.effect, t, base))] * len(CHANNELS)
            pkt = hue_stream_packet(colors)
            try:
                proc.stdin.write(pkt)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                print("Stream pipe closed early; see /tmp/hue_stream_openssl.log", file=sys.stderr)
                break
            frames += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        clip("PUT", username, {"action": "stop"})
        errlog.close()

    elapsed = time.monotonic() - t0
    lead = f", principal=ch{principal}" if args.effect in ("wave", "pulse") else ""
    print(f"Streamed {frames} frames over {elapsed:.1f}s "
          f"(~{frames/elapsed:.0f} fps) — effect '{args.effect}'{lead} on 7 channels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
