from time import sleep,strftime,localtime
from pathlib import Path
import sys
import os
import signal
import subprocess
import pkgutil
import importlib.util


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
                f"  sudo -E {system_python} /opt/vilib/picar-x/example/9.record_video.py\n"
                f"Original error: {exc}"
            )
        else:
            VILIB_IMPORT_ERROR = f"Unable to import vilib: {exc}"

import readchar

manual = '''
Press keys on keyboard to control recording:
    Q: record/pause/continue
    E: stop
    Ctrl + C: Quit
'''

def print_overwrite(msg,  end='', flush=True):
    print('\r\033[2K', end='',flush=True)
    print(msg, end=end, flush=True)


def _safe_camera_close():
    if Vilib is None:
        return
    try:
        Vilib.camera_close()
    except Exception:
        pass

def main():
    if Vilib is None:
        print(VILIB_IMPORT_ERROR or "Unable to import vilib.")
        return

    rec_flag = 'stop' # start,pause,stop
    vname = None
    username = os.getlogin()
    
    Vilib.rec_video_set["path"] = f"/home/{username}/Videos/" # set path

    Vilib.camera_start(vflip=False,hflip=False)
    Vilib.display(local=True,web=True)
    sleep(0.8)  # wait for startup

    print(manual)
    while True:
        # read keyboard
        key = readchar.readkey()
        key = key.lower()
        # start,pause
        if key == 'q':
            key = None
            if rec_flag == 'stop':
                rec_flag = 'start'
                # set name
                vname = strftime("%Y-%m-%d-%H.%M.%S", localtime())
                Vilib.rec_video_set["name"] = vname
                # start record
                Vilib.rec_video_run()
                Vilib.rec_video_start()
                print_overwrite('rec start ...')
            elif rec_flag == 'start':
                rec_flag = 'pause'
                Vilib.rec_video_pause()
                print_overwrite('pause')
            elif rec_flag == 'pause':
                rec_flag = 'start'
                Vilib.rec_video_start()
                print_overwrite('continue')
        # stop
        elif key == 'e' and rec_flag != 'stop':
            key = None
            rec_flag = 'stop'
            Vilib.rec_video_stop()
            print_overwrite("The video saved as %s%s.avi"%(Vilib.rec_video_set["path"],vname),end='\n')
        # quit
        elif key == readchar.key.CTRL_C:
            _safe_camera_close()
            print('\nquit')
            break

        sleep(0.1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        _safe_camera_close()