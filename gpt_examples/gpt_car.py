import os
import importlib.util
from pathlib import Path
import json
import wave
import struct
import math

def _load_module_from_file(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec for {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    from gpt_examples import follow_human_face
except Exception:
    try:
        import follow_human_face
    except Exception:
        follow_human_face = _load_module_from_file(
            "follow_human_face",
            Path(__file__).resolve().with_name("follow_human_face.py"),
        )

pretend_roomba = None
_pretend_roomba_import_error = None
try:
    from gpt_examples import pretend_roomba
except Exception as exc:
    _pretend_roomba_import_error = exc
    try:
        from example import fauroomba as pretend_roomba
    except Exception as exc2:
        _pretend_roomba_import_error = exc2
        try:
            pretend_roomba = _load_module_from_file(
                "pretend_roomba",
                Path(__file__).resolve().parents[1] / "example" / "fauroomba.py",
            )
        except Exception as exc3:
            _pretend_roomba_import_error = exc3
            pretend_roomba = None

from openai_helper import OpenAiHelper
from keys import (
    OPENAI_API_KEY,
    OPENAI_ASSISTANT_ID,
    OPENAI_ASSISTANT_NAME,
    OPENAI_ASSISTANT_MODEL,
)
from preset_actions import *
from utils import *

SOUND_EFFECT_ACTIONS = ()
try:
    SOUND_EFFECT_ACTIONS
except NameError:
    SOUND_EFFECT_ACTIONS = ()

# STT/TTS config (see gpt_examples/README.md "Modify parameters")
LANGUAGE = ['en']  # Keep a single language for faster STT turnaround in command-driving mode.
VOLUME_DB = 0  # TTS post-gain in dB via sox; keep 0 by default to avoid clipping/loud jumps
TTS_VOICE = 'nova'  # alloy, echo, fable, onyx, nova, or shimmer
VOICE_INSTRUCTIONS = ""  # https://www.openai.fm/
STT_NO_SPEECH_FILLER = "this is the conversation between me and a robot"
VOICE_TIMEOUT_FALLBACK_COUNT = 6
VOICE_MIN_ENERGY_THRESHOLD = 35.0
VOICE_MAX_ENERGY_THRESHOLD = 95.0
VOICE_TIMEOUT_BACKOFF = 0.7
VOICE_LISTEN_TIMEOUT_SEC = 4
VOICE_PHRASE_TIME_LIMIT_SEC = 2.5
VOICE_LISTEN_CUE_ENABLED = True
VOICE_LISTEN_START_BEEPS = 1
VOICE_LISTEN_END_BEEPS = 2
VOICE_LISTEN_BEEP_GAP_SEC = 0.12
VOICE_LISTEN_BEEP_FREQ_HZ = 880
VOICE_LISTEN_BEEP_DURATION_SEC = 0.06
VOICE_POST_COMMAND_COOLDOWN_SEC = 1.0
VOICE_POST_MOTION_COOLDOWN_SEC = 0.15
VOICE_MAX_REPEAT_STEPS = 4
VOICE_REPEATABLE_INCREMENT_KEYS = ('w', 'x', 'a', 'd', 'i', 'm', 'j', 'l')
# Throttle hold timeout for voice forward/backward. Set to 0 to keep moving
# until an explicit stop/reset command is spoken.
VOICE_THROTTLE_FAILSAFE_SEC = 0.0
VOICE_MODE_CHAT_ENABLED = False
OFFLINE_COMMAND_STT_ENABLED = True
OPENAI_STT_FALLBACK_WHEN_OFFLINE_MISS = False
OPENAI_MODE_SWITCH_FALLBACK = True
OFFLINE_COMMAND_KEYWORD_WEIGHT = 1e-18
OFFLINE_USE_KEYWORD_SPOTTING = False
OFFLINE_SECOND_PASS_KEYWORD_SPOTTING = False
OFFLINE_CRITICAL_COMMAND_SPOTTING = False
OFFLINE_CRITICAL_KEYWORD_WEIGHT = 1e-20
OFFLINE_STT_ENGINE = "vosk"  # "vosk" or "pocketsphinx"
OFFLINE_STT_ENABLE_POCKETSPHINX_FALLBACK = True
VOSK_MODEL_PATH = os.environ.get("PICARX_VOSK_MODEL_PATH", "./vosk-model-small-en-us-0.15")
VOSK_SAMPLE_RATE = 16000
VOICE_VERBOSE_LOGS = False
OFFLINE_MAX_COMMAND_TOKENS = 5
OFFLINE_MAX_COMMAND_UNIQUE_TOKENS = 3
OFFLINE_MAX_NOISY_LOG_CHARS = 140
VOICE_REQUIRE_WAKE_WORD_FOR_CHAT = True
VOICE_CHAT_WAKE_WORDS = ("assistant", "pie car", "pai car","piecar", "piecar x", "paicar x")
TTS_PLAYBACK_VOLUME = None  # None means read current ALSA mixer volume dynamically
TTS_PLAYBACK_VOLUME_FALLBACK = 30
ENABLE_THINK_GESTURE = False
LOCAL_TTS_ENABLED_FOR_ZEN = True
ZEN_LOCAL_PLAYBACK_TIMEOUT_SEC = 15

ZEN_THOUGHTS = (
    "Breathe in, breathe out. Small steps still move you forward.",
    "The wheel turns best when we do one thing at a time.",
    "A steady path beats a fast zigzag.",
    "Quiet sensors, clear choices, smooth motion.",
    "I'm sorry Dave, I'm afraid I can't do that.",
)

import readline # optimize keyboard input, only need to import

try:
    import readchar
except ImportError:
    class _ReadCharFallbackKey:
        CTRL_C = "\x03"

    class _ReadCharFallback:
        key = _ReadCharFallbackKey()

        @staticmethod
        def readkey():
            import tty
            import termios

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    readchar = _ReadCharFallback()

import speech_recognition as sr

from contextlib import contextmanager
import re
import sys
import subprocess
import signal

for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        sys.path.insert(0, str(parent))
        sibling_vilib_root = parent.parent
        if sibling_vilib_root.is_dir():
            sys.path.insert(0, str(sibling_vilib_root))
        break


def _purge_legacy_python311_paths():
    legacy_paths = {
        "/usr/local/lib/python3.11",
        "/usr/local/lib/python3.11/site-packages",
        "/usr/local/lib/python3.11/dist-packages",
    }
    sys.path[:] = [p for p in sys.path if p and p not in legacy_paths and "python3.11" not in p]


def _add_vilib_dependency_paths():
    for dep_path in (
        "/usr/lib/python3/dist-packages",
        "/usr/lib/python3.11/dist-packages",
        "/usr/lib/aarch64-linux-gnu/python3.11/dist-packages",
    ):
        p = Path(dep_path)
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _cleanup_orphan_camera_processes():
    if os.environ.get("PICARX_AUTO_CLEAN_CAMERA", "1") != "1":
        return
    if os.geteuid() != 0:
        return

    script_markers = (
        "7.display.py",
        "8.stare_at_you.py",
        "9.record_video.py",
        "10.bull_fight.py",
        "11.video_car.py",
        "12.treasure_hunt.py",
        "13.app_control.py",
        "gpt_car.py",
    )

    try:
        proc = subprocess.run(["ps", "-eo", "pid=,args="], check=False, text=True, capture_output=True)
        lines = (proc.stdout or "").splitlines()
    except Exception:
        return

    current_pid = os.getpid()
    kill_pids = []
    for line in lines:
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid_text, args = parts
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid == current_pid:
            continue
        if any(marker in args for marker in script_markers):
            kill_pids.append(pid)

    for pid in kill_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def _cleanup_stale_audio_processes():
    """Release stale ALSA playback processes that keep the output card busy."""
    if os.environ.get("PICARX_AUTO_CLEAN_AUDIO", "1") != "1":
        return

    stale_markers = (
        "bluealsa-aplay",
        "aplay -D default",
        "aplay -D hw:2,0",
        "speaker-test -D hw:2,0",
    )

    try:
        proc = subprocess.run(["ps", "-eo", "pid=,args="], check=False, text=True, capture_output=True)
        lines = (proc.stdout or "").splitlines()
    except Exception:
        return

    current_pid = os.getpid()
    kill_pids = []
    for line in lines:
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid_text, args = parts
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid == current_pid:
            continue
        if any(marker in args for marker in stale_markers):
            kill_pids.append(pid)

    for pid in kill_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    if not kill_pids and os.geteuid() == 0:
        pattern = "bluealsa-aplay|aplay -D default|aplay -D hw:2,0|speaker-test -D hw:2,0"
        try:
            subprocess.run(["pkill", "-f", pattern], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    if not kill_pids and os.geteuid() != 0:
        try:
            subprocess.run(["sudo", "-n", "pkill", "-f", "bluealsa-aplay|aplay -D default|aplay -D hw:2,0|speaker-test -D hw:2,0"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


_purge_legacy_python311_paths()
_add_vilib_dependency_paths()
_cleanup_orphan_camera_processes()
_cleanup_stale_audio_processes()

from picarx import Picarx
from robot_hat import Music, Pin
try:
    # The vendored robot_hat shim only re-exports a curated name list at the top level and
    # doesn't include this, so import it directly from its real submodule path.
    from robot_hat.services.battery.sunfounder_battery import Battery as SunfounderBattery
except Exception:
    SunfounderBattery = None

import time
import threading
import random

# Global runtime defaults keep the script safe when imported for smoke tests or when
# no audio capture hardware is available on startup.
input_mode = "voice"
with_img = True
audio_profile = "auto"
audio_device_override = None
my_car = None
music = None
led = None
battery = None
openai_helper = None

os.popen("pinctrl set 20 op dh") # enable robot_hat speake switch
current_path = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_path) # change working directory


def _device_name_for_alsa_lookup(device_name):
    value = str(device_name or "").strip()
    if not value:
        return ""
    return value.lower().replace("plughw:", "hw:")


@contextmanager
def _quiet_alsa():
    """Suppress ALSA/PortAudio's C-level stderr spam (e.g. 'Unknown PCM ...') during device probes."""
    old_stderr = redirect_error_2_null()
    try:
        yield
    finally:
        cancel_redirect_error(old_stderr)


def _audio_override_is_valid_output(device_override):
    """Reject input-only ALSA devices such as a USB mic when they are passed as speaker output."""
    candidate = str(device_override or "").strip()
    if not candidate:
        return True

    candidate_lower = candidate.lower()
    if candidate_lower in {"default", "sysdefault", "dmix", "plug:dmix", "auto"}:
        return True

    try:
        with _quiet_alsa():
            pyaudio_module = sr.Microphone.get_pyaudio()
            pa = pyaudio_module.PyAudio()
    except Exception:
        return True

    try:
        count = pa.get_device_count()
        for idx in range(count):
            try:
                info = pa.get_device_info_by_index(idx)
            except Exception:
                continue
            name = str(info.get("name") or "").lower()
            if not name:
                continue
            if f"(hw:{candidate_lower})" in name or f"(hw:{_device_name_for_alsa_lookup(candidate_lower)})" in name:
                if int(info.get("maxOutputChannels") or 0) <= 0:
                    return False
                return True
        
        if re.search(r"hw:(\d+)", _device_name_for_alsa_lookup(candidate_lower)):
            return True
        return True
    except Exception:
        return True
    finally:
        try:
            pa.terminate()
        except Exception:
            pass


def _get_audio_device_candidates(include_input=False):
    candidates = []
    try:
        with _quiet_alsa():
            pyaudio_module = sr.Microphone.get_pyaudio()
            pa = pyaudio_module.PyAudio()
    except Exception:
        return candidates

    try:
        count = pa.get_device_count()
        for idx in range(count):
            try:
                info = pa.get_device_info_by_index(idx)
            except Exception:
                continue
            name = str(info.get("name") or "")
            max_in = int(info.get("maxInputChannels") or 0)
            max_out = int(info.get("maxOutputChannels") or 0)
            if include_input and max_in > 0:
                candidates.append((idx, name, "input"))
            if not include_input and max_out > 0:
                candidates.append((idx, name, "output"))
    except Exception:
        pass
    finally:
        try:
            pa.terminate()
        except Exception:
            pass
    return candidates


def _resolve_alsa_card_index(name_hints, default=None):
    """Find an ALSA card index by name, since card numbers shift across reboots/replugs
    (e.g. USB device order depends on enumeration timing) and must not be hardcoded."""
    try:
        with open("/proc/asound/cards", "r") as f:
            content = f.read()
    except Exception:
        return default

    for line in content.splitlines():
        line_lower = line.lower()
        match = re.match(r"\s*(\d+)\s*\[", line)
        if not match:
            continue
        card_index = match.group(1)
        if any(hint.lower() in line_lower for hint in name_hints):
            return card_index
    return default


def _apply_audio_route(profile_name=None, device_override=None):
    """Set ALSA environment variables for separate input and output routes.

    Playback output should use an actual output-capable device such as the HifiBerry DAC.
    Input capture should use the USB mic device, which is usually capture-only.
    """
    if profile_name is not None:
        profile_name = profile_name.lower()

    usb_card = _resolve_alsa_card_index(("usb", "device"), default="3")
    hifiberry_card = _resolve_alsa_card_index(("hifiberry",), default="2")

    playback_preset = {
        "hdmi": {
            "AUDIODEV": "default",
            "PICARX_AUDIODEV": "default",
            "PICARX_AUDIO_CARD_ID": "0",
            "PICARX_AUDIO_CARD_NAME": "vc4hdmi",
            "PICARX_AUDIO_CARD_HINT": "hdmi",
        },
        "usb": {
            "AUDIODEV": f"plughw:{usb_card},0",
            "PICARX_AUDIODEV": f"plughw:{usb_card},0",
            "PICARX_AUDIO_CARD_ID": usb_card,
            "PICARX_AUDIO_CARD_NAME": "USB PnP Audio Device",
            "PICARX_AUDIO_CARD_HINT": "usb_audio",
        },
        "i2s": {
            "AUDIODEV": f"plughw:{hifiberry_card},0",
            "PICARX_AUDIODEV": f"plughw:{hifiberry_card},0",
            "PICARX_AUDIO_CARD_ID": hifiberry_card,
            "PICARX_AUDIO_CARD_NAME": "snd_rpi_hifiberry_dac",
            "PICARX_AUDIO_CARD_HINT": "hifiberry",
        },
        "auto": {
            "AUDIODEV": f"plughw:{usb_card},0",
            "PICARX_AUDIODEV": f"plughw:{usb_card},0",
            "PICARX_AUDIO_CARD_ID": usb_card,
            "PICARX_AUDIO_CARD_NAME": "USB PnP Audio Device",
            "PICARX_AUDIO_CARD_HINT": "usb_audio",
        },
    }.get(profile_name or "auto", {})

    if device_override:
        device_override = str(device_override).strip()
        if device_override.startswith("hw:") or device_override.startswith("plughw:"):
            usb_card_for_check = _resolve_alsa_card_index(("usb", "device"), default="3")
            if "USB" in device_override.upper() or "DEVICE" in device_override.upper() or f"{usb_card_for_check},0" in device_override:
                print(f"Ignoring capture-only USB device for mixer output: {device_override}")
                device_override = None
        if device_override:
            os.environ["AUDIODEV"] = device_override
            os.environ["PICARX_AUDIODEV"] = device_override
            os.environ.setdefault("PICARX_AUDIO_CARD_ID", "2")
            os.environ.setdefault("PICARX_AUDIO_CARD_NAME", "speaker")
            os.environ.setdefault("PICARX_AUDIO_CARD_HINT", "output")
            return

    for key, value in playback_preset.items():
        os.environ[key] = str(value)

    if profile_name and profile_name not in {"auto"}:
        print(f"Playback route selected: {profile_name}")


def initialize_runtime():
    global input_mode, with_img, audio_profile, audio_device_override
    global my_car, music, led, openai_helper

    input_mode = None
    with_img = True
    args = sys.argv[1:]

    # audio selection is a CLI option instead of editing environment variables by hand
    audio_profile = "auto"
    audio_device_override = None
    for i, arg in enumerate(args):
        low = arg.lower()
        if low == "--keyboard":
            input_mode = 'keyboard'
        elif low == "--voice":
            input_mode = 'voice'
        elif low == "--no-img":
            with_img = False
        elif low in {"--audio", "--audio-profile"} and i + 1 < len(args):
            audio_profile = args[i + 1].lower()
        elif low == "--audio-device" and i + 1 < len(args):
            audio_device_override = args[i + 1]

    if input_mode is None:
        input_mode = 'voice'

    # Startup health check: clear stale ALSA holders before initializing playback.
    _cleanup_stale_audio_processes()
    if audio_device_override:
        _apply_audio_route(device_override=audio_device_override)
    else:
        _apply_audio_route(audio_profile)

    # The capture side must remain separate from the speaker path.
    output_name = os.environ.get("PICARX_AUDIO_CARD_NAME") or "default output"
    output_dev = os.environ.get("PICARX_AUDIODEV") or os.environ.get("AUDIODEV") or "unset"
    capture_index = _select_input_device_index()
    if capture_index is not None:
        print(f"Audio config: output={output_name} ({output_dev}), input=PyAudio device index {capture_index}.")
    else:
        print(f"Audio config: output={output_name} ({output_dev}), input=no capture device detected yet.")

    # For backwards compatibility with the original example setup, keep these as defaults.
    os.environ.setdefault("SDL_AUDIODRIVER", "alsa")

    # openai assistant init
    # =================================================================
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is empty; set it in gpt_examples/keys.py or in the environment")

    # Without a system prompt, gpt-4o defaults to describing an attached camera image instead of
    # reacting to what was actually said. Build one from the real action/sound tables so it can't
    # drift out of sync with what the car can actually do.
    _known_actions = ', '.join(f'"{a}"' for a in globals().get('actions_dict', {}))
    _known_sounds = ', '.join(f'"{s}"' for s in globals().get('sounds_dict', {}))
    assistant_instructions = (
        "You are a small car with AI capabilities named PaiCar-X. You can engage in conversations "
        "with people and react accordingly to different situations with actions or sounds. You are "
        "driven by two rear wheels, with two front wheels that can turn left and right, and equipped "
        "with a camera mounted on a 2-axis gimbal. If a camera image is attached, only describe it "
        "when the user's message actually asks about what you see; otherwise respond to what they said.\n\n"
        "Respond ONLY with a JSON object (no markdown, no code fences) in this exact shape:\n"
        '{"actions": ["<action1>", "<action2>"], "answer": "<your spoken reply>"}\n\n'
        f"Available actions: {_known_actions}.\n"
        f"Available sound effects (include in actions to play them): {_known_sounds}."
    )

    openai_helper = OpenAiHelper(
        OPENAI_API_KEY,
        OPENAI_ASSISTANT_ID or "",
        OPENAI_ASSISTANT_NAME,
        model=OPENAI_ASSISTANT_MODEL,
        instructions=assistant_instructions,
    )

    # car init
    # =================================================================
    try:
        my_car = Picarx()
        time.sleep(1)
    except Exception as e:
        raise RuntimeError(e)

    try:
        with _quiet_alsa():
            music = Music()
    except Exception as exc:
        msg = str(exc)
        if "Device or resource busy" in msg or "Couldn't open audio device" in msg or "No such device" in msg:
            print("Detected a stale ALSA output lock. Attempting to clear the stale audio holder and retrying once...")
            _cleanup_stale_audio_processes()
            try:
                with _quiet_alsa():
                    music = Music()
            except Exception as retry_exc:
                print(f"Audio mixer unavailable after cleanup: {retry_exc}. If this persists, run: sudo pkill -f 'bluealsa-aplay|aplay -D default|aplay -D hw:2,0|speaker-test -D hw:2,0'")
                music = None
        else:
            print(f"Audio mixer unavailable: {exc}. Continuing without TTS/sound effects; voice capture remains available if a mic is detected.")
            music = None

        if music is None:
            class _NullMusic:
                def __init__(self, *args, **kwargs):
                    pass

                def sound_play(self, *args, **kwargs):
                    return None

                def sound_play_threading(self, *args, **kwargs):
                    return None

                def music_play(self, *args, **kwargs):
                    return None

                def music_stop(self, *args, **kwargs):
                    return None

                def music_set_volume(self, *args, **kwargs):
                    return None

                def music_get_volume(self, *args, **kwargs):
                    return 0

                def music_pause(self, *args, **kwargs):
                    return None

                def music_resume(self, *args, **kwargs):
                    return None

            music = _NullMusic()

    led = Pin('LED')

    # battery init
    # =================================================================
    global battery
    if SunfounderBattery is None:
        print("Battery ADC support not available in this robot_hat install; battery checks will be skipped.")
        battery = None
    else:
        try:
            battery = SunfounderBattery(channel="A4")  # RoboHAT v4's documented battery ADC channel
        except Exception as exc:
            print(f"Battery ADC unavailable: {exc}. Battery checks will be skipped.")
            battery = None

    # Vilib start
    # =================================================================
    if with_img:
        global cv2, Vilib
        try:
            from vilib import Vilib
        except Exception as exc:
            raise RuntimeError(
                "Unable to import vilib. This usually means the camera stack is not on the active Python path. "
                "Start the script with the repo's configured interpreter or run the no-image mode (--no-img). "
                f"Original error: {exc}"
            ) from exc

        import cv2

        Vilib.camera_start(vflip=False,hflip=False)
        Vilib.show_fps()
        Vilib.display(local=False,web=True)

        while True:
            if Vilib.flask_start:
                break
            time.sleep(0.01)

        time.sleep(.5)
        print('\n')

    return input_mode


def _voice_input_available():
    return _select_input_device_index() is not None


# Each pyaudio.PyAudio() instantiation reinitializes jack/bluealsa probing, which is expensive
# and appears to exhaust an ALSA/PortAudio resource after several turns if repeated too often.
# Cache the results instead of re-probing on every single listen attempt.
_cached_capture_device_index = None
_cached_capture_channels = {}


def _reset_capture_device_cache():
    global _cached_capture_device_index, _cached_capture_channels
    _cached_capture_device_index = None
    _cached_capture_channels = {}


def _select_input_device_index():
    global _cached_capture_device_index
    if _cached_capture_device_index is not None:
        return _cached_capture_device_index
    result = _probe_input_device_index()
    if result is not None:
        _cached_capture_device_index = result
    return result


def _probe_input_device_index():
    try:
        with _quiet_alsa():
            pyaudio_module = sr.Microphone.get_pyaudio()
            pa = pyaudio_module.PyAudio()
    except Exception:
        return None

    try:
        count = pa.get_device_count()
        if count <= 0:
            return None

        # The USB mic is the capture device on this stack and is usually reported as index 1.
        # Prefer the actual device map instead of the stale default ALSA route and avoid forcing
        # the broken HDMI/default capture indices during startup.
        for preferred in (1, 3, 2, 0):
            if preferred >= count:
                continue
            try:
                device_info = pa.get_device_info_by_index(preferred)
            except Exception:
                continue
            if int(device_info.get("maxInputChannels") or 0) > 0:
                return preferred

        preferred_names = ["usb", "mic", "capture", "input", "audio"]
        explicit_candidates = []
        best_index = None
        best_score = -1

        for idx in range(count):
            try:
                device_info = pa.get_device_info_by_index(idx)
            except Exception:
                continue
            input_channels = int(device_info.get("maxInputChannels") or 0)
            if input_channels <= 0:
                continue
            name = str(device_info.get("name") or "").lower()

            if "usb" in name or "device" in name or "audio" in name:
                explicit_candidates.append(idx)

            score = 0
            if "usb" in name:
                score += 60
            if "mic" in name or "capture" in name:
                score += 35
            if "input" in name:
                score += 10
            if any(token in name for token in preferred_names):
                score += 5
            if "hifiberry" in name or "wm8960" in name or "robot" in name or "robot_hat" in name:
                score += 15
            if score > best_score:
                best_index = idx
                best_score = score

        # Prefer the actual USB microphone when present. This avoids the broken ALSA default route.
        for idx in explicit_candidates:
            try:
                device_info = pa.get_device_info_by_index(idx)
                name = str(device_info.get("name") or "").lower()
            except Exception:
                continue
            if "usb" in name or "device" in name:
                return idx

        if best_index is not None:
            return best_index

        for idx in range(count):
            try:
                if int(pa.get_device_info_by_index(idx).get("maxInputChannels") or 0) > 0:
                    return idx
            except Exception:
                continue
        return None
    except Exception:
        return None
    finally:
        try:
            pa.terminate()
        except Exception:
            pass


def _ensure_voice_or_keyboard_mode():
    global input_mode
    if input_mode == 'voice':
        selected = _select_input_device_index()
        if selected is None:
            print("Voice mode selected; no usable USB capture device was detected, so the script will fall back to keyboard input.")
            input_mode = 'keyboard'
            return input_mode
        print(f"Voice mode selected; using capture device index {selected}.")
    return input_mode


def _open_microphone_for_listen(device_index=None):
    """Open the mic explicitly instead of using the flaky context-manager teardown.

    speech_recognition.Microphone.__enter__ suppresses its own audio-open errors and returns an
    object whose stream is still None. When the context manager later exits, it calls
    self.stream.close() on that None and raises: AttributeError: 'NoneType' object has no
    attribute 'close'.

    Some USB audio devices advertise stereo capture but reject mono streams even though
    the device info reports maxInputChannels > 1. Try the valid channel counts in order,
    rather than assuming every device accepts one channel.
    """
    device_index = 1 if device_index is None else device_index
    mic = sr.Microphone(device_index=device_index, chunk_size=8192)
    mic.audio = None
    mic.stream = None

    preferred_channels = [1, 2]
    if device_index in _cached_capture_channels:
        preferred_channels = _cached_capture_channels[device_index]
    else:
        try:
            with _quiet_alsa():
                pyaudio_module = sr.Microphone.get_pyaudio()
                pa = pyaudio_module.PyAudio()
            try:
                device_info = pa.get_device_info_by_index(device_index)
                max_input = int(device_info.get("maxInputChannels") or 0)
                if max_input > 0:
                    preferred_channels = []
                    for channels in (1, 2):
                        if channels <= max_input:
                            preferred_channels.append(channels)
            except Exception:
                pass
            finally:
                try:
                    pa.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        _cached_capture_channels[device_index] = preferred_channels

    last_exc = None
    for channels in preferred_channels:
        try:
            with _quiet_alsa():
                mic.audio = mic.pyaudio_module.PyAudio()
                mic.stream = sr.Microphone.MicrophoneStream(
                    mic.audio.open(
                        input_device_index=mic.device_index,
                        channels=channels,
                        format=mic.format,
                        rate=mic.SAMPLE_RATE,
                        frames_per_buffer=mic.CHUNK,
                        input=True,
                    )
                )
            return mic
        except Exception as exc:
            last_exc = exc
            if mic.audio is not None:
                try:
                    mic.audio.terminate()
                except Exception:
                    pass
            mic.audio = None
            mic.stream = None

    # The cached channel count didn't actually work (e.g. device changed); drop it so the
    # next attempt re-probes instead of repeating a stale, failing value forever.
    _cached_capture_channels.pop(device_index, None)
    raise last_exc if last_exc is not None else OSError("Unable to open microphone stream")


def _close_microphone_for_listen(mic):
    try:
        if getattr(mic, "stream", None) is not None:
            mic.stream.close()
    except Exception:
        pass
    finally:
        mic.stream = None
        try:
            if getattr(mic, "audio", None) is not None:
                mic.audio.terminate()
        except Exception:
            pass
        mic.audio = None

# For backwards compatibility with the original example setup, keep these as defaults.
os.environ.setdefault("SDL_AUDIODRIVER", "alsa")

# speech_recognition init
# =================================================================
'''
self.energy_threshold = 300  # minimum audio energy to consider for recording
self.dynamic_energy_threshold = True
self.dynamic_energy_adjustment_damping = 0.15
self.dynamic_energy_ratio = 1.5
self.pause_threshold = 0.8  # seconds of non-speaking audio before a phrase is considered complete
self.operation_timeout = None  # seconds after an internal operation (e.g., an API request) starts before it times out, or ``None`` for no timeout

self.phrase_threshold = 0.3  # minimum seconds of speaking audio before we consider the speaking audio a phrase - values below this are ignored (for filtering out clicks and pops)
self.non_speaking_duration = 0.5  # seconds of non-speaking audio to keep on both sides of the recording

'''
recognizer = sr.Recognizer()
recognizer.dynamic_energy_adjustment_damping = 0.16
recognizer.dynamic_energy_ratio = 1.6
# Dynamic thresholding can climb too high on this drivetrain/camera noise profile
# and then reject normal speech for many consecutive turns.
recognizer.dynamic_energy_threshold = False
recognizer.energy_threshold = 70

# speak_hanlder
# =================================================================
global speech_loaded
speech_loaded = False

global speech_lock
speech_lock = threading.Lock()

global tts_file
tts_file = None


def _resolve_tts_playback_volume(default=TTS_PLAYBACK_VOLUME_FALLBACK):
    """Resolve playback volume from ALSA mixer percentage (0-100).

    Falls back to a safe default when amixer is unavailable or cannot be parsed.
    """
    if isinstance(TTS_PLAYBACK_VOLUME, int):
        return max(0, min(100, TTS_PLAYBACK_VOLUME))

    for control in ("Speaker", "Master", "PCM"):
        try:
            proc = subprocess.run(
                ["amixer", "get", control],
                check=False,
                text=True,
                capture_output=True,
                timeout=1,
            )
            output = proc.stdout or ""
            match = re.search(r"\[(\d{1,3})%\]", output)
            if match:
                return max(0, min(100, int(match.group(1))))
        except Exception:
            continue

    return max(0, min(100, default))

def speak_hanlder():
    global speech_loaded, tts_file
    while True:
        try:
            with speech_lock:
                _isloaded = speech_loaded
            if _isloaded:
                # gray_print('speak start')
                speak_block(music, tts_file, _resolve_tts_playback_volume())
                # gray_print('speak done')
                with speech_lock:
                    speech_loaded = False
        except Exception as exc:
            # Never let the speech worker die; otherwise callers waiting on
            # speech_loaded can block indefinitely and freeze manual input flow.
            print(f"speak_hanlder error: {exc}")
            with speech_lock:
                speech_loaded = False
        time.sleep(0.05)

global speak_thread
speak_thread = threading.Thread(target=speak_hanlder)
speak_thread.daemon = True


# actions thread
# =================================================================
action_status = 'standby' # 'standby', 'think', 'actions', 'actions_done'
led_status = 'standby' # 'standby', 'think' or 'actions', 'actions_done'
last_action_status = 'standby'
last_led_status = 'standby'

LED_DOUBLE_BLINK_INTERVAL = 0.8 # seconds
LED_BLINK_INTERVAL = 0.1 # seconds

actions_to_be_done = []
action_lock = threading.Lock()

# Head and motor limits and initial values
DEFAULT_MOTOR_SPEED = 0
DEFAULT_DIR_SERVO_ANGLE = 0
DEFAULT_HEAD_PAN = 0 # initial head pan angle
DEFAULT_HEAD_TILT = 0 # initial head tilt angle
MAX_MOTOR_SPEED = 100
MIN_MOTOR_SPEED = 0
MAX_DIR_SERVO_ANGLE = 45
MIN_DIR_SERVO_ANGLE = -45
MAX_HEAD_PAN = 55
MIN_HEAD_PAN = -55
MAX_HEAD_TILT = 55
MIN_HEAD_TILT = -55
FOLLOW_HUMAN_FACE_DURATION = 60.0 # seconds
ROOMBA_MODE_DURATION = 60.0 # seconds
global follow_duration
follow_duration=FOLLOW_HUMAN_FACE_DURATION
global roomba_duration
roomba_duration = ROOMBA_MODE_DURATION

global motor_speed
motor_speed = DEFAULT_MOTOR_SPEED   # initial motor speed
global dir_servo_angle
dir_servo_angle = DEFAULT_DIR_SERVO_ANGLE # initial direction
global head_pan
head_pan = DEFAULT_HEAD_PAN   # initial head pan angle
global head_tilt    
head_tilt = DEFAULT_HEAD_TILT # initial head tilt angle

WARNING_VOLTAGE = 6.8  # Alert the user
SHUTDOWN_VOLTAGE = 6.4 # Force safe shutdown to protect the Pi and batteries
SPEECH_WAIT_TIMEOUT_SEC = 20.0
ACTION_WAIT_TIMEOUT_SEC = 8.0


def action_handler():
    global action_status, actions_to_be_done, led_status, last_action_status, last_led_status
    global dir_servo_angle

    # standby_actions = ['waiting', 'feet_left_right']
    # standby_weights = [1, 0.3]

    action_interval = 5 # seconds
    last_action_time = time.time()
    last_led_time = time.time()

    while True:
      try:
        with action_lock:
            _state = action_status

        # led
        # ------------------------------
        led_status = _state

        if led_status != last_led_status:
            last_led_time = 0
            last_led_status = led_status

        if led_status == 'standby':
            if time.time() - last_led_time > LED_DOUBLE_BLINK_INTERVAL:
                try:
                    led.off()
                    led.on()
                    sleep(.1)
                    led.off()
                    sleep(.1)
                    led.on()
                    sleep(.1)
                    led.off()
                except Exception as exc:
                    print(f"LED update error (standby): {exc}")
                last_led_time = time.time()
        elif led_status == 'think':
            if time.time() - last_led_time > LED_BLINK_INTERVAL:
                try:
                    led.off()
                    sleep(LED_BLINK_INTERVAL)
                    led.on()
                    sleep(LED_BLINK_INTERVAL)
                except Exception as exc:
                    print(f"LED update error (think): {exc}")
                last_led_time = time.time()
        elif led_status == 'actions':
                try:
                    led.on()
                except Exception as exc:
                    print(f"LED update error (actions): {exc}")

        # actions
        # ------------------------------
        if _state == 'standby':
            last_action_status = 'standby'
            if time.time() - last_action_time > action_interval:
                # TODO: standby actions
                last_action_time = time.time()
                action_interval = random.randint(2, 6)
        elif _state == 'think':
            if last_action_status != 'think':
                last_action_status = 'think'
                if ENABLE_THINK_GESTURE:
                    # Optional decorative gesture while waiting on GPT response.
                    keep_think(my_car)
        elif _state == 'actions':
            last_action_status = 'actions'
            with action_lock:
                _actions = actions_to_be_done
            for _action in _actions:
                try:
                    actions_dict[_action](my_car)
                except Exception as e:
                    print(f'action error: {e}')
                time.sleep(0.5)

            # Preset gesture actions (wave_hands, resist, twist_body, etc.) drive the steering
            # servo directly and always finish by re-centering it, so resync the tracked angle
            # here or the next voice/keyboard turn command would compute from a stale value.
            dir_servo_angle = DEFAULT_DIR_SERVO_ANGLE

            with action_lock:
                action_status = 'actions_done'
            last_action_time = time.time()

        time.sleep(0.01)
      except Exception as exc:
        # Swallow transient errors (e.g. GPIO released by shutdown cleanup while this daemon
        # thread is mid-iteration) instead of letting the whole thread die with a stack trace.
        print(f"action_handler error: {exc}")
        time.sleep(0.1)

action_thread = threading.Thread(target=action_handler)
action_thread.daemon = True


def reset_motor_and_direction(motor_speed=motor_speed, dir_servo_angle=dir_servo_angle):
    my_car.forward(MIN_MOTOR_SPEED)
    my_car.stop()
    my_car.set_dir_servo_angle(dir_servo_angle)
    return motor_speed, dir_servo_angle

def motor_forward(motor_speed): 
    # motor_speed = abs(motor_speed)
    motor_speed += 5
    if motor_speed > MAX_MOTOR_SPEED:
        motor_speed = MAX_MOTOR_SPEED
    elif motor_speed < MIN_MOTOR_SPEED:
        motor_speed = MIN_MOTOR_SPEED
    my_car.forward(motor_speed)
    return motor_speed

def motor_backward(motor_speed):
    # motor_speed = abs(motor_speed)
    motor_speed += 5
    if motor_speed > MAX_MOTOR_SPEED:
        motor_speed = MAX_MOTOR_SPEED
    elif motor_speed < MIN_MOTOR_SPEED:
        motor_speed = MIN_MOTOR_SPEED
    # motor speed adjustment, a positive increment that will have sign reversal in backward movement
    my_car.backward(motor_speed)
    return motor_speed

def steer_right(dir_servo_angle):
    dir_servo_angle += 5
    if dir_servo_angle > MAX_DIR_SERVO_ANGLE:
        dir_servo_angle = MAX_DIR_SERVO_ANGLE
    my_car.set_dir_servo_angle(dir_servo_angle)
    return dir_servo_angle

def steer_left(dir_servo_angle):
    dir_servo_angle -= 5
    if dir_servo_angle < MIN_DIR_SERVO_ANGLE:
        dir_servo_angle = MIN_DIR_SERVO_ANGLE
    my_car.set_dir_servo_angle(dir_servo_angle)
    return dir_servo_angle

def stop_car():
    my_car.forward(MIN_MOTOR_SPEED)
    my_car.stop()
    return MIN_MOTOR_SPEED

def reset_head_position(head_pan=head_pan, head_tilt=head_tilt ):
    my_car.set_cam_tilt_angle(head_tilt)
    my_car.set_cam_pan_angle(head_pan)
    return head_pan, head_tilt

def tilt_head_down(head_tilt):
    head_tilt -= 5
    if head_tilt < MIN_HEAD_TILT:
        head_tilt = MIN_HEAD_TILT
    my_car.set_cam_tilt_angle(head_tilt)
    return head_tilt

def tilt_head_up(head_tilt):
    head_tilt += 5
    if head_tilt > MAX_HEAD_TILT:
        head_tilt = MAX_HEAD_TILT
    my_car.set_cam_tilt_angle(head_tilt)
    return head_tilt

def pan_head_left(head_pan):
    head_pan -= 5
    if head_pan < MIN_HEAD_PAN:
        head_pan = MIN_HEAD_PAN
    my_car.set_cam_pan_angle(head_pan)
    return head_pan

def pan_head_right(head_pan):
    head_pan += 5
    if head_pan > MAX_HEAD_PAN:
        head_pan = MAX_HEAD_PAN
    my_car.set_cam_pan_angle(head_pan)
    return head_pan

def shutdown_gptcar():
    my_car.forward(MIN_MOTOR_SPEED)
    my_car.stop()
    my_car.set_dir_servo_angle(DEFAULT_DIR_SERVO_ANGLE)
    reset_head_position(DEFAULT_HEAD_PAN, DEFAULT_HEAD_TILT)
    return MIN_MOTOR_SPEED, DEFAULT_DIR_SERVO_ANGLE, DEFAULT_HEAD_PAN, DEFAULT_HEAD_TILT

def activate_voice_input():
    global input_mode
    input_mode = 'voice'

def activate_camera():
    # Implement the logic to activate the camera here
    pass

def _speak_text(text) -> None:
    """Speak text through the existing TTS pipeline (same path used for GPT replies) and
    block until playback finishes, instead of a separate ad-hoc TTS call."""
    global tts_file, speech_loaded
    if openai_helper is None:
        print(f"TTS unavailable (no OpenAI helper): {text}")
        return
    _time = time.strftime("%y-%m-%d_%H-%M-%S", time.localtime())
    _tts_f = f"./tts/{_time}_raw.wav"
    if not openai_helper.text_to_speech(text, _tts_f, TTS_VOICE, response_format='wav', instructions=VOICE_INSTRUCTIONS):
        print(f"TTS failed for: {text}")
        return
    _tts_file = f"./tts/{_time}_{VOLUME_DB}dB.wav"
    if not sox_volume(_tts_f, _tts_file, VOLUME_DB):
        _tts_file = _tts_f

    _play_tts_file_and_wait(_tts_file)


def _play_tts_file_and_wait(audio_file):
    global tts_file, speech_loaded
    with speech_lock:
        tts_file = audio_file
        speech_loaded = True

    wait_started = time.time()
    while True:
        with speech_lock:
            if not speech_loaded:
                break
        if time.time() - wait_started > SPEECH_WAIT_TIMEOUT_SEC:
            print("Local TTS wait timeout; clearing speech flag and continuing.")
            with speech_lock:
                speech_loaded = False
            break
        time.sleep(.01)


def _synthesize_local_tts_wav(text, output_wav):
    engines = (
        ["espeak-ng", "-w", output_wav, text],
        ["espeak", "-w", output_wav, text],
        ["pico2wave", "-w", output_wav, text],
    )
    for cmd in engines:
        try:
            proc = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc.returncode == 0 and os.path.isfile(output_wav) and os.path.getsize(output_wav) > 0:
                return True
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return False


def _speak_text_local(text):
    os.makedirs("./tts", exist_ok=True)
    local_stamp = f"{time.strftime('%y-%m-%d_%H-%M-%S', time.localtime())}_{int(time.time() * 1000) % 1000:03d}"
    local_raw = f"./tts/{local_stamp}_local_raw.wav"
    if not _synthesize_local_tts_wav(text, local_raw):
        return False

    local_out = f"./tts/{local_stamp}_local_{VOLUME_DB}dB.wav"
    if not sox_volume(local_raw, local_out, VOLUME_DB):
        local_out = local_raw

    if _play_wav_with_aplay(local_out):
        return True

    # Fallback to the existing music worker path if direct ALSA playback is unavailable.
    _play_tts_file_and_wait(local_out)
    return True


def _play_wav_with_aplay(audio_file):
    if not os.path.isfile(audio_file):
        return False

    aplay_path = None
    for candidate in ("/usr/bin/aplay", "aplay"):
        try:
            probe = subprocess.run([candidate, "--version"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if probe.returncode == 0:
                aplay_path = candidate
                break
        except Exception:
            continue

    if aplay_path is None:
        return False

    device = os.environ.get("PICARX_AUDIODEV") or os.environ.get("AUDIODEV")
    cmd = [aplay_path, "-q"]
    if device:
        cmd.extend(["-D", device])
    cmd.append(audio_file)

    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=ZEN_LOCAL_PLAYBACK_TIMEOUT_SEC,
        )
        return proc.returncode == 0
    except Exception:
        return False


_listen_beep_wav = None


def _ensure_listen_beep_wav():
    global _listen_beep_wav
    if _listen_beep_wav and os.path.isfile(_listen_beep_wav):
        return _listen_beep_wav

    os.makedirs("./tts", exist_ok=True)
    beep_path = "./tts/listen_beep.wav"
    sample_rate = 16000
    samples = max(1, int(VOICE_LISTEN_BEEP_DURATION_SEC * sample_rate))
    amplitude = 9000

    try:
        with wave.open(beep_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for i in range(samples):
                env = 1.0 - (i / samples)
                value = int(amplitude * env * math.sin(2.0 * math.pi * VOICE_LISTEN_BEEP_FREQ_HZ * i / sample_rate))
                wav_file.writeframesraw(struct.pack("<h", value))

        _listen_beep_wav = beep_path
        return _listen_beep_wav
    except Exception:
        return None


def _play_listen_beeps(count):
    if not VOICE_LISTEN_CUE_ENABLED or count <= 0:
        return

    beep_path = _ensure_listen_beep_wav()
    if not beep_path:
        return

    for idx in range(count):
        played = _play_wav_with_aplay(beep_path)
        if not played:
            try:
                # Fallback to robot_hat audio path when direct aplay output is unavailable.
                music.sound_play(beep_path, _resolve_tts_playback_volume())
            except Exception:
                pass
        if idx < count - 1:
            time.sleep(VOICE_LISTEN_BEEP_GAP_SEC)

def _follow_human_face(follow_duration: float = 60.0):
    if 'Vilib' not in globals() or Vilib is None:
        print("Follow-face unavailable: camera runtime is not initialized.")
        return None

    return follow_human_face.follow_human_face(my_car, Vilib, _speak_text, follow_duration)

def _pretend_roomba(roomba_duration: float = 60.0):
    if pretend_roomba is None:
        print(f"Pretend Roomba unavailable: {_pretend_roomba_import_error}")
        return None
    return pretend_roomba.pretend_roomba(my_car, Vilib, _speak_text, roomba_duration)


def _wiggle_gesture():
    """Run a brief local 'thinking' gesture on-demand."""
    keep_think(my_car)


def _offer_zen_thought():
    """Speak a short local Zen line without calling GPT dialogue."""
    zen_text = random.choice(ZEN_THOUGHTS)
    if LOCAL_TTS_ENABLED_FOR_ZEN and _speak_text_local(zen_text):
        return
    if LOCAL_TTS_ENABLED_FOR_ZEN:
        print("Zen local TTS unavailable; falling back to OpenAI TTS.")
    _speak_text(zen_text)

def main_battery_check(prn_voltage: bool = False):
    """
    Check the main battery voltage and handle low battery situations.
    """
    if battery is None:
        print("Battery check unavailable: no battery ADC was detected at startup.")
        return None
    try:
        # Read the scaling voltage
        # battery = SunfounderBattery(channel="A4")  
        # # RoboHAT v4's documented battery ADC channel
        voltage = round(battery.get_battery_voltage(), 2)
        if prn_voltage:
            print(f"Battery voltage: {voltage:.2f}V")
    
        # Check if the voltage is below the shutdown threshold
        if voltage <= SHUTDOWN_VOLTAGE:
            # Step 1: Emergency stop the robot motors
            my_car.forward(MIN_MOTOR_SPEED)
            my_car.stop()
            
            # Step 2: Play an audio alert
            _speak_text("Battery critical. Shutting down now.")
            time.sleep(3)
            
            # Step 3: Trigger Linux OS safe shutdown
            os.system("sudo shutdown -h now")
            
        # Check if the voltage is below the warning threshold
        elif voltage <= WARNING_VOLTAGE:
            print(f"Warning: Low Battery! Voltage is {voltage}V")
            _speak_text("Low battery. Please charge.")
        
    except Exception as exc:
        print(f"Battery check error: {exc}")
        return None
    finally:
        if 'voltage' in locals():
            return voltage
        return None


def activate_keyboard_input():
    # Voice command 't'/'type'/'keyboard' should drop straight into the WASD manual control
    # loop, same as typing 'manual' at the input prompt, not the free-text GPT chat prompt.
    manual_keyboard_loop()

# Shared by keyboard 'manual' mode and voice commands so both dispatch identically.
def _apply_manual_key(key):
    global motor_speed, dir_servo_angle, head_pan, head_tilt, follow_duration
    if key in ('wxsad'):
        if key == 'w': # Move forward with increasing motor speed and steering current direction
            motor_speed = motor_forward(motor_speed)

        elif key == 'x': # move backward with increasing motor speed and steering current dir
            motor_speed = motor_backward(motor_speed)

        elif key == 'a': # Turn left with current motor speed and direction
            dir_servo_angle = steer_left(dir_servo_angle)

        elif key == 'd': # Turn right with current motor speed and direction
            dir_servo_angle = steer_right(dir_servo_angle)

        elif key == 's': # STOP! Reset the picar's direction and motor speed, then STOP!!!
            motor_speed = stop_car()

    elif key in ('ikmjl'):
        if key == 'i': # Move tilt angle up
            head_tilt = tilt_head_up(head_tilt)

        elif key == 'k': # Reset tilt and pan angle to 0 (level+straight)
            head_pan, head_tilt = reset_head_position(head_pan = DEFAULT_HEAD_PAN, head_tilt = DEFAULT_HEAD_TILT)

        elif key == 'm': # Move tilt angle down
            head_tilt = tilt_head_down(head_tilt)

        elif key == 'j': # Move pan angle left
            head_pan = pan_head_left(head_pan)

        elif key == 'l': # Move pan angle right
            head_pan = pan_head_right(head_pan)
    elif key in 'rvcbtfpzg':
        if key == 'r': # Reset Motor and Direction
            motor_speed, dir_servo_angle = reset_motor_and_direction(DEFAULT_MOTOR_SPEED, DEFAULT_DIR_SERVO_ANGLE)
        elif key == 'v': # Activate voice input
            activate_voice_input()
        elif key == 'c': # Activate camera
            activate_camera()
        elif key == 'b': # Check battery
            main_battery_check(True)
        elif key == 't': # Manual input
            activate_keyboard_input()
        elif key == 'f': # Follow human face for a duration
            _follow_human_face(follow_duration)
        elif key == 'p': # Pretend Roomba mode
            _pretend_roomba(roomba_duration)
        elif key == 'z': # Speak a Zen thought
            _offer_zen_thought()
        elif key == 'g': # Run a wiggle gesture
            _wiggle_gesture()


# Recognized speech that matches one of these phrases drives the car directly instead of going through GPT.
_VOICE_COMMAND_KEYS = {
    'w': ('forward', 'go forward', 'move forward', 'drive forward'),
    'x': ('backward', 'back up', 'go backward', 'move backward', 'go back', 'move back', 'reverse'),
    'a': ('left', 'turn left', 'left turn','steer left', 'go left'),
    'd': ('right', 'turn right', 'right turn', 'steer right', 'go right'),
    's': ('stop', 'halt', 'brake', 'quit', 'exit', 'cancel'),
    'r': ('reset', 'reset car', 'reset motor', 'reset direction'),
    'i': ('tilt up', 'look up', 'head up', 'tilt head up'),
    'm': ('tilt down', 'look down', 'head down', 'tilt head down'),
    'k': ('center', 'center head', 'look straight', 'reset head'),
    'j': ('pan left', 'look left', 'pan head left'),
    'l': ('pan right', 'look right', 'pan head right'),
    'v': ('voice input', 'activate voice input'),
    'c': ('camera', 'activate camera', 'start camera'),
    'b': ('battery check', 'check battery', 'battery status'),
    't': ('manual input', 'type commands', 'switch to keyboard', 'keyboard mode'),
    'f': ('follow face', 'follow the face', 'follow that face', 'follow human face', 'track face', 'track human face'),
    'p': ('pretend roomba', 'roomba mode', 'start roomba mode', 'activate roomba mode'),
    'z': ('zen', 'zen thought', 'offer zen thought', 'offer zen thoughts', 'ai offer zen thoughts'),
    # Keep wiggle intentionally strict so random single-token STT noise does not trigger gestures.
    'g': ('do a wiggle', 'wiggle gesture', 'start wiggle mode')
}

# Common Whisper one-word mis-hearings seen on this stack.
_VOICE_COMMAND_ALIASES = {
    "for a word": "forward",
    "for word": "forward",
    "forwards": "forward",
    "go for": "go forward",
    "go four": "go forward",
    "back word": "backward",
    "backwards": "backward",
    "back": "backward",
    "wright": "right",
    "rite": "right",
    "pen": "pan",
    "lift": "left",
    "break": "brake",
    "quite": "quit",
    "quick": "quit",
    "ex it": "exit",
    "centered": "center",
    "sen": "zen",
    "send": "zen",
}

_VOICE_SINGLE_WORD_KEYS = {
    "forward": "w",
    "backward": "x",
    "left": "a",
    "right": "d",
    "stop": "s",
    "halt": "s",
    "brake": "s",
    "quit": "s",
    "exit": "s",
    "cancel": "s",
    "reset": "r",
    "up": "i",
    "down": "m",
    "center": "k",
    "voice": "v",
    "camera": "c",
    "battery": "b",
    "manual": "t",
    "keyboard": "t",
    "face": "f",
    "roomba": "p",
    "zen": "z",
    "wiggle": "g",
}


def _should_ignore_voice_text(text, had_recent_timeouts=False):
    normalized = re.sub(r"[^a-z0-9\s]", " ", str(text or "").strip().lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return True

    if normalized == STT_NO_SPEECH_FILLER:
        return True

    tokens = normalized.split()

    # Ignore short non-command snippets that are commonly produced by noise,
    # breath, or clipping after listen timeout cycles.
    short_limit = 5 if had_recent_timeouts else 2
    if len(tokens) <= short_limit:
        if _match_voice_command_key(normalized) is None:
            return True

    return False


def _has_chat_wake_word(text):
    normalized = re.sub(r"[^a-z0-9\s]", " ", str(text or "").strip().lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return False
    for wake_word in VOICE_CHAT_WAKE_WORDS:
        if wake_word in normalized:
            return True
    return False


def _normalize_command_text(text):
    normalized = str(text or '').strip().lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return "", []

    # First pass allows exact phrase remaps, then per-token remaps for homophones.
    normalized = _VOICE_COMMAND_ALIASES.get(normalized, normalized)
    tokens = [_VOICE_COMMAND_ALIASES.get(tok, tok) for tok in normalized.split()]
    return " ".join(tokens), tokens

def _match_voice_command_key(text):
    normalized, tokens = _normalize_command_text(text)

    if not normalized:
        return None

    if not tokens:
        return None

    # Keep wiggle available as an explicit one-word command only.
    if normalized == "wiggle":
        return 'g'

    # Zen should be easy to trigger in command-only mode without over-matching
    # random keyword soup from offline recognizers.
    if tokens[0] == "zen":
        return 'z'

    # Prefer local face-follow control for natural phrasings such as
    # "follow that face" or "can you track the face".
    if "face" in normalized and ("follow" in normalized or "track" in normalized):
        return 'f'

    # Single-word commands are common in noisy environments; check these early
    # before broader phrase containment logic.
    if len(tokens) == 1:
        single = tokens[0]
        if single in _VOICE_SINGLE_WORD_KEYS:
            return _VOICE_SINGLE_WORD_KEYS[single]

    # Prefer exact phrase matches before token-level shortcuts so commands like
    # "pan left"/"pan right" are routed to camera pan instead of steering.
    for key, phrases in _VOICE_COMMAND_KEYS.items():
        if normalized in phrases:
            return key

    # Handle emphatic repeats like "right right right" or "stop stop".
    if len(tokens) >= 2 and len(set(tokens)) == 1:
        repeated = tokens[0]
        if repeated in _VOICE_SINGLE_WORD_KEYS:
            return _VOICE_SINGLE_WORD_KEYS[repeated]

    if len(tokens) == 2:
        mapped = [(idx, _VOICE_SINGLE_WORD_KEYS.get(tok)) for idx, tok in enumerate(tokens)]
        mapped = [(idx, key) for idx, key in mapped if key is not None]
        if len(mapped) == 2 and mapped[0][1] == mapped[1][1]:
            return mapped[0][1]
        if len(mapped) == 1:
            other_idx = 1 - mapped[0][0]
            other_token = tokens[other_idx]
            if other_token in ("go", "move", "turn", "drive", "please"):
                return mapped[0][1]

    # Graceful fallback: allow phrase containment for longer commands
    # like "please go forward" without requiring exact equality.
    for key, phrases in _VOICE_COMMAND_KEYS.items():
        for phrase in phrases:
            if not phrase:
                continue
            # Avoid over-matching on single words such as "right" or "manual".
            if " " not in phrase:
                continue
            if phrase in normalized:
                return key

    return None


def _voice_command_repeat_steps(text, matched_key):
    """Map repeated token commands (e.g. 'right right right') to repeated key steps."""
    normalized, tokens = _normalize_command_text(text)
    if not normalized or not matched_key:
        return 1

    # Incremental controls support repeated-step accumulation.
    if matched_key not in VOICE_REPEATABLE_INCREMENT_KEYS:
        return 1

    if len(tokens) >= 2 and len(set(tokens)) == 1:
        repeated_token = tokens[0]
        token_key = _VOICE_SINGLE_WORD_KEYS.get(repeated_token)
        if token_key == matched_key:
            return min(len(tokens), VOICE_MAX_REPEAT_STEPS)

    # Support repeated multi-word phrase commands, e.g. "pan right pan right".
    phrases = _VOICE_COMMAND_KEYS.get(matched_key, ())
    phrase_repeat = 1
    for phrase in phrases:
        if " " not in phrase:
            continue
        count = len(re.findall(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized))
        if count > phrase_repeat:
            phrase_repeat = count

    return min(phrase_repeat, VOICE_MAX_REPEAT_STEPS)


_vosk_model_cache = None
_vosk_model_missing_logged = False
_vosk_model_load_error_logged = False


def _voice_debug(msg):
    if VOICE_VERBOSE_LOGS:
        gray_print(msg)


def _get_vosk_model():
    global _vosk_model_cache, _vosk_model_missing_logged, _vosk_model_load_error_logged
    if _vosk_model_cache is not None:
        return _vosk_model_cache

    model_path = Path(VOSK_MODEL_PATH).expanduser()
    if not model_path.is_absolute():
        model_path = (Path(__file__).resolve().parent / model_path).resolve()

    if not model_path.is_dir():
        if not _vosk_model_missing_logged:
            _vosk_model_missing_logged = True
            print(f"Vosk model not found at {model_path}; offline local STT unavailable.")
        return None

    try:
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)

        _vosk_model_cache = Model(str(model_path))
        return _vosk_model_cache
    except Exception as exc:
        if not _vosk_model_load_error_logged:
            _vosk_model_load_error_logged = True
            print(f"Unable to load Vosk model at {model_path}: {exc}")
        return None


def _offline_command_stt_vosk(audio):
    model = _get_vosk_model()
    if model is None:
        return None

    phrases = [
        "forward",
        "go forward",
        "move forward",
        "backward",
        "back up",
        "go back",
        "move back",
        "reverse",
        "left",
        "turn left",
        "go left",
        "right",
        "turn right",
        "go right",
        "stop",
        "halt",
        "brake",
        "quit",
        "exit",
        "cancel",
        "reset",
        "tilt up",
        "look up",
        "head up",
        "tilt down",
        "look down",
        "head down",
        "pan left",
        "pan right",
        "look left",
        "look right",
        "center",
        "center head",
        "reset head",
        "keyboard",
        "manual",
        "voice",
        "camera",
        "battery",
        "face",
        "follow face",
        "pretend roomba",
        "zen",
        "wiggle",
        "wiggle gesture",
        "do a wiggle",
    ]
    grammar = json.dumps(phrases)

    try:
        from vosk import KaldiRecognizer

        raw = audio.get_raw_data(convert_rate=VOSK_SAMPLE_RATE, convert_width=2)
        rec = KaldiRecognizer(model, VOSK_SAMPLE_RATE, grammar)
        rec.SetWords(False)
        rec.AcceptWaveform(raw)

        result = json.loads(rec.Result() or "{}")
        text = str(result.get("text") or "").strip()
        if text:
            return text

        final = json.loads(rec.FinalResult() or "{}")
        return str(final.get("text") or "").strip() or None
    except Exception as exc:
        print(f"Offline STT error (vosk): {exc}")
        return None


def _offline_command_stt_pocketsphinx(audio):
    # Keep the previous PocketSphinx path as an optional fallback engine.
    if OFFLINE_CRITICAL_COMMAND_SPOTTING:
        critical_keywords = [
            ("stop", OFFLINE_CRITICAL_KEYWORD_WEIGHT),
            ("halt", OFFLINE_CRITICAL_KEYWORD_WEIGHT),
            ("brake", OFFLINE_CRITICAL_KEYWORD_WEIGHT),
            ("keyboard", OFFLINE_CRITICAL_KEYWORD_WEIGHT),
            ("manual", OFFLINE_CRITICAL_KEYWORD_WEIGHT),
        ]
        try:
            critical_result = recognizer.recognize_sphinx(audio, keyword_entries=critical_keywords).strip()
            if critical_result:
                normalized, tokens = _normalize_command_text(critical_result)
                critical_tokens = [t for t in tokens if t in ("stop", "halt", "brake", "keyboard", "manual")]
                if critical_tokens:
                    return " ".join(critical_tokens)
                if normalized:
                    return normalized
        except sr.UnknownValueError:
            pass
        except Exception:
            pass

    if not OFFLINE_USE_KEYWORD_SPOTTING:
        try:
            first_pass = recognizer.recognize_sphinx(audio).strip()
            if first_pass:
                normalized, _ = _normalize_command_text(first_pass)
                if normalized:
                    return normalized
        except sr.UnknownValueError:
            pass
        except Exception as exc:
            print(f"Offline STT error: {exc}")
            pass

        if not OFFLINE_SECOND_PASS_KEYWORD_SPOTTING:
            return None

    keyword_entries = []
    for phrase in (
        "forward",
        "go forward",
        "backward",
        "left",
        "right",
        "stop",
        "halt",
        "brake",
        "reset",
        "face",
        "follow face",
        "zen",
        "wiggle",
        "pretend roomba",
    ):
        keyword_entries.append((phrase, OFFLINE_COMMAND_KEYWORD_WEIGHT))

    try:
        return recognizer.recognize_sphinx(audio, keyword_entries=keyword_entries).strip()
    except sr.UnknownValueError:
        return None
    except Exception as exc:
        print(f"Offline STT error: {exc}")
        return None


def _offline_command_stt(audio):
    """Fast local STT path for command driving; returns transcript text or None."""
    if not OFFLINE_COMMAND_STT_ENABLED:
        return None

    if OFFLINE_STT_ENGINE == "vosk":
        result = _offline_command_stt_vosk(audio)
        if result:
            return result
        if OFFLINE_STT_ENABLE_POCKETSPHINX_FALLBACK:
            return _offline_command_stt_pocketsphinx(audio)
        return None

    return _offline_command_stt_pocketsphinx(audio)


def _offline_transcript_is_noisy(text):
    """Drop long mixed-keyword hypotheses that are not actionable command phrases."""
    normalized, tokens = _normalize_command_text(text)
    if not normalized:
        return True

    # In voice mode, pure "voice" utterances are not actionable and often come from
    # recognizer feedback loops, so always discard them.
    if all(token == "voice" for token in tokens):
        return True

    # Repeated identical commands are valid for short control phrases.
    if len(tokens) >= 2 and len(set(tokens)) == 1:
        key = _VOICE_SINGLE_WORD_KEYS.get(tokens[0])
        if key is not None:
            # Keep repeated motion commands bounded; reject long spam bursts.
            if key in ('w', 'x','s', 'a', 'd') and len(tokens) > VOICE_MAX_REPEAT_STEPS:
                return True
            # Non-motion repeats like "voice voice voice ..." are usually decoder loops.
            if key not in ('w', 'x','s', 'a', 'd') and len(tokens) > 2:
                return True
            return False

    if len(tokens) > OFFLINE_MAX_COMMAND_TOKENS:
        return True

    if len(set(tokens)) > OFFLINE_MAX_COMMAND_UNIQUE_TOKENS:
        return True

    # Reject mixed-intent transcripts (e.g. "up face voice down right zen") that are
    # recognizer hypotheses rather than a single actionable user command.
    mapped_keys = []
    for token in tokens:
        token_key = _VOICE_SINGLE_WORD_KEYS.get(token)
        if token_key is not None:
            mapped_keys.append(token_key)
    if len(set(mapped_keys)) > 1:
        return True

    return False


def _shorten_for_log(text, max_chars=OFFLINE_MAX_NOISY_LOG_CHARS):
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + " ..."


def _collapse_offline_hypothesis(text):
    """Collapse repeated/mixed same-intent tokens into one actionable command phrase."""
    normalized, tokens = _normalize_command_text(text)
    if not normalized:
        return normalized

    mapped_keys = []
    unmapped_tokens = []
    for token in tokens:
        key = _VOICE_SINGLE_WORD_KEYS.get(token)
        if key is not None:
            mapped_keys.append(key)
        else:
            unmapped_tokens.append(token)

    if not mapped_keys:
        return normalized

    # Only collapse when non-command tokens are harmless filler words.
    # This preserves intent phrases like "pan left" and "look right" so
    # they can still match camera commands downstream.
    collapse_fillers = {"go", "move", "turn", "drive", "please", "the", "a", "to"}
    if any(token not in collapse_fillers for token in unmapped_tokens):
        return normalized

    # If recognizer outputs variants that all map to STOP, keep one canonical stop.
    if len(set(mapped_keys)) == 1:
        key = mapped_keys[0]
        canonical_by_key = {
            'w': 'forward',
            'x': 'backward',
            'a': 'left',
            'd': 'right',
            's': 'stop',
            'r': 'reset',
            't': 'keyboard',
            'v': 'voice',
            'f': 'face',
            'p': 'roomba',
            'z': 'zen',
            'g': 'wiggle',
            'i': 'up',
            'm': 'down',
            'k': 'center',
            'j': 'left',
            'l': 'right',
            'b': 'battery',
            'c': 'camera',
        }
        canonical = canonical_by_key.get(key)
        if not canonical:
            return normalized

        if key in ('w', 'x', 'a', 'd'):
            repeat = min(len(mapped_keys), VOICE_MAX_REPEAT_STEPS)
            return " ".join([canonical] * repeat)

        return canonical

    return normalized


def _try_openai_mode_fallback(audio, had_recent_timeouts=False):
    """Use cloud STT only for low-frequency control intents (mode switch and stop)."""
    if not OPENAI_MODE_SWITCH_FALLBACK:
        return None, None

    st = time.time()
    candidate = openai_helper.stt(audio, language=LANGUAGE)
    _voice_debug(f"openai fallback stt takes: {time.time() - st:.3f} s")

    if not isinstance(candidate, str):
        return None, None

    candidate = candidate.strip()
    if not candidate:
        return None, None

    if _should_ignore_voice_text(candidate, had_recent_timeouts=had_recent_timeouts):
        return None, None

    key = _match_voice_command_key(candidate)
    if key in ('t', 'v', 's'):
        return candidate, key

    return None, None

def manual_keyboard_loop():
    global motor_speed, dir_servo_angle, head_pan, head_tilt
    head_pan = DEFAULT_HEAD_PAN
    head_tilt = DEFAULT_HEAD_TILT
    print("\nManual: w/x =fwd|bk s =stop, a/d =lt|rt, r= reset, i/m =tilt up|down,\n k =cntr, j/l =pan lt|rt, p =roomba, f =face, z =zen, g =wiggle, ctrl+c =exit")

    while True:
        main_battery_check(False)
        try:
            key = readchar.readkey().lower()
        except KeyboardInterrupt:
            # The real readchar library raises KeyboardInterrupt for Ctrl+C instead of
            # returning it as a key, so readchar.key.CTRL_C below is unreachable dead code.
            # Catch it here so Ctrl+C only exits this manual-control loop, not the whole script.
            motor_speed, dir_servo_angle, head_pan, head_tilt = shutdown_gptcar()
            return

        if key in ('wxsadikmjlrvcbtfpzg'):
            _apply_manual_key(key)

        elif key == readchar.key.CTRL_C:
            motor_speed, dir_servo_angle, head_pan, head_tilt = shutdown_gptcar()
            return


# main
# =================================================================
def main():
    global current_feeling, last_feeling
    global speech_loaded
    global action_status, actions_to_be_done
    global tts_file
    global input_mode
    global motor_speed, dir_servo_angle, head_pan, head_tilt
    global last_time
    global follow_duration

    initialize_runtime()
    input_mode = _ensure_voice_or_keyboard_mode()

    if OFFLINE_COMMAND_STT_ENABLED:
        mode_msg = f"Voice command STT mode: local {OFFLINE_STT_ENGINE} primary"
        if OFFLINE_STT_ENGINE == "vosk" and OFFLINE_STT_ENABLE_POCKETSPHINX_FALLBACK:
            mode_msg += ", PocketSphinx fallback"
        if OPENAI_MODE_SWITCH_FALLBACK:
            mode_msg += ", OpenAI mode-switch fallback enabled"
        else:
            mode_msg += ", OpenAI fallback disabled"
        print(mode_msg + ".")
    else:
        print("Voice command STT mode: OpenAI primary.")

    my_car.reset()
    my_car.set_cam_tilt_angle(DEFAULT_HEAD_TILT)

    speak_thread.start()
    action_thread.start()
    last_time = time.time() 
    voice_timeout_streak = 0
    voice_command_cooldown_until = 0.0
    voice_motion_failsafe_until = 0.0

    while True:
        # Check every pass so a low battery is caught regardless of which branch below
        # runs (GPT dialogue, a direct voice/keyboard command, or manual WASD mode).

        if input_mode == 'voice':
            main_battery_check(False)

            if voice_motion_failsafe_until > 0 and time.time() >= voice_motion_failsafe_until and motor_speed > MIN_MOTOR_SPEED:
                motor_speed = stop_car()
                voice_motion_failsafe_until = 0.0
                gray_print("Voice motion failsafe: auto-stop while waiting for next command.")

            if voice_command_cooldown_until > time.time():
                time.sleep(0.05)
                continue

            _play_listen_beeps(VOICE_LISTEN_START_BEEPS)
            # listen
            # ----------------------------------------------------------------
            gray_print("listening ...")

            with action_lock:
                action_status = 'standby'

            voice_candidates = []
            selected_index = _select_input_device_index()
            if selected_index is not None:
                voice_candidates.append(selected_index)
            for preferred in (1, 3, 2, 0):
                if preferred not in voice_candidates:
                    voice_candidates.append(preferred)

            audio = None
            last_voice_error = None
            timed_out = False
            for attempt_index, mic_device_index in enumerate(voice_candidates):
                mic = None
                _stderr_back = None
                try:
                    _stderr_back = redirect_error_2_null() # ignore ALSA chatter while probing capture devices
                    mic = _open_microphone_for_listen(mic_device_index)
                    cancel_redirect_error(_stderr_back)
                    # Calibrate once when entering a fresh listen cycle, then clamp tightly so
                    # ambient spikes don't make the listener effectively deaf.
                    if voice_timeout_streak == 0 and attempt_index == 0:
                        recognizer.adjust_for_ambient_noise(mic, duration=0.2)
                    recognizer.energy_threshold = max(
                        VOICE_MIN_ENERGY_THRESHOLD,
                        min(float(recognizer.energy_threshold), VOICE_MAX_ENERGY_THRESHOLD),
                    )
                    # Motor/drivetrain noise from a moving car can spike the dynamically adjusted
                    # threshold (seen climbing past 1700+ after several 'forward' commands), which
                    # then keeps voice from ever clearing it. Cap it so a noisy moment doesn't stick.
                    print(
                        f"Say something now (listening for up to {VOICE_LISTEN_TIMEOUT_SEC}s, "
                        f"energy_threshold={recognizer.energy_threshold:.1f})..."
                    )
                    audio = recognizer.listen(
                        mic,
                        timeout=VOICE_LISTEN_TIMEOUT_SEC,
                        phrase_time_limit=VOICE_PHRASE_TIME_LIMIT_SEC,
                    )
                    break
                except sr.WaitTimeoutError:
                    # No speech detected within the timeout; the mic itself is fine, so retry listening
                    # instead of falling back to keyboard input.
                    recognizer.energy_threshold = max(
                        VOICE_MIN_ENERGY_THRESHOLD,
                        float(recognizer.energy_threshold) * VOICE_TIMEOUT_BACKOFF,
                    )
                    print(f"Timed out waiting for speech above energy_threshold={recognizer.energy_threshold:.1f}. If your voice never triggers it, try lowering recognizer.energy_threshold or speaking louder/closer to the mic.")
                    timed_out = True
                    break
                except (AttributeError, OSError, ValueError) as exc:
                    if _stderr_back is not None:
                        cancel_redirect_error(_stderr_back)
                    last_voice_error = exc
                    if attempt_index == len(voice_candidates) - 1:
                        break
                    print(f"Voice input unavailable on capture index {mic_device_index}; trying the next candidate.")
                finally:
                    if mic is not None:
                        _close_microphone_for_listen(mic)
                        mic = None

            _play_listen_beeps(VOICE_LISTEN_END_BEEPS)

            if timed_out:
                voice_timeout_streak += 1
                if voice_timeout_streak >= VOICE_TIMEOUT_FALLBACK_COUNT:
                    print(
                        f"No speech detected for {voice_timeout_streak} consecutive attempts; "
                        "switching to keyboard mode. Say 'voice input' or type 'voice' to switch back."
                    )
                    input_mode = 'keyboard'
                    voice_timeout_streak = 0
                    print()
                    continue
                print("No speech detected; listening again.")
                continue

            if audio is None:
                print(f"Voice input unavailable for all capture candidates; falling back to keyboard input. Last error: {last_voice_error}")
                _reset_capture_device_cache()
                input_mode = 'keyboard'
                voice_timeout_streak = 0
                continue

            had_recent_timeouts = voice_timeout_streak > 0

            # stt
            # ----------------------------------------------------------------
            gray_print('stt ...')
            _result = None

            st = time.time()
            offline_result = _offline_command_stt(audio)
            offline_elapsed = time.time() - st
            if offline_result:
                _voice_debug(f"offline stt takes: {offline_elapsed:.3f} s")
                offline_result = _collapse_offline_hypothesis(offline_result)
                if _offline_transcript_is_noisy(offline_result):
                    _voice_debug(f"Ignoring noisy offline STT text: {_shorten_for_log(offline_result)!r}")
                    fallback_text, fallback_key = _try_openai_mode_fallback(audio, had_recent_timeouts=had_recent_timeouts)
                    if fallback_key is not None:
                        _result = fallback_text
                    else:
                        _voice_debug("")
                        continue
                else:
                    _result = offline_result
            else:
                _voice_debug(f"offline stt miss: {offline_elapsed:.3f} s")
                fallback_text, fallback_key = _try_openai_mode_fallback(audio, had_recent_timeouts=had_recent_timeouts)
                if fallback_key is not None:
                    _result = fallback_text

            if not _result and OPENAI_STT_FALLBACK_WHEN_OFFLINE_MISS:
                st = time.time()
                _result = openai_helper.stt(audio, language=LANGUAGE)
                _voice_debug(f"openai stt takes: {time.time() - st:.3f} s")
            elif not _result:
                _voice_debug("No local command recognized; listening again.")
                _voice_debug("")
                continue

            if isinstance(_result, str):
                _result = _result.strip()
                if _should_ignore_voice_text(_result, had_recent_timeouts=had_recent_timeouts):
                    print(f"Ignoring low-confidence STT text: {_result!r}; listening again.")
                    print()
                    continue

            if _result == False or _result == "":
                print() # new line
                continue

            voice_key = _match_voice_command_key(_result)
            if voice_key is not None:
                voice_timeout_streak = 0
                # A direct voice command should immediately own motion control and
                # cancel any leftover async action/think state.
                with action_lock:
                    action_status = 'standby'
                    actions_to_be_done = []
                repeat_steps = _voice_command_repeat_steps(_result, voice_key)
                gray_print(f"Manual voice command: {_result!r} -> '{voice_key}' x{repeat_steps}")
                for _ in range(repeat_steps):
                    _apply_manual_key(voice_key)

                # Keep forward/backward persistent by default; only explicit stop/reset
                # should clear any existing throttle failsafe deadline.
                if voice_key in ('s', 'r'):
                    voice_motion_failsafe_until = 0.0

                if voice_key in VOICE_REPEATABLE_INCREMENT_KEYS:
                    cooldown = VOICE_POST_MOTION_COOLDOWN_SEC
                else:
                    cooldown = VOICE_POST_COMMAND_COOLDOWN_SEC
                voice_command_cooldown_until = time.time() + cooldown
                continue

            if not VOICE_MODE_CHAT_ENABLED:
                print(f"Ignoring non-command voice text (command-only mode): {_result!r}")
                print()
                continue

            if VOICE_REQUIRE_WAKE_WORD_FOR_CHAT and not _has_chat_wake_word(_result):
                print(f"Ignoring non-command voice text (no wake word): {_result!r}")
                print()
                continue

            # A non-command transcript made it through the filter; treat this as a
            # deliberate chat turn and reset timeout recovery state.
            voice_timeout_streak = 0

        elif input_mode == 'keyboard':
            with action_lock:
                action_status = 'standby'

            _result = input(f'\033[1;30m{"input: "}\033[0m').encode(sys.stdin.encoding).decode('utf-8').strip()

            if _result == False or _result == "":
                print() # new line
                continue

            if _result.lower() == 'manual':
                manual_keyboard_loop()
                continue

            if _result.lower() == 'chat':
                print("Chat mode selected. Type your message to send to OpenAI.")
                continue

            if _result.lower() in ('t', 'voice'):
                activate_voice_input()
                gray_print("Switching to voice input.")
                continue

        else:
            raise ValueError("Invalid input mode")

        # chat-gpt
        # ---------------------------------------------------------------- 
        gray_print(f'thinking ...')
        response = {}
        st = time.time()

        with action_lock:
            action_status = 'think'

        if with_img:
            img_path = './img_imput.jpg'
            cv2.imwrite(img_path, Vilib.img)
            response = openai_helper.dialogue_with_img(_result, img_path)
        else:
            response = openai_helper.dialogue(_result)

        gray_print(f'chat takes: {time.time() - st:.3f} s')

        # actions & TTS
        # ----------------------------------------------------------------
        _sound_actions = [] 
        actions = []
        answer = ''
        try:
            if isinstance(response, dict):
                if 'actions' in response:
                    actions = list(response['actions'])
                else:
                    actions = ['stop']

                if 'answer' in response:
                    answer = response['answer']
                else:
                    answer = ''

                if len(answer) > 0:
                    _actions = list.copy(actions)
                    for _action in _actions:
                        if _action in SOUND_EFFECT_ACTIONS:
                            _sound_actions.append(_action)
                            actions.remove(_action)

            else:
                response = str(response)
                if len(response) > 0:
                    actions = []
                    answer = response

        except:
            actions = []
            answer = ''
    
        try:
            # ---- tts ----
            _tts_status = False
            if answer != '':
                st = time.time()
                _time = time.strftime("%y-%m-%d_%H-%M-%S", time.localtime())
                _tts_f = f"./tts/{_time}_raw.wav"
                _tts_status = openai_helper.text_to_speech(answer, _tts_f, TTS_VOICE, response_format='wav', instructions=VOICE_INSTRUCTIONS) # alloy, echo, fable, onyx, nova, and shimmer
                if _tts_status:
                    tts_file = f"./tts/{_time}_{VOLUME_DB}dB.wav"
                    if not sox_volume(_tts_f, tts_file, VOLUME_DB):
                        # sox (module or CLI) may be missing, e.g. when run under sudo without the venv's
                        # site-packages; fall back to the unadjusted TTS file instead of dropping speech.
                        print("Volume adjustment via sox failed; playing the unadjusted TTS audio instead.")
                        tts_file = _tts_f
                gray_print(f'tts takes: {time.time() - st:.3f} s')

            # ---- actions ----
            with action_lock:
                actions_to_be_done = actions
                gray_print(f'actions: {actions_to_be_done}')
                action_status = 'actions' if actions_to_be_done else 'actions_done'

            # --- sound effects and voice ---
            for _sound in _sound_actions:
                try:
                    sounds_dict[_sound](music)
                except Exception as e:
                    print(f'action error: {e}')

            if _tts_status:
                with speech_lock:
                    speech_loaded = True

            # ---- wait speak done ----
            if _tts_status:
                speech_wait_started = time.time()
                while True:
                    with speech_lock:
                        if not speech_loaded:
                            break
                    if time.time() - speech_wait_started > SPEECH_WAIT_TIMEOUT_SEC:
                        print("TTS wait timeout; clearing speech flag and continuing.")
                        with speech_lock:
                            speech_loaded = False
                        break
                    time.sleep(.01)

            # ---- wait actions done ----
            if actions:
                action_wait_started = time.time()
                while True:
                    with action_lock:
                        if action_status != 'actions':
                            break
                    if time.time() - action_wait_started > ACTION_WAIT_TIMEOUT_SEC:
                        print("Action wait timeout; forcing action state to actions_done and continuing.")
                        with action_lock:
                            action_status = 'actions_done'
                            actions_to_be_done = []
                        break
                    time.sleep(.01)

            ##
            print() # new line

        except Exception as e:
            print(f'actions or TTS error: {e}')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"\033[31mERROR: {e}\033[m")
    finally:
        # Each cleanup step is independent so one failure (e.g. camera already closed)
        # doesn't skip the others and leave motors, servos, or the audio device stuck.
        if with_img and 'Vilib' in globals():
            try:
                Vilib.camera_close()
                # camera_close() only flips a flag and sleeps 0.1s; it doesn't join the
                # capture thread or wait for picamera2/libcamera to release the native
                # camera pipeline. Exiting before that finishes can hit the native
                # library mid-teardown, producing "terminate called without an active
                # exception" from a background thread during interpreter shutdown.
                camera_thread = getattr(Vilib, "camera_thread", None)
                if camera_thread is not None and camera_thread.is_alive():
                    camera_thread.join(timeout=2)
                time.sleep(0.5)
            except Exception as exc:
                print(f"Camera cleanup error: {exc}")

        if 'led' in globals() and led is not None:
            try:
                led.off()
            except Exception:
                pass

        if 'my_car' in globals() and my_car is not None:
            try:
                my_car.reset()
            except Exception as exc:
                print(f"Motor/servo cleanup error: {exc}")

        if 'music' in globals() and music is not None:
            try:
                music.music_stop()
            except Exception:
                pass

        _cleanup_stale_audio_processes()
        time.sleep(3)


