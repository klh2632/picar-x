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
from time import sleep


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
                f"  sudo -E {system_python} /opt/vilib/picar-x/example/10.bull_fight.py\n"
                f"Original error: {exc}"
            )
        else:
            VILIB_IMPORT_ERROR = f"Unable to import vilib: {exc}"


px = Picarx()

def clamp_number(num,a,b):
  return max(min(num, max(a, b)), min(a, b))

def main():
    if Vilib is None:
        print(VILIB_IMPORT_ERROR or "Unable to import vilib.")
        return

    Vilib.camera_start()
    Vilib.display()
    Vilib.color_detect("red")
    speed = 50
    dir_angle=0
    x_angle =0
    y_angle =0
    while True:
        if Vilib.detect_obj_parameter['color_n']!=0:
            coordinate_x = Vilib.detect_obj_parameter['color_x']
            coordinate_y = Vilib.detect_obj_parameter['color_y']
            
            # change the pan-tilt angle for track the object
            x_angle +=(coordinate_x*10/640)-5
            x_angle = clamp_number(x_angle,-35,35)
            px.set_cam_pan_angle(x_angle)

            y_angle -=(coordinate_y*10/480)-5
            y_angle = clamp_number(y_angle,-35,35)
            px.set_cam_tilt_angle(y_angle)

            # move
            # The movement direction will change slower than the pan/tilt direction 
            # change to avoid confusion when the picture changes at high speed.
            if dir_angle > x_angle:
                dir_angle -= 1
            elif dir_angle < x_angle:
                dir_angle += 1
            px.set_dir_servo_angle(x_angle)
            px.forward(speed)
            sleep(0.05)

        else :
            px.forward(0)
            sleep(0.05)


if __name__ == "__main__":
    try:
       main()
    except KeyboardInterrupt:
        pass
    
    
    finally:
        px.stop()
        print("stop and exit")
        sleep(0.1)
