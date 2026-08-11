from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
vendor_dir = Path(__file__).resolve().parent.parent / ".vendor"
if (vendor_dir / "robot_hat" / "__init__.py").is_file():
    sys.path.insert(0, str(vendor_dir))

from picarx import Picarx
import time


if __name__ == "__main__":
    px = None
    try:
        # init picarx
        px = Picarx()

        # test motor
        px.forward(30)
        time.sleep(0.5)
        # test direction servo
        for angle in range(0, 35):
            px.set_dir_servo_angle(angle)
            time.sleep(0.01)
        for angle in range(35, -35, -1):
            px.set_dir_servo_angle(angle)
            time.sleep(0.01)
        for angle in range(-35, 0):
            px.set_dir_servo_angle(angle)
            time.sleep(0.01)
        px.stop()
        time.sleep(1)
        # test cam servos
        for angle in range(0, 35):
            px.set_cam_pan_angle(angle)
            time.sleep(0.01)
        for angle in range(35, -35, -1):
            px.set_cam_pan_angle(angle)
            time.sleep(0.01)        
        for angle in range(-35, 0):
            px.set_cam_pan_angle(angle)
            time.sleep(0.01)
        for angle in range(0, 35):
            px.set_cam_tilt_angle(angle)
            time.sleep(0.01)
        for angle in range(35, -35,-1):
            px.set_cam_tilt_angle(angle)
            time.sleep(0.01)        
        for angle in range(-35, 0):
            px.set_cam_tilt_angle(angle)
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        if px is not None:
            px.stop()
            time.sleep(0.2)


