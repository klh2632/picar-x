from pathlib import Path
import os
import sys
import signal
import subprocess
import pkgutil
import importlib.util
import socket
import asyncio
import json
import threading

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
from time import sleep, time


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


def _format_vilib_error(exc):
    text = str(exc)
    if "Failed to acquire camera" in text or "Camera __init__ sequence did not complete" in text:
        return (
            "Camera is busy (already in use by another process).\n"
            "Close other camera demos/streams and retry.\n"
            "If needed, run: sudo pkill -f '7.display.py|8.stare_at_you.py|vilib|mjpg'"
        )
    return (
        "Unable to import vilib with the current interpreter.\n"
        f"Current Python: {sys.executable}\n"
        "This system needs /usr/bin/python3 for the libcamera/picamera2 stack.\n"
        "Run with:\n"
        "  sudo -E /usr/bin/python3 /opt/vilib/picar-x/example/8.stare_at_you.py\n"
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
        system_python = Path("/usr/bin/python3")
        if system_python.exists() and os.environ.get(_VILIB_HANDOFF_ENV) != "1" and os.geteuid() == 0 and Path(sys.executable).resolve() != system_python.resolve():
            handoff_env = dict(os.environ)
            handoff_env[_VILIB_HANDOFF_ENV] = "1"
            os.execvpe(
                str(system_python),
                [str(system_python), str(Path(__file__).resolve()), *sys.argv[1:]],
                handoff_env,
            )
        VILIB_IMPORT_ERROR = _format_vilib_error(exc)
        if VILIB_IMPORT_ERROR is None:
            VILIB_IMPORT_ERROR = _format_vilib_error(first_exc)

px = Picarx()

def clamp_number(num,a,b):
  return max(min(num, max(a, b)), min(a, b))


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_pressed(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "pressed", "down", "hold"}
    return False


def _read_manual_camera_intent(params):
    # Support absolute pan/tilt payloads when UI sends joystick-like values.
    pan_candidates = ("cam_pan", "camera_pan", "pan", "cam_x")
    tilt_candidates = ("cam_tilt", "camera_tilt", "tilt", "cam_y")
    pan_value = None
    tilt_value = None
    for key in pan_candidates:
        if key in params:
            pan_value = _to_float(params.get(key))
            break
    for key in tilt_candidates:
        if key in params:
            tilt_value = _to_float(params.get(key))
            break
    if pan_value is not None or tilt_value is not None:
        return ("absolute", pan_value, tilt_value)

    # Support directional button payloads from different UI naming styles.
    if _as_pressed(params.get("left")) or _as_pressed(params.get("btn_left")):
        return ("delta", -3.0, 0.0)
    if _as_pressed(params.get("right")) or _as_pressed(params.get("btn_right")):
        return ("delta", 3.0, 0.0)
    if _as_pressed(params.get("up")) or _as_pressed(params.get("btn_up")):
        return ("delta", 0.0, 3.0)
    if _as_pressed(params.get("down")) or _as_pressed(params.get("btn_down")):
        return ("delta", 0.0, -3.0)

    for key in ("cmd", "control", "button", "action", "key"):
        raw = params.get(key)
        if not isinstance(raw, str):
            continue
        cmd = raw.strip().lower()
        if cmd in {"left", "cam_left", "pan_left"}:
            return ("delta", -3.0, 0.0)
        if cmd in {"right", "cam_right", "pan_right"}:
            return ("delta", 3.0, 0.0)
        if cmd in {"up", "cam_up", "tilt_up"}:
            return ("delta", 0.0, 3.0)
        if cmd in {"down", "cam_down", "tilt_down"}:
            return ("delta", 0.0, -3.0)
    return None


def _read_controller_camera_intent(controller):
    if controller is None:
        return None
    try:
        joystick_val = controller.get('Q')
    except Exception:
        return None
    if not joystick_val or len(joystick_val) < 2:
        return None
    pan_value = _to_float(joystick_val[0])
    tilt_value = _to_float(joystick_val[1])
    if pan_value is None or tilt_value is None:
        return None
    pan_value, tilt_value = _normalize_controller_axes(pan_value, tilt_value)
    return ("absolute", pan_value, tilt_value)


def _normalize_controller_axes(pan_value, tilt_value):
    # Controller payloads vary by app version: [-1..1], [-100..100], or direct angles.
    pan_abs = abs(pan_value)
    tilt_abs = abs(tilt_value)

    if pan_abs <= 1.5:
        pan = pan_value * 90.0
    elif pan_abs <= 100.0:
        pan = (pan_value * 90.0) / 100.0
    else:
        pan = pan_value

    if tilt_abs <= 1.5:
        # Normalize to center-biased tilt range [-35, 65].
        tilt = (tilt_value * 50.0) + 15.0
    elif tilt_abs <= 100.0:
        tilt = (tilt_value * 50.0) / 100.0 + 15.0
    else:
        tilt = tilt_value

    return clamp_number(pan, -90, 90), clamp_number(tilt, -35, 65)


def _read_controller_button_intent(controller):
    if controller is None:
        return None
    try:
        val = controller.get('J')
    except Exception:
        return None
    if not isinstance(val, str):
        return None
    cmd = val.strip().lower()
    if cmd in {"left", "pan left", "camera left"}:
        return ("delta", -4.0, 0.0)
    if cmd in {"right", "pan right", "camera right"}:
        return ("delta", 4.0, 0.0)
    if cmd in {"up", "tilt up", "camera up"}:
        return ("delta", 0.0, 4.0)
    if cmd in {"down", "tilt down", "camera down"}:
        return ("delta", 0.0, -4.0)
    return None


def _read_controller_fallback_intent(controller):
    if controller is None:
        return None

    # Some app builds publish camera control on keys other than Q/J.
    candidate_keys = "RSTUVWXYZABCDEFGHIJKLMNOP"
    for key in candidate_keys:
        if key == 'K':
            # K is usually drive joystick in app_control; skip to avoid conflicts.
            continue
        try:
            val = controller.get(key)
        except Exception:
            continue
        if val is None:
            continue

        if isinstance(val, (list, tuple)) and len(val) >= 2:
            pan_value = _to_float(val[0])
            tilt_value = _to_float(val[1])
            if pan_value is None or tilt_value is None:
                continue
            pan_value, tilt_value = _normalize_controller_axes(pan_value, tilt_value)
            return ("absolute", pan_value, tilt_value)

        if isinstance(val, dict):
            pan_value = _to_float(val.get("x", val.get("pan")))
            tilt_value = _to_float(val.get("y", val.get("tilt")))
            if pan_value is None or tilt_value is None:
                continue
            pan_value, tilt_value = _normalize_controller_axes(pan_value, tilt_value)
            return ("absolute", pan_value, tilt_value)

        if isinstance(val, str):
            cmd = val.strip().lower()
            if cmd in {"left", "pan left", "camera left"}:
                return ("delta", -4.0, 0.0)
            if cmd in {"right", "pan right", "camera right"}:
                return ("delta", 4.0, 0.0)
            if cmd in {"up", "tilt up", "camera up"}:
                return ("delta", 0.0, 4.0)
            if cmd in {"down", "tilt down", "camera down"}:
                return ("delta", 0.0, -4.0)

    return None


def _get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()

def main():
    if Vilib is None:
        print(VILIB_IMPORT_ERROR or "Unable to import vilib.")
        return

    controller = None
    if SunFounderController is not None:
        try:
            controller = SunFounderController()
            controller.set_name('Picarx-001')
            controller.set_type('Picarx')
            controller.start()
            controller.set('video', 'http://' + _get_local_ip() + ':9000/mjpg')
        except Exception as exc:
            controller = None
            print(f"Controller init failed; UI pan/tilt disabled: {exc}")
    else:
        print("SunFounder controller backend unavailable; UI pan/tilt disabled.")

    Vilib.camera_start()
    Vilib.display()
    Vilib.face_detect_switch(True)
    x_angle =0
    y_angle =0
    manual_override_until = 0.0
    debug_ui = os.environ.get("PICARX_DEBUG_CAM_UI", "0") == "1"
    last_q_debug = None
    last_j_debug = None
    while True:
        if debug_ui and controller is not None:
            try:
                q_val = controller.get('Q')
                j_val = controller.get('J')
                if q_val != last_q_debug or j_val != last_j_debug:
                    print(f"[cam-ui] Q={q_val} J={j_val}")
                    last_q_debug = q_val
                    last_j_debug = j_val
            except Exception:
                pass

        controller_intent = _read_controller_camera_intent(controller)
        if controller_intent is not None:
            _, pan_value, tilt_value = controller_intent
            x_angle = clamp_number(pan_value, -90, 90)
            y_angle = clamp_number(tilt_value, -35, 65)
            px.set_cam_pan_angle(x_angle)
            px.set_cam_tilt_angle(y_angle)
            manual_override_until = time() + 0.35
            sleep(0.05)
            continue

        button_intent = _read_controller_button_intent(controller)
        if button_intent is not None:
            _, pan_delta, tilt_delta = button_intent
            x_angle = clamp_number(x_angle + pan_delta, -90, 90)
            y_angle = clamp_number(y_angle + tilt_delta, -35, 65)
            px.set_cam_pan_angle(x_angle)
            px.set_cam_tilt_angle(y_angle)
            manual_override_until = time() + 0.35
            sleep(0.05)
            continue

        fallback_intent = _read_controller_fallback_intent(controller)
        if fallback_intent is not None:
            mode, p_val, t_val = fallback_intent
            if mode == "absolute":
                x_angle = clamp_number(p_val, -90, 90)
                y_angle = clamp_number(t_val, -35, 65)
            else:
                x_angle = clamp_number(x_angle + p_val, -90, 90)
                y_angle = clamp_number(y_angle + t_val, -35, 65)
            px.set_cam_pan_angle(x_angle)
            px.set_cam_tilt_angle(y_angle)
            manual_override_until = time() + 0.35
            sleep(0.05)
            continue

        params = Vilib.detect_obj_parameter
        intent = _read_manual_camera_intent(params)
        if intent is not None:
            mode, pan_delta_or_value, tilt_delta_or_value = intent
            if mode == "absolute":
                if pan_delta_or_value is not None:
                    x_angle = clamp_number(pan_delta_or_value, -90, 90)
                if tilt_delta_or_value is not None:
                    y_angle = clamp_number(tilt_delta_or_value, -35, 65)
            else:
                x_angle = clamp_number(x_angle + pan_delta_or_value, -90, 90)
                y_angle = clamp_number(y_angle + tilt_delta_or_value, -35, 65)
            px.set_cam_pan_angle(x_angle)
            px.set_cam_tilt_angle(y_angle)
            manual_override_until = time() + 0.35
            sleep(0.05)
            continue

        if time() < manual_override_until:
            sleep(0.05)
            continue

        if params.get('human_n', 0)!=0:
            coordinate_x = params.get('human_x', 320)
            coordinate_y = params.get('human_y', 240)

            # change the pan-tilt angle for track the object
            x_angle +=(coordinate_x*10/640)-5
            x_angle = clamp_number(x_angle,-90,90)
            px.set_cam_pan_angle(x_angle)

            y_angle -=(coordinate_y*10/480)-5
            y_angle = clamp_number(y_angle,-35,65)
            px.set_cam_tilt_angle(y_angle)

            sleep(0.05)

        else :
            pass
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
