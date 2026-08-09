#!/usr/bin/env bash
set -euo pipefail

# Run the TTS example with root privileges for hardware/audio access.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec sudo -E env SDL_AUDIODRIVER=alsa /usr/bin/python "$SCRIPT_DIR/3.tts_example.py"