---
name: hue-principal-sync
description: >-
  Designate a random "principal" light in the Home group and make all the other
  Home lights mirror its full state (color + brightness + on/off). Use this skill
  whenever the user wants one light to lead and the rest to follow, to unify the
  room to a single look, or to randomly pick a master light — e.g. "pick a random
  principal light", "make all the lights match one", "set a master light and sync
  the rest", "mirror the home lights", "unify the living room to one color",
  "choisis une lumière principale au hasard", "que toutes les lumières suivent
  une seule". On-demand sync: it copies the principal's state to the others when
  invoked (it does not run a background watcher). Also handles rapid/smooth color
  animation: a slow REST rotation (--cycle) and a real Entertainment-streaming
  mode (~50 fps over DTLS) for fast effects like rainbow, strobe, pulse, or
  "rave" lighting on the Home area. Trigger on "change colors rapidly", "make the
  lights pulse/strobe", "rainbow effect", "fast color animation", "ambiance qui
  change vite", etc. For plain per-light or per-group control without a
  leader/follower or animation, use the hue-lighting skill instead.
---

# Hue Principal Sync

Make the Home group act like one light: a randomly chosen **principal** leads,
and the other six **followers** copy its **full state** — color, brightness, and
on/off. This is an *on-demand* action: the followers update each time you run the
sync, not continuously in the background.

## How it works

The bridge has no native "linked lights" feature and no "copy state" tool, and
mirroring full state across six lights by hand is fragile, so this skill drives a
bundled script that does it reliably in one shot:

```
scripts/principal_sync.py
```

Run it with the HueSync project's Python (which has `phue` installed), from the
skill directory:

```
/home/tor/hue-mcp/.venv/bin/python scripts/principal_sync.py [flags]
```

(If that venv ever moves, `uv run --project /home/tor/hue-mcp python
scripts/principal_sync.py` also works.)

It connects with the saved HueSync credentials (`~/.hue-mcp/config.json`), picks
the principal, optionally sets the principal's look first, reads the principal's
full state, then writes that state to the other Home lights (43, 47, 48, 49, 50,
51, 52 — minus the principal).

## When to run it

Run the script and report which light became the principal. Pick flags from what
the user asked:

- **Just unify the room to a random light's current look** (no color given):
  `python scripts/principal_sync.py`
  → random principal, everyone copies its current state.

- **Pick a random principal and give it a color** (the headline use):
  `python scripts/principal_sync.py --color 0,0,255`
  → random principal set to blue, all followers turn blue too.

- **Specific principal / brightness / white temperature:**
  `python scripts/principal_sync.py --principal 49 --ct 2700 --bri 120`

- **Turn the room off via the principal:** `--off`. **Force on:** `--on`.

- **Rapidly cycle color** (principal leads, whole room follows each tick):
  `python scripts/principal_sync.py --cycle --interval 0.4 --duration 30`
  → smooth rainbow sweep. Add `--random` for random colors, `--transition 0`
  for instant/strobe-style jumps (vs the default crossfade).

  Reality check on speed: over the REST API the bridge **throttles group
  updates to roughly 1 per second**, so intervals below ~0.5s get choppy or
  dropped. A single group command per tick (which this uses) is the fastest
  safe approach over REST. For genuinely smooth/fast animation use the streaming
  script below instead.

## Smooth fast effects — Entertainment streaming (~50 fps)

When the user wants *rapid*, smooth color (real animation, strobes, gradients),
the REST `--cycle` is not enough. Use the bundled streaming script, which talks
the Hue **Entertainment streaming API** (HueStream 2.0 over DTLS, UDP 2100) to
the "Home Entertainment" area and hits ~45–50 fps across all 7 lights:

```
/home/tor/hue-mcp/.venv/bin/python scripts/hue_stream.py [flags]
```

Effects: `--effect rainbow|wave|strobe|pulse|solid`, `--color r,g,b` (base for
strobe/pulse/solid), `--duration <sec>`, `--hz <rate up to ~50>`. Examples:

- `scripts/hue_stream.py --effect rainbow --duration 30`
- `scripts/hue_stream.py --effect strobe --color 255,0,0`
- `scripts/hue_stream.py --effect pulse --color 0,80,255 --hz 50`

**Principal-driven `wave`** — the principal channel leads a hue and the other
channels lag it, so color rolls across the room as a chase. This is the streaming
analogue of the principal concept:

- `scripts/hue_stream.py --effect wave --principal 3 --spread 0.14 --duration 30`
- `--principal <0-6>` picks the leading channel; `--spread` is the per-channel
  phase offset (bigger = more colors visible across the room at once). `pulse`
  also respects `--principal`/`--spread` for a breathing wave.

How it works and its requirements (so you can debug it):
- It **starts** the v2 entertainment_configuration `c108aaae-…` ("Home
  Entertainment", 7 channels), streams DTLS packets, then **stops** it on exit.
- DTLS needs an **application key + clientkey**. A clientkey is only issued at
  registration with `generateclientkey=true`; phue never requested one, so the
  script reuses an existing pair from `~/.hue-mcp/stream.json` (seeded from
  huenicorn's config). If those creds are missing, streaming can't authenticate.
- Transport is `openssl s_client -dtls1_2 -psk …` — **openssl must be
  installed**. Handshake errors are logged to `/tmp/hue_stream_openssl.log`.
- Only **one** entertainment stream can run at a time — make sure
  `huenicorn.service` (or any sync app) is **not** streaming, or it will
  conflict. Check: `systemctl --user is-active huenicorn.service`.

This streaming path is the right answer whenever "rapidly", "smooth", "fast",
"strobe", "rave", or "animation" comes up; the REST `--cycle` is only for slow
rotations.

Flags: `--principal <id>` (default random Home light), `--color r,g,b`,
`--ct <kelvin 2000-6500>`, `--bri <0-254>`, `--on`, `--off`. Color and ct are
mutually exclusive (color wins). Brightness is 0–254, not a percentage
(~50% ≈ 127).

## After running

The script prints the chosen principal, the mirrored state, and a note if any
Home lights were unreachable (powered off at the wall) and therefore didn't
visibly change. Relay that to the user — especially which light was picked, since
it's random and they may want to re-roll (just run it again) or pin one with
`--principal`.

## Scope

This skill is specifically the leader/follower "principal" behavior on the Home
group. It does not watch for changes in the background — to re-sync after
changing the principal again, run it again. For ordinary lighting control (single
lights, groups, moods, scenes, entertainment areas) use the **hue-lighting**
skill.
