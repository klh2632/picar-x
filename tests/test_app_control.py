import os
import runpy
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GPT_CAR_PATH = PROJECT_ROOT / "gpt_examples" / "gpt_car.py"


def _default_fake_speech_recognition():
    fake_sr = types.ModuleType("speech_recognition")

    class FakeMicrophone:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise OSError("No Default Input Device Available")

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class FakeRecognizer:
        def __init__(self, *args, **kwargs):
            pass

        def adjust_for_ambient_noise(self, *args, **kwargs):
            return None

        def listen(self, *args, **kwargs):
            return None

    fake_sr.Microphone = FakeMicrophone
    fake_sr.Recognizer = FakeRecognizer
    return fake_sr


def _install_gpt_car_stubs(fake_sr=None):
    """Stub every module gpt_car.py imports at top level.

    Every test that runs gpt_car.py via runpy needs the same set of stubs; centralizing
    them here avoids order-dependent failures caused by a test missing one and silently
    relying on real modules left behind in sys.modules by an earlier test.
    """
    sys.modules.pop("speech_recognition", None)
    sys.modules.pop("openai_helper", None)
    sys.modules.pop("keys", None)
    sys.modules.pop("preset_actions", None)
    sys.modules.pop("utils", None)
    sys.modules.pop("picarx", None)
    sys.modules.pop("robot_hat", None)
    sys.modules.pop("vilib", None)

    sys.modules["speech_recognition"] = fake_sr or _default_fake_speech_recognition()

    openai_helper_module = types.ModuleType("openai_helper")

    class FakeOpenAiHelper:
        def __init__(self, *args, **kwargs):
            pass

    openai_helper_module.OpenAiHelper = FakeOpenAiHelper
    sys.modules["openai_helper"] = openai_helper_module

    keys_module = types.ModuleType("keys")
    keys_module.OPENAI_API_KEY = "test-key"
    keys_module.OPENAI_ASSISTANT_ID = "test-assistant"
    keys_module.OPENAI_ASSISTANT_NAME = "test-name"
    keys_module.OPENAI_ASSISTANT_MODEL = "gpt-4o-mini"
    sys.modules["keys"] = keys_module

    preset_actions_module = types.ModuleType("preset_actions")
    preset_actions_module.actions_dict = {}
    sys.modules["preset_actions"] = preset_actions_module

    utils_module = types.ModuleType("utils")
    utils_module.gray_print = lambda *args, **kwargs: None
    utils_module.redirect_error_2_null = lambda: None
    utils_module.cancel_redirect_error = lambda *args, **kwargs: None
    utils_module.speak_block = lambda *args, **kwargs: None
    utils_module.keep_think = lambda *args, **kwargs: None
    utils_module.sleep = __import__("time").sleep
    sys.modules["utils"] = utils_module

    picarx_module = types.ModuleType("picarx")

    class FakePicarx:
        def __init__(self, *args, **kwargs):
            pass

        def reset(self, *args, **kwargs):
            return None

        def set_cam_tilt_angle(self, *args, **kwargs):
            return None

        def set_cam_pan_angle(self, *args, **kwargs):
            return None

        def set_dir_servo_angle(self, *args, **kwargs):
            return None

        def set_motor_speed(self, *args, **kwargs):
            return None

        def stop(self, *args, **kwargs):
            return None

        def forward(self, *args, **kwargs):
            return None

        def backward(self, *args, **kwargs):
            return None

    picarx_module.Picarx = FakePicarx
    sys.modules["picarx"] = picarx_module

    robot_hat_module = types.ModuleType("robot_hat")

    class FakeMusic:
        def __init__(self, *args, **kwargs):
            pass

    class FakePin:
        def __init__(self, *args, **kwargs):
            pass

        def on(self, *args, **kwargs):
            return None

        def off(self, *args, **kwargs):
            return None

    class FakeSunfounderBattery:
        def __init__(self, *args, **kwargs):
            pass

        def get_battery_voltage(self):
            return 8.4

    robot_hat_module.Music = FakeMusic
    robot_hat_module.Pin = FakePin
    sys.modules["robot_hat"] = robot_hat_module

    battery_module = types.ModuleType("robot_hat.services.battery.sunfounder_battery")
    battery_module.Battery = FakeSunfounderBattery
    sys.modules["robot_hat.services.battery.sunfounder_battery"] = battery_module


def _run_gpt_car(argv):
    sys.argv = argv
    return runpy.run_path(str(GPT_CAR_PATH), run_name="gpt_car_test")


def _live_globals(module_globals):
    """runpy.run_path returns a snapshot copy of the module globals, so state mutated
    by calling a function afterwards (e.g. via `global`) won't show up in that dict.
    Read the function's own __globals__ instead to see live state."""
    return module_globals["initialize_runtime"].__globals__


class AppControlImportTests(unittest.TestCase):
    def test_gpt_car_falls_back_to_keyboard_when_mic_unavailable(self):
        _install_gpt_car_stubs()
        module_globals = _run_gpt_car(["gpt_car.py", "--no-img", "--voice"])
        live_globals = _live_globals(module_globals)
        live_globals["_ensure_voice_or_keyboard_mode"]()
        self.assertEqual(live_globals["input_mode"], "keyboard")

    def test_tts_cleanup_ignores_non_process_objects(self):
        sys.modules.pop("robot_hat", None)
        sys.modules.pop("readchar", None)

        robot_hat_module = types.ModuleType("robot_hat")

        class Music:
            def __init__(self, *args, **kwargs):
                pass

            def music_stop(self, *args, **kwargs):
                pass

            def music_play(self, *args, **kwargs):
                pass

            def music_set_volume(self, *args, **kwargs):
                pass

            def sound_play(self, *args, **kwargs):
                pass

            def sound_play_threading(self, *args, **kwargs):
                pass

        robot_hat_module.Music = Music
        sys.modules["robot_hat"] = robot_hat_module

        example_path = PROJECT_ROOT / "example" / "3.tts_example.py"
        module_globals = runpy.run_path(str(example_path), run_name="tts_example_test")
        module_globals["fallback_bgm_proc"] = object()

        module_globals["_stop_fallback_bgm"]()
        module_globals["_release_audio_resources"]()

    def test_gpt_car_allows_start_without_audio_hardware(self):
        _install_gpt_car_stubs()

        class FakeMusic:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("No audio device")

        sys.modules["robot_hat"].Music = FakeMusic

        module_globals = _run_gpt_car(["gpt_car.py", "--no-img", "--voice"])
        live_globals = _live_globals(module_globals)
        live_globals["initialize_runtime"]()
        live_globals["_ensure_voice_or_keyboard_mode"]()

        self.assertIsNotNone(live_globals["music"])
        self.assertEqual(live_globals["input_mode"], "keyboard")

    def test_usb_audio_preset_uses_usb_output_device(self):
        _install_gpt_car_stubs()
        module_globals = _run_gpt_car(["gpt_car.py", "--no-img", "--voice"])

        for key in ("AUDIODEV", "PICARX_AUDIODEV", "PICARX_AUDIO_CARD_ID", "PICARX_AUDIO_CARD_NAME", "PICARX_AUDIO_CARD_HINT"):
            os.environ.pop(key, None)

        module_globals["_apply_audio_route"]("usb")

        # ALSA card numbers shift across reboots/replugs, so assert against the live-resolved
        # card index rather than a hardcoded number.
        expected_card = module_globals["_resolve_alsa_card_index"](("usb", "device"), default="3")
        self.assertEqual(os.environ["AUDIODEV"], f"plughw:{expected_card},0")
        self.assertEqual(os.environ["PICARX_AUDIODEV"], f"plughw:{expected_card},0")
        self.assertEqual(os.environ["PICARX_AUDIO_CARD_ID"], expected_card)
        self.assertEqual(os.environ["PICARX_AUDIO_CARD_NAME"], "USB PnP Audio Device")
        self.assertEqual(os.environ["PICARX_AUDIO_CARD_HINT"], "usb_audio")

    def test_open_microphone_retries_stereo_when_mono_is_invalid(self):
        class FakePyAudio:
            def __init__(self):
                self.calls = []

            def open(self, **kwargs):
                self.calls.append(kwargs["channels"])
                if kwargs["channels"] == 1:
                    raise OSError("[Errno -9998] Invalid number of channels")
                return object()

            def terminate(self):
                pass

        class FakeMicrophoneStream:
            def __init__(self, stream):
                self.stream = stream

            def close(self):
                return None

        fake_sr = types.ModuleType("speech_recognition")

        class FakeMicrophone:
            def __init__(self, *args, **kwargs):
                self.device_index = kwargs.get("device_index", 0)
                self.format = 8
                self.SAMPLE_RATE = 16000
                self.CHUNK = 8192
                self.pyaudio_module = types.SimpleNamespace(PyAudio=lambda: FakePyAudio())

        class FakeRecognizer:
            def __init__(self, *args, **kwargs):
                pass

        fake_sr.Microphone = FakeMicrophone
        fake_sr.Microphone.MicrophoneStream = FakeMicrophoneStream
        fake_sr.Recognizer = FakeRecognizer

        _install_gpt_car_stubs(fake_sr=fake_sr)
        module_globals = _run_gpt_car(["gpt_car.py", "--no-img", "--voice"])
        mic = module_globals["_open_microphone_for_listen"](1)
        self.assertIsNotNone(mic)
        self.assertTrue(hasattr(mic, "stream"))

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
