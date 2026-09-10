from pathlib import Path
import os
import sys
import pkgutil
import importlib.util
import socket
import asyncio
import json
import threading

# Keep the vendored compatibility package as a fallback, but never let it shadow
# the real installed robot_hat package. Older Picar-X code expects legacy import
# names such as robot_hat.adc and robot_hat.filedb, so these are mapped below.
VENDOR_DIR = Path(__file__).resolve().parent.parent / ".vendor"
VENDOR_DIR = VENDOR_DIR.resolve()
for candidate in list(sys.path):
    if not candidate:
        continue
    try:
        if Path(candidate).resolve() == VENDOR_DIR:
            sys.path.remove(candidate)
    except Exception:
        pass
if str(VENDOR_DIR) not in sys.path:
    sys.path.append(str(VENDOR_DIR))

try:
    from sunfounder_controller import SunFounderController
except Exception:
    SunFounderController = None

if SunFounderController is None:
    try:
        import websockets
    except Exception:
        websockets = None

    if websockets is not None:
        class SunFounderController:
            PORT = 8765

            def __init__(self, port=PORT):
                self.port = int(port)
                self.client_num = 0
                self.client = {}
                self.is_received = False
                self.work_flag = False
                self.server = None
                self.server_thread = threading.Thread(target=self.work, daemon=True)
                self.send_dict = {
                    'Name': '',
                    'Type': None,
                    'Check': 'SunFounder Controller',
                }
                self.recv_dict = {
                    'A': None,
                    'B': None,
                    'C': None,
                    'D': None,
                    'E': None,
                    'F': None,
                    'G': None,
                    'H': None,
                    'I': None,
                    'J': None,
                    'K': None,
                    'L': None,
                    'M': None,
                    'N': None,
                    'O': None,
                    'P': None,
                    'Q': None,
                    'Heart': None,
                }

            def start(self):
                self.work_flag = True
                if not self.server_thread.is_alive():
                    self.server_thread.start()

            def work(self):
                asyncio.run(self._main())

            async def _main(self):
                self.server = await websockets.serve(self._handler, "0.0.0.0", self.port)
                print(f"websocket server start at port {self.port}")
                async with self.server:
                    await asyncio.Future()

            async def _handler(self, websocket):
                client_num = self.client_num
                self.client_num += 1
                client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
                self.client[str(client_num)] = client_ip
                print(f"client {(client_num, client_ip)} conneted")
                last_msg = None

                while self.work_flag:
                    try:
                        try:
                            last_msg = await asyncio.wait_for(websocket.recv(), timeout=0.001)
                        except asyncio.TimeoutError:
                            pass

                        try:
                            await websocket.send(json.dumps(self.send_dict))
                        except Exception:
                            pass

                        if isinstance(last_msg, str):
                            try:
                                payload = json.loads(last_msg)
                                if isinstance(payload, dict):
                                    self.recv_dict.update(payload)
                                    self.is_received = True
                                    if self.recv_dict.get('Heart') == 'ping':
                                        self.send_dict['Heart'] = 'pong'
                            except Exception:
                                self.is_received = False

                        await asyncio.sleep(0.01)
                    except Exception:
                        break

                self.client.pop(str(client_num), None)

            def get(self, key='A', default=None):
                return self.recv_dict.get(key, default)

            def getall(self):
                return self.recv_dict

            def set(self, key='A_region', value=None):
                self.send_dict[key] = value

            def set_name(self, name=None):
                self.send_dict['Name'] = name

            def set_type(self, type=None):
                self.send_dict['Type'] = type

for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        sys.path.insert(0, str(parent))
        sibling_vilib_root = parent.parent
        if sibling_vilib_root.is_dir():
            sys.path.insert(0, str(sibling_vilib_root))
        break


def _purge_legacy_python311_paths():
    legacy_paths = {
        "/usr/local/lib/python3.11",
        "/usr/local/lib/python3.11/site-packages",
        "/usr/local/lib/python3.11/dist-packages",
    }
    sys.path[:] = [p for p in sys.path if p and p not in legacy_paths and "python3.11" not in p]


_purge_legacy_python311_paths()


from picarx import Picarx
from time import sleep, time


def _remove_incompatible_py311_paths():
    bad_paths = {
        "/usr/local/lib/python3.11/site-packages",
        "/usr/local/lib/python3.11/dist-packages",
    }
    sys.path[:] = [p for p in sys.path if p not in bad_paths]

Vilib = None
VILIB_IMPORT_ERROR = None


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


def _format_vilib_error(exc):
    text = str(exc)
    if "Failed to acquire camera" in text or "Camera __init__ sequence did not complete" in text:
        return (
            "Camera is busy (already in use by another process).\n"
            "Close other camera demos/streams and retry.\n"
            "If needed, run: sudo pkill -f '7_display.py|8_stare_at_you.py|vilib|mjpg'"
        )
    return (
        "Unable to import vilib with the current interpreter.\n"
        f"Current Python: {sys.executable}\n"
        "This system needs /usr/bin/python3 for the libcamera/picamera2 stack.\n"
        "Run with:\n"
        "  sudo -E /usr/bin/python3 /opt/vilib/picar-x/example/8_stare_at_you.py\n"
        f"Original error: {exc}"
    )

try:
    from vilib import Vilib
except Exception as first_exc:
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
            try:
                module = importlib.util.module_from_spec(spec)
                sys.modules["vilib"] = module
                spec.loader.exec_module(module)
            except Exception as load_exc:
                VILIB_IMPORT_ERROR = _format_vilib_error(load_exc)
    try:
        from vilib import Vilib
    except Exception as exc:
        VILIB_IMPORT_ERROR = _format_vilib_error(exc)
        if VILIB_IMPORT_ERROR is None:
            VILIB_IMPORT_ERROR = _format_vilib_error(first_exc)

px = Picarx()

def clamp_number(num,a,b):
  return max(min(num, max(a, b)), min(a, b))


def main():
    if Vilib is None:
        print(VILIB_IMPORT_ERROR or "Unable to import vilib.")
        return

    Vilib.camera_start()
    Vilib.display()
    Vilib.face_detect_switch(True)
    # Initialize pan-tilt angles, wonder if we're reading the calibration correctly?
    x_angle =10.0
    y_angle =6.0
    px.set_cam_pan_angle(x_angle)
    px.set_cam_tilt_angle(y_angle)

    while True:
        if Vilib.detect_obj_parameter['human_n']!=0:
            coordinate_x = Vilib.detect_obj_parameter['human_x']
            coordinate_y = Vilib.detect_obj_parameter['human_y']

            # change the pan-tilt angle for track the object
            x_angle +=(coordinate_x*10/640)-2.5
            x_angle = clamp_number(x_angle,-75,75)
            px.set_cam_pan_angle(x_angle)

            y_angle -=(coordinate_y*10/480)-2.5
            y_angle = clamp_number(y_angle,-75,75)
            px.set_cam_tilt_angle(y_angle)

            sleep(0.05)

        else :
            pass
            sleep(0.05)


if __name__ == "__main__":
    try:
       main()


    finally:
        px.stop()
        print("stop and exit")
        sleep(0.1)
