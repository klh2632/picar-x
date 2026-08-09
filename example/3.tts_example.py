from pathlib import Path
import sys
import shutil
import subprocess
import os
import importlib.util
import re
import tempfile

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
                    music_obj.sound_play(str(wav_path), 75)
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

    # Detect preferred playback card (HiFiBerry first, otherwise first card).
    selected_card_id = None
    selected_card_name = None
    try:
        cards = Path("/proc/asound/cards").read_text(encoding="utf-8", errors="ignore")
        detected_cards = []
        for line in cards.splitlines():
            match = re.search(r"^\s*(\d+)\s+\[([^\]]+)\]:", line)
            if match:
                detected_cards.append((match.group(1), match.group(2), line.lower()))

        for card_id, card_name, lower_line in detected_cards:
            if "snd_rpi_hifiberry_dac" in lower_line or "hifiberry" in lower_line:
                selected_card_id = card_id
                selected_card_name = card_name
                break

        if selected_card_name is None and detected_cards:
            selected_card_id, selected_card_name, _ = detected_cards[0]
    except Exception:
        selected_card_id = None
        selected_card_name = None

    # Do not auto-force PICARX_AUDIODEV here; bad routes can mute TTS.
    # Users can set PICARX_AUDIODEV explicitly when they want hard routing.
    if selected_card_id:
        os.environ["PICARX_AUDIO_CARD_ID"] = str(selected_card_id)
    if selected_card_name:
        os.environ["PICARX_AUDIO_CARD_NAME"] = selected_card_name

    # Raise ALSA playback volume if amixer is available.
    if shutil.which("amixer"):
        # Allow tuning via environment variable, defaulting to max output.
        try:
            target_percent = int(os.environ.get("PICARX_SYSVOL", "100"))
        except ValueError:
            target_percent = 100
        target_percent = max(0, min(100, target_percent))

        amixer_base = ["amixer"]
        if selected_card_id is not None:
            amixer_base += ["-c", str(selected_card_id)]

        controls = subprocess.run(
            amixer_base + ["scontrols"],
            check=False,
            text=True,
            capture_output=True,
        )
        controls_out = controls.stdout or ""

        for control_name in ("Digital", "PCM", "Speaker", "Master"):
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
    global music
    print(manual)

    flag_bgm = False

    if music is not None:
        # Set the volume to a reasonable level for background music ~ 75 percent of max sys volume. 
        music.music_set_volume(75)
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
                        music.music_set_volume(75)
                        flag_bgm = False
                        print("Music mixer recovered.")
                return music is not None

            key = readchar.readkey()
            key = key.lower()
            if key == "q":
                if not _ensure_music_ready():
                    print("Music unavailable: audio mixer is not initialized.")
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
                    print("Sound effect unavailable: audio mixer is not initialized.")
                    continue
                print('Beep beep beep !')
                music.sound_play(str(SOUNDS_DIR / 'car-double-horn.wav'), 75)
                sleep(0.05)

            elif key == "c":
                if not _ensure_music_ready():
                    print("Sound effect unavailable: audio mixer is not initialized.")
                    continue
                print('Beep beep beep !')
                for x in range(5):
                    music.sound_play_threading(str(SOUNDS_DIR / 'car-double-horn.wav'), 75)
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
                         "Danny is my master"
                )
                
                print(f'{words}')
                if tts is not None:
                   for word in words:
                       tts.say(word)
                else:
                    print("TTS unavailable.")
    except KeyboardInterrupt:
        if music is not None:
            music.music_stop()
        print("\nExiting TTS example.")

if __name__ == "__main__":
    main()