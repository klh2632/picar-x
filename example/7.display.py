from pathlib import Path
import sys
import os
import signal
import subprocess
import pkgutil
import importlib.util


for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        sys.path.insert(0, str(parent))
        # Allow importing a sibling /opt/vilib package layout when present.
        sibling_vilib_root = parent.parent
        if sibling_vilib_root.is_dir():
            sys.path.insert(0, str(sibling_vilib_root))
        break


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
    # /usr/local Python does not include Debian dist-packages by default.
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
    # Fallback: load only the vilib package path to avoid pulling incompatible wheels.
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
                f"  sudo -E {system_python} /opt/vilib/picar-x/example/7.display.py\n"
                f"Original error: {exc}"
            )
        else:
            VILIB_IMPORT_ERROR = f"Unable to import vilib: {exc}"

from time import sleep, time, strftime, localtime
import threading
import readchar

flag_face = False
flag_color = False
qr_code_flag = False

manual = '''
Input key to call the function!
    q: Take photo
    1: Color detect : red
    2: Color detect : orange
    3: Color detect : yellow
    4: Color detect : green
    5: Color detect : blue
    6: Color detect : purple
    0: Switch off Color detect
    r: Scan the QR code
    f: Switch ON/OFF face detect
    s: Display detected object information
'''

color_list = ['close', 'red', 'orange', 'yellow',
        'green', 'blue', 'purple',
]

def face_detect(flag):
    print("Face Detect:" + str(flag))
    Vilib.face_detect_switch(flag)


def qrcode_detect():
    global qr_code_flag
    if qr_code_flag == True:
        Vilib.qrcode_detect_switch(True)
        print("Waitting for QR code")

    text = None
    while True:
        temp = Vilib.detect_obj_parameter['qr_data']
        if temp != "None" and temp != text:
            text = temp
            print('QR code:%s'%text)
        if qr_code_flag == False:
            break
        sleep(0.5)
    Vilib.qrcode_detect_switch(False)


def take_photo():
    _time = strftime('%Y-%m-%d-%H-%M-%S',localtime(time()))
    name = 'photo_%s'%_time
    username = os.getlogin()

    path = f"/home/{username}/Pictures/"
    Vilib.take_photo(name, path)
    print('photo save as %s%s.jpg'%(path,name))


def object_show():
    global flag_color, flag_face

    if flag_color is True:
        if Vilib.detect_obj_parameter['color_n'] == 0:
            print('Color Detect: None')
        else:
            color_coodinate = (Vilib.detect_obj_parameter['color_x'],Vilib.detect_obj_parameter['color_y'])
            color_size = (Vilib.detect_obj_parameter['color_w'],Vilib.detect_obj_parameter['color_h'])
            print("[Color Detect] ","Coordinate:",color_coodinate,"Size",color_size)

    if flag_face is True:
        if Vilib.detect_obj_parameter['human_n'] == 0:
            print('Face Detect: None')
        else:
            human_coodinate = (Vilib.detect_obj_parameter['human_x'],Vilib.detect_obj_parameter['human_y'])
            human_size = (Vilib.detect_obj_parameter['human_w'],Vilib.detect_obj_parameter['human_h'])
            print("[Face Detect] ","Coordinate:",human_coodinate,"Size",human_size)


def main():
    global flag_face, flag_color, qr_code_flag
    qrcode_thread = None

    if Vilib is None:
        print(VILIB_IMPORT_ERROR or "Unable to import vilib.")
        return

    Vilib.camera_start(vflip=False,hflip=False)
    Vilib.display(local=True,web=True)
    print(manual)

    while True:
        # readkey
        key = readchar.readkey()
        key = key.lower()
        # take photo
        if key == 'q':
            take_photo()
        # color detect
        elif key != '' and key in ('0123456'):  # '' in ('0123') -> True
            index = int(key)
            if index == 0:
                flag_color = False
                Vilib.color_detect('close')
            else:
                flag_color = True
                Vilib.color_detect(color_list[index]) # color_detect(color:str -> color_name/close)
            print('Color detect : %s'%color_list[index])
        # face detection
        elif key =="f":
            flag_face = not flag_face
            face_detect(flag_face)
        # qrcode detection
        elif key =="r":
            qr_code_flag = not qr_code_flag
            if qr_code_flag == True:
                if qrcode_thread == None or not qrcode_thread.is_alive():
                    qrcode_thread = threading.Thread(target=qrcode_detect)
                    qrcode_thread.daemon = True
                    qrcode_thread.start()
            else:
                if qrcode_thread != None and qrcode_thread.is_alive():
                # wait for thread to end
                    qrcode_thread.join()
                    print('QRcode Detect: close')
        # show detected object information
        elif key == "s":
            object_show()

        sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass