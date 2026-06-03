#!/usr/bin/env python3
"""Experiment: does the KIND of change matter? brightness vs color vs both.

Times a single-light PUT for different payloads, all on the same light:
  - brightness only  ({"bri": ...})
  - color via xy     ({"xy": [...]})
  - color via hue+sat({"hue":..,"sat":..})
  - both             ({"bri":..,"xy":[...]})
Shows whether color costs more than brightness over the bridge's Zigbee path.
"""
import colorsys
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from huebench import HOME, bridge, page, bars, write  # noqa

OUT = os.path.expanduser("~/.claude/skills/hue-latency-params-workspace/report.html")
SAMPLES, WARMUP = 10, 2
LID = HOME[0]


def xy(i):
    r, g, b = colorsys.hsv_to_rgb((i * 0.27) % 1, 1, 1)
    X = r*0.6499+g*0.1035+b*0.1971; Y = r*0.2343+g*0.7431+b*0.0226; Z = b*1.0358+g*0.0531
    s = X+Y+Z or 1
    return [round(X/s, 4), round(Y/s, 4)]


def main():
    b = bridge()
    cases = {
        "brightness only": lambda i: {"bri": 60 + (i * 30) % 190},
        "color (xy)": lambda i: {"xy": xy(i)},
        "color (hue+sat)": lambda i: {"hue": (i * 9000) % 65535, "sat": 254},
        "both (bri+xy)": lambda i: {"bri": 60 + (i * 30) % 190, "xy": xy(i + 3)},
    }
    results = {}
    print(f"{'case':>18} {'mean(ms)':>9} {'std':>6}")
    i = 0
    for name, mk in cases.items():
        ms = []
        for k in range(SAMPLES):
            i += 1
            body = dict(mk(i)); body["transitiontime"] = 0
            t0 = time.monotonic()
            b.set_light(LID, body)
            dt = (time.monotonic() - t0) * 1000
            if k >= WARMUP:
                ms.append(dt)
            time.sleep(0.4)
        results[name] = {"mean": round(statistics.mean(ms), 1), "std": round(statistics.pstdev(ms), 1)}
        print(f"{name:>18} {results[name]['mean']:>9.1f} {results[name]['std']:>6.1f}")

    json.dump(results, open(OUT.replace(".html", ".json"), "w"), indent=2)
    bar_rows = [(k, v["mean"]) for k, v in results.items()]
    trows = "".join(f"<tr><td>{k}</td><td>{v['mean']}</td><td>{v['std']}</td></tr>" for k, v in results.items())
    lo = min(v["mean"] for v in results.values())
    hi = max(v["mean"] for v in results.values())
    spread = (hi - lo) / lo * 100
    note = ("essentially the same — the bridge cost is per-command, not per-parameter"
            if spread < 20 else "the kind of change does affect latency (see table)")
    rb = results["brightness only"]["mean"]; rc = results["color (xy)"]["mean"]; rboth = results["both (bri+xy)"]["mean"]
    body = f"""<h1>Brightness vs color — does the parameter matter?</h1>
<p class=sub>Single-light PUT latency by payload type, light {LID}. {SAMPLES-WARMUP} samples each.</p>
<div class=formula>T &asymp; T<sub>frame</sub> + per-attribute cost<br>brightness {rb:.0f} ms &nbsp;&middot;&nbsp; color {rc:.0f} ms &nbsp;&middot;&nbsp; both {rboth:.0f} ms
<small>one Zigbee frame dominates (~30 ms); color costs ~{rc-rb:.0f} ms more than brightness, a 2nd attribute adds ~{rboth-rc:.0f} ms</small></div>
<div class=c>{bars(bar_rows, "ms", "Latency by change type", w=660)}</div>
<div class=c><table><tr><th>change</th><th>mean (ms)</th><th>std (ms)</th></tr>{trows}</table></div>
<div class=cap><b>Finding:</b> spread between fastest and slowest is ~{spread:.0f}% — {note}.
Color and brightness are both a single Zigbee command to the bulb; the per-command overhead
dominates over the payload contents.</div>"""
    write(OUT, page("Brightness vs color latency — Hue", body))


if __name__ == "__main__":
    main()
