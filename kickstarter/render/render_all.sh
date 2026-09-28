#!/bin/sh
# Render every reward/item scene. Usage: sh kickstarter/render/render_all.sh [samples] [scene ...]
cd "$(dirname "$0")/../.."
SAMPLES=${1:-160}; shift 2>/dev/null
SCENES=${*:-"dream-cube early-bird supporter give-a-cube buy-one-give-one chip-kit school-starter school-ngo-pack item-dream-cube item-chip-kit item-teaching-guide"}
for s in $SCENES; do
  /Applications/Blender.app/Contents/MacOS/Blender -b -P kickstarter/render/lvc_render.py -- "$s" "$SAMPLES" 2>&1 | grep -E "RENDERED|Error|Traceback|File \"" | sed "s/^/[$s] /"
done
echo ALL_DONE
