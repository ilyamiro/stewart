import logging
import subprocess as sp
import threading
import os
import shutil
from datetime import datetime
import sys
import time
import webbrowser
from pathlib import Path

from utils import *
from data.constants import CONFIG_FILE, PROJECT_DIR, BEEP_SOUND

from api import app

import_utils(app.lang, globals())

log = logging.getLogger("module: " + __file__)

stopwatch_start_time = None


from typing import Union, List, Optional
from api.commands.actions import BaseAction, ActionParameters, ActionResult, ExecutionContext, Field

# =====================================================================
# Input & Desktop Actions
# =====================================================================

class TypingParams(ActionParameters):
    context: str = Field(default="", description="Text to type into active application")


class TypingAction(BaseAction):
    name = "typing"
    description = "Types specified text from context into the currently focused application."
    parameters_schema = TypingParams
    category = "input"
    sample_phrases = ["type hello world", "enter text"]
    requires_context = True

    def execute(self, params: TypingParams, ctx: ExecutionContext) -> ActionResult:
        text = params.context or ctx.context
        if not text:
            return ActionResult(success=False, error="No text provided to type")
        ok = ctx.desktop.type_text(text)
        return ActionResult(success=ok)


class SubprocessParams(ActionParameters):
    command: Union[List[str], str] = Field(default="", description="Command or arguments list to execute, e.g. ['nautilus'] or ['kitty']")
    context: str = Field(default="", description="Optional context or target name")


class SubprocessAction(BaseAction):
    name = "subprocess"
    description = "Launches an application or runs an external desktop command."
    parameters_schema = SubprocessParams
    category = "system"
    sample_phrases = ["open terminal", "launch file manager", "open browser"]

    def execute(self, params: SubprocessParams, ctx: ExecutionContext) -> ActionResult:
        cmd = params.command
        if not cmd and hasattr(params, "subprocess"):
            cmd = getattr(params, "subprocess")
        if not cmd:
            return ActionResult(success=False, error="No command specified")
        ok = ctx.desktop.launch_app(cmd)
        return ActionResult(success=ok)


class ClickParams(ActionParameters):
    button: str = Field(default="left", description="Mouse button to click ('left' or 'right')")


class ClickAction(BaseAction):
    name = "click"
    description = "Performs a mouse click with the specified button."
    parameters_schema = ClickParams
    category = "input"
    sample_phrases = ["mouse click", "click left", "right click"]

    def execute(self, params: ClickParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.mouse_click(params.button)
        return ActionResult(success=ok)


class HotkeyParams(ActionParameters):
    hotkey: List[str] = Field(default_factory=list, description="Keys to press simultaneously, e.g. ['ctrl', 'w']")
    xdotool: bool = Field(default=False, description="Whether to force using xdotool delay")


class HotkeyAction(BaseAction):
    name = "hotkey"
    description = "Executes a keyboard hotkey combination."
    parameters_schema = HotkeyParams
    category = "input"
    sample_phrases = ["close tab", "copy text", "paste clipboard"]

    def execute(self, params: HotkeyParams, ctx: ExecutionContext) -> ActionResult:
        keys = params.hotkey
        if not keys and hasattr(params, "keys"):
            keys = getattr(params, "keys")
        if not keys:
            return ActionResult(success=False, error="No hotkey keys specified")
        ok = ctx.desktop.send_hotkey(keys, use_xdotool_delay=params.xdotool)
        return ActionResult(success=ok)


class KeyParams(ActionParameters):
    key: str = Field(default="", description="Single keyboard key to tap, e.g. 'space', 'k', 'enter'")


class KeyAction(BaseAction):
    name = "key"
    description = "Presses a single key on the keyboard."
    parameters_schema = KeyParams
    category = "input"
    sample_phrases = ["press enter", "tap space"]

    def execute(self, params: KeyParams, ctx: ExecutionContext) -> ActionResult:
        if not params.key:
            return ActionResult(success=False, error="No key specified")
        ok = ctx.desktop.tap_key(params.key)
        return ActionResult(success=ok)


class ScrollParams(ActionParameters):
    way: str = Field(default="up", description="Direction to scroll: 'up' or 'down'")
    amount: int = Field(default=10, description="Scroll amount")


class ScrollAction(BaseAction):
    name = "scroll"
    description = "Scrolls the mouse wheel up or down."
    parameters_schema = ScrollParams
    category = "input"
    sample_phrases = ["scroll up", "scroll down"]

    def execute(self, params: ScrollParams, ctx: ExecutionContext) -> ActionResult:
        ok = ctx.desktop.mouse_scroll(direction=params.way, amount=params.amount)
        return ActionResult(success=ok)


class BrowserParams(ActionParameters):
    url: str = Field(default="", description="URL to open in the default web browser")


class BrowserAction(BaseAction):
    name = "browser"
    description = "Opens a URL in the user's default web browser."
    parameters_schema = BrowserParams
    category = "web"
    sample_phrases = ["open website", "browse to google"]

    def execute(self, params: BrowserParams, ctx: ExecutionContext) -> ActionResult:
        if not params.url:
            return ActionResult(success=False, error="No URL specified")
        ok = ctx.desktop.open_url(params.url)
        return ActionResult(success=ok)


# Callable module-level instances for backward compatibility
typing = TypingAction()
subprocess = SubprocessAction()
click = ClickAction()
hotkey = HotkeyAction()
key = KeyAction()
scroll = ScrollAction()
browser = BrowserAction()


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
        app.say(
            app.localeService.translate("core", "core.list_usb.total_connected", count=count, device_list=device_list))
    else:
        app.say(app.localeService.translate("core", "core.list_usb.no_connected"))


def power_reload(**kwargs) -> None:
    """
    Handles system reload based on the specified parameters.
    """
    way = kwargs["command"].parameters["way"]

    if way == "off":
        results = find_num(kwargs["context"])
        num = results[0] if results else None

        if num:
            minutes = num2words(num, lang="en")
            app.say(app.localeService.translate("core", "core.power_reload.x_minutes", minutes=minutes))
            if shutil.which("shutdown"):
                sp.run(["shutdown", "-r", f"+{num}"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif shutil.which("systemctl"):
                sp.run(["systemctl", "reboot"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        else:
            app.say(app.localeService.translate("core", "core.power_reload.one_minute"))
            if shutil.which("shutdown"):
                sp.run(["shutdown", "-r", "+1"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif shutil.which("systemctl"):
                sp.run(["systemctl", "reboot"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    elif way == "now":
        app.say(app.localeService.translate("core", "core.power_reload.now"))
        def _do_reboot():
            if shutil.which("systemctl"):
                sp.run(["systemctl", "reboot"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            else:
                sp.run(["shutdown", "-r", "now"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        thread = threading.Timer(2.5, _do_reboot)
        thread.start()

    else:
        app.say(app.localeService.translate("core", "core.power_reload.cancel"))
        if shutil.which("shutdown"):
            sp.run(["shutdown", "-c"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def power_off(**kwargs) -> None:
    way = kwargs["command"].parameters["way"]

    if way == "off":
        results = find_num(kwargs["context"])
        num = results[0] if results else None

        if num:
            minutes = num2words(num, lang="en")
            app.say(app.localeService.translate("core", "core.power_off.x_minutes", minutes=minutes))
            if shutil.which("shutdown"):
                sp.run(["shutdown", "-h", f"+{num}"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif shutil.which("systemctl"):
                sp.run(["systemctl", "poweroff"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        else:
            app.say(app.localeService.translate("core", "core.power_off.one_minute"))
            if shutil.which("shutdown"):
                sp.run(["shutdown", "-h", "+1"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif shutil.which("systemctl"):
                sp.run(["systemctl", "poweroff"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    elif way == "now":
        app.say(app.localeService.translate("core", "core.power_off.now"))
        def _do_poweroff():
            if shutil.which("systemctl"):
                sp.run(["systemctl", "poweroff"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            else:
                sp.run(["shutdown", "-h", "now"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        thread = threading.Timer(2.5, _do_poweroff)
        thread.start()

    else:
        app.say(app.localeService.translate("core", "core.power_off.cancel"))
        if shutil.which("shutdown"):
            sp.run(["shutdown", "-c"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def update(**kwargs) -> None:
    config = app.get_config()
    custom_update = config.get("system", {}).get("update_command")
    if custom_update:
        app.say("Starting system update.")
        if isinstance(custom_update, str):
            sp.run(custom_update, shell=True)
        else:
            sp.run(custom_update)
        app.say("System update completed.")
        return

    # NixOS
    if shutil.which("nixos-rebuild"):
        app.say("NixOS detected. Please run nixos-rebuild switch to update your system.")
        return

    # Fedora / RHEL
    if shutil.which("dnf"):
        dnf_check = sp.run(["dnf", "check-update"], capture_output=True, text=True)
        lines = [l for l in dnf_check.stdout.splitlines() if l.strip() and not l.startswith("Last metadata")]
        number_of_lines = len(lines)

        if number_of_lines == 0:
            app.say(app.localeService.translate("core", "core.update.no_update"))
        else:
            app.say(app.localeService.translate("core", "core.update.update_before"),
                    number_of_lines=num2words(number_of_lines, app.lang))
            sp.run(["sudo", "dnf", "update", "--refresh", "--best", "--allowerasing", "-y"])
            app.say(app.localeService.translate("core", "core.update.update_after"))
        return

    # Debian / Ubuntu
    if shutil.which("apt"):
        app.say("Updating package lists.")
        sp.run(["sudo", "apt", "update"])
        sp.run(["sudo", "apt", "upgrade", "-y"])
        app.say("System update completed.")
        return

    # Arch
    if shutil.which("pacman"):
        app.say("Updating Arch packages.")
        sp.run(["sudo", "pacman", "-Syu", "--noconfirm"])
        app.say("System update completed.")
        return

    app.say("No supported package manager found to update the system.")


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

    hour_words = num2words(hour, to='cardinal',
                           lang=app.localeService.translate("core", "core.tell_time.num2words_lang"))
    minute_words = num2words(minute, to='cardinal',
                             lang=app.localeService.translate("core", "core.tell_time.num2words_lang"))

    phrases = [
        app.localeService.translate("core", "core.tell_time.variant_1", hour_words=hour_words,
                                    minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_2", hour_words=hour_words,
                                    minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_3", hour_words=hour_words,
                                    minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_4", hour_words=hour_words,
                                    minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_5", hour_words=hour_words,
                                    minute_words=minute_words),
        app.localeService.translate("core", "core.tell_time.variant_6", hour_words=hour_words,
                                    minute_words=minute_words)
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


def _find_battery():
    base = Path("/sys/class/power_supply")
    if base.exists():
        for p in base.iterdir():
            if (p / "capacity").exists() and (p / "status").exists():
                return p / "capacity", p / "status"
    return None, None


def battery(**kwargs):
    battery_path, charging_path = _find_battery()
    if not battery_path or not charging_path:
        app.say("No battery detected or unable to read battery information.")
        return

    try:
        with open(battery_path, "r") as f:
            percentage = int(f.read().strip())

        with open(charging_path, "r") as f:
            status = f.read().strip()

        word_percent = num2words(percentage, lang=app.lang)

        if status.lower() == "charging":
            if percentage >= 80:
                app.say(
                    f"Your laptop is charging and already at {word_percent} percent. You might consider unplugging soon.")
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
                app.say(
                    f"Warning! Your battery is critically low at {word_percent} percent. Plug in your charger immediately!")
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
        beep_file = str(BEEP_SOUND) if Path(BEEP_SOUND).exists() else f"{PROJECT_DIR}/data/sounds/beep.wav"
        for i in range(6):
            if os.path.exists(beep_file):
                app.audio.play(beep_file)
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
    way = kwargs["command"].parameters.get("way", "on")

    # Try brightnessctl first
    if shutil.which("brightnessctl"):
        val = "100%" if way == "on" else "0%"
        res = sp.run(["brightnessctl", "--device=*kbd_backlight*", "set", val], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        if res.returncode == 0:
            return

    # Fallback to sysfs search
    base = Path("/sys/class/leds")
    if base.exists():
        for p in base.iterdir():
            if "kbd_backlight" in p.name:
                b_file = p / "brightness"
                max_file = p / "max_brightness"
                max_val = "3"
                if max_file.exists():
                    try:
                        max_val = max_file.read_text().strip()
                    except Exception:
                        pass
                val = max_val if way == "on" else "0"
                try:
                    b_file.write_text(f"{val}\n")
                except PermissionError:
                    sp.run(["sudo", "tee", str(b_file)], input=f"{val}\n", text=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
                return