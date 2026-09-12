'''
   FauRoomba Methods:
   In spiral mode, spiraling outward until an obstacle is encountered.
   Back and forth mode, going back and forth until stuck.
   Stuck mode, where the PiCar tries backing up and randomly turning to unstick itself.

   The program is fairly simple:
'''
from __future__ import annotations


from picarx import Picarx
from vilib import Vilib
from typing import Callable
import time
import random

PRETEND_ROOMBA_POWER = 20
PRETEND_ROOMBA_SPIRAL = 1
PRETEND_ROOMBA_BACKANDFORTH = 2
PRETEND_ROOMBA_STUCK = 3

global state
state = PRETEND_ROOMBA_SPIRAL
global StartTurn
StartTurn = 80
global foundObstacle
foundObstacle = 40
global StuckDist
StuckDist = 10
global spiralAngle
spiralAngle = 40

def executeSpiral(px, speak_text_fn=None):
    global state, spiralAngle
    px.set_dir_servo_angle(spiralAngle)
    px.forward(PRETEND_ROOMBA_POWER)
    time.sleep(0.5)
    spiralAngle = spiralAngle - 5
    if spiralAngle < 5:
        spiralAngle = 40
    distance = round(px.ultrasonic.read(), 2)
    print("spiral distance: ",distance)
    if distance <= foundObstacle:
        if speak_text_fn is not None:
            speak_text_fn("Obstacle found, switching to back and forth mode.")
        state = PRETEND_ROOMBA_BACKANDFORTH

def executeUnskick(px, speak_text_fn=None):
    global state    
    print("unskick backing up")
    if speak_text_fn is not None:
        speak_text_fn("unskick backing up")
    px.set_dir_servo_angle(random.randint(-50, 50))
    px.backward(PRETEND_ROOMBA_POWER)
    time.sleep(0.5)
    state = PRETEND_ROOMBA_SPIRAL                    

def executeBackandForth(px, speak_text_fn=None):
    global state    
    distance = round(px.ultrasonic.read(), 2)
    print("back and forth distance: ",distance)

    if distance >= StartTurn:
        px.set_dir_servo_angle(0)
        px.forward(PRETEND_ROOMBA_POWER)
        time.sleep(1)
    elif distance < StuckDist:
        state = PRETEND_ROOMBA_STUCK
    else:
        px.set_dir_servo_angle(40)
        px.forward(PRETEND_ROOMBA_POWER)
        time.sleep(5)
    time.sleep(0.5)                

def pretend_roomba(px: Picarx,  vilib: Vilib, speak_text_fn: Callable[[str], None] | None = None, roomba_duration: float = 60.0):
    global state
    def _speak_text(text):
        if speak_text_fn is not None:
            speak_text_fn(text)

    if px is None:
        print("Picarx instance is not provided.")
        _speak_text("Picarx instance is not provided.")
        return
    start_time = time.time()
    last_announced_state = None

    try:
        while True:
            if time.time() - start_time > roomba_duration:
                print("Roomba duration ended.")
                _speak_text(f"Roomba duration: {roomba_duration} ended.")
                break

            if state != last_announced_state:
                if state == PRETEND_ROOMBA_SPIRAL:
                    _speak_text("Executing Roomba spiral mode.")
                elif state == PRETEND_ROOMBA_BACKANDFORTH:
                    _speak_text("Executing Roomba back and forth mode.")
                elif state == PRETEND_ROOMBA_STUCK:
                    _speak_text("Executing Roomba stuck mode.")
                last_announced_state = state

            if state == PRETEND_ROOMBA_SPIRAL:   
                print("Executing spiral mode.")
                executeSpiral(px, _speak_text)
            elif state == PRETEND_ROOMBA_BACKANDFORTH:
                print("Executing back and forth mode.")
                executeBackandForth(px, _speak_text)
            elif state == PRETEND_ROOMBA_STUCK:
                print("Executing stuck mode.")
                executeUnskick(px, _speak_text)

    finally:
        px.forward(0)
        _speak_text("Exiting Roomba mode: ")
