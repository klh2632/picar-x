from pathlib import Path
import sys
import shutil
import subprocess
import os

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
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOUNDS_DIR = PROJECT_ROOT / "sounds"
MUSICS_DIR = PROJECT_ROOT / "musics"

os.environ.setdefault("SDL_AUDIODRIVER", "alsa")

from time import sleep
from robot_hat import Music
import readchar
from os import geteuid

try:
    from robot_hat import TTS
except ImportError:
    TTS = None


class EspeakTTS:
    def __init__(self):
        self.voice = "en-us"

    def lang(self, language):
        normalized = (language or "en-US").replace("_", "-").lower()
        self.voice = normalized

    def say(self, words):
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
    subprocess.run(["pkill", "-f", "pulseaudio"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if geteuid() != 0:
    print(f"\033[0;33m{'The program needs to be run using sudo, otherwise there may be no sound.'}\033[0m")
else:
    _prepare_audio_backend()

music = Music()
tts = TTS() if TTS is not None else (EspeakTTS() if shutil.which("espeak") else None)

manual = '''
Input key to call the function!
    space: Play sound effect (Car horn)
    c: Play sound effect with threads
    t: Text to speak
    q: Play/Stop Music
'''

def main():
    print(manual)

    flag_bgm = False
    music.music_set_volume(20)
    if tts is not None:
        tts.lang("en-US")
    else:
        print("No TTS backend found; speech command is disabled.")

    try:
        while True:
            key = readchar.readkey()
            key = key.lower()
            if key == "q":
                flag_bgm = not flag_bgm
                if flag_bgm is True:
                    print('Play Music')
                    music.music_play(str(MUSICS_DIR / 'slow-trail-Ahjay_Stelino.mp3'))
                else:
                    print('Stop Music')
                    music.music_stop()

            elif key == readchar.key.SPACE:
                print('Beep beep beep !')
                music.sound_play(str(SOUNDS_DIR / 'car-double-horn.wav'))
                sleep(0.05)

            elif key == "c":
                print('Beep beep beep !')
                music.sound_play_threading(str(SOUNDS_DIR / 'car-double-horn.wav'))
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
                         "and I am a bit naughty"
                )
                
                print(f'{words}')
                if tts is not None:
                   for word in words:
                       tts.say(word)
                else:
                    print("TTS unavailable.")
    except KeyboardInterrupt:
        music.music_stop()
        print("\nExiting TTS example.")

if __name__ == "__main__":
    main()