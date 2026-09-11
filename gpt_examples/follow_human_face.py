"""
    follow_human_face.py    KLH 091126 MIT Public License   

    This script allows a Picarx robot to follow a human face using the Vilib library.
    It adjusts the pan and tilt angles of the camera based on the detected face coordinates.
    It runs in a loop, continuously adjusting the camera angles to keep the detected human face centered.
    It is time limited and will stop after a certain duration. Follow_Duration is controlled within the script.
"""

from __future__ import annotations


# from gpt_examples.preset_actions import Picarx
# from vilib import Vilib
from typing import Callable
import time
from time import sleep, time

def clamp_number(num,a,b):
  return max(min(num, max(a, b)), min(a, b))


def follow_human_face(px: Picarx, vilib: Vilib, speak_text_fn: Callable[[str], None] | None = None, follow_duration: float = 60.0):
    def _speak_text(text):
        if speak_text_fn is not None:
            speak_text_fn(text)

    if px is None:
        print("Picarx instance is not provided.")
        _speak_text("Picarx instance is not provided.")
        return

    if vilib is None:
        print("Unable to import vilib.")
        _speak_text("Vilib instance is not provided.")
        return

    # Camera initialization is handled in the calling function(s)
    # vilib.camera_start()

    # No web display is necessary
    # vilib.display()

    vilib.face_detect_switch(True)

    # Initialize pan-tilt angles, wonder if we're reading the calibration correctly?
    x_angle =10.0
    y_angle =6.0
    px.set_cam_pan_angle(x_angle)
    px.set_cam_tilt_angle(y_angle)
    start_time = time()

    while time() - start_time < follow_duration:
        detect = getattr(vilib, 'detect_obj_parameter', {}) or {}

        # Vilib exposes different key names depending on detector mode/version.
        # face_detect_switch() typically populates face_* keys; some builds still
        # provide human_* keys. Support both so tracking remains portable.
        count = int(detect.get('face_n', detect.get('human_n', 0)) or 0)

        if count != 0:
            coordinate_x = float(detect.get('face_x', detect.get('human_x', 320)) or 320)
            coordinate_y = float(detect.get('face_y', detect.get('human_y', 240)) or 240)

            # change the pan-tilt angle for track the object
            x_angle +=(coordinate_x*10/640)-2.5
            x_angle = clamp_number(x_angle,-75,75)
            px.set_cam_pan_angle(x_angle)

            y_angle -= (coordinate_y*10/480)-2.5
            y_angle = clamp_number(y_angle,-75,75)
            px.set_cam_tilt_angle(y_angle)

            sleep(0.05)

        else:
            sleep(0.05)

    # camera stop is handled in calling function(s)
    # vilib.camera_stop()
