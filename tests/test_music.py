import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".vendor"))

from robot_hat.music import Music


class MusicPlaybackTests(unittest.TestCase):
    def test_play_tone_for_uses_sound_play(self):
        class RecordingMusic(Music):
            def __init__(self):
                super().__init__()
                self.played = []

            def sound_play(self, filename, volume=None):
                self.played.append((filename, volume))

        music = RecordingMusic()
        music.play_tone_for(440, 0.01)

        self.assertEqual(len(music.played), 1)
        filename, volume = music.played[0]
        self.assertTrue(filename.endswith(".wav"))
        self.assertIsNone(volume)


if __name__ == "__main__":
    unittest.main()
