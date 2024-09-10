import logging
import subprocess as sp

# third-party
import pyautogui
from pynput.mouse import Controller, Button
from num2words import num2words

from utils.utils import get_connected_usb_devices
from audio.output import ttsi

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


def list_usb(**kwargs):
    devices = get_connected_usb_devices()
    ttsi.say(f"There are in total {num2words(len(devices))} devices connected. That is a {', and '.join(devices)}")

