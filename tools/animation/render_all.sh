#!/bin/bash
# Render every stage clip and pack it as an animated WebP into assets/anim/.
# Needs: Python 3.11 with `pip install bpy` (Blender as a Python module), ffmpeg,
# and the two models in tools/animation/models/ (see README.md here).
set -e
cd "$(dirname "$0")"
OUT=frames
mkdir -p "$OUT" ../../assets/anim
for c in throw_m pet throw_s throw_l finish; do
  rm -rf "$OUT/$c"
  RES=${RES:-900x225} SAMPLES=${SAMPLES:-12} python build_clips.py -- models/human.glb models/dog.glb "$OUT/$c" "$c"
  ffmpeg -v error -y -framerate 24 -i "$OUT/$c/f%04d.png" -c:v libwebp_anim -pix_fmt yuva420p \
         -quality 82 -loop 0 "../../assets/anim/$c.webp"
done
echo "done -> assets/anim/"
