from pathlib import Path
import sys
import shutil
import subprocess

for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        sys.path.insert(0, str(parent))
        vendor_dir = parent / ".vendor"
        if vendor_dir.is_dir():
            sys.path.insert(0, str(vendor_dir))
        break

from picarx import Picarx
from time import sleep
from robot_hat import Music
from vilib import Vilib
import readchar
import random
import threading

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
        subprocess.run(["espeak", "-v", self.voice, str(words)], check=False)

px = Picarx()

music = Music()
tts = TTS() if TTS is not None else (EspeakTTS() if shutil.which("espeak") else None)
if tts is not None:
    tts.lang("en-US")
else:
    print("No TTS backend found; treasure hunt speech is disabled.")

manual = '''
Press keys on keyboard to control Picar-X!
    w: Forward
    a: Turn left
    s: Backward
    d: Turn right
    space: Say the target again
    ctrl+c: Quit
'''

color = "red"
color_list=["red","orange","yellow","green","blue","purple"]

def renew_color_detect():
    global color
    color = random.choice(color_list)
    Vilib.color_detect(color)
    if tts is not None:
        tts.say("Look for " + color)

key = None
lock = threading.Lock()
def key_scan_thread():
    global key
    while True:
        try:
            key_temp = readchar.readkey()
        except KeyboardInterrupt:
            with lock:
                key = 'quit'
            break

        print('\r',end='')
        with lock:
            key = key_temp.lower()
            if key == readchar.key.SPACE:
                key = 'space'
            elif key == readchar.key.CTRL_C:
                key = 'quit'
                break
        sleep(0.01)

def car_move(key):
    if 'w' == key:
        px.set_dir_servo_angle(0)
        px.forward(80)
    elif 's' == key:
        px.set_dir_servo_angle(0)
        px.backward(80)
    elif 'a' == key:
        px.set_dir_servo_angle(-30)
        px.forward(80)
    elif 'd' == key:
        px.set_dir_servo_angle(30)
        px.forward(80)


def main():
    global key
    Vilib.camera_start(vflip=False,hflip=False)
    Vilib.display(local=False,web=True)
    sleep(0.8)
    print(manual)

    sleep(1)
    _key_t = threading.Thread(target=key_scan_thread)
    _key_t.daemon = True
    _key_t.start()

    if tts is not None:
        tts.say("game start")
    sleep(0.05)
    renew_color_detect()
    while True:

        if Vilib.detect_obj_parameter['color_n']!=0 and Vilib.detect_obj_parameter['color_w']>100:
            if tts is not None:
                tts.say("will done")
            sleep(0.05)
            renew_color_detect()

        with lock:
            if key != None and key in ('wsad'):
                car_move(key)
                sleep(0.5)
                px.stop()
                key =  None
            elif key == 'space':
                if tts is not None:
                    tts.say("Look for " + color)
                key =  None
            elif key == 'quit':
                _key_t.join()
                print("\n\rQuit")
                break

        sleep(0.05)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        Vilib.camera_close()
        px.stop()
        sleep(.2)