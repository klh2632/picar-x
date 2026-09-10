'''
   14. Fau Roomba Example:
   In spiral mode, spiraling outward until an obstacle is encountered.
   Back and forth mode, going back and forth until stuck.
   Stuck mode, where the PiCar tries backing up and randomly turning to unstick itself.

   The program is fairly simple:
'''

from picarx import Picarx
import time
import random

POWER = 20
SPIRAL = 1
BACKANDFORTH = 2
STUCK = 3

state = SPIRAL
StartTurn = 80
foundObstacle = 40
StuckDist = 10
spiralAngle = 40

def executeSpiral(px):
    global state, spiralAngle
    px.set_dir_servo_angle(spiralAngle)
    px.forward(POWER)
    time.sleep(0.5)
    spiralAngle = spiralAngle - 5
    if spiralAngle < 5:
        spiralAngle = 40
    distance = round(px.ultrasonic.read(), 2)
    print("spiral distance: ",distance)
    if distance <= foundObstacle:
        state = BACKANDFORTH

def executeUnskick(px):
    global state    
    print("unskick backing up")
    px.set_dir_servo_angle(random.randint(-50, 50))
    px.backward(POWER)
    time.sleep(0.5)
    state = SPIRAL                    

def executeBackandForth(px):
    global state    
    distance = round(px.ultrasonic.read(), 2)
    print("back and forth distance: ",distance)
    if distance >= StartTurn:
        px.set_dir_servo_angle(0)
        px.forward(POWER)
        time.sleep(1)
    elif distance < StuckDist:
        state = STUCK
    else:
        px.set_dir_servo_angle(40)
        px.forward(POWER)
        time.sleep(5)
    time.sleep(0.5)                

def main():
    global state
    try:
        px = Picarx()
        while True:
            if state == SPIRAL:               
                executeSpiral(px)
            elif state == BACKANDFORTH:
                executeBackandForth(px)
            elif state == STUCK:
                executeUnskick(px)

    finally:
        px.forward(0)

if __name__ == "__main__":
    main()