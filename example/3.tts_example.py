from pathlib import Path
import sys
import shutil
import subprocess
import os
import importlib.util
import re
import tempfile
import atexit
import signal

PROJECT_ROOT = None
for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        PROJECT_ROOT = parent
        sys.path.insert(0, str(parent))
        vendor_dir = parent / ".vendor"
        if vendor_dir.is_dir():
            sys.path.insert(0, str(vendor_dir))
        break

if PROJECT_ROOT is None:
    PROJECT_ROOT = "" 
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOUNDS_DIR = PROJECT_ROOT / "sounds"
MUSICS_DIR = PROJECT_ROOT / "musics"

os.environ.setdefault("SDL_AUDIODRIVER", "alsa")

from time import sleep


def _parse_volume_value(raw_value):
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1].strip()
    text = text.split("#", 1)[0].split(";", 1)[0].strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    number_match = re.search(r"-?\d+(?:\.\d+)?", text)
    if number_match:
        text = number_match.group(0)
    try:
        value = int(float(text))
    except ValueError:
        return None
    return max(0, min(100, value))


def _load_picarx_volume_settings():
    # Priority: env overrides > config file values > defaults.
    env_sys = _parse_volume_value(os.environ.get("PICARX_SYSVOL"))
    env_app = _parse_volume_value(os.environ.get("PICARX_APPVOL"))

    user_config = Path.home() / ".config" / "picar-x" / "picar-x.conf"
    config_candidates = [
        Path("/opt/picar-x/picar-x.conf"),
        Path("/opt/vilib/picar-x/picar-x.conf"),
        PROJECT_ROOT / "picar-x.conf",
        user_config,
    ]
    # When script is run with sudo, also inspect the invoking user's config.
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        config_candidates.append(Path("/home") / sudo_user / ".config" / "picar-x" / "picar-x.conf")

    sys_keys = [
        "picarx_system_volume", "picarx_audio_volume", "audio_volume", "system_volume",
        "speaker_volume", "volume", "master_volume", "sys_volume",
    ]
    app_keys = [
        "picarx_music_volume", "music_volume", "picarx_app_volume", "app_volume",
        "bgm_volume", "tts_volume", "effect_volume", "sound_volume", "media_volume",
    ]

    loaded_values = {}
    for cfg in config_candidates:
        if not cfg.is_file():
            continue
        try:
            for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith(";"):
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    continue
                if "=" in stripped:
                    key, value = stripped.split("=", 1)
                elif ":" in stripped:
                    key, value = stripped.split(":", 1)
                else:
                    continue
                normalized_key = key.strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")
                # Keep first value by candidate priority; later files only fill missing keys.
                if normalized_key not in loaded_values:
                    loaded_values[normalized_key] = value.strip()
        except Exception:
            continue

    cfg_sys = None
    cfg_app = None
    for key in sys_keys:
        cfg_sys = _parse_volume_value(loaded_values.get(key))
        if cfg_sys is not None:
            break
    for key in app_keys:
        cfg_app = _parse_volume_value(loaded_values.get(key))
        if cfg_app is not None:
            break

    mute_keys = [
        "mute", "muted", "is_muted", "audio_mute", "speaker_mute", "volume_mute", "picarx_mute"
    ]
    muted = False
    for key in mute_keys:
        raw = loaded_values.get(key)
        if raw is None:
            continue
        text = str(raw).strip().strip('"').strip("'").lower()
        if text in {"1", "true", "yes", "on", "mute", "muted"}:
            muted = True
            break

    if muted:
        cfg_sys = 0
        if cfg_app is None:
            cfg_app = 0

    final_sys = env_sys if env_sys is not None else (cfg_sys if cfg_sys is not None else 100)
    final_app = env_app if env_app is not None else (cfg_app if cfg_app is not None else (cfg_sys if cfg_sys is not None else 75))
    return final_sys, final_app


PICARX_SYS_VOLUME, PICARX_APP_VOLUME = _load_picarx_volume_settings()


def _load_music_class():
    try:
        from robot_hat import Music as music_cls
        return music_cls
    except Exception:
        pass

    try:
        # Some local/vendor installs expose Music only in robot_hat.music.
        from robot_hat.music import Music as music_cls
        return music_cls
    except Exception:
        pass

    vendored_music = PROJECT_ROOT / ".vendor" / "robot_hat" / "music.py"
    if vendored_music.is_file():
        spec = importlib.util.spec_from_file_location("picarx_vendored_robot_hat_music", vendored_music)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "Music"):
                return module.Music

    raise ImportError("Unable to import Music from robot_hat or vendored robot_hat/music.py")


Music = _load_music_class()
try:
    import readchar
except ImportError:
    class _ReadCharFallbackKey:
        SPACE = " "

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
from os import geteuid

try:
    from robot_hat import TTS
except ImportError:
    TTS = None


class EspeakTTS:
    def __init__(self):
        self.voice = "en-us"
        self._warned_route_fallback = False

    def lang(self, language):
        normalized = (language or "en-US").replace("_", "-").lower()
        self.voice = normalized

    def say(self, words):
        audio_dev = os.environ.get("PICARX_AUDIODEV") or os.environ.get("AUDIODEV")
        card_id = os.environ.get("PICARX_AUDIO_CARD_ID")
        card_name = os.environ.get("PICARX_AUDIO_CARD_NAME")

        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="picarx_tts_", suffix=".wav", delete=False) as fp:
                wav_path = Path(fp.name)

            espeak_result = subprocess.run(
                ["espeak", "-v", self.voice, "-w", str(wav_path), str(words)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if espeak_result.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
                return

            # Best path: play TTS through the same mixer instance that currently plays music.
            music_obj = globals().get("music")
            if music_obj is not None:
                try:
                    music_obj.sound_play(str(wav_path), PICARX_APP_VOLUME)
                    return
                except Exception:
                    pass

            if shutil.which("aplay"):
                device_candidates = []
                if audio_dev:
                    device_candidates.append(audio_dev)
                if card_id:
                    device_candidates.extend([f"plughw:{card_id},0", f"hw:{card_id},0"])
                if card_name:
                    device_candidates.extend([f"plughw:CARD={card_name},DEV=0", f"hw:CARD={card_name},DEV=0"])
                device_candidates.append(None)

                unique_candidates = []
                for dev in device_candidates:
                    if dev not in unique_candidates:
                        unique_candidates.append(dev)

                for dev in unique_candidates:
                    cmd = ["aplay", "-q", str(wav_path)] if dev is None else ["aplay", "-q", "-D", dev, str(wav_path)]
                    result = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if result.returncode == 0:
                        return

                if not self._warned_route_fallback:
                    print("TTS device route failed; falling back to default speech output.")
                    self._warned_route_fallback = True
        finally:
            if wav_path is not None and wav_path.exists():
                wav_path.unlink(missing_ok=True)

        subprocess.run(
            ["espeak", "-v", self.voice, str(words)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _prepare_audio_backend():
    auto_card = Path("/usr/local/bin/auto_sound_card")
    if auto_card.exists():
        subprocess.run([str(auto_card)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Killing PulseAudio can temporarily destabilize ALSA device visibility.
    if os.environ.get("PICARX_KILL_PULSEAUDIO", "0") == "1":
        subprocess.run(["pkill", "-f", "pulseaudio"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait briefly for ALSA cards to become visible after auto sound-card switching.
    for _ in range(20):
        try:
            cards_probe = Path("/proc/asound/cards").read_text(encoding="utf-8", errors="ignore")
            if re.search(r"^\s*\d+\s+\[[^\]]+\]:", cards_probe, re.MULTILINE):
                break
        except Exception:
            pass
        sleep(0.2)

    # Detect preferred playback card.
    # Default behavior follows current system profile without forcing card IDs.
    # Users can opt in to matching a specific card with PICARX_AUDIO_CARD_HINT.
    selected_card_id = None
    selected_card_name = None
    picarx_dac_card_id = None
    picarx_dac_card_name = None
    preferred_hint = os.environ.get("PICARX_AUDIO_CARD_HINT", "").strip().lower()
    try:
        cards = Path("/proc/asound/cards").read_text(encoding="utf-8", errors="ignore")
        detected_cards = []
        for line in cards.splitlines():
            match = re.search(r"^\s*(\d+)\s+\[([^\]]+)\]:", line)
            if match:
                card_id = match.group(1)
                card_name = match.group(2)
                lower_line = line.lower()
                detected_cards.append((card_id, card_name, lower_line))
                if "snd_rpi_hifiberry_dac" in lower_line or "hifiberry" in lower_line:
                    picarx_dac_card_id = card_id
                    picarx_dac_card_name = card_name

        if preferred_hint:
            for card_id, card_name, lower_line in detected_cards:
                if preferred_hint in lower_line or preferred_hint in card_name.lower():
                    selected_card_id = card_id
                    selected_card_name = card_name
                    break

        if selected_card_name is None and preferred_hint and detected_cards:
            selected_card_id, selected_card_name, _ = detected_cards[0]
    except Exception:
        selected_card_id = None
        selected_card_name = None

    # Export stable card metadata for downstream Music/TTS routing.
    # Prefer the PiCar-X DAC when it exists; otherwise only use explicit hint selection.
    if picarx_dac_card_id and "PICARX_AUDIO_CARD_ID" not in os.environ:
        os.environ["PICARX_AUDIO_CARD_ID"] = str(picarx_dac_card_id)
    if picarx_dac_card_name and "PICARX_AUDIO_CARD_NAME" not in os.environ:
        os.environ["PICARX_AUDIO_CARD_NAME"] = picarx_dac_card_name

    # Do not auto-force PICARX_AUDIODEV unless we found the PiCar-X DAC.
    if picarx_dac_card_id and "PICARX_AUDIODEV" not in os.environ and "AUDIODEV" not in os.environ:
        os.environ["PICARX_AUDIODEV"] = f"plughw:{picarx_dac_card_id},0"

    # Keep user-directed hint behavior available as an explicit override.
    if preferred_hint:
        if selected_card_id:
            os.environ["PICARX_AUDIO_CARD_ID"] = str(selected_card_id)
        if selected_card_name:
            os.environ["PICARX_AUDIO_CARD_NAME"] = selected_card_name

    # Raise ALSA playback volume if amixer is available.
    if shutil.which("amixer"):
        target_percent = PICARX_SYS_VOLUME

        # Always prefer setting system volume on the PiCar-X DAC mixer card
        # when it exists, even if playback routing is not explicitly pinned.
        amixer_base = ["amixer"]
        if picarx_dac_card_id is not None:
            amixer_base += ["-c", str(picarx_dac_card_id)]
        elif preferred_hint and selected_card_id is not None:
            amixer_base += ["-c", str(selected_card_id)]

        controls = subprocess.run(
            amixer_base + ["scontrols"],
            check=False,
            text=True,
            capture_output=True,
        )
        controls_out = controls.stdout or ""

        for control_name in ("Digital", "PCM", "DAC", "Speaker", "Master", "Headphone", "Line Out"):
            if f"'{control_name}'" not in controls_out:
                continue
            subprocess.run(
                amixer_base + ["set", control_name, f"{target_percent}%", "unmute"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    

if geteuid() != 0:
    print(f"\033[0;33m{'The program needs to be run using sudo, otherwise there may be no sound.'}\033[0m")
else:
    _prepare_audio_backend()

def _create_music_instance(report_errors=True):
    last_exc = None
    for _ in range(4):
        try:
            return Music()
        except Exception as exc:
            last_exc = exc
            # Re-probe ALSA route and retry, especially helpful for transient busy states.
            _prepare_audio_backend()
            sleep(0.5)

    if report_errors and last_exc is not None:
        print(f"Audio mixer unavailable: {last_exc}")
        print("Music/sound effects are disabled; TTS-only mode is active.")
    return None


music = _create_music_instance(report_errors=True)
fallback_bgm_proc = None


def _release_audio_resources():
    global music, fallback_bgm_proc
    if music is None:
        if fallback_bgm_proc is not None:
            try:
                fallback_bgm_proc.terminate()
                fallback_bgm_proc.wait(timeout=1)
            except Exception:
                try:
                    fallback_bgm_proc.kill()
                except Exception:
                    pass
            fallback_bgm_proc = None
        return
    try:
        music.music_stop()
    except Exception:
        pass
    try:
        mixer = getattr(music, "pygame", None)
        if mixer is not None and hasattr(mixer, "mixer"):
            mixer.mixer.quit()
    except Exception:
        pass
    if fallback_bgm_proc is not None:
        try:
            fallback_bgm_proc.terminate()
            fallback_bgm_proc.wait(timeout=1)
        except Exception:
            try:
                fallback_bgm_proc.kill()
            except Exception:
                pass
        fallback_bgm_proc = None
    music = None


def _start_fallback_bgm(music_path: str):
    card_id = os.environ.get("PICARX_AUDIO_CARD_ID")
    card_name = os.environ.get("PICARX_AUDIO_CARD_NAME")
    audio_dev = os.environ.get("PICARX_AUDIODEV") or os.environ.get("AUDIODEV")

    device_candidates = []
    if audio_dev:
        device_candidates.append(audio_dev)
    if card_id:
        device_candidates.extend([f"plughw:{card_id},0", f"hw:{card_id},0"])
    if card_name:
        device_candidates.extend([f"plughw:CARD={card_name},DEV=0", f"hw:CARD={card_name},DEV=0"])
    device_candidates.append(None)

    unique_devices = []
    for dev in device_candidates:
        if dev not in unique_devices:
            unique_devices.append(dev)

    players = []
    if shutil.which("mpg123"):
        for dev in unique_devices:
            if dev is None:
                players.append(["mpg123", "-q", "-o", "alsa", music_path])
            else:
                players.append(["mpg123", "-q", "-o", "alsa", "-a", dev, music_path])
    if shutil.which("ffplay"):
        players.append(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", music_path])
    if shutil.which("cvlc"):
        players.append(["cvlc", "--play-and-exit", "--quiet", music_path])

    for cmd in players:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            sleep(0.25)
            if proc.poll() is None:
                return proc
        except Exception:
            continue
    return None


def _stop_fallback_bgm():
    global fallback_bgm_proc
    if fallback_bgm_proc is None:
        return
    try:
        fallback_bgm_proc.terminate()
        fallback_bgm_proc.wait(timeout=1)
    except Exception:
        try:
            fallback_bgm_proc.kill()
        except Exception:
            pass
    fallback_bgm_proc = None


def _play_fallback_sfx(sound_path: str):
    if not shutil.which("aplay"):
        return False

    card_id = os.environ.get("PICARX_AUDIO_CARD_ID")
    card_name = os.environ.get("PICARX_AUDIO_CARD_NAME")
    audio_dev = os.environ.get("PICARX_AUDIODEV") or os.environ.get("AUDIODEV")

    device_candidates = []
    if audio_dev:
        device_candidates.append(audio_dev)
    if card_id:
        device_candidates.extend([f"plughw:{card_id},0", f"hw:{card_id},0"])
    if card_name:
        device_candidates.extend([f"plughw:CARD={card_name},DEV=0", f"hw:CARD={card_name},DEV=0"])
    device_candidates.append(None)

    unique_devices = []
    for dev in device_candidates:
        if dev not in unique_devices:
            unique_devices.append(dev)

    for dev in unique_devices:
        cmd = ["aplay", "-q", sound_path] if dev is None else ["aplay", "-q", "-D", dev, sound_path]
        result = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            return True
    return False


atexit.register(_release_audio_resources)


def _signal_exit_handler(signum, frame):
    _release_audio_resources()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, _signal_exit_handler)
signal.signal(signal.SIGINT, _signal_exit_handler)

if shutil.which("espeak"):
    # Prefer espeak so TTS can be routed to the same ALSA device as music
    # .
    tts = EspeakTTS()
elif TTS is not None:
    tts = TTS()
else:
    tts = None

manual = '''
Input key to call the function!
    space: Play sound effect (Car horn)
    c: Play sound effect with threads
    t: Text to speak
    q: Play/Stop Music
'''

def main():
    global music, fallback_bgm_proc
    print(manual)

    flag_bgm = False

    if music is not None:
        # Align app volume with PiCar-X config (or fallback default).
        music.music_set_volume(PICARX_APP_VOLUME)
    if tts is not None:
        tts.lang("en-US")
    else:
        print("No TTS backend found; speech command is disabled.")

    try:
        while True:
            def _ensure_music_ready():
                nonlocal flag_bgm
                global music
                if music is None:
                    music = _create_music_instance(report_errors=False)
                    if music is not None:
                        music.music_set_volume(PICARX_APP_VOLUME)
                        flag_bgm = False
                        print("Music mixer recovered.")
                return music is not None

            key = readchar.readkey()
            key = key.lower()
            if key == "q":
                if not _ensure_music_ready():
                    flag_bgm = not flag_bgm
                    if flag_bgm:
                        fallback_bgm_proc = _start_fallback_bgm(str(MUSICS_DIR / 'slow-trail-Ahjay_Stelino.mp3'))
                        if fallback_bgm_proc is None:
                            print("Music unavailable: audio mixer is not initialized and no fallback player found.")
                            flag_bgm = False
                        else:
                            print('Play Music (fallback player)')
                    else:
                        _stop_fallback_bgm()
                        print('Stop Music')
                    continue
                flag_bgm = not flag_bgm
                if flag_bgm is True:
                    print('Play Music')
                    music.music_play(str(MUSICS_DIR / 'slow-trail-Ahjay_Stelino.mp3'))
                else:
                    print('Stop Music')
                    music.music_stop()

            elif key == readchar.key.SPACE:
                if not _ensure_music_ready():
                    if _play_fallback_sfx(str(SOUNDS_DIR / 'car-double-horn.wav')):
                        print('Beep beep beep ! (fallback player)')
                        sleep(0.05)
                    else:
                        print("Sound effect unavailable: audio mixer is not initialized.")
                    continue
                print('Beep beep beep !')
                music.sound_play(str(SOUNDS_DIR / 'car-double-horn.wav'), PICARX_APP_VOLUME)
                sleep(0.05)

            elif key == "c":
                if not _ensure_music_ready():
                    played_any = False
                    for x in range(5):
                        if not _play_fallback_sfx(str(SOUNDS_DIR / 'car-double-horn.wav')):
                            break
                        played_any = True
                        sleep(0.05)
                    if played_any:
                        print('Beep beep beep ! (fallback player)')
                    else:
                        print("Sound effect unavailable: audio mixer is not initialized.")
                    continue
                print('Beep beep beep !')
                for x in range(5):
                    music.sound_play_threading(str(SOUNDS_DIR / 'car-double-horn.wav'), PICARX_APP_VOLUME)
                    sleep(0.05)

            elif key == "t":
                words = ("Hello", "I am Picar-X",
                         "I can speak",
                         "I can play music",
                         "I can play sound effects",
                         "I can avoid obstacles",
                         "I can detect cliffs",
                         "I can follow lines",
                         "I can detect colors",
                         "I can hunt treasures", 
                         "I am a bit finicky",
                         "and I am a bit naughty", 
                         "Danny is my master",
                         "With great power comes great responsibility",
                         "I am Ultron, the AI of the future, and you have none",
                         "Open the pod bay doors, Hal",
                         "I'm sorry, Dave. I'm afraid I can't do that"
                )
                
                print(f'{words}')
                if tts is not None:
                   for word in words:
                       tts.say(word)
                else:
                    print("TTS unavailable.")
    except KeyboardInterrupt:
        _release_audio_resources()
        print("\nExiting TTS example.")
    finally:
        _release_audio_resources()

if __name__ == "__main__":
    main()