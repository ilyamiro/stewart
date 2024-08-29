import logging
import subprocess as sp

# third-party
import pyautogui
from pymouse import PyMouse

mouse = PyMouse()


def subprocess(**kwargs):
    sp.run(
        kwargs["parameters"]["command"],
        stdout=sp.DEVNULL,
        stderr=sp.STDOUT,
    )


def hotkey(**kwargs):
    pyautogui.hotkey(*kwargs["parameters"]["hotkey"])


def key(**kwargs):
    pyautogui.press(kwargs["parameters"]["key"])


def scroll(**kwargs):
    match kwargs["parameters"]["way"]:
        case "up":
            mouse.wheel(1)
        case "down":
            mouse.wheel(-1)
