
from pathlib import Path
import sys

for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        sys.path.insert(0, str(parent))
        vendor_dir = parent / ".vendor"
        if vendor_dir.is_dir():
            sys.path.insert(0, str(vendor_dir))
        break

from robot_hat import Servo, utils
from time import sleep

# Newer robot_hat releases may not expose reset_mcu.
if hasattr(utils, "reset_mcu"):
    utils.reset_mcu()
sleep(0.2)

if __name__ == '__main__':
    try:
        print(f"Set servo to zero")
        for i in range(12):
            # print(f"Servo {i} set to zero")
            Servo(i).angle(10)
            sleep(0.1)
            Servo(i).angle(0)
            sleep(0.1)
        while True:
            sleep(1)
    except KeyboardInterrupt:
        pass