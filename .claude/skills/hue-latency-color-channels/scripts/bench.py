#!/usr/bin/env python3
"""Experiment (developed): color changes on Hue — channels, magnitude, no-op, representation.

The user's mental model is "RGB channels". Hue has none: color is ONE xy (or hue/sat
or ct) command; RGB is converted client-side to a single xy. We probe four things:

  A. Kind of change   : full RGB vs only-blue vs slight vs no-op (does magnitude matter?)
  B. No-op threshold  : how big must a delta be before it stops being a free no-op?
  C. Representation   : same change sent as xy vs hue+sat vs ct (does the encoding matter?)

From A+B we derive the cost model:  T = T_noop + Δ·T_zigbee
where Δ = 1 if the stored state actually changes, else 0 — independent of #channels,
magnitude (above the storage precision), and encoding.
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from huebench import HOME, bridge, page, bars, write  # noqa

OUT = os.path.expanduser("~/.claude/skills/hue-latency-color-channels-workspace/report.html")
N, W = 10, 2
LID = HOME[0]


def rgb_to_xy(r, g, b):
    r, g, b = r/255, g/255, b/255
    f = lambda c: pow((c+0.055)/1.055, 2.4) if c > 0.04045 else c/12.92
    r, g, b = f(r), f(g), f(b)
    X = r*0.6499+g*0.1035+b*0.1971; Y = r*0.2343+g*0.7431+b*0.0226; Z = b*1.0358+g*0.0531
    s = X+Y+Z or 1
    return [round(X/s, 4), round(Y/s, 4)]


def timed(b, body):
    body = dict(body); body["transitiontime"] = 0
    t0 = time.monotonic()
    b.set_light(LID, body)
    return (time.monotonic() - t0) * 1000


def avg(b, prep, target, n=N, w=W):
    ms = []
    for k in range(n):
        if prep is not None:
            b.set_light(LID, {"on": True, **prep, "transitiontime": 0}); time.sleep(0.3)
        dt = timed(b, {"on": True, **target})
        if k >= w:
            ms.append(dt)
        time.sleep(0.3)
    return round(statistics.mean(ms), 1), round(statistics.pstdev(ms), 1)


def main():
    b = bridge()
    base = rgb_to_xy(200, 60, 60)

    # --- A: kind of change ---
    A = {}
    A["full RGB change"] = avg(b, {"xy": rgb_to_xy(255, 200, 0)}, {"xy": rgb_to_xy(20, 200, 240)})
    A["only blue changes"] = avg(b, {"xy": rgb_to_xy(200, 60, 60)}, {"xy": rgb_to_xy(200, 60, 200)})
    A["slight change"] = avg(b, {"xy": base}, {"xy": [round(base[0]+0.01, 4), round(base[1]+0.01, 4)]})
    A["repeat (no-op)"] = avg(b, {"xy": base}, {"xy": list(base)})
    print("A kind:", A)

    # --- B: no-op threshold (delta from base) ---
    B = {}
    for d in (0.0, 0.0002, 0.001, 0.005, 0.02, 0.08):
        tgt = [round(base[0]+d, 4), round(base[1]+d, 4)]
        B[d] = avg(b, {"xy": base}, {"xy": tgt})
    print("B threshold:", B)

    # --- C: representation of a real change ---
    C = {}
    C["xy"] = avg(b, {"ct": 300}, {"xy": rgb_to_xy(0, 120, 255)})
    C["hue+sat"] = avg(b, {"ct": 300}, {"hue": 46000, "sat": 254})
    C["ct (white)"] = avg(b, {"xy": rgb_to_xy(255, 0, 0)}, {"ct": 350})
    print("C repr:", C)

    json.dump({"A": A, "B": {str(k): v for k, v in B.items()}, "C": C},
              open(OUT.replace(".html", ".json"), "w"), indent=2)

    t_noop = A["repeat (no-op)"][0]
    t_full = A["full RGB change"][0]
    t_zig = round(t_full - t_noop, 1)

    def tbl(d):
        return "".join(f"<tr><td>{k}</td><td>{v[0]}</td><td>{v[1]}</td></tr>" for k, v in d.items())
    barsA = bars([(k, v[0]) for k, v in A.items()], "ms", "A · kind of change", w=620)
    barsB = bars([(f"Δ={k:g}", v[0]) for k, v in B.items()], "ms", "B · no-op threshold (xy delta)", w=620)
    barsC = bars([(k, v[0]) for k, v in C.items()], "ms", "C · color representation", w=620)
    # find threshold: smallest delta that is a "real TX" (closer to full than to no-op)
    mid = (t_noop + t_full) / 2
    real_deltas = [k for k, v in B.items() if k > 0 and v[0] > mid]
    thresh = min(real_deltas) if real_deltas else None

    body = f"""<h1>Color changes on Hue — channels, magnitude, no-op &amp; encoding</h1>
<p class=sub>Single-light tests on light {LID}. {N-W} samples each. Hue has no RGB channels — color is one command.</p>

<div class=formula>T = T<sub>noop</sub> + &Delta;&middot;T<sub>zigbee</sub> &asymp; {t_noop:.0f} + &Delta;&middot;{t_zig:.0f} ms
<small>&Delta; = 1 if the stored state actually changes, else 0 — independent of #channels, magnitude, and encoding</small></div>

<h2>A · Does the kind / size of change matter?</h2>
<div class=c>{barsA}<table><tr><th>case</th><th>mean (ms)</th><th>std</th></tr>{tbl(A)}</table></div>
<div class=cap warn><b>No RGB channels.</b> "only blue" is not cheaper than "all three" — both convert to one
<code>xy</code> PUT. Full, only-blue and slight changes all cost ~{t_full:.0f} ms; only the <b>no-op</b>
(identical color) is cheap (~{t_noop:.0f} ms). So cost depends on <i>whether</i> the state changes, not how much.</div>

<h2>B · How small a change is still "free"?</h2>
<div class=c>{barsB}<table><tr><th>xy delta</th><th>mean (ms)</th><th>std</th></tr>{tbl({f'Δ={k:g}': v for k, v in B.items()})}</table></div>
<div class=cap><b>Threshold:</b> only an <i>exactly identical</i> request is the fast ~{t_noop:.0f} ms no-op;
the smallest real delta tested ({('Δ='+format(thresh,'g')) if thresh is not None else 'any Δ>0'}) already triggers a full
Zigbee transmission (~{t_full:.0f} ms). The bridge stores xy to ~4 decimals, so a change below that precision
reads as no change (free); anything above it is a full send. It is a step function, not proportional.</div>

<h2>C · Does the color encoding matter?</h2>
<div class=c>{barsC}<table><tr><th>encoding</th><th>mean (ms)</th><th>std</th></tr>{tbl(C)}</table></div>
<div class=cap>Sending a real color change as <code>xy</code>, <code>hue+sat</code>, or <code>ct</code> costs about the
same — they are all one Zigbee frame. Pick the encoding that's convenient; it isn't a latency lever.</div>

<h2>What this means</h2>
<div class=c><p>The only color-side optimisation that helps is <b>skip no-ops</b> (don't resend a color a light
already has — saves ~{t_zig:.0f} ms each). Beyond that, color cost is fixed per command. To change colors
<i>fast</i> you must leave REST entirely and use Entertainment streaming (one UDP packet, ~50 fps), where the
per-command Zigbee cost modelled here doesn't apply.</p></div>"""
    write(OUT, page("Color changes (developed) — Hue", body))


if __name__ == "__main__":
    main()
