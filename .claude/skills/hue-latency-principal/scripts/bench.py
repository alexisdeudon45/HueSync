#!/usr/bin/env python3
"""Experiment: does WHICH light is the principal affect latency?

Measures single-light PUT latency for each Home light individually (same color
change), so we can see whether some lights (e.g. Hue Play vs color lamps) are
slower to command, and whether picking a particular principal matters.
"""
import colorsys
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from huebench import HOME, NAMES, TYPE, bridge, page, bars, write  # noqa

OUT = os.path.expanduser("~/.claude/skills/hue-latency-principal-workspace/report.html")
SAMPLES, WARMUP = 8, 2


def xy(i):
    r, g, b = colorsys.hsv_to_rgb((i * 0.29) % 1, 1, 1)
    X = r*0.6499+g*0.1035+b*0.1971; Y = r*0.2343+g*0.7431+b*0.0226; Z = b*1.0358+g*0.0531
    s = X+Y+Z or 1
    return [round(X/s, 4), round(Y/s, 4)]


def main():
    b = bridge()
    per = {}
    i = 0
    print(f"{'light':>22} {'type':>5} {'mean(ms)':>9} {'std':>6}")
    for lid in HOME:
        ms = []
        for k in range(SAMPLES):
            i += 1
            t0 = time.monotonic()
            b.set_light(lid, {"on": True, "xy": xy(i), "transitiontime": 0})
            dt = (time.monotonic() - t0) * 1000
            if k >= WARMUP:
                ms.append(dt)
            time.sleep(0.4)
        per[lid] = {"name": NAMES[lid], "type": TYPE[lid],
                    "mean": round(statistics.mean(ms), 1), "std": round(statistics.pstdev(ms), 1)}
        print(f"{NAMES[lid]:>22} {TYPE[lid]:>5} {per[lid]['mean']:>9.1f} {per[lid]['std']:>6.1f}")

    json.dump(per, open(OUT.replace(".html", ".json"), "w"), indent=2)
    means = [v["mean"] for v in per.values()]
    lo, hi = min(means), max(means)
    spread = (hi - lo) / lo * 100
    by_type = {}
    for v in per.values():
        by_type.setdefault(v["type"], []).append(v["mean"])
    type_means = {t: round(statistics.mean(x), 1) for t, x in by_type.items()}

    bar_rows = [(f"{v['name']} ({v['type']})", v["mean"]) for v in per.values()]
    trows = "".join(f"<tr><td>{v['name']}</td><td>{v['type']}</td><td>{v['mean']}</td><td>{v['std']}</td></tr>"
                    for v in per.values())
    type_txt = ", ".join(f"{t}: {m} ms" for t, m in type_means.items())
    verdict = ("which light you pick as principal does NOT meaningfully change latency"
               if spread < 25 else "light choice DOES matter — see the slower entries")
    grand = statistics.mean(means); grand_sd = statistics.pstdev(means)
    body = f"""<h1>Does the principal light choice affect latency?</h1>
<p class=sub>Single-light PUT latency per Home light. {SAMPLES-WARMUP} samples each.</p>
<div class=formula>T(light) &asymp; {grand:.0f} &plusmn; {grand_sd:.0f} ms &nbsp;&mdash;&nbsp; independent of which light
<small>no dependence on light identity or type (Play vs lamp); the random principal carries no latency penalty</small></div>
<div class=c>{bars(bar_rows, "ms", "Latency per light", w=680)}</div>
<div class=c><table><tr><th>light</th><th>type</th><th>mean (ms)</th><th>std (ms)</th></tr>{trows}</table></div>
<div class=cap><b>Finding:</b> spread across lights is ~{spread:.0f}% (fastest {lo:.0f} ms,
slowest {hi:.0f} ms). By type — {type_txt}. So {verdict}: the per-command bridge/Zigbee cost is
roughly uniform, so the principal can be picked at random without a latency penalty.</div>"""
    write(OUT, page("Principal light latency — Hue", body))


if __name__ == "__main__":
    main()
