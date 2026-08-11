'''
    Cliff detection program for Picar-X:

    Pay attention to modify the reference value of the grayscale module 
    according to the practical usage scenarios.
    Auto calibrate grayscale values:
        Please run ./calibration/grayscale_calibration.py
    Manual modification:
        Use the following: 
            px.set_cliff_reference([200, 200, 200])
        The reference value be close to the middle of the line gray value
        and the background gray value.

'''
from pathlib import Path
import sys
import shutil
import subprocess
import os

for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        sys.path.insert(0, str(parent))
        vendor_dir = parent / ".vendor"
        if vendor_dir.is_dir():
            sys.path.insert(0, str(vendor_dir))
        break


def _handoff_to_system_python():
    target_python = Path("/usr/bin/python3")
    handoff_env = "PICARX_PY313_HANDOFF"
    if not target_python.exists():
        return
    if os.geteuid() != 0:
        return
    if os.environ.get(handoff_env) == "1":
        return
    if Path(sys.executable).resolve() == target_python.resolve():
        return

    env = dict(os.environ)
    env[handoff_env] = "1"
    os.execvpe(
        str(target_python),
        [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        env,
    )


_handoff_to_system_python()

from picarx import Picarx
from time import sleep
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

tts = TTS() if TTS is not None else (EspeakTTS() if shutil.which("espeak") else None)
if tts is not None:
    tts.lang("en-US")
else:
    print("No TTS backend found; cliff warning speech is disabled.")

px = Picarx()
# px = Picarx(grayscale_pins=['A0', 'A1', 'A2'])
# manual modify reference value
px.set_cliff_reference([200, 200, 200])

current_state = None
px_power = 10
offset = 20
last_state = "safe"



if __name__=='__main__':
    try:
        while True:
            gm_val_list = px.get_grayscale_data()
            gm_state = px.get_cliff_status(gm_val_list)
            # print("cliff status is:  %s"%gm_state)

            if gm_state is False:
                state = "safe"
                px.stop()
            else:
                state = "danger"   
                px.backward(80)
                if last_state == "safe":
                    if tts is not None:
                        tts.say("danger")
                    sleep(0.1)
            last_state = state
    except KeyboardInterrupt:
        pass

    finally:
        px.stop()
        print("stop and exit")
        sleep(0.1)


                