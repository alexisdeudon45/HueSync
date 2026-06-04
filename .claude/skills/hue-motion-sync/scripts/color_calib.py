#!/usr/bin/env python3
"""Shared Hue color calibration: map a desired color to the RGB you must actually send.

The room does not render the color you command 1:1 — the lamp gamut + the bridge's
gamut-mapping + the camera's response bend it. We measured that bend by sweeping the hue
wheel and reading the room back with the webcam (camera locked so the numbers are stable).
This module turns those measurements into two operations both skills need:

  * invert(target_room_hue) -> the commanded hue that best produces it
  * correct_rgb(rgb)        -> remap a desired-display RGB to the RGB to send

Crucially the bend DIFFERS by control path, so there are two anchor sets:
  REST_ANCHORS    — REST / xy + separate `bri` (hue-room-illumination / set_room)
  STREAM_ANCHORS  — Entertainment streaming, RGB carries brightness (hue-motion-sync)
On REST the magnitude is thrown away (color = chromaticity, light = bri); on the stream the
RGB magnitude IS the brightness, so correct_rgb preserves the original value there.

Each anchor is (commanded_hue°, measured_room_hue°, illuminated_pct, purity_pct) at full
saturation & max output. purity lets invert() skip commanded hues that don't render
faithfully (the green/yellow-green band collapses — REST toward ~143°, stream toward ~170°).
These constants are specific to THIS room+webcam at the locked WB/exposure used to measure
them; re-sweep and replace them if the room, camera, or lock changes. Numbers, not magic.

This file is kept as a copy in each skill that needs it (like huestream.py) so skills stay
self-contained — keep the copies in sync.
"""
import colorsys

import numpy as np

# (commanded_hue, room_hue, illuminated_pct, purity_pct)
REST_ANCHORS = [
    (0, 0, 60, 99), (30, 3, 57, 99), (60, 48, 27, 95), (90, 143, 22, 1), (120, 143, 22, 96),
    (150, 149, 23, 98), (180, 187, 22, 98), (210, 225, 42, 99), (240, 243, 49, 98),
    (270, 269, 42, 98), (300, 319, 48, 67), (330, 354, 56, 99),
]
STREAM_ANCHORS = [
    (0, 3, 96, 99), (30, 13, 99, 99), (60, 33, 94, 86), (90, 169, 81, 0), (120, 174, 81, 0),
    (150, 179, 86, 96), (180, 200, 100, 86), (210, 229, 100, 90), (240, 246, 100, 93),
    (270, 258, 100, 96), (300, 278, 100, 85), (330, 315, 88, 98),
]


def _circdist(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)


class HueCalibration:
    def __init__(self, anchors):
        self.cmd, self.room, self.gain, self.purity = (np.array(c, float) for c in zip(*anchors))

    def room_hue(self, cmd):
        return float(np.interp(cmd % 360, self.cmd, self.room))

    def gain_of(self, cmd):
        return float(np.interp(cmd % 360, self.cmd, self.gain))

    def purity_of(self, cmd):
        return float(np.interp(cmd % 360, self.cmd, self.purity))

    def invert(self, target_room_hue, min_purity=50):
        """Commanded hue whose predicted room hue is closest to target, ignoring commanded
        hues that don't render faithfully (low purity). Returns (cmd_hue, residual_deg)."""
        best, best_err = 0.0, 1e9
        for c in np.arange(0, 360, 1.0):
            if self.purity_of(c) < min_purity:
                continue
            e = _circdist(self.room_hue(c), target_room_hue)
            if e < best_err:
                best, best_err = float(c), e
        return best, best_err

    def command_rgb(self, target_room_hue, sat=1.0, val=1.0):
        cmd, resid = self.invert(target_room_hue)
        r, g, b = colorsys.hsv_to_rgb(cmd / 360.0, sat, val)
        return (round(r * 255), round(g * 255), round(b * 255)), cmd, resid, self.gain_of(cmd)

    def correct_rgb(self, rgb, max_residual=30):
        """Remap a desired-display RGB to the RGB to send so the room shows that hue.
        Saturation and value are preserved (value matters on the stream, where it = brightness).
        If the desired hue can't be rendered (residual too big), return it unchanged rather than
        distorting it into a far-off hue."""
        h, s, v = colorsys.rgb_to_hsv(*[x / 255.0 for x in rgb])
        if s < 0.12:                       # near-neutral: no hue to correct
            return tuple(rgb)
        cmd, resid = self.invert(h * 360.0)
        if resid > max_residual:
            return tuple(rgb)
        r, g, b = colorsys.hsv_to_rgb(cmd / 360.0, s, v)
        return (round(r * 255), round(g * 255), round(b * 255))


REST = HueCalibration(REST_ANCHORS)
STREAM = HueCalibration(STREAM_ANCHORS)
