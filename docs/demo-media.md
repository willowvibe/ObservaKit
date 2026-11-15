# Demo media pipeline

This document is the reproducible path for ObservaKit's demo assets: the full narrated video, the Pages player, and the README GIF.

## Assets

| Asset | Location | Purpose |
|---|---|---|
| Full video | `https://willowvibe.github.io/ObservaKit/observakit-demo.mp4` | Autoplaying 113 s, 1080p, voiceover-only demo |
| Release fallback | v1.0.0 asset `observakit-demo-v2.mp4` | Download / fallback `<source>` |
| Poster | `docs/assets/observakit-demo-poster-v2.jpg`, `landing-page/public/` | Video poster before first frame |
| README preview | `docs/assets/observakit-demo.gif` | 11.8 s looping highlight, linked to the Pages demo |

## Build the full video

1. Record the running demo to `video-work/observakit-raw.webm`.
2. Generate narration with the TTS pipeline; the current run uses `/tmp/observakit-tts/narration.wav` and `/tmp/observakit-tts/holds.json`.
3. Assemble with crossfades:

```bash
python scripts/assemble_demo.py
```

`assemble_demo.py` cuts each scene, pads outgoing scenes by the transition length (0.35 s), joins with `xfade`, muxes AAC narration, and extracts the poster. The result is `observakit-demo.mp4` at the repo root (git-ignored).

Verify:

```bash
ffprobe -v error -show_entries format=duration -show_entries stream=codec_type,codec_name -of default=nw=1 observakit-demo.mp4
```

Expect 113 s, one H.264 video stream, one AAC audio stream, and no subtitle stream.

## Serve the video on Pages

GitHub release assets are `application/octet-stream` with `Content-Disposition: attachment`, so browsers download them. GitHub Pages serves `.mp4` as `video/mp4` with byte ranges.

`.github/workflows/deploy-pages.yml` downloads the release cut into the Pages artifact after the Vite build:

```yaml
- name: Fetch demo video for inline playback
  run: |
    curl -fsSL --retry 3 \
      -o landing-page/dist/observakit-demo.mp4 \
      https://github.com/willowvibe/ObservaKit/releases/download/v1.0.0/observakit-demo-v2.mp4
    test -s landing-page/dist/observakit-demo.mp4
```

The player lists `observakit-demo.mp4` first and the release URL as a fallback `<source>`.

## Make the README GIF

```bash
bash scripts/make_demo_gif.sh
```

The script takes the full video and writes `docs/assets/observakit-demo.gif`: 960×540, 12 fps, four shots (dashboard, freshness, quality checks, CLI), 256-color palette, about 1.2 MB. Keep README GIFs under ~2 MB; a full two-minute GIF would be tens of megabytes.

## Autoplay behavior

`landing-page/src/App.jsx` implements:

- `autoPlay muted playsInline controls preload="auto"` with a poster.
- An `IntersectionObserver` at 0.25 visibility: play when visible, pause offscreen.
- `prefers-reduced-motion` opts out of autoplay.
- A centered **Play demo** button when paused; it unmutes and plays under the user gesture.
- An **Unmute narration** button while playing muted.

Browsers block audible autoplay until a gesture, so this is the expected behavior, not a bug.

## Verify

```bash
curl -sI https://willowvibe.github.io/ObservaKit/observakit-demo.mp4 \
  | grep -iE 'HTTP|content-type|content-length|accept-ranges'
```

Expect `200`, `video/mp4`, `accept-ranges: bytes`.

In a fresh browser at `https://willowvibe.github.io/ObservaKit/#demo`, confirm:

- video starts muted and advances;
- **Unmute narration** enables sound;
- pausing shows **Play demo** and clicking resumes;
- scrolling away pauses;
- no console errors.

## Cache-busting

GitHub Camo and browsers cache by URL. When the bytes change, rename the asset (`observakit-demo-v2.mp4`, `observakit-demo-poster-v2.jpg`) rather than relying only on a query string.
