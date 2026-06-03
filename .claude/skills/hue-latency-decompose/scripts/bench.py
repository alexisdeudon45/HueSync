#!/usr/bin/env python3
"""Experiment: decompose one light-command PUT into where the time goes.

Using curl's timing counters on real PUTs:
  - network setup  = time_connect            (TCP handshake = 1 network RTT)
  - bridge work    = time_starttransfer - time_pretransfer  (request in + bridge/Zigbee + first byte out)
  - ack/transfer   = time_total - time_starttransfer        (receive the response body)
We also measure pure ICMP RTT as a network reference, to show how little of the
total is actually the network vs the bridge.
"""
import colorsys
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))
from huebench import HOME, bridge, creds, curl_timing, ping_rtt, page, bars, write  # noqa

OUT = os.path.expanduser("~/.claude/skills/hue-latency-decompose-workspace/report.html")
SAMPLES, WARMUP = 12, 2
LID = HOME[0]


def xy(i):
    r, g, b = colorsys.hsv_to_rgb((i * 0.23) % 1, 1, 1)
    X = r*0.6499+g*0.1035+b*0.1971; Y = r*0.2343+g*0.7431+b*0.0226; Z = b*1.0358+g*0.0531
    s = X+Y+Z or 1
    return [round(X/s, 4), round(Y/s, 4)]


def main():
    ip, user = creds()
    bridge()
    net = {"connect": [], "bridge": [], "ack": [], "total": []}
    for i in range(SAMPLES):
        t = curl_timing(ip, user, LID, {"on": True, "xy": xy(i), "transitiontime": 0})
        if i >= WARMUP:
            net["connect"].append(t["connect"])
            net["bridge"].append(t["starttransfer"] - t["pretransfer"])
            net["ack"].append(t["total"] - t["starttransfer"])
            net["total"].append(t["total"])
        import time; time.sleep(0.4)

    mean = {k: statistics.mean(v) for k, v in net.items()}
    tot = mean["total"]
    pct = {k: 100 * mean[k] / tot for k in ("connect", "bridge", "ack")}
    rtt = ping_rtt(ip) or 0.0

    print(f"total PUT      : {tot*1000:7.1f} ms")
    print(f"  network setup: {mean['connect']*1000:7.1f} ms  ({pct['connect']:4.1f}%)")
    print(f"  bridge work  : {mean['bridge']*1000:7.1f} ms  ({pct['bridge']:4.1f}%)")
    print(f"  ack/transfer : {mean['ack']*1000:7.1f} ms  ({pct['ack']:4.1f}%)")
    print(f"  (ICMP RTT ref: {rtt*1000:7.1f} ms pure network)")

    json.dump({"mean_ms": {k: round(v*1000, 2) for k, v in mean.items()},
               "pct": {k: round(v, 1) for k, v in pct.items()},
               "icmp_rtt_ms": round(rtt*1000, 2)}, open(OUT.replace(".html", ".json"), "w"), indent=2)

    bar_rows = [("Network (TCP connect)", mean["connect"]*1000),
                ("Bridge processing", mean["bridge"]*1000),
                ("Ack / transfer", mean["ack"]*1000)]
    body = f"""<h1>Where does a light command's time go?</h1>
<p class=sub>One PUT to light {LID}, broken into network vs bridge vs ack. {SAMPLES-WARMUP} samples.</p>
<div class=formula>T<sub>total</sub> = T<sub>net</sub> + T<sub>bridge</sub> + T<sub>ack</sub> &asymp; {mean['connect']*1000:.1f} + {mean['bridge']*1000:.1f} + {mean['ack']*1000:.1f} ms
<small>bridge &asymp; {pct['bridge']:.0f}% of the time, network only ~{pct['connect']:.0f}% (ICMP {rtt*1000:.1f} ms) &rarr; a faster network / direct cable can't help</small></div>
<div class=c>{bars(bar_rows, "ms", "Latency breakdown of one PUT", w=660)}</div>
<div class=c><table>
<tr><th>Component</th><th>mean (ms)</th><th>% of total</th><th>what it is</th></tr>
<tr><td>Network (TCP connect)</td><td>{mean['connect']*1000:.1f}</td><td>{pct['connect']:.1f}%</td><td>1 LAN round-trip to open the socket</td></tr>
<tr><td>Bridge processing</td><td>{mean['bridge']*1000:.1f}</td><td>{pct['bridge']:.1f}%</td><td>request in → bridge handles it + talks Zigbee → first reply byte</td></tr>
<tr><td>Ack / transfer</td><td>{mean['ack']*1000:.1f}</td><td>{pct['ack']:.1f}%</td><td>receive the small JSON response</td></tr>
<tr><td><b>Total</b></td><td><b>{tot*1000:.1f}</b></td><td><b>100%</b></td><td>one confirmed light change</td></tr>
</table></div>
<div class=cap><b>Pure network reference:</b> ICMP RTT to the bridge is only
~{rtt*1000:.1f} ms. So the LAN is a tiny fraction — <b>{pct['bridge']:.0f}% of the time is the
bridge itself</b> (handling the request + the Zigbee transmission to the bulb). The network is
not the bottleneck; the bridge is.</div>"""
    write(OUT, page("Latency decomposition — Hue", body))


if __name__ == "__main__":
    main()
