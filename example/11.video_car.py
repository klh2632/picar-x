# #!/usr/bin/env python3

from pathlib import Path
import os
import sys
import signal
import subprocess
import pkgutil
import importlib.util

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


def _ensure_xdg_runtime_dir():
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/picarx-runtime-{os.getuid()}"
    os.makedirs(runtime_dir, exist_ok=True)
    os.chmod(runtime_dir, 0o700)
    os.environ["XDG_RUNTIME_DIR"] = runtime_dir


_ensure_xdg_runtime_dir()

def _reset_robot_hat_mcu_if_available():
    try:
        from robot_hat import utils as utils_mod
        if hasattr(utils_mod, "reset_mcu"):
            utils_mod.reset_mcu()
            return
    except Exception:
        pass

    try:
        import robot_hat
        if hasattr(robot_hat, "reset_mcu"):
            robot_hat.reset_mcu()
            return
    except Exception:
        pass

from picarx import Picarx


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
                f"  sudo -E {system_python} /opt/vilib/picar-x/example/11.video_car.py\n"
                f"Original error: {exc}"
            )
        else:
            VILIB_IMPORT_ERROR = f"Unable to import vilib: {exc}"

from time import sleep, time, strftime, localtime
import readchar

user = os.getlogin()
user_home = os.path.expanduser(f'~{user}')

_reset_robot_hat_mcu_if_available()
sleep(0.2)

manual = '''
Press key to call the function(non-case sensitive):

    O: speed up
    P: speed down
    W: forward  
    S: backward
    A: turn left
    D: turn right
    F: stop
    T: take photo

    Ctrl+C: quit
'''


px = Picarx()


def _safe_camera_close():
    if Vilib is None:
        return
    try:
        Vilib.camera_close()
    except Exception:
        pass

def take_photo():
    _time = strftime('%Y-%m-%d-%H-%M-%S',localtime(time()))
    name = 'photo_%s'%_time
    path = f"{user_home}/Pictures/picar-x/"
    os.makedirs(path, exist_ok=True)
    try:
        ok = Vilib.take_photo(name, path)
    except Exception as exc:
        print(f"\nphoto save failed: {exc}")
        return
    if ok:
        print('\nphoto save as %s%s.jpg'%(path,name))
    else:
        print('\nphoto save failed')


def move(operate:str, speed):

    if operate == 'stop':
        px.stop()  
    else:
        if operate == 'forward':
            px.set_dir_servo_angle(0)
            px.forward(speed)
        elif operate == 'backward':
            px.set_dir_servo_angle(0)
            px.backward(speed)
        elif operate == 'turn left':
            px.set_dir_servo_angle(-30)
            px.forward(speed)
        elif operate == 'turn right':
            px.set_dir_servo_angle(30)
            px.forward(speed)
        


def main():
    if Vilib is None:
        print(VILIB_IMPORT_ERROR or "Unable to import vilib.")
        return

    speed = 0
    status = 'stop'

    Vilib.camera_start(vflip=False,hflip=False)
    # Local OpenCV windows can steal keyboard focus from the terminal.
    # Default to web-only display so terminal key commands remain responsive.
    local_display = os.environ.get("PICARX_VIDEO_CAR_LOCAL", "0") == "1"
    Vilib.display(local=local_display,web=True)
    sleep(2)  # wait for startup
    print(manual)
    try:
        while True:
            print("\rstatus: %s , speed: %s    "%(status, speed), end='', flush=True)
            # readkey
            key = readchar.readkey().lower()
            # operation 
            if key in ('wsadfop'):
                # throttle
                if key == 'o':
                    if speed <=90:
                        speed += 10           
                elif key == 'p':
                    if speed >=10:
                        speed -= 10
                    if speed == 0:
                        status = 'stop'
                # direction
                elif key in ('wsad'):
                    if speed == 0:
                        speed = 10
                    if key == 'w':
                        # Speed limit when reversing,avoid instantaneous current too large
                        if status != 'forward' and speed > 60:  
                            speed = 60
                        status = 'forward'
                    elif key == 'a':
                        status = 'turn left'
                    elif key == 's':
                        if status != 'backward' and speed > 60: # Speed limit when reversing
                            speed = 60
                        status = 'backward'
                    elif key == 'd':
                        status = 'turn right' 
                # stop
                elif key == 'f':
                    status = 'stop'
                # move 
                move(status, speed)  
            # take photo
            elif key == 't':
                take_photo()
            # quit
            elif key == readchar.key.CTRL_C:
                print('\nquit ...')
                break 

            sleep(0.1)
    except KeyboardInterrupt:
        print('\nquit ...')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:    
        print("error:%s"%e)
    finally:
        try:
            px.stop()
        except Exception:
            pass
        _safe_camera_close()


        