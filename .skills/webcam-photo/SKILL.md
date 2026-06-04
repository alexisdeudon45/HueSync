---
name: webcam-photo
description: >-
  Take a still photo from this computer's webcam and save it (then optionally show it).
  Use whenever the user wants to capture an image from the camera — e.g. "take a photo",
  "take a picture with the webcam", "snap a selfie", "what does the camera see right now",
  "grab a frame from the camera", "capture from my webcam", "prends une photo", "prends-moi
  en photo", "capture la webcam", "qu'est-ce que voit la caméra", "photo avec la caméra".
  Triggers even when the user doesn't say "webcam" but clearly wants the camera to take a
  picture. Captures one frame via ffmpeg from the V4L2 device, with an exposure warm-up so
  the shot isn't dark. This is for STILL photos from the local camera — not for recording
  video, not for screen capture/screenshots (the screen is a different source), and not for
  editing existing image files.
---

# Webcam photo

Captures a single still image from the computer's webcam and saves it as a JPEG.

This machine has **ffmpeg** but not `fswebcam`/`v4l2-ctl`, and the camera is a standard
V4L2 device at `/dev/video0`. The bundled script `scripts/snap.py` wraps ffmpeg so you
don't have to remember the flags, and it handles the one thing that trips people up:
exposure.

## Take a photo
```
python scripts/snap.py
```
Saves to `~/Pictures/webcam/webcam_<timestamp>.jpg` and prints the path. Then **read the
saved file** so you (and the user) can see what was captured — confirming the camera
actually produced a real, well-lit image rather than a black or frozen frame.

Common options:
```
python scripts/snap.py -o /tmp/me.jpg        # choose the output path
python scripts/snap.py --size 640x480        # lower resolution
python scripts/snap.py --device /dev/video2  # a different camera
python scripts/snap.py --list                # list cameras + supported formats/resolutions
```

## Why the warm-up matters
The first frame a webcam hands over is typically dark, greenish, or washed out because
auto-exposure and white balance haven't converged yet. So the script captures a short
burst (`--warmup`, default 15 frames) and keeps only the **last** one, giving the sensor
time to settle. If photos still look dark, increase `--warmup` (e.g. 30); if you need the
shot as fast as possible and lighting is good, lower it.

## Notes
- **One app owns the camera at a time.** If a browser tab, video call, or another tool
  holds `/dev/video0`, ffmpeg fails with "Device or resource busy" — the script says so;
  close the other app and retry.
- Default device `/dev/video0` is the capture node. A second node like `/dev/video1` is
  usually metadata-only and won't produce an image — use `--list` to see which nodes
  actually report capture formats.
- Supported here: MJPEG/YUYV up to **1280x720**. Asking for a size the camera doesn't
  support makes ffmpeg fail; stick to a listed resolution.
- The capture happens locally; the image is written to disk and nothing is uploaded.
- Privacy: this turns the camera on and takes a picture of whoever/whatever is in front
  of it. Only do it when the user actually asked for a photo.
