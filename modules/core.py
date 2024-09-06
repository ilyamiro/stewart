import logging
import subprocess as sp

# third-party
import pyautogui
from pynput.mouse import Controller, Button

mouse = Controller()

log = logging.getLogger("module: " + __file__)


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
            mouse.scroll(1)
        case "down":
            mouse.scroll(-1)
