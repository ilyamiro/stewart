import logging
import subprocess as sp
import threading
import os
from datetime import datetime
import sys
import time
import webbrowser

from utils import *
from data.constants import CONFIG_FILE, PROJECT_DIR

from api import app

import_utils(app.lang, globals())

log = logging.getLogger("module: " + __file__)

stopwatch_start_time = None


def typing(**kwargs) -> None:
    """
    Types a specified text from the context
    """
    app.keyboard.type(kwargs["context"])


def subprocess(**kwargs) -> None:
    """
    Runs a command using python subprocess module
    """
    sp.run(
        kwargs["command"].parameters["command"],
        stdout=sp.DEVNULL,
        stderr=sp.STDOUT,
    )


def click(**kwargs) -> None:
    app.mouse.click(app.MouseButton.left)


def hotkey(**kwargs) -> None:
    """
    Executes a hotkey using xdotool or pynput backend
    """
    key_list = kwargs["command"].parameters["hotkey"]
    if kwargs["command"].parameters.get("xdotool"):
        run("xdotool", "key", "--delay", "0", "+".join(key_list))
    else:
        key_objects = []
        for k in key_list:
            try:
                key_obj = getattr(app.Key, k)
            except AttributeError:
                key_obj = k
            key_objects.append(key_obj)

        for name in key_objects:
            app.keyboard.press(name)

        for name in reversed(key_objects):
            app.keyboard.release(name)


def key(**kwargs) -> None:
    """
    Presses a key on the keyboard
    """
    name = kwargs["command"].parameters["key"]
    run("xdotool", "key", name)


def scroll(**kwargs) -> None:
    match kwargs["command"].parameters["way"]:
        case "up":
            app.mouse.scroll(dy=10, dx=0)
        case "down":
            app.mouse.scroll(dy=-10, dx=0)


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
        app.say(app.localeService.translate("core", "core.list_usb.total_connected", count=count, device_list=device_list))
    else:
        app.say(app.localeService.translate("core", "core.list_usb.no_connected"))


def power_reload(**kwargs) -> None:
    """
    Handles system reload based on the specified parameters.
    """
    way = kwargs["command"].parameters["way"]

    if way == "off":
        results = find_num(kwargs["context"])
        if results:
            num = results[0]
        else:
            num = None

        if num:
            minutes = num2words(num, lang="en")
            app.say(app.localeService.translate("core", "core.power_reload.x_minutes", minutes=minutes))
            os.system(f"shutdown -r -h +{num} /dev/null 2>&1")
        else:
            app.say(app.localeService.translate("core", "core.power_reload.one_minute"))
            os.system(f"sudo shutdown -r -h +1 /dev/null 2>&1")

    elif way == "now":
        app.say(app.localeService.translate("core", "core.power_reload.now"))
        thread = threading.Timer(2.5, os.system, args=["sudo shutdown -r now"])
        thread.start()

    else:
        app.say(app.localeService.translate("core", "core.power_reload.cancel"))
        os.system("sudo shutdown -c /dev/null 2>&1")


def power_off(**kwargs) -> None:
    way = kwargs["command"].parameters["way"]

    if way == "off":
        results = find_num(kwargs["context"])
        if results:
            num = results[0]
        else:
            num = None

        if num:
            minutes = num2words(num, lang="en")
            app.say(app.localeService.translate("core", "core.power_off.x_minutes", minutes=minutes))
            sp.run(["sudo", "shutdown", "-h", f"+{num}"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        else:
            app.say(app.localeService.translate("core", "core.power_off.one_minute"))
            sp.run(["sudo", "shutdown", "-h", "+1"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    elif way == "now":
        app.say(app.localeService.translate("core", "core.power_off.now"))
        thread = threading.Timer(2.5, lambda: sp.run(["sudo", "shutdown", "now"]))
        thread.start()

    else:
        tts.say(app.localeService.translate("core", "core.power_off.cancel"))
        sp.run(["sudo", "shutdown", "-c"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def update(**kwargs) -> None:
    dnf_check = sp.run(["sudo", "dnf", "check-update"], capture_output=True, text=True)
    tail_output = sp.run(["tail", "-n", "+3"], input=dnf_check.stdout, capture_output=True, text=True)
    wc_output = sp.run(["wc", "-l"], input=tail_output.stdout, capture_output=True, text=True)
    number_of_lines = int(wc_output.stdout.strip())

    if number_of_lines == 0:
        app.say(app.localeService.translate("core", "core.update.no_update"))
    else:
        app.say(app.localeService.translate("core", "core.update.update_before"), number_of_lines=num2words(number_of_lines, app.lang))
        sp.run(["sudo", "dnf", "update", "--refresh", "--best", "--allowerasing", "-y"])
        app.say(app.localeService.translate("core", "core.update.update_after"))


def brightness(**kwargs):
    results = find_num(kwargs["context"])
    num = results[0] if results else None

    command = kwargs["command"].parameters["command"]

    try:
        # Get brightnessctl output and parse percentage in Python
        output = sp.check_output(
            ["brightnessctl"],
            text=True
        )
        match = re.search(r"\((\d+)%\)", output)
        if not match:
            log.error("Could not parse brightness percentage from brightnessctl output.")
            return
        current = int(match.group(1))
    except Exception as e:
        log.error(f"Failed to get current brightness: {e}")
        return

    adjustment = num if num is not None else 25  # Default step

    if command == "set" and num is not None:
        try:
            sp.run(
                ["brightnessctl", "set", f"{num}%"],
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL
            )
            log.info(f"Set brightness to {num}%")
        except Exception as e:
            log.error(f"Failed to set brightness: {e}")
    else:
        new_brightness = max(0, min(100, current + adjustment if command == "up" else current - adjustment))
        try:
            sp.run(
                ["brightnessctl", "set", f"{new_brightness}%"],
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL
            )
            log.info(f"Set brightness to {new_brightness}%")
        except Exception as e:
            log.error(f"Failed to adjust brightness: {e}")


def tell_time(**kwargs):
    s = time.time()

    now = datetime.now()
    hour = now.hour
    minute = now.minute

    hour_words = num2words(hour, to='cardinal', lang=app.localeService.translate("core", "core.tell_time.num2words_lang"))
    minute_words = num2words(minute, to='cardinal', lang=app.localeService.translate("core", "core.tell_time.num2words_lang"))

    phrases = [
        app.localeService.translate("core", "core.tell_time.variant_1", hour_words=hour_words, minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_2", hour_words=hour_words, minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_3", hour_words=hour_words, minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_4", hour_words=hour_words, minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_5", hour_words=hour_words, minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_6", hour_words=hour_words, minute_words=minute_words)
    ]

    app.say(random.choice(phrases))


def tell_day(**kwargs):
    now = datetime.now()
    day_of_week = app.localeService.translate("core", f"core.tell_day.mapping.{now.strftime('%A')}")

    phrases = [
        app.localeService.translate("core", "core.tell_day.variant_1", day_of_week=day_of_week),
        app.localeService.translate("core", "core.tell_day.variant_2", day_of_week=day_of_week),
        app.localeService.translate("core", "core.tell_day.variant_3", day_of_week=day_of_week),
        app.localeService.translate("core", "core.tell_day.variant_4", day_of_week=day_of_week),
        app.localeService.translate("core", "core.tell_day.variant_5", day_of_week=day_of_week),
        app.localeService.translate("core", "core.tell_day.variant_6", day_of_week=day_of_week)
    ]

    app.say(random.choice(phrases))


def tell_month(**kwargs):
    now = datetime.now()
    month = app.localeService.translate("core", f"core.tell_month.mapping.{now.strftime('%B')}")

    phrases = [
        app.localeService.translate("core", "core.tell_month.variant_1", month=month),
        app.localeService.translate("core", "core.tell_month.variant_2", month=month),
        app.localeService.translate("core", "core.tell_month.variant_3", month=month),
        app.localeService.translate("core", "core.tell_month.variant_4", month=month),
    ]

    app.say(random.choice(phrases))


def battery(**kwargs):
    battery_path = "/sys/class/power_supply/BAT0/capacity"
    charging_path = "/sys/class/power_supply/BAT0/status"

    try:
        with open(battery_path, "r") as f:
            percentage = int(f.read().strip())

        with open(charging_path, "r") as f:
            status = f.read().strip()
            
        word_percent = num2words(percentage, lang=app.lang)

        if status.lower() == "charging":
            if percentage >= 80:
                app.say(f"Your laptop is charging and already at {word_percent} percent. You might consider unplugging soon.")
            elif percentage >= 50:
                app.say(f"Your laptop is charging and currently at {word_percent} percent. Keep it plugged in for now.")
            else:
                app.say(f"Your laptop is charging and only at {word_percent} percent. Let it charge longer.")
        else:  # Not charging
            if percentage >= 80:
                app.say(f"Your battery is at {word_percent} percent. You're good to go!")
            elif percentage >= 50:
                app.say(f"Your battery is at {word_percent} percent. You might want to charge it soon.")
            elif percentage >= 20:
                app.say(f"Your battery is getting low at {word_percent} percent. Please find a charger.")
            else:
                app.say(f"Warning! Your battery is critically low at {word_percent} percent. Plug in your charger immediately!")
    except FileNotFoundError:
        app.say("No battery detected or unable to read battery information.")


def timer(**kwargs):
    """
    Extracts multiple numbers from kwargs["context"] (e.g., hours, minutes, and seconds)
    and creates a timer for the total time in seconds.
    Handles cases where 'hours', 'minutes', and 'seconds' are all mentioned.
    """
    context = kwargs.get("context", "")

    time_values = find_num(context)

    if not time_values:
        app.say("I couldn't find any time specifications in your request. Please try again.")
        return

    hours = 0
    minutes = 0
    seconds = 0

    context_lower = context.lower()

    if "hour" in context_lower or "hours" in context_lower:
        hours = time_values[0] if len(time_values) > 0 else 0

    if "minute" in context_lower or "minutes" in context_lower:
        if hours == 0:
            minutes = time_values[0] if len(time_values) > 0 else 0
        else:
            minutes = time_values[1] if len(time_values) > 1 else 0

    if "second" in context_lower or "seconds" in context_lower:
        if minutes == 0 and hours == 0:
            seconds = time_values[0] if len(time_values) > 0 else 0
        else:
            seconds = time_values[-1] if len(time_values) > 1 else 0

    total_seconds = (hours * 3600) + (minutes * 60) + seconds

    readable_time = seconds_readable(total_seconds)

    app.say(f"Starting a timer for {readable_time}.")

    def countdown():
        time.sleep(total_seconds)
        app.say(f"Timer is up!. Your {readable_time} are over.")
        for i in range(6):
            app.audio.play(f"{PROJECT_DIR}/data/sounds/beep.wav")
            app.audio.player.wait_for_playback()

    threading.Thread(target=countdown, daemon=True).start()


def stopwatch(**kwargs):
    global stopwatch_start_time

    if kwargs["command"].parameters["way"] == "on":
        stopwatch_start_time = time.time()
    elif kwargs["command"].parameters["way"] == "off":
        if stopwatch_start_time is not None:
            to_read = seconds_readable(time.time() - stopwatch_start_time)
            print(to_read)
            app.say(numbers_to_strings(to_read) + " have passed, sir")
            stopwatch_start_time = None
        else:
            app.say("The stopwatch was not started yet, sir")


def backlight(**kwargs):
    sp.run(
        ["sudo", "tee", "/sys/class/leds/asus::kbd_backlight/brightness"],
        input="3\n" if kwargs["command"].parameters["way"] == "on" else "0\n",
        text=True
    )