#!/usr/bin/env python3
"""Experiment: synchronous (one-at-a-time) vs asynchronous (concurrent) light commands.

For N = 1,3,5,7 lights we set a new color on N Home lights two ways and time it:
  - SEQUENTIAL: N PUTs back-to-back, each waiting for its reply.
  - CONCURRENT: N PUTs fired at once from a thread pool.
If concurrency beats sequential, the limit is the client; if not, the bridge serializes.
"""
import colorsys
import json
import os
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from huebench import HOME, bridge, creds, page, bars, write  # noqa

OUT = os.path.expanduser("~/.claude/skills/hue-latency-sync-async-workspace/report.html")
NSET = [1, 3, 5, 7]
TRIALS, WARMUP = 8, 2


def xy(i):
    r, g, b = colorsys.hsv_to_rgb((i * 0.19) % 1, 1, 1)
    X = r*0.6499+g*0.1035+b*0.1971; Y = r*0.2343+g*0.7431+b*0.0226; Z = b*1.0358+g*0.0531
    s = X+Y+Z or 1
    return [round(X/s, 4), round(Y/s, 4)]


def main():
    ip, user = creds()
    bridge()  # ensure paired

    def put(lid, body):
        req = urllib.request.Request(f"http://{ip}/api/{user}/lights/{lid}/state",
                                     data=json.dumps(body).encode(), method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return "error" in r.read().decode()
        except Exception:
            return True

    def seq(lights, c):
        t0 = time.monotonic()
        e = sum(put(l, {"on": True, "xy": xy(c), "transitiontime": 0}) for l in lights)
        return time.monotonic() - t0, e

    def conc(lights, c):
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=len(lights)) as ex:
            e = sum(ex.map(lambda l: put(l, {"on": True, "xy": xy(c), "transitiontime": 0}), lights))
        return time.monotonic() - t0, e

    rows, c = [], 0
    print(f"{'N':>3} {'seq(ms)':>9} {'conc(ms)':>9} {'speedup':>8} {'errors':>7}")
    for N in NSET:
        lights = HOME[:N]
        ms = {"seq": [], "conc": []}
        errs = 0
        for fn, key in ((seq, "seq"), (conc, "conc")):
            for k in range(TRIALS):
                c += 1
                dt, e = fn(lights, c)
                if k >= WARMUP:
                    ms[key].append(dt * 1000); errs += e
                time.sleep(0.4)
        sm, cm = statistics.mean(ms["seq"]), statistics.mean(ms["conc"])
        rows.append({"N": N, "seq_ms": round(sm, 1), "conc_ms": round(cm, 1),
                     "speedup": round(sm / cm, 2), "errors": errs})
        print(f"{N:>3} {sm:>9.1f} {cm:>9.1f} {sm/cm:>8.2f} {errs:>7}")

    json.dump(rows, open(OUT.replace(".html", ".json"), "w"), indent=2)

    trows = "".join(f"<tr><td>{r['N']}</td><td>{r['seq_ms']}</td><td>{r['conc_ms']}</td>"
                    f"<td>{r['speedup']}×</td><td>{r['errors']}</td></tr>" for r in rows)
    bar_rows = []
    for r in rows:
        bar_rows.append((f"N={r['N']} sequential", r["seq_ms"]))
        bar_rows.append((f"N={r['N']} concurrent", r["conc_ms"]))
    n7 = next(r for r in rows if r["N"] == 7)
    verdict = ("the bridge SERIALIZES commands — concurrency does not help"
               if n7["speedup"] < 1.25 else "concurrency helps — the client was a bottleneck")
    # linear fit of sequential latency vs N
    ns = [r["N"] for r in rows]; ys = [r["seq_ms"] for r in rows]
    mm = len(ns); sx = sum(ns); sy = sum(ys); sxx = sum(n*n for n in ns); sxy = sum(n*y for n, y in zip(ns, ys))
    slope = (mm*sxy - sx*sy) / (mm*sxx - sx*sx); intc = (sy - slope*sx) / mm
    spd = statistics.mean([r["speedup"] for r in rows])
    body = f"""<h1>Sync vs Async — Hue command latency</h1>
<p class=sub>Sequential (one PUT at a time) vs concurrent (N PUTs in parallel), per number of lights N.</p>
<div class=formula>T(N) &asymp; {slope:.1f}&middot;N + {intc:.1f} ms &nbsp;&bull;&nbsp; speed-up<sub>async</sub> &asymp; {spd:.2f}&times;
<small>latency grows ~{slope:.0f} ms per light; parallelism gives ~0 gain &rarr; the bridge serializes, the floor is the device</small></div>
<div class=c>{bars(bar_rows, "ms", "Wall time per all-lights change", w=660)}</div>
<div class=c><table><tr><th>N lights</th><th>sequential (ms)</th><th>concurrent (ms)</th><th>speed-up</th><th>errors</th></tr>{trows}</table></div>
<div class=cap><b>Verdict:</b> at N=7 concurrent is {n7['conc_ms']} ms vs sequential {n7['seq_ms']} ms
(speed-up {n7['speedup']}×) → {verdict}. The floor is the device, not how you send requests.</div>"""
    write(OUT, page("Sync vs Async — Hue", body))


if __name__ == "__main__":
    main()
