from pathlib import Path
import os
import sys
import signal
import subprocess
import pkgutil
import importlib.util

try:
    from sunfounder_controller import SunFounderController
except ImportError:
    class SunFounderController:
        def __init__(self, *args, **kwargs):
            pass

        def set_name(self, *args, **kwargs):
            pass

        def set_type(self, *args, **kwargs):
            pass

        def start(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            return None

        def get(self, *args, **kwargs):
            return None

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


def _cleanup_orphan_camera_processes():
    # Set PICARX_AUTO_CLEAN_CAMERA=0 to disable automatic stale-process cleanup.
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
    )

    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            check=False,
            text=True,
            capture_output=True,
        )
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
        except ProcessLookupError:
            pass
        except PermissionError:
            pass


_cleanup_orphan_camera_processes()

from picarx import Picarx
from robot_hat import utils, Music


def _remove_incompatible_py311_paths():
    bad_paths = {
        "/usr/local/lib/python3.11/site-packages",
        "/usr/local/lib/python3.11/dist-packages",
    }
    sys.path[:] = [p for p in sys.path if p not in bad_paths]

Vilib = None
VILIB_IMPORT_ERROR = None
_VILIB_HANDOFF_ENV = "PICARX_VILIB_PY311_HANDOFF"


def _ensure_pkgutil_compat():
    if hasattr(pkgutil, "ImpImporter"):
        return
    class _ImpImporter:
        pass
    pkgutil.ImpImporter = _ImpImporter


def _add_vilib_dependency_paths():
    for dep_path in (
        "/usr/lib/python3/dist-packages",
        "/usr/lib/python3.11/dist-packages",
        "/usr/lib/aarch64-linux-gnu/python3.11/dist-packages",
    ):
        p = Path(dep_path)
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))


_add_vilib_dependency_paths()
_ensure_pkgutil_compat()
os.environ.setdefault("VILIB_WELCOME", "0")
_remove_incompatible_py311_paths()

try:
    from vilib import Vilib
except Exception:
    py311_vilib_init = Path("/usr/local/lib/python3.11/site-packages/vilib/__init__.py")
    py311_site = py311_vilib_init.parent.parent
    try:
        import numpy as _np
        sys.modules.setdefault("numpy", _np)
    except Exception:
        pass
    if py311_site.is_dir() and str(py311_site) not in sys.path:
        sys.path.append(str(py311_site))
    if py311_vilib_init.is_file():
        spec = importlib.util.spec_from_file_location(
            "vilib",
            str(py311_vilib_init),
            submodule_search_locations=[str(py311_vilib_init.parent)],
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["vilib"] = module
            spec.loader.exec_module(module)
    try:
        from vilib import Vilib
    except Exception as exc:
        system_python = Path("/usr/bin/python3")
        if system_python.exists() and os.environ.get(_VILIB_HANDOFF_ENV) != "1" and os.geteuid() == 0 and Path(sys.executable).resolve() != system_python.resolve():
            handoff_env = dict(os.environ)
            handoff_env[_VILIB_HANDOFF_ENV] = "1"
            os.execvpe(
                str(system_python),
                [str(system_python), str(Path(__file__).resolve()), *sys.argv[1:]],
                handoff_env,
            )
        if system_python.exists():
            VILIB_IMPORT_ERROR = (
                "Unable to import vilib with the current interpreter.\n"
                f"Current Python: {sys.executable}\n"
                "This system needs /usr/bin/python3 for the libcamera/picamera2 stack.\n"
                "Run with:\n"
                f"  sudo -E {system_python} /opt/vilib/picar-x/example/13.app_control.py\n"
                f"Original error: {exc}"
            )
        else:
            VILIB_IMPORT_ERROR = f"Unable to import vilib: {exc}"

import socket
from pathlib import Path as _Path
import pwd
from time import sleep

# reset robot_hat
if hasattr(utils, "reset_mcu"):
    utils.reset_mcu()
sleep(0.2)

# init SunFounder Controller class
sc = SunFounderController()
sc.set_name('Picarx-001')
sc.set_type('Picarx')
sc.start()

# init picarx
px = Picarx()
speed = 0

current_line_state = None
last_line_state = "stop"
LINE_TRACK_SPEED = 10
LINE_TRACK_ANGLE_OFFSET = 20

AVOID_OBSTACLES_SPEED = 40
SafeDistance = 40   # > 40 safe
DangerDistance = 20 # > 20 && < 40 turn around, < 20 backward

DETECT_COLOR = 'red' # red, green, blue, yellow , orange, purple

# init music player
User = os.environ.get("SUDO_USER") or os.environ.get("LOGNAME") or pwd.getpwuid(os.getuid()).pw_name
UserHome = pwd.getpwnam(User).pw_dir

try:
    music = Music()
except Exception as exc:
    music = None
    print(f"Audio mixer unavailable, horn disabled: {exc}")
if os.geteuid() != 0:
    print('\033[33mPlay sound needs to be run with sudo.\033[m')


def get_local_ip():
    """Resolve local IP using robot_hat utility when available, else stdlib fallback."""
    if hasattr(utils, "get_ip"):
        ip = utils.get_ip()
        if ip:
            return ip

    # UDP socket trick: no packets are sent, but OS selects the outbound interface.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()

def horn(): 
    if music is None:
        return
    _status, _result = utils.run_command('sudo killall pulseaudio')
    music.sound_play_threading(f'{UserHome}/picar-x/sounds/car-double-horn.wav')

def avoid_obstacles():
    distance = px.get_distance()
    if distance >= SafeDistance:
        px.set_dir_servo_angle(0)
        px.forward(AVOID_OBSTACLES_SPEED)
    elif distance >= DangerDistance:
        px.set_dir_servo_angle(30)
        px.forward(AVOID_OBSTACLES_SPEED)
        sleep(0.1)
    else:
        px.set_dir_servo_angle(-30)
        px.backward(AVOID_OBSTACLES_SPEED)
        sleep(0.5) 

def get_status(val_list):
    _state = px.get_line_status(val_list)  # [bool, bool, bool], 0 means line, 1 means background
    if _state == [0, 0, 0]:
        return 'stop'
    elif _state[1] == 1:
        return 'forward'
    elif _state[0] == 1:
        return 'right'
    elif _state[2] == 1:
        return 'left'

def outHandle():
    global last_line_state, current_line_state
    if last_line_state == 'left':
        px.set_dir_servo_angle(-30)
        px.backward(10)
    elif last_line_state == 'right':
        px.set_dir_servo_angle(30)
        px.backward(10)
    while True:
        gm_val_list = px.get_grayscale_data()
        gm_state = get_status(gm_val_list)
        currentSta = gm_state
        if currentSta != last_line_state:
            break
    sleep(0.001)

def line_track():
    global last_line_state
    gm_val_list = px.get_grayscale_data()
    gm_state = get_status(gm_val_list)

    if gm_state != "stop":
        last_line_state = gm_state

    if gm_state == 'forward':
        px.set_dir_servo_angle(0)
        px.forward(LINE_TRACK_SPEED) 
    elif gm_state == 'left':
        px.set_dir_servo_angle(LINE_TRACK_ANGLE_OFFSET)
        px.forward(LINE_TRACK_SPEED) 
    elif gm_state == 'right':
        px.set_dir_servo_angle(-LINE_TRACK_ANGLE_OFFSET)
        px.forward(LINE_TRACK_SPEED) 
    else:
        outHandle()

def main():
    global speed

    if Vilib is None:
        print(VILIB_IMPORT_ERROR or "Unable to import vilib.")
        return

    ip = get_local_ip()
    print('ip : %s'%ip)
    sc.set('video','http://'+ip+':9000/mjpg')

    Vilib.camera_start(vflip=False,hflip=False)
    Vilib.display(local=False, web=True)
    speak = None
    while True:
        # --- send data ---
        sc.set("A", speed)

        grayscale_data = px.get_grayscale_data()
        sc.set("D", grayscale_data )

        distance = px.get_distance()
        sc.set("F", distance)

        # --- control ---

        # # horn
        if sc.get('M') == True:
            horn()

        # speaker
        if sc.get('J') != None:
            speak=sc.get('J')
            print(f'speaker: {speak}')
        if speak in ["forward"]:
            px.forward(speed)
        elif speak in ["backward"]:
            px.backward(speed)
        elif speak in ["left"]:
            px.set_dir_servo_angle(-30)
            px.forward(60)
            sleep(1.2)
            px.set_dir_servo_angle(0)
            px.forward(speed)
        elif speak in ["right", "white", "rice"]:
            px.set_dir_servo_angle(30)
            px.forward(60)
            sleep(1.2)
            px.set_dir_servo_angle(0)
            px.forward(speed)
        elif speak in ["stop"]:
            px.stop()

        # line_track and avoid_obstacles
        line_track_switch = sc.get('I')
        avoid_obstacles_switch = sc.get('E')
        if line_track_switch == True:
            speed = LINE_TRACK_SPEED
            line_track()
        elif avoid_obstacles_switch == True:
            speed = AVOID_OBSTACLES_SPEED
            avoid_obstacles()
    
        # joystick moving
        if line_track_switch != True and avoid_obstacles_switch != True:
            Joystick_K_Val = sc.get('K')
            if Joystick_K_Val != None:
                dir_angle = utils.mapping(Joystick_K_Val[0], -100, 100, -30, 30)
                speed = Joystick_K_Val[1]
                px.set_dir_servo_angle(dir_angle)
                if speed > 0:
                    px.forward(speed)
                elif speed < 0:
                    speed = -speed
                    px.backward(speed)
                else:
                    px.stop()

        # camera servos control
        Joystick_Q_Val = sc.get('Q')
        if Joystick_Q_Val != None:
            pan = min(90, max(-90, Joystick_Q_Val[0]))
            tilt = min(65, max(-35, Joystick_Q_Val[1]))
            px.set_cam_pan_angle(pan)
            px.set_cam_tilt_angle(tilt)

        # image recognition
        if sc.get('N') == True:
            Vilib.color_detect(DETECT_COLOR)
        else:
            Vilib.color_detect("close")

        if sc.get('O') == True:
            Vilib.face_detect_switch(True)  
        else:
            Vilib.face_detect_switch(False)  

        if sc.get('P') == True:
            Vilib.object_detect_switch(True) 
        else:
            Vilib.object_detect_switch(False)


def _safe_camera_close():
    if Vilib is None:
        return
    try:
        Vilib.camera_close()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print("stop and exit")
        px.stop()
        _safe_camera_close()




