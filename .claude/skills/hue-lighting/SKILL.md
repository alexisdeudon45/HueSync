---
name: hue-lighting
description: >-
  Control Philips Hue lights through the HueSync MCP server (mcp__hue__* tools):
  set moods and scene recipes (movie night, party, focus/concentrate, relax,
  cozy, reading, energize) and do direct control (color, brightness, on/off,
  color temperature, presets, scenes, entertainment areas). Use this skill
  whenever the user wants to change the lighting, lamps, or ambiance in English
  or French — e.g. "make it cozy", "movie night", "dim the lights", "turn
  everything blue", "focus mode", "set the bedroom to relax", "ambiance cosy",
  "tamise la lumière", "mets les lumières en bleu". Trigger even when the user
  doesn't name Hue explicitly but clearly means the room lighting. Do NOT use it
  for non-lighting devices (TV, speakers) or unrelated requests.
---

# Hue Lighting

Translate a natural-language lighting request into the smallest correct set of
`mcp__hue__*` calls against this specific bridge. The point is to act like
someone who knows the house: pick the right group, the right recipe, and skip
busywork.

## The bridge at a glance

- **Default group: Home (id 81)** — living space. Lights: 43 (Hue Play 1), 47
  (Hue Play 2), 48 (color lamp 6), 49 (Hue play 3), 50 (Hue play 4), 51 (color
  lamp 7), 52 (color lamp 8). All color-capable and usually reachable.
- **Bedroom Ishan (id 84)** — lights 31, 33, 34, 35, 40, 41. These are **often
  powered off at the wall switch**, so they report `reachable: false` and the
  bridge accepts commands but nothing visibly changes. If a user targets the
  bedroom and sees no effect, tell them to flip the wall switch on.
- When the user says "the lights" / "everything" / "in here" with no room,
  assume **Home**. Mention which group you acted on so it's correctable.

Group tools default `group_id` to Home, so you can omit it for Home and pass
`group_id=84` for the bedroom. Being explicit is fine and clearer.

## Pick the smallest tool that does the job

Prefer **group** tools over looping per-light — one call changes the whole room
and reads cleanly:

- on / off → `turn_on_group` / `turn_off_group`
- whole-room color → `set_group_color_rgb(red, green, blue)`
- whole-room brightness → `set_group_brightness(brightness)` (0–254)
- whole-room named look → `set_group_color_preset(preset)`
- apply a saved scene → `set_scene(scene_id)` (find IDs with `get_all_scenes`)

Per-light tools (`turn_on_light`, `set_color_rgb`, `set_brightness`,
`set_color_temperature`, `set_color_preset`, `set_light_effect`, `alert_light`)
are for when the user names one lamp, or for effects that only exist per-light
(see the color-temperature and party notes below).

Read state with `get_all_lights`, `get_light`, `get_all_groups`, `get_group`,
`find_light_by_name`, `get_all_scenes`. Use `refresh_lights` if something looks
stale.

## Two gotchas worth knowing

1. **There is no group color-temperature tool.** To set a specific warm/cool
   white (in Kelvin) across a room, either use a preset (`warm`, `cool`,
   `daylight`) via `set_group_color_preset`, or loop the room's reachable lights
   with `set_color_temperature(light_id, kelvin)`. When the user asks for a
   precise Kelvin value, the per-light loop is the only way to honor it exactly.
2. **Brightness is 0–254, not a percentage.** Convert: ~25% ≈ 64, ~50% ≈ 127,
   ~75% ≈ 190, full ≈ 254. The tools report back the percentage.

## Valid preset names

`warm`, `cool`, `daylight`, `concentration`, `relax`, `reading`, `energize`,
`red`, `green`, `blue`, `purple`, `orange`. Use these exact strings with
`set_color_preset` / `set_group_color_preset`.

## Mood recipes

These are starting points, not rigid scripts — adjust to the user's words (e.g.
"a bit dimmer", "more orange"). Default to the Home group unless a room is named.
Apply brightness and color/preset as separate calls.

**Movie night / cinéma** — low, warm, immersive.
`set_group_color_preset("warm")` then `set_group_brightness(45)` (~18%).

**Cozy / cosy / chill** — soft warm glow.
`set_group_color_preset("relax")` then `set_group_brightness(90)` (~35%).

**Relax / détente** — `set_group_color_preset("relax")` at a comfortable
brightness (~120).

**Focus / concentrate / work / travail** — bright cool white. The user usually
wants real daylight-cool light, so set color temperature to **~6500K**: loop the
group's reachable lights with `set_color_temperature(id, 6500)` and
`set_group_brightness(254)`. (Or `set_group_color_preset("concentration")` if an
exact Kelvin isn't important — say which you did.)

**Reading / lecture** — `set_group_color_preset("reading")`,
`set_group_brightness(200)`.

**Energize / wake up / réveil** — `set_group_color_preset("energize")`,
`set_group_brightness(254)`.

**Party / fête** — colorful and moving. The bridge has no group effect tool, so
loop the room's reachable lights with `set_light_effect(id, "colorloop")` and
`set_group_brightness(254)`. To stop it later, set the effect back to `"none"`.

## Direct control examples

**Example — "turn everything blue"**
`set_group_color_rgb(0, 0, 255)` (Home). Confirm the room.

**Example — "dim the lights"**
`set_group_brightness(64)` (~25%) on Home. If they say "a bit", nudge from the
current level instead of jumping to a fixed value.

**Example — "set the bedroom to relax"**
`set_group_color_preset("relax", group_id=84)`. Note the bedroom lights may be
off at the wall.

**Example — "make light 48 warm and half brightness"**
`set_color_preset(48, "warm")` then `set_brightness(48, 127)`.

**Example — "lights off"**
`turn_off_group()` (Home). For the whole house, do both groups (81 and 84).

## Entertainment areas

When the user wants a sync / entertainment area, use
`create_entertainment_area(name, light_ids, entertainment_class, locations)`.
Class is one of `TV`, `Music`, `3DSpace`, `Other`. If you omit `locations`, each
light gets a random position in the −1..1 cube — fine to make the area valid, but
tell the user that screen-sync directionality won't match their real room until
they arrange the lights in the Hue app or pass explicit coordinates. For a
"whole living room" area, use the Home lights: 43, 47, 48, 49, 50, 51, 52.

## After acting

State briefly what you changed and on which group, so the user can course-
correct in one line ("too bright" → adjust brightness). If lights were
unreachable, say so rather than implying success.
