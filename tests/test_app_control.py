import runpy
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AppControlImportTests(unittest.TestCase):
    def test_missing_controller_dependency_does_not_crash_import(self):
        sys.modules.pop("sunfounder_controller", None)

        picarx_module = types.ModuleType("picarx")

        class Picarx:
            pass

        picarx_module.Picarx = Picarx
        sys.modules["picarx"] = picarx_module

        robot_hat_module = types.ModuleType("robot_hat")
        utils_module = types.ModuleType("robot_hat.utils")

        class Music:
            def __init__(self, *args, **kwargs):
                pass

            def sound_play_threading(self, *args, **kwargs):
                pass

        robot_hat_module.Music = Music
        robot_hat_module.utils = utils_module
        sys.modules["robot_hat"] = robot_hat_module
        sys.modules["robot_hat.utils"] = utils_module

        vilib_module = types.ModuleType("vilib")

        class Vilib:
            @staticmethod
            def camera_start(*args, **kwargs):
                return None

            @staticmethod
            def display(*args, **kwargs):
                return None

            @staticmethod
            def camera_close(*args, **kwargs):
                return None

            @staticmethod
            def color_detect(*args, **kwargs):
                return None

            @staticmethod
            def face_detect_switch(*args, **kwargs):
                return None

            @staticmethod
            def object_detect_switch(*args, **kwargs):
                return None

        vilib_module.Vilib = Vilib
        sys.modules["vilib"] = vilib_module

        example_path = PROJECT_ROOT / "example" / "13.app_control.py"
        runpy.run_path(str(example_path), run_name="app_control_test")

    def test_main_uses_ip_fallback_when_utils_get_ip_missing(self):
        sys.modules.pop("sunfounder_controller", None)

        controller_module = types.ModuleType("sunfounder_controller")

        class SunFounderController:
            def __init__(self):
                self._values = {}

            def set_name(self, *args, **kwargs):
                return None

            def set_type(self, *args, **kwargs):
                return None

            def start(self, *args, **kwargs):
                return None

            def set(self, key, value):
                self._values[key] = value

            def get(self, key):
                # Stop the infinite control loop after first iteration.
                if key == "K":
                    raise KeyboardInterrupt
                return None

        controller_module.SunFounderController = SunFounderController
        sys.modules["sunfounder_controller"] = controller_module

        picarx_module = types.ModuleType("picarx")

        class Picarx:
            def stop(self):
                return None

            def get_grayscale_data(self):
                return [0, 0, 0]

            def get_distance(self):
                return 100

            def set_dir_servo_angle(self, *args, **kwargs):
                return None

            def forward(self, *args, **kwargs):
                return None

            def backward(self, *args, **kwargs):
                return None

            def get_line_status(self, *args, **kwargs):
                return [0, 0, 0]

            def set_cam_pan_angle(self, *args, **kwargs):
                return None

            def set_cam_tilt_angle(self, *args, **kwargs):
                return None

        picarx_module.Picarx = Picarx
        sys.modules["picarx"] = picarx_module

        robot_hat_module = types.ModuleType("robot_hat")
        utils_module = types.ModuleType("robot_hat.utils")

        def mapping(x, in_min, in_max, out_min, out_max):
            return int((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

        utils_module.mapping = mapping
        utils_module.run_command = lambda *args, **kwargs: (0, "")
        robot_hat_module.utils = utils_module

        class Music:
            def __init__(self, *args, **kwargs):
                return None

            def sound_play_threading(self, *args, **kwargs):
                return None

        robot_hat_module.Music = Music
        sys.modules["robot_hat"] = robot_hat_module
        sys.modules["robot_hat.utils"] = utils_module

        vilib_module = types.ModuleType("vilib")

        class Vilib:
            @staticmethod
            def camera_start(*args, **kwargs):
                return None

            @staticmethod
            def display(*args, **kwargs):
                return None

            @staticmethod
            def camera_close(*args, **kwargs):
                return None

            @staticmethod
            def color_detect(*args, **kwargs):
                return None

            @staticmethod
            def face_detect_switch(*args, **kwargs):
                return None

            @staticmethod
            def object_detect_switch(*args, **kwargs):
                return None

        vilib_module.Vilib = Vilib
        sys.modules["vilib"] = vilib_module

        example_path = PROJECT_ROOT / "example" / "13.app_control.py"
        with self.assertRaises(KeyboardInterrupt):
            runpy.run_path(str(example_path), run_name="__main__")


if __name__ == "__main__":
    unittest.main()
