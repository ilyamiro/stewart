import logging
import subprocess as sp
import os
import sys
import time
import webbrowser

# third-party
import pyautogui
# from pynput.mouse import Controller, Button
from num2words import num2words

# local imports
from utils.utils import *
from data.constants import CONFIG_FILE

from api import app


# mouse = Controller()
log = logging.getLogger("module: " + __file__)


def subprocess(**kwargs) -> None:
    """
    Runs a command using python subprocess module
    """
    sp.run(
        kwargs["parameters"]["command"],
        stdout=sp.DEVNULL,
        stderr=sp.STDOUT,
    )


def hotkey(**kwargs) -> None:
    """
    Executes a hotkey using pyautogui backend
    """
    pyautogui.hotkey(*kwargs["parameters"]["hotkey"])


def key(**kwargs) -> None:
    """
    Presses a key on the keyboard
    """
    pyautogui.press(kwargs["parameters"]["key"])


def scroll(**kwargs) -> None:
    match kwargs["parameters"]["way"]:
        case "up":
            mouse.scroll(dy=1, dx=0)
        case "down":
            mouse.scroll(dy=-1, dx=0)


def browser(**kwargs) -> None:
    webbrowser.open(kwargs["parameters"]["url"])


def get_connected_usb_devices() -> list:
    defaults = app.get_config().get("command-specifications").get("usb-default")

    devices = []

    # Run the lsusb command and capture its output
    result = sp.run(['lsusb'], capture_output=True, text=True)

    # Extract the device names using sed
    device_names = sp.run(['sed', '-E', 's/^.*ID [0-9a-fA-F:]+ +//'], input=result.stdout, capture_output=True,
                          text=True)

    # Store the output in a variable
    device_names_output = numbers_to_strings(device_names.stdout.strip().lower()).split("\n")

    for device in device_names_output:
        if not any(spec in device for spec in defaults):
            # If no word is found, add the phrase to the filtered list
            devices.append(device.replace(".", " ").replace(",", " "))

    return devices


def list_usb(**kwargs) -> None:
    devices = get_connected_usb_devices()
    if len(devices) != 0:
        app.say(f"There are in total {num2words(len(devices))} devices connected. That is a {', and '.join(devices)}")
    else:
        app.say("There aren't any devices connected, sir")


def power_reload(**kwargs) -> None:
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


def power_off(**kwargs) -> None:
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


def update(**kwargs) -> None:
    # Run 'sudo dnf check-update'
    dnf_check = sp.run(["sudo", "dnf", "check-update"], capture_output=True, text=True)

    # Pass the output of the previous command to 'tail -n +3'
    tail_output = sp.run(["tail", "-n", "+3"], input=dnf_check.stdout, capture_output=True, text=True)

    # Pass the output of the 'tail' command to 'wc -l' to count the lines
    wc_output = sp.run(["wc", "-l"], input=tail_output.stdout, capture_output=True, text=True)

    # The final output is the line count
    number_of_lines = wc_output.stdout.strip()

    app.say(f"Updating {num2words(number_of_lines)} packages, sir")

    sp.run(["sudo", "dnf", "update", "--refresh", "--best", "--allowerasing", "-y"])

    app.say("The system was successfully updated")


