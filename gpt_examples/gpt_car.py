import os

from openai_helper import OpenAiHelper
from keys import (
    OPENAI_API_KEY,
    OPENAI_ASSISTANT_ID,
    OPENAI_ASSISTANT_NAME,
    OPENAI_ASSISTANT_MODEL,
)
from preset_actions import *
from utils import *

# STT/TTS config (see gpt_examples/README.md "Modify parameters")
LANGUAGE = ['en','zh']  # e.g. ['zh', 'en']; empty list lets Whisper auto-detect all languages
VOLUME_DB = 3  # TTS post-gain in dB via sox; avoid exceeding 5 to prevent distortion
TTS_VOICE = 'nova'  # alloy, echo, fable, onyx, nova, or shimmer
VOICE_INSTRUCTIONS = ""  # https://www.openai.fm/

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

from pathlib import Path
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

# speak_hanlder
# =================================================================
speech_loaded = False
speech_lock = threading.Lock()
tts_file = None

def speak_hanlder():
    global speech_loaded, tts_file
    while True:
        with speech_lock:
            _isloaded = speech_loaded
        if _isloaded:
            # gray_print('speak start')
            speak_block(music, tts_file)
            # gray_print('speak done')
            with speech_lock:
                speech_loaded = False
        time.sleep(0.05)

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

motor_speed = DEFAULT_MOTOR_SPEED   # initial motor speed
dir_servo_angle = DEFAULT_DIR_SERVO_ANGLE # initial direction

head_pan = DEFAULT_HEAD_PAN   # initial head pan angle
head_tilt = DEFAULT_HEAD_TILT # initial head tilt angle

WARNING_VOLTAGE = 6.8  # Alert the user
SHUTDOWN_VOLTAGE = 6.4 # Force safe shutdown to protect the Pi and batteries


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
                led.off()
                led.on()
                sleep(.1)
                led.off()
                sleep(.1)
                led.on()
                sleep(.1)
                led.off()
                last_led_time = time.time()
        elif led_status == 'think':
            if time.time() - last_led_time > LED_BLINK_INTERVAL:
                led.off()
                sleep(LED_BLINK_INTERVAL)
                led.on()
                sleep(LED_BLINK_INTERVAL)
                last_led_time = time.time()
        elif led_status == 'actions':
                led.on() 

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
                # think(my_car)
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

def _speak_text(text):
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

    with speech_lock:
        tts_file = _tts_file
        speech_loaded = True
    while True:
        with speech_lock:
            if not speech_loaded:
                break
        time.sleep(.01)


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
    global motor_speed, dir_servo_angle, head_pan, head_tilt
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
    elif key in 'rvcbt':
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



# Recognized speech that matches one of these phrases drives the car directly instead of going through GPT.
_VOICE_COMMAND_KEYS = {
    'w': ('forward', 'go forward', 'move forward', 'drive forward'),
    'x': ('backward', 'back up', 'go backward', 'move backward', 'reverse'),
    'a': ('left', 'turn left', 'left turn','steer left', 'go left'),
    'd': ('right', 'turn right', 'right turn', 'steer right', 'go right'),
    's': ('stop', 'halt', 'brake'),
    'r': ('reset', 'reset car', 'reset motor', 'reset direction'),
    'i': ('tilt up', 'look up', 'head up', 'tilt head up'),
    'm': ('tilt down', 'look down', 'head down', 'tilt head down'),
    'k': ('center', 'center head', 'look straight', 'reset head'),
    'j': ('pan left', 'look left', 'pan head left'),
    'l': ('pan right', 'look right', 'pan head right'),
    'v': ('voice input', 'activate voice input'),
    'c': ('camera', 'activate camera', 'start camera'),
    'b': ('battery check', 'check battery', 'battery status'),
    't': ('manual input', 'type commands', 'keyboard', 'type')
}

def _match_voice_command_key(text):
    normalized = str(text or '').strip().lower().rstrip('.!?')
    for key, phrases in _VOICE_COMMAND_KEYS.items():
        if normalized in phrases:
            return key
    return None

def manual_keyboard_loop():
    global motor_speed, dir_servo_angle, head_pan, head_tilt
    head_pan = DEFAULT_HEAD_PAN
    head_tilt = DEFAULT_HEAD_TILT
    print("\nManual: w/x =fwd|bk s =stop, a/d =lt|rt, r= reset, i/m =tilt up|down, k =cntr, j/l =pan lt|rt, ctrl+c =exit")

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

        if key in ('wxsadikmjlrvcbt'):
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

    initialize_runtime()
    input_mode = _ensure_voice_or_keyboard_mode()

    my_car.reset()
    my_car.set_cam_tilt_angle(DEFAULT_HEAD_TILT)

    speak_thread.start()
    action_thread.start()
    last_time = time.time() 

    while True:
        # Check every pass so a low battery is caught regardless of which branch below
        # runs (GPT dialogue, a direct voice/keyboard command, or manual WASD mode).

        if input_mode == 'voice':
            main_battery_check(False)
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
                    recognizer.adjust_for_ambient_noise(mic)
                    # Motor/drivetrain noise from a moving car can spike the dynamically adjusted
                    # threshold (seen climbing past 1700+ after several 'forward' commands), which
                    # then keeps voice from ever clearing it. Cap it so a noisy moment doesn't stick.
                    recognizer.energy_threshold = min(recognizer.energy_threshold, 600)
                    print(f"Say something now (listening for up to 10s, energy_threshold={recognizer.energy_threshold:.1f})...")
                    audio = recognizer.listen(mic, timeout=10, phrase_time_limit=15)
                    break
                except sr.WaitTimeoutError:
                    # No speech detected within the timeout; the mic itself is fine, so retry listening
                    # instead of falling back to keyboard input.
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

            if timed_out:
                print("No speech detected; listening again.")
                continue

            if audio is None:
                print(f"Voice input unavailable for all capture candidates; falling back to keyboard input. Last error: {last_voice_error}")
                _reset_capture_device_cache()
                input_mode = 'keyboard'
                continue

            # stt
            # ----------------------------------------------------------------
            gray_print('stt ...')
            st = time.time()
            _result = openai_helper.stt(audio, language=LANGUAGE)
            gray_print(f"stt takes: {time.time() - st:.3f} s")

            if _result == False or _result == "":
                print() # new line
                continue

            voice_key = _match_voice_command_key(_result)
            if voice_key is not None:
                _apply_manual_key(voice_key)
                gray_print(f"Manual voice command: {_result!r} -> '{voice_key}'")
                continue

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
                action_status = 'actions'

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
                while True:
                    with speech_lock:
                        if not speech_loaded:
                            break
                    time.sleep(.01)

            # ---- wait actions done ----
            while True:
                with action_lock:
                    if action_status != 'actions':
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


