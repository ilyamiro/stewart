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

from data.constants import CONFIG_FILE
from utils.utils import yaml_load

config = yaml_load(CONFIG_FILE)

__import__(f"utils.{config['lang']['prefix']}.text")


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
            mouse.scroll(dy=1, dx=0)
        case "down":
            mouse.scroll(dy=-1, dx=0)


def list_usb(**kwargs):
    devices = get_connected_usb_devices()
    ttsi.say(f"There are in total {num2words(len(devices))} devices connected. That is a {', and '.join(devices)}")


def power_reload(**kwargs):
    if kwargs["parameters"]["way"] == "off":
        num = find_num_in_list(kwargs["command"])
        if num:
            tts.say(
                f"Computer will be reloaded in {num2words(num, lang='en')} minutes, sir")
            os.system(f'shutdown -r -h +{num} /dev/null 2>&1')
        else:
            msg = "System will be reloaded in a minute, sir"
            os.system(f'sudo shutdown -r -h +1 /dev/null 2>&1')
            tts.say(msg)
    elif kwargs["parameters"]["way"] == "now":
        thread = threading.Timer(2.5, os.system, args=["sudo shutdown -r now"])
        thread.start()
    else:
        tts.say("System reload was cancelled")
        os.system("sudo shutdown -c /dev/null 2>&1")


def power_off(**kwargs):
    if kwargs["parameters"]["way"] == "off":
        num = find_num_in_list(kwargs["command"])
        if num:
            tts.say(
                f"System will shutdown in {num2words(num, lang='en')} minutes, sir")
            os.system(f'shutdown -h +{num} /dev/null 2>&1')
        else:
            msg = "System will shutdown in a minute, sir"
            os.system(f'sudo shutdown -h +1 /dev/null 2>&1')
            tts.say(msg)
    elif kwargs["parameters"]["way"] == "now":
        thread = threading.Timer(2.5, os.system, args=["sudo shutdown now"])
        thread.start()
    else:
        tts.say("Shutdown was cancelled")
        os.system("sudo shutdown -c /dev/null 2>&1")
