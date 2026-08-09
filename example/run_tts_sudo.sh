#!/usr/bin/env bash
set -euo pipefail

# Run the TTS example with root privileges for hardware/audio access.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer the Pi HiFiBerry DAC card when present.
HIFIBERRY_CARD_ID=""
if [[ -r /proc/asound/cards ]]; then
	HIFIBERRY_CARD_ID="$(awk '/snd_rpi_hifiberry_dac|hifiberry/ {print $1; exit}' /proc/asound/cards | tr -d ' ')"
fi

EXTRA_ENV=(SDL_AUDIODRIVER=alsa PICARX_KILL_PULSEAUDIO=0)
if [[ -n "$HIFIBERRY_CARD_ID" ]]; then
	EXTRA_ENV+=("PICARX_AUDIODEV=plughw:${HIFIBERRY_CARD_ID},0")
	EXTRA_ENV+=("PICARX_AUDIO_CARD_ID=${HIFIBERRY_CARD_ID}")
fi

exec sudo -E env "${EXTRA_ENV[@]}" /usr/bin/python "$SCRIPT_DIR/3.tts_example.py"