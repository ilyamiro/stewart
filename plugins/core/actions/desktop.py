import logging
import os
import shutil
import subprocess as sp
import re
from pathlib import Path as _Path
from api import app

log = logging.getLogger("action: desktop")

WORD_TO_NUM = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "один": "1", "два": "2", "три": "3", "четыре": "4", "пять": "5",
    "шесть": "6", "семь": "7", "восемь": "8", "девять": "9", "десять": "10",
    "первый": "1", "второй": "2", "третий": "3", "четвертый": "4", "пятый": "5",
    "шестой": "6", "седьмой": "7", "восьмой": "8", "девятый": "9", "десятый": "10",
}


def _extract_workspace(text: str) -> str:
    nums = re.findall(r"\d+", text)
    if nums:
        return nums[0]
    for word, num in WORD_TO_NUM.items():
        if word in text.lower():
            return num
    return "+1"


SERP_DISPATCH_PATHS = [
    _Path.home() / ".config/hypr/serp-dispatch.sh",
    _Path.home() / ".config/niri/serp-dispatch.sh",
]


def _get_compositor() -> str:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "hyprland" in desktop:
        return "hyprland"
    if "niri" in desktop:
        return "niri"
    if shutil.which("hyprctl"):
        return "hyprland"
    if shutil.which("niri"):
        return "niri"
    return "other"


def _run_serp(*args) -> bool:
    for script_path in SERP_DISPATCH_PATHS:
        if script_path.exists() and os.access(script_path, os.X_OK):
            try:
                res = sp.run([str(script_path), *args], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
                if res.returncode == 0:
                    return True
            except Exception as e:
                log.debug(f"Failed to execute {script_path}: {e}")

    serp = shutil.which("serpantinum")
    if serp:
        try:
            res = sp.run([serp, *args], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return res.returncode == 0
        except Exception as e:
            log.debug(f"Failed to execute serpantinum: {e}")
    return False


def close_window(**kwargs):
    """
    Closes the active window using Hyprland/Niri compositor calls or Alt+F4 fallback.
    """
    comp = _get_compositor()
    if comp == "hyprland" and shutil.which("hyprctl"):
        sp.run(["hyprctl", "dispatch", "killactive"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        return
    if comp == "niri" and shutil.which("niri"):
        sp.run(["niri", "msg", "action", "close-window"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        return

    # Fallback to hotkey Alt+F4
    if app.keyboard and app.Key:
        try:
            with app.keyboard.pressed(app.Key.alt):
                app.keyboard.tap(app.Key.f4)
            return
        except Exception as e:
            log.warning(f"Fallback close window failed: {e}")
    if shutil.which("xdotool"):
        sp.run(["xdotool", "key", "alt+F4"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def toggle_floating(**kwargs):
    """
    Toggles floating mode for the active window.
    """
    comp = _get_compositor()
    if comp == "hyprland" and shutil.which("hyprctl"):
        sp.run(["hyprctl", "dispatch", "togglefloating"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif comp == "niri" and shutil.which("niri"):
        sp.run(["niri", "msg", "action", "toggle-window-floating"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def toggle_fullscreen(**kwargs):
    """
    Toggles fullscreen mode for the active window.
    """
    comp = _get_compositor()
    if comp == "hyprland" and shutil.which("hyprctl"):
        sp.run(["hyprctl", "dispatch", "fullscreen", "1"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif comp == "niri" and shutil.which("niri"):
        sp.run(["niri", "msg", "action", "fullscreen-window"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def move_window_to_monitor(**kwargs):
    """
    Moves the active window to the other / next monitor.
    """
    direction = kwargs.get("command", {}).parameters.get("direction", "next") if "command" in kwargs else "next"
    comp = _get_compositor()
    if comp == "hyprland" and shutil.which("hyprctl"):
        target = "mon:+1" if direction in ["next", "right"] else "mon:-1"
        sp.run(["hyprctl", "dispatch", "movewindow", target], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif comp == "niri" and shutil.which("niri"):
        action = "move-window-to-monitor-right" if direction in ["next", "right"] else "move-window-to-monitor-left"
        sp.run(["niri", "msg", "action", action], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def switch_workspace(**kwargs):
    """
    Switches to a workspace by number or relative direction.
    """
    params = kwargs.get("command", {}).parameters or {}
    ws = params.get("workspace")
    if not ws:
        ws = _extract_workspace(kwargs.get("context", ""))
    else:
        ws = str(ws)

    comp = _get_compositor()
    if _run_serp("msg", "workspace", ws):
        return
    if comp == "hyprland" and shutil.which("hyprctl"):
        sp.run(["hyprctl", "dispatch", "workspace", ws], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif comp == "niri" and shutil.which("niri"):
        sp.run(["niri", "msg", "action", "focus-workspace", ws], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def move_to_workspace(**kwargs):
    """
    Moves active window to a workspace.
    """
    params = kwargs.get("command", {}).parameters or {}
    ws = params.get("workspace")
    if not ws:
        ws = _extract_workspace(kwargs.get("context", ""))
    else:
        ws = str(ws)

    comp = _get_compositor()
    if _run_serp("msg", "workspace", ws, "move"):
        return
    if comp == "hyprland" and shutil.which("hyprctl"):
        sp.run(["hyprctl", "dispatch", "movetoworkspace", ws], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif comp == "niri" and shutil.which("niri"):
        sp.run(["niri", "msg", "action", "move-window-to-workspace", ws], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def serp_widget(**kwargs):
    """
    Toggles a Serpantinum shell widget (launcher, clipboard, music, calendar, volume, network, system, wallpaper, guide).
    """
    params = kwargs.get("command", {}).parameters or {}
    widget = params.get("widget", "launcher")
    _run_serp("msg", "toggle", widget)


def serp_reload(**kwargs):
    """
    Forces quickshell / Serpantinum shell reload.
    """
    _run_serp("reload")


def screenshot(**kwargs):
    """
    Captures a screenshot (full or interactive area).
    """
    params = kwargs.get("command", {}).parameters or {}
    mode = params.get("mode", "area")

    if mode == "full":
        if _run_serp("screenshot", "--full"):
            return
        if shutil.which("grim"):
            sp.run(["bash", "-c", "grim - | wl-copy"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    else:
        if _run_serp("screenshot"):
            return
        if shutil.which("grim") and shutil.which("slurp"):
            sp.run(["bash", "-c", "grim -g \"$(slurp)\" - | wl-copy"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def lock_session(**kwargs):
    """
    Locks the user session cleanly.
    """
    if _run_serp("lock"):
        return
    if shutil.which("loginctl"):
        sp.run(["loginctl", "lock-session"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def media_control(**kwargs):
    """
    Controls media playback using playerctl (play-pause, next, previous).
    """
    params = kwargs.get("command", {}).parameters or {}
    cmd = params.get("control", "play-pause")
    if shutil.which("playerctl"):
        sp.run(["playerctl", cmd], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
