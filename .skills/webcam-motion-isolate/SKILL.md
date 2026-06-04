---
name: webcam-motion-isolate
description: >-
  Capture several webcam frames a second apart, find the pixels that are COMMON to all
  of them (the static background), and remove those — leaving only what changed/moved.
  Use when the user wants to isolate motion or strip the static background from the
  camera by comparing multiple shots over time — e.g. "take 5 photos one second apart
  and remove what's common between them", "capture a few frames and keep only what
  moved", "subtract the static background from the webcam", "isolate the moving parts",
  "compare frames pixel by pixel and delete the common pixels", "prends plusieurs
  captures à 1s d'intervalle et enlève ce qui est commun", "garde seulement ce qui
  bouge", "retire le fond statique de la caméra", "compare les frames pixel par pixel".
  This compares frames over time to find motion — it is NOT for a single snapshot (use
  webcam-photo for one plain photo), not for screen capture, and not for editing an
  existing image file.
---

# Webcam motion isolate

Takes N webcam frames spaced a second apart, decides per pixel which ones are **common**
to every frame (the unchanging background), and **removes** them so only the parts that
moved remain.

## Why this works
Over a few seconds the background — wall, desk, chair — barely changes, so a background
pixel reads almost the same value in every frame. Anything that moves (a person, a hand,
a passing object) covers different pixels at different moments, so those pixels differ
between frames. Measuring how much each pixel **varies across the frames** therefore
separates "background" (low variation → common → removed) from "motion" (high variation →
kept). The output is a PNG with transparency, so the removed background is genuinely gone
rather than painted over.

## Run it
```
python scripts/framediff.py
```
Captures 5 frames 1s apart at 640x480 and saves
`~/Pictures/webcam/isolated_<timestamp>.png` (transparent where the scene was static).
After it runs, **read the saved PNG** to confirm the isolation looks right, and tell the
user the kept/removed percentage it prints.

Options:
```
python scripts/framediff.py --frames 8 --interval 0.5   # more frames, captured faster
python scripts/framediff.py --threshold 40              # remove more (more counts as "common")
python scripts/framediff.py --threshold 18              # remove less (keep faint changes)
python scripts/framediff.py -o /tmp/moved.png --keep-frames   # also save each source frame
python scripts/framediff.py --size 1280x720             # higher resolution (slower)
```

## Tuning — the threshold is the main dial
A pixel is treated as common (and removed) when its variation across the frames is at or
below `--threshold` (0-255, default 30). The right value depends on the scene:
- **Too much speckly noise kept** → raise the threshold (e.g. 40-50). Camera sensor noise
  and tiny lighting flicker make even static pixels wobble a little; a higher threshold
  absorbs that.
- **The moving subject is being erased too** → lower the threshold (e.g. 18-22), or make
  sure there's real movement between shots — if nothing moved, almost everything is
  "common" and the result is nearly empty (that's correct, not a bug).

The result is only as good as the motion in the window: ask the user to actually move (or
let something in frame move) across the capture, otherwise there's little to keep.

## How it decides (the pixel math)
Frames are stacked into an `(N, H, W, 3)` array. For each pixel the script takes the
**range** (max − min) across the N frames, then the worst of the three color channels —
one number per pixel saying "how much did this pixel move at all". Pixels at or below the
threshold get alpha 0 (transparent/removed); the rest keep their color from the **last**
frame (the most recent look of whatever moved).

## Notes
- Needs only **ffmpeg** + **numpy** (system `python3` has numpy here). Frames are grabbed
  as raw RGB and the PNG is written by piping raw RGBA back through ffmpeg — no PIL/OpenCV.
- Each capture warms the camera up for a few frames so exposure settles (see also the
  sibling skill `webcam-photo`).
- **One app owns the camera at a time** — if it's busy (browser, video call), ffmpeg
  fails with "Device or resource busy"; close the other app and retry.
- Everything stays local; nothing is uploaded. As with any camera use, only run it when
  the user actually asked.
