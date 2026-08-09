import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / ".vendor"))

import robot_hat
from robot_hat import Music


class StubMusic(Music):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_calls = 0

    def music_set_volume(self, value):
        return None

    def music_play(self, *args, **kwargs):
        return None

    def music_stop(self):
        self.stop_calls += 1


class TTSExampleTests(unittest.TestCase):
    def test_main_handles_keyboard_interrupt(self):
        example_path = PROJECT_ROOT / "example" / "3.tts_example.py"

        readchar_stub = types.ModuleType("readchar")

        class _Key:
            SPACE = " "

        readchar_stub.key = _Key()
        readchar_stub.readkey = lambda: " "
        sys.modules.setdefault("readchar", readchar_stub)

        with patch.object(readchar_stub, "readkey", side_effect=KeyboardInterrupt), \
             patch("builtins.print") as mocked_print:
            with patch("robot_hat.Music", new=StubMusic):
                runpy.run_path(str(example_path), run_name="__main__")

        self.assertTrue(any("Exiting TTS example" in str(call.args[0]) for call in mocked_print.call_args_list))


if __name__ == "__main__":
    unittest.main()
