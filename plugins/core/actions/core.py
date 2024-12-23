import logging
import subprocess as sp
import os
import sys
import time
import webbrowser

import pyautogui
from num2words import num2words

from utils import *
from data.constants import CONFIG_FILE

from api import app

log = logging.getLogger("module: " + __file__)


def subprocess(**kwargs) -> None:
    """
    Runs a command using python subprocess module
    """
    sp.run(
        kwargs["command"].parameters["command"],
        stdout=sp.DEVNULL,
        stderr=sp.STDOUT,
    )


def hotkey(**kwargs) -> None:
    """
    Executes a hotkey using pyautogui backend
    """
    pyautogui.hotkey(*kwargs["command"].parameters["hotkey"])


def key(**kwargs) -> None:
    """
    Presses a key on the keyboard
    """
    pyautogui.press(kwargs["command"].parameters["key"])


def scroll(**kwargs) -> None:
    match kwargs["command"].parameters["way"]:
        case "up":
            mouse.scroll(dy=1, dx=0)
        case "down":
            mouse.scroll(dy=-1, dx=0)


def browser(**kwargs) -> None:
    webbrowser.open(kwargs["command"].parameters["url"])


def get_connected_usb_devices() -> list:
    """
    Fetches the list of connected USB devices, excluding default ones.

    Returns:
        list: A list of connected USB device names.
    """
    defaults = app.get_config().get("plugins", {}).get("core", {}).get("usb-default", [])
    devices = []

    result = sp.run(['lsusb'], capture_output=True, text=True)

    device_names = sp.run(
        ['sed', '-E', 's/^.*ID [0-9a-fA-F:]+ +//'],
        input=result.stdout,
        capture_output=True,
        text=True
    )

    device_names_output = numbers_to_strings(device_names.stdout.strip().lower()).split("\n")

    for device in device_names_output:
        if not any(spec in device for spec in defaults):
            devices.append(device.replace(".", " ").replace(",", " "))

    return devices


def list_usb(**kwargs) -> None:
    """
    Lists connected USB devices using tts
    """
    devices = get_connected_usb_devices()

    if devices:
        count = num2words(len(devices))
        device_list = ', and '.join(devices)
        app.say(f"There are in total {count} devices connected. That is {device_list}.")
    else:
        app.say("There aren't any devices connected, sir.")


def power_reload(**kwargs) -> None:
    """
    Handles system reload based on the specified parameters.
    """
    way = kwargs["command"].parameters["way"]
    context = kwargs["context"]

    if way == "off":
        num = find_num_in_list(context)
        if num:
            minutes = num2words(num, lang="en")
            app.say(f"Computer will be reloaded in {minutes} minutes, sir.")
            os.system(f"shutdown -r -h +{num} /dev/null 2>&1")
        else:
            app.say("System will be reloaded in a minute, sir.")
            os.system(f"sudo shutdown -r -h +1 /dev/null 2>&1")

    elif way == "now":
        app.say("Reloading system immediately, sir.")
        thread = threading.Timer(2.5, os.system, args=["sudo shutdown -r now"])
        thread.start()

    else:
        app.say("System reload was cancelled.")
        os.system("sudo shutdown -c /dev/null 2>&1")


def power_off(**kwargs) -> None:
    """
    Handle system shutdown based on the specified parameters.

    Args:
        kwargs (dict): Contains parameters for shutdown behavior and command details.

    Parameters:
        - kwargs["parameters"]["way"]: The shutdown method ("off", "now", or others to cancel shutdown).
        - kwargs["command"]: The command string, potentially containing the delay in minutes.
    """
    way = kwargs["command"].parameters["way"]
    context = kwargs["context"]

    if way == "off":
        num = find_num_in_list(context)
        if num:
            minutes = num2words(num, lang="en")
            app.say(f"System will shut down in {minutes} minutes, sir.")
            os.system(f"shutdown -h +{num} /dev/null 2>&1")
        else:
            app.say("System will shut down in a minute, sir.")
            os.system("sudo shutdown -h +1 /dev/null 2>&1")
    elif way == "now":
        app.say("Shutting down immediately, sir.")
        thread = threading.Timer(2.5, os.system, args=["sudo shutdown now"])
        thread.start()

    else:
        tts.say("Shutdown was cancelled.")
        os.system("sudo shutdown -c /dev/null 2>&1")


def update(**kwargs) -> None:
    dnf_check = sp.run(["sudo", "dnf", "check-update"], capture_output=True, text=True)
    tail_output = sp.run(["tail", "-n", "+3"], input=dnf_check.stdout, capture_output=True, text=True)
    wc_output = sp.run(["wc", "-l"], input=tail_output.stdout, capture_output=True, text=True)
    number_of_lines = int(wc_output.stdout.strip())

    if number_of_lines == 0:
        app.say("All packages are up to date, sir")
    else:
        app.say(f"Updating {num2words(number_of_lines)} packages, sir")
        sp.run(["sudo", "dnf", "update", "--refresh", "--best", "--allowerasing", "-y"])
        app.say("The system was successfully updated")
