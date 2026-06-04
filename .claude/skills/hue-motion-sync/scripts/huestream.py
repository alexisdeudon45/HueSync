"""Minimal Hue Entertainment streaming helper (HueStream 2.0 over DTLS via openssl).

Shared by hue-gradient-noise and hue-screen-sync (each keeps its own copy).
Streams to the v2 entertainment_configuration "Home Entertainment" (7 channels).
Credentials (application key + clientkey) come from ~/.hue-mcp/stream.json.

Usage:
    with HueStream() as s:
        s.send([(255,0,0)] * 7)   # one RGB per channel, 0-255
"""
import json
import os
import ssl
import subprocess
import time
import urllib.request

BRIDGE_IP = "192.168.178.37"
CONFIG_ID = "c108aaae-b53c-4780-b902-5a0e7e6232b6"   # v2 "Home Entertainment", 7 channels
CHANNELS = [0, 1, 2, 3, 4, 5, 6]
STREAM_CREDS = os.path.expanduser("~/.hue-mcp/stream.json")
HUENICORN_CFG = os.path.expanduser("~/.config/huenicorn/config.json")


def _creds():
    for path, get in ((STREAM_CREDS, lambda d: (d["username"], d["clientkey"])),
                      (HUENICORN_CFG, lambda d: (d["credentials"]["username"], d["credentials"]["clientkey"]))):
        if os.path.exists(path):
            try:
                return get(json.load(open(path)))
            except Exception:
                pass
    raise SystemExit("No streaming credentials (username+clientkey) in ~/.hue-mcp/stream.json")


class HueStream:
    def __init__(self, config_id=CONFIG_ID, channels=CHANNELS, debug=False):
        self.config_id = config_id
        self.channels = channels
        self.debug = debug
        self.username, self.clientkey = _creds()
        self.proc = None

    def _clip(self, action):
        url = f"https://{BRIDGE_IP}/clip/v2/resource/entertainment_configuration/{self.config_id}"
        req = urllib.request.Request(url, data=json.dumps({"action": action}).encode(),
                                     method="PUT",
                                     headers={"hue-application-key": self.username,
                                              "Content-Type": "application/json"})
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx, timeout=6) as r:
            return r.read()

    def __enter__(self):
        self._clip("start")
        time.sleep(0.4)
        cmd = ["openssl", "s_client", "-dtls1_2", "-connect", f"{BRIDGE_IP}:2100",
               "-cipher", "PSK-AES128-GCM-SHA256",
               "-psk_identity", self.username, "-psk", self.clientkey, "-quiet"]
        self._err = open("/tmp/huestream_openssl.log", "w")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=(None if self.debug else subprocess.DEVNULL),
                                     stderr=(None if self.debug else self._err))
        time.sleep(1.5)
        if self.proc.poll() is not None:
            self._clip("stop")
            raise SystemExit("DTLS handshake failed; see /tmp/huestream_openssl.log")
        return self

    def send(self, rgb_per_channel):
        """rgb_per_channel: list of (r,g,b) ints 0-255, one per channel."""
        p = bytearray(b"HueStream")
        p += bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])   # ver 2.0, seq, reserved, RGB, reserved
        p += self.config_id.encode("ascii")
        for ch, (r, g, b) in zip(self.channels, rgb_per_channel):
            p += bytes([ch])
            p += (r*257).to_bytes(2, "big") + (g*257).to_bytes(2, "big") + (b*257).to_bytes(2, "big")
        try:
            self.proc.stdin.write(bytes(p)); self.proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def __exit__(self, *a):
        try:
            if self.proc:
                self.proc.stdin.close(); self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        finally:
            try:
                self._clip("stop")
            except Exception:
                pass
            try:
                self._err.close()
            except Exception:
                pass
