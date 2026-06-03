"""Shared helpers for the hue-latency-* benchmark skills (each skill keeps its own copy).

Connection, the Home light set, a curl-based timing breakdown, and tiny self-contained
HTML/SVG output (no external libraries).
"""
import json
import os
import subprocess
import time

from phue import Bridge

HOME = [43, 47, 48, 49, 50, 51, 52]            # principal = HOME[0], followers = rest
NAMES = {43: "Hue Play 1", 47: "Hue Play 2", 48: "color lamp 6", 49: "Hue play 3",
         50: "Hue play 4", 51: "color lamp 7", 52: "color lamp 8"}
TYPE = {43: "Play", 47: "Play", 48: "lamp", 49: "Play", 50: "Play", 51: "lamp", 52: "lamp"}


def creds():
    cfg = json.load(open(os.path.expanduser("~/.hue-mcp/config.json")))
    return cfg["bridge_ip"], cfg.get("username")


def bridge():
    ip, u = creds()
    b = Bridge(ip, username=u)
    b.connect()
    return b


def curl_timing(ip, user, lid, body):
    """One PUT via curl; returns dict of phase times (seconds)."""
    fmt = "%{time_connect} %{time_pretransfer} %{time_starttransfer} %{time_total}"
    out = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", fmt, "-X", "PUT",
         "-d", json.dumps(body), f"http://{ip}/api/{user}/lights/{lid}/state"],
        capture_output=True, text=True, timeout=8).stdout.split()
    c, p, s, t = (float(x) for x in out)
    return {"connect": c, "pretransfer": p, "starttransfer": s, "total": t}


def ping_rtt(ip, n=5):
    """Mean ICMP RTT in seconds (pure network), or None."""
    try:
        out = subprocess.run(["ping", "-c", str(n), "-q", ip],
                             capture_output=True, text=True, timeout=15).stdout
        for line in out.splitlines():
            if "min/avg" in line or "rtt" in line:
                return float(line.split("=")[1].split("/")[1]) / 1000.0
    except Exception:
        return None
    return None


# ---------- tiny self-contained HTML/SVG ----------
def page(title, body):
    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
body{{font:15px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}}
.w{{max-width:880px;margin:auto;padding:30px 20px 80px}}
h1{{font-size:25px;margin:0 0 4px}}h2{{font-size:19px;border-bottom:1px solid #334155;padding-bottom:5px;margin:30px 0 10px;color:#fff}}
.sub{{color:#94a3b8;margin:0 0 16px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0}}
th,td{{border:1px solid #334155;padding:6px 10px;text-align:right}}td:first-child,th:first-child{{text-align:left}}th{{background:#0b1220;color:#cbd5e1}}
.c{{background:#1e293b;border:1px solid #334155;border-radius:11px;padding:16px 18px;margin:12px 0}}
.cap{{border-left:4px solid #38bdf8;background:#0b1220;padding:11px 15px;border-radius:0 8px 8px 0;margin:11px 0}}
.warn{{border-left-color:#f59e0b}}
.formula{{background:#0b1220;border:1px solid #38bdf8;border-radius:9px;padding:14px;text-align:center;font-size:17px;color:#fff}}
svg{{width:100%;height:auto;background:#0b1220;border-radius:9px;margin:6px 0}}
.bar{{fill:#2563eb}}.bar2{{fill:#7c3aed}}.t{{fill:#e2e8f0;font-size:12px}}.tm{{fill:#94a3b8;font-size:11px}}.ttl{{fill:#e2e8f0;font-size:13px;font-weight:600}}
code{{background:#0b1220;padding:1px 5px;border-radius:4px;color:#7dd3fc}}
</style><div class=w>{body}</div></html>"""


def bars(rows, unit, title="", vmax=None, w=640, rowh=42, cls="bar"):
    vmax = vmax or max(v for _, v in rows) * 1.18 or 1
    x0, x1 = 240, w - 80
    H = 30 + len(rows) * rowh
    s = [f'<svg viewBox="0 0 {w} {H}">']
    if title:
        s.append(f'<text x="{w/2}" y="18" class=ttl text-anchor=middle>{title}</text>')
    for i, (lab, v) in enumerate(rows):
        y = 28 + i * rowh
        bw = (v / vmax) * (x1 - x0)
        s += [f'<text x="{x0-10}" y="{y+16}" class=t text-anchor=end>{lab}</text>',
              f'<rect class={cls} x="{x0}" y="{y+1}" width="{max(bw,0):.1f}" height="22" rx="3"/>',
              f'<text x="{x0+max(bw,0)+8:.1f}" y="{y+17}" class=tm>{v:.1f} {unit}</text>']
    s.append("</svg>")
    return "".join(s)


def write(path, html):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(html)
    print("wrote", path)
