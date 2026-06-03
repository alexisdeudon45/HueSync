#!/usr/bin/env python3
"""Gradient-noise (Perlin/Simplex) lighting on the Home Entertainment area.

Demonstrates and runs gradient-noise driven color, the organic alternative to a
rigid color sweep. Effects:

  noise    : per-channel 1D fBm over time   -> each light breathes independently
  spatial  : 2D fBm over (light position, time) -> an organic wave across the room
  warp     : domain-warped fBm -> swirling, liquid look

With --music, audio (captured from the system monitor via parec) MODULATES the
noise: loudness -> speed & brightness, treble -> hue shift, onsets -> a breath.
This keeps the smoothness of noise while reacting to sound (no harsh strobing).

Why gradient noise (vs random): it is continuous and band-limited, so colors flow
smoothly with no flicker; summing octaves (fBm) adds natural detail.
"""
import argparse
import colorsys
import math
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))
from huestream import HueStream, CHANNELS  # noqa

from opensimplex import OpenSimplex  # noqa

GEN_H = OpenSimplex(seed=101)
GEN_S = OpenSimplex(seed=202)
GEN_V = OpenSimplex(seed=303)
GEN_W = OpenSimplex(seed=404)


def fbm(gen, x, y, octaves=3):
    """Fractal Brownian motion: sum of noise octaves, result in ~[-1,1]."""
    amp, freq, total, norm = 1.0, 1.0, 0.0, 0.0
    for _ in range(octaves):
        total += amp * gen.noise2(x * freq, y * freq)
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm


def unit(v):  # [-1,1] -> [0,1]
    return (v + 1) * 0.5


class Audio:
    """Background audio level reader via `parec` (PulseAudio/PipeWire monitor). Optional."""
    def __init__(self, source=None):
        import numpy as np
        self.np = np
        self.rms = 0.0; self.bass = 0.0; self.treble = 0.0; self.onset = 0.0
        self._prev = 0.0
        self.source = source or self._default_monitor()
        self.alive = True
        threading.Thread(target=self._run, daemon=True).start()

    def _default_monitor(self):
        import subprocess
        try:
            sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True).stdout.strip()
            return sink + ".monitor" if sink else "@DEFAULT_MONITOR@"
        except Exception:
            return "@DEFAULT_MONITOR@"

    def _run(self):
        import subprocess
        np = self.np
        rate, n = 44100, 1024
        p = subprocess.Popen(["parec", "--format=s16le", f"--rate={rate}", "--channels=1",
                              "-d", self.source], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        win = np.hanning(n)
        while self.alive:
            raw = p.stdout.read(n * 2)
            if len(raw) < n * 2:
                break
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            self.rms = float(np.sqrt(np.mean(x * x)))
            spec = np.abs(np.fft.rfft(x * win))
            freqs = np.fft.rfftfreq(n, 1 / rate)
            self.bass = float(spec[(freqs >= 20) & (freqs < 250)].mean())
            self.treble = float(spec[(freqs >= 4000)].mean())
            flux = max(0.0, self.bass - self._prev); self._prev = self.bass
            self.onset = min(1.0, flux / 5.0)
        p.terminate()


def main():
    ap = argparse.ArgumentParser(description="Gradient-noise lighting")
    ap.add_argument("--effect", choices=["noise", "spatial", "warp"], default="noise")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--fps", type=float, default=40.0)
    ap.add_argument("--speed", type=float, default=0.15, help="base time speed of the noise")
    ap.add_argument("--octaves", type=int, default=3)
    ap.add_argument("--sat", type=float, default=1.0, help="saturation 0..1")
    ap.add_argument("--music", action="store_true", help="modulate the noise with system audio")
    ap.add_argument("--source", default=None, help="audio monitor source (default: default sink monitor)")
    ap.add_argument("--per-light", action="store_true",
                    help="give each light its own color (default: one principal color shared by ALL lights)")
    args = ap.parse_args()

    audio = None
    if args.music:
        try:
            audio = Audio(args.source)
            print(f"music: reading {audio.source}")
        except Exception as e:
            print(f"music disabled ({e}); run `uv pip install numpy` and ensure parec works", file=sys.stderr)

    n = len(CHANNELS)
    dt = 1.0 / args.fps
    with HueStream() as s:
        t0 = time.monotonic(); frames = 0
        try:
            while True:
                t = time.monotonic() - t0
                if t >= args.duration:
                    break
                speed = args.speed
                hue_shift = 0.0; vboost = 0.0
                if audio:
                    speed *= 1.0 + 3.0 * audio.rms
                    hue_shift = 0.3 * min(1.0, audio.treble / 3.0)
                    vboost = min(0.6, 2.5 * audio.rms) + 0.4 * audio.onset
                def channel_color(i):
                    pos = i / max(1, n - 1)
                    if args.effect == "noise":
                        h = unit(fbm(GEN_H, t * speed, i * 1.3, args.octaves))
                        sv = unit(fbm(GEN_S, t * speed, 50 + i * 1.3, args.octaves))
                        v = unit(fbm(GEN_V, t * speed, 99 + i * 1.3, args.octaves))
                    elif args.effect == "spatial":
                        h = unit(fbm(GEN_H, pos * 2.0, t * speed, args.octaves))
                        sv = unit(fbm(GEN_S, pos * 2.0 + 10, t * speed, args.octaves))
                        v = unit(fbm(GEN_V, pos * 2.0 + 20, t * speed, args.octaves))
                    else:  # warp
                        q = fbm(GEN_W, pos * 2.0, t * speed, args.octaves)
                        h = unit(fbm(GEN_H, pos * 2.0 + q, t * speed + q, args.octaves))
                        sv = unit(fbm(GEN_S, pos * 2.0 + q + 5, t * speed, args.octaves))
                        v = unit(fbm(GEN_V, pos * 2.0 + q + 9, t * speed, args.octaves))
                    hue = (h + hue_shift) % 1.0
                    sat = max(0.0, min(1.0, args.sat * (0.6 + 0.4 * sv)))
                    val = max(0.0, min(1.0, 0.35 + 0.55 * v + vboost))
                    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
                    return (int(r * 255), int(g * 255), int(b * 255))

                # Default: one PRINCIPAL color (channel 0) shared by every light.
                # --per-light gives each light its own sample (the old behaviour).
                if args.per_light:
                    colors = [channel_color(i) for i in range(n)]
                else:
                    colors = [channel_color(0)] * n
                if not s.send(colors):
                    print("stream closed early; see /tmp/huestream_openssl.log", file=sys.stderr)
                    break
                frames += 1
                time.sleep(dt)
        except KeyboardInterrupt:
            print("\nstopped.")
        finally:
            if audio:
                audio.alive = False
    el = time.monotonic() - t0
    print(f"{args.effect}: {frames} frames in {el:.1f}s (~{frames/el:.0f} fps){' + music' if audio else ''}")


if __name__ == "__main__":
    main()
