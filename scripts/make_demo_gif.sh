#!/usr/bin/env bash
# Build the README highlight GIF from the full demo video.
set -euo pipefail

input="${1:-observakit-demo.mp4}"
output="${2:-docs/assets/observakit-demo.gif}"

if [[ ! -f "$input" ]]; then
  echo "missing input video: $input" >&2
  exit 1
fi

# Four shots: dashboard, freshness, quality checks, CLI.
ffmpeg -y -loglevel error -i "$input" -filter_complex "
[0:v]split=4[a][b][c][d];
[a]trim=start=16.3:duration=3.0,setpts=PTS-STARTPTS,fps=12,scale=960:-1:flags=lanczos[v0];
[b]trim=start=29.3:duration=3.0,setpts=PTS-STARTPTS,fps=12,scale=960:-1:flags=lanczos[v1];
[c]trim=start=42.3:duration=3.0,setpts=PTS-STARTPTS,fps=12,scale=960:-1:flags=lanczos[v2];
[d]trim=start=102.0:duration=2.8,setpts=PTS-STARTPTS,fps=12,scale=960:-1:flags=lanczos[v3];
[v0][v1][v2][v3]concat=n=4:v=1:a=0,split[g][p];
[p]palettegen=max_colors=256:stats_mode=full[pal];
[g][pal]paletteuse=dither=sierra2_4a[out]" \
  -map "[out]" -loop 0 "$output"

echo "wrote $output"
