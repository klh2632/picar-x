#!/usr/bin/python3
from pathlib import Path
import sys

try:
    import readchar
except ImportError:
    class _ReadCharFallbackKey:
        SPACE = " "
        CTRL_C = "\x03"
        ESC = "\x1b"

    class _ReadCharFallback:
        key = _ReadCharFallbackKey()

        @staticmethod
        def readkey():
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    readchar = _ReadCharFallback()

for parent in Path(__file__).resolve().parents:
    if (parent / "picarx").is_dir():
        sys.path.insert(0, str(parent))
        break

from picarx import Picarx
from time import sleep

manual = '''
--------------- Picar-X Calibration Helper -----------------

    [1]: direction servo            [W/D]: increase servo angle
    [2]: camera pan servo           [S/A]: decrease servo angle
    [3]: camera tilt servo          [R]: servos test

    [4]: left motor                 [Q]: change motor direction
    [5]: right motor                [E]: motors run/stop

    [M]: switch mode                [W/S]: trim selected motor in motor mode
    [SPACE]: confirm calibration     [Crtl+C]: quit

    Note: trim acts immediately when the motors are running.
                                      
'''    

px = Picarx()
px_power = 30

servo_num = 0
motor_num = 0
edit_mode = 'servo'
servo_names = ['direction servo', 'camera pan servo', 'camera tilt servo']
motor_names = ['left motor', 'right motor']
servos_cali = [px.dir_cali_val, px.cam_pan_cali_val, px.cam_tilt_cali_val]
motors_cali = px.cali_dir_value
motors_speed_trim = list.copy(px.cali_speed_value)
servos_offset = list.copy(servos_cali)
motors_offset = list.copy(motors_cali)

def servos_test():
    px.set_dir_servo_angle(-30)
    sleep(0.5)
    px.set_dir_servo_angle(30)
    sleep(0.5)
    px.set_dir_servo_angle(0)
    sleep(0.5)
    px.set_cam_pan_angle(-30)
    sleep(0.5)
    px.set_cam_pan_angle(30)
    sleep(0.5)
    px.set_cam_pan_angle(0)
    sleep(0.5)
    px.set_cam_tilt_angle(-30)
    sleep(0.5)
    px.set_cam_tilt_angle(30)
    sleep(0.5)
    px.set_cam_tilt_angle(0)
    sleep(0.5)

def servos_move(servo_num, value):
    if servo_num == 0:
        px.set_dir_servo_angle(value)
    elif servo_num == 1:
        px.set_cam_pan_angle(value)
    elif servo_num == 2:
        px.set_cam_tilt_angle(value)
    sleep(0.2)

def set_servos_offset(servo_num, value):
    if servo_num == 0:
        px.dir_cali_val = value
    elif servo_num == 1:
        px.cam_pan_cali_val = value
    elif servo_num == 2:
        px.cam_tilt_cali_val  = value  

def servos_reset():
    for i in range(3):
        servos_move(i,0)

def show_info():
    print("\033[H\033[J", end='')  # clear terminal windows
    print(manual)
    print('[ %s ] [ %s ] [mode: %s]'%(servo_names[servo_num], motor_names[motor_num], edit_mode))
    print('servo offset: %s, motor direction: %s, motor trim: %s'%(servos_offset, motors_offset, motors_speed_trim))


def cali_helper(): 
    global servo_num, motor_num, edit_mode
    global servos_cali, motors_cali, servos_offset, motors_offset, motors_speed_trim
    motor_run = False
    step = 0.4
    trim_step = 2
    # step = (180 / 2000) * (20000 / 4095)  # actual precision of steering gear

    # reset
    servos_reset()
    # show_info 
    show_info()

    # key control
    while True:
        # readkey
        key = readchar.readkey()
        key = key.lower()
        if key == 'm':
            edit_mode = 'motor' if edit_mode == 'servo' else 'servo'
            show_info()
        # select the servo 
        elif key in ('123'):
            servo_num = int(key)-1
            edit_mode = 'servo'
            show_info()
        elif key in ('45'):
            motor_num = int(key)-4
            edit_mode = 'motor'
            show_info()
        # servo adjustments
        elif edit_mode == 'servo' and (key == 'w' or key == 'd'):
            servos_offset[servo_num] += step
            if servos_offset[servo_num] > 20:
                servos_offset[servo_num] =20
            servos_offset[servo_num] = round(servos_offset[servo_num], 2) 
            show_info()
            set_servos_offset(servo_num, servos_offset[servo_num])
            servos_move(servo_num, 0)
        elif edit_mode == 'servo' and (key == 's' or key == 'a'):
            servos_offset[servo_num] -= step
            if servos_offset[servo_num] < -20:
                servos_offset[servo_num] = -20
            servos_offset[servo_num] = round(servos_offset[servo_num], 2) 
            show_info()
            set_servos_offset(servo_num, servos_offset[servo_num])
            servos_move(servo_num, 0)
        # motor trim adjustments
        elif edit_mode == 'motor' and key == 'w':
            motors_speed_trim[motor_num] += trim_step
            if motors_speed_trim[motor_num] > 50:
                motors_speed_trim[motor_num] = 50
            px.set_single_motor_speed_calibration(motor_num + 1, motors_speed_trim[motor_num])
            if not motor_run:
                motor_run = True
            px.forward(px_power)
            show_info()
        elif edit_mode == 'motor' and key == 's':
            motors_speed_trim[motor_num] -= trim_step
            if motors_speed_trim[motor_num] < -50:
                motors_speed_trim[motor_num] = -50
            px.set_single_motor_speed_calibration(motor_num + 1, motors_speed_trim[motor_num])
            if not motor_run:
                motor_run = True
            px.forward(px_power)
            show_info()
        # motors move
        elif key == 'q': 
            motors_offset[motor_num] = -1 * motors_offset[motor_num]
            px.cali_dir_value = list.copy(motors_offset)
            motor_run = True
            px.forward(px_power)
            show_info()
        elif key == 'e':
            if motor_run == False:
                motor_run = True
                px.forward(px_power)
            else:
                motor_run = False
                px.stop()
        # save
        elif key == readchar.key.SPACE:
            print('Confirm save ?(y/n)')
            while True:
                key = readchar.readkey()
                key = key.lower()
                if key == 'y':
                    px.dir_servo_calibrate(servos_offset[0])
                    px.cam_pan_servo_calibrate(servos_offset[1])
                    px.cam_tilt_servo_calibrate(servos_offset[2])
                    px.motor_direction_calibrate(motor_num +1 , motors_offset[motor_num])
                    px.set_motor_speed_calibration(motors_speed_trim)
                    sleep(0.2)
                    servos_offset = [px.dir_cali_val, px.cam_pan_cali_val, px.cam_tilt_cali_val]
                    motors_speed_trim = list.copy(px.cali_speed_value)
                    show_info()
                    print('The calibration value has been saved.')
                    break
                elif key == 'n':
                    show_info()
                    break   
                sleep(0.01) 

        # quit
        elif key == readchar.key.CTRL_C or key in readchar.key.ESC:
            print('quit')
            break 

        sleep(0.01)


if __name__ == "__main__":
    try:
        cali_helper()
    except KeyboardInterrupt:
        print('quit')
    except Exception as e:
        print(e)
    finally:
        px.stop()
        sleep(0.1)
