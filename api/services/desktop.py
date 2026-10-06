import os
import re
import shutil
import logging
import threading
import webbrowser
import subprocess as sp
from pathlib import Path
from typing import List, Optional, Union, Dict, Any

log = logging.getLogger("service: desktop")

SERP_DISPATCH_PATHS = [
    Path.home() / ".config/hypr/serp-dispatch.sh",
    Path.home() / ".config/niri/serp-dispatch.sh",
]


class DesktopService:
    """
    Hardware and Desktop Compatibility Layer for Stewart.
    Decouples user intent from specific Wayland compositors (Hyprland, Niri, Sway),
    X11 utilities (xdotool), shell frameworks (Serpantinum), and input backends (pynput).
    """

    def __init__(self, api=None):
        self.api = api

    # ---------------------------------------------------------
    # Compositor & Shell Detection
    # ---------------------------------------------------------
    def get_compositor(self) -> str:
        """Identifies active Wayland compositor or desktop environment."""
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            return "hyprland"
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "hyprland" in desktop:
            return "hyprland"
        if "niri" in desktop:
            return "niri"
        if "sway" in desktop:
            return "sway"
        if shutil.which("hyprctl"):
            return "hyprland"
        if shutil.which("niri"):
            return "niri"
        return "other"

    def run_serp(self, *args) -> bool:
        """Executes a command through Serpantinum dispatch scripts or binary."""
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

    @staticmethod
    def extract_workspace(text: str) -> str:
        """
        Extracts workspace number from text using digits, modules.words2num,
        or localized number finders.
        """
        nums = re.findall(r"\d+", text)
        if nums:
            return nums[0]

        # Use modules.words2num for spoken number words
        words = text.strip().split()
        for word in words:
            clean = re.sub(r"[^a-zA-Z]", "", word).lower()
            if clean:
                try:
                    from modules.words2num import w2n
                    return str(w2n(clean))
                except Exception:
                    pass

        # Check Russian language number parsing if applicable
        try:
            from utils.lang.ru import find_num
            ru_nums = find_num(text)
            if ru_nums:
                return str(ru_nums[0])
        except Exception:
            pass

        return "+1"

    # ---------------------------------------------------------
    # Window Management
    # ---------------------------------------------------------
    def close_active_window(self) -> bool:
        """Closes the currently focused active window."""
        comp = self.get_compositor()
        if comp == "hyprland" and shutil.which("hyprctl"):
            sp.run(["hyprctl", "dispatch", "killactive"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if comp == "niri" and shutil.which("niri"):
            sp.run(["niri", "msg", "action", "close-window"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True

        # Keyboard fallback (Alt+F4)
        if self.api and getattr(self.api, "keyboard", None) and getattr(self.api, "Key", None):
            try:
                with self.api.keyboard.pressed(self.api.Key.alt):
                    self.api.keyboard.tap(self.api.Key.f4)
                return True
            except Exception as e:
                log.warning(f"Fallback close window via pynput failed: {e}")

        if shutil.which("xdotool"):
            sp.run(["xdotool", "key", "alt+F4"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True

        return False

    def toggle_floating(self) -> bool:
        """Toggles floating state for the active window."""
        comp = self.get_compositor()
        if comp == "hyprland" and shutil.which("hyprctl"):
            sp.run(["hyprctl", "dispatch", "togglefloating"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if comp == "niri" and shutil.which("niri"):
            sp.run(["niri", "msg", "action", "toggle-window-floating"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    def toggle_fullscreen(self) -> bool:
        """Toggles fullscreen state for the active window."""
        comp = self.get_compositor()
        if comp == "hyprland" and shutil.which("hyprctl"):
            sp.run(["hyprctl", "dispatch", "fullscreen", "1"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if comp == "niri" and shutil.which("niri"):
            sp.run(["niri", "msg", "action", "fullscreen-window"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    def move_window_to_monitor(self, direction: str = "next") -> bool:
        """Moves active window to next/previous monitor."""
        comp = self.get_compositor()
        is_right = direction.lower() in ["next", "right"]
        if comp == "hyprland" and shutil.which("hyprctl"):
            target = "mon:+1" if is_right else "mon:-1"
            sp.run(["hyprctl", "dispatch", "movewindow", target], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if comp == "niri" and shutil.which("niri"):
            action = "move-window-to-monitor-right" if is_right else "move-window-to-monitor-left"
            sp.run(["niri", "msg", "action", action], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    def switch_workspace(self, workspace: str) -> bool:
        """Switches desktop viewport to given workspace."""
        if self.run_serp("msg", "workspace", str(workspace)):
            return True
        comp = self.get_compositor()
        if comp == "hyprland" and shutil.which("hyprctl"):
            sp.run(["hyprctl", "dispatch", "workspace", str(workspace)], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if comp == "niri" and shutil.which("niri"):
            sp.run(["niri", "msg", "action", "focus-workspace", str(workspace)], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    def move_to_workspace(self, workspace: str) -> bool:
        """Moves active window to given workspace."""
        if self.run_serp("msg", "workspace", str(workspace), "move"):
            return True
        comp = self.get_compositor()
        if comp == "hyprland" and shutil.which("hyprctl"):
            sp.run(["hyprctl", "dispatch", "movetoworkspace", str(workspace)], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if comp == "niri" and shutil.which("niri"):
            sp.run(["niri", "msg", "action", "move-window-to-workspace", str(workspace)], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    # ---------------------------------------------------------
    # Shell & System Session
    # ---------------------------------------------------------
    def toggle_widget(self, widget: str = "launcher") -> bool:
        """Toggles a shell widget (e.g. launcher, clipboard, music, calendar)."""
        return self.run_serp("msg", "toggle", widget)

    def reload_shell(self) -> bool:
        """Forces quickshell / Serpantinum shell reload."""
        return self.run_serp("reload")

    def screenshot(self, mode: str = "area") -> bool:
        """Takes a screenshot and copies it to clipboard."""
        if mode == "full":
            if self.run_serp("screenshot", "--full"):
                return True
            if shutil.which("grim"):
                sp.run(["bash", "-c", "grim - | wl-copy"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
                return True
        else:
            if self.run_serp("screenshot"):
                return True
            if shutil.which("grim") and shutil.which("slurp"):
                sp.run(["bash", "-c", "grim -g \"$(slurp)\" - | wl-copy"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
                return True
        return False

    def lock_session(self) -> bool:
        """Locks the active session cleanly."""
        if self.run_serp("lock"):
            return True
        if shutil.which("loginctl"):
            sp.run(["loginctl", "lock-session"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    # ---------------------------------------------------------
    # Input Automation (Keyboard, Mouse, Typing)
    # ---------------------------------------------------------
    def get_system_layout(self) -> str:
        """Queries localectl for current system X11 keyboard layout."""
        try:
            result = sp.run(["localectl", "status"], stdout=sp.PIPE, text=True, check=True)
            for line in result.stdout.splitlines():
                if "X11 Layout:" in line:
                    return line.split(":", 1)[1].strip()
            return "us"
        except Exception:
            return "us"

    def set_xwayland_layout(self, layout: str) -> None:
        """Syncs XWayland layout to ensure proper character typing."""
        if shutil.which("setxkbmap") and os.environ.get("DISPLAY"):
            try:
                sp.run(["setxkbmap", layout], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            except Exception:
                pass

    def send_hotkey(self, keys: List[str], use_xdotool_delay: bool = False) -> bool:
        """Presses and releases a combination of keys."""
        if keys == ["shift", "n"] and shutil.which("playerctl"):
            sp.run(["playerctl", "next"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True

        if use_xdotool_delay and shutil.which("xdotool"):
            sp.run(["xdotool", "key", "--delay", "0", "+".join(keys)], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True

        keyboard = getattr(self.api, "keyboard", None)
        key_class = getattr(self.api, "Key", None)
        if keyboard and key_class:
            try:
                key_objects = []
                for k in keys:
                    try:
                        key_obj = getattr(key_class, k)
                    except AttributeError:
                        key_obj = k
                    key_objects.append(key_obj)

                for name in key_objects:
                    keyboard.press(name)
                for name in reversed(key_objects):
                    keyboard.release(name)
                return True
            except Exception as e:
                log.debug(f"pynput hotkey failed: {e}")

        if shutil.which("xdotool"):
            sp.run(["xdotool", "key", "--delay", "0", "+".join(keys)], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    def tap_key(self, key_name: str) -> bool:
        """Taps a single key."""
        if key_name in ["k", "space"] and shutil.which("playerctl"):
            sp.run(["playerctl", "play-pause"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True

        if shutil.which("xdotool"):
            sp.run(["xdotool", "key", key_name], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True

        keyboard = getattr(self.api, "keyboard", None)
        if keyboard:
            try:
                keyboard.tap(key_name)
                return True
            except Exception as e:
                log.debug(f"pynput key tap failed: {e}")
        return False

    def type_text(self, text: str) -> bool:
        """Types raw text into the focused application."""
        if not text:
            return False
        layout = self.get_system_layout()
        self.set_xwayland_layout(layout)

        keyboard = getattr(self.api, "keyboard", None)
        if keyboard:
            try:
                keyboard.type(text)
                return True
            except Exception as e:
                log.debug(f"pynput typing failed: {e}")

        if shutil.which("wtype"):
            sp.run(["wtype", text], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if shutil.which("ydotool"):
            sp.run(["ydotool", "type", text], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        if shutil.which("wl-copy"):
            sp.run(["wl-copy", text], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    def mouse_click(self, button: str = "left") -> bool:
        """Performs a mouse click."""
        mouse = getattr(self.api, "mouse", None)
        mouse_button = getattr(self.api, "MouseButton", None)
        if mouse and mouse_button:
            try:
                btn = mouse_button.right if button == "right" else mouse_button.left
                mouse.click(btn)
                return True
            except Exception as e:
                log.debug(f"pynput click failed: {e}")
        return False

    def mouse_scroll(self, direction: str = "up", amount: int = 10) -> bool:
        """Scrolls the mouse wheel."""
        mouse = getattr(self.api, "mouse", None)
        if mouse:
            try:
                dy = amount if direction == "up" else -amount
                mouse.scroll(dy=dy, dx=0)
                return True
            except Exception as e:
                log.debug(f"pynput scroll failed: {e}")
        return False

    # ---------------------------------------------------------
    # Applications, Browsing & Media
    # ---------------------------------------------------------
    def launch_app(self, command: Union[str, List[str]], detached: bool = True) -> bool:
        """Launches a desktop application in detached background mode."""
        try:
            cmd = command if isinstance(command, list) else command.split()
            if detached:
                sp.Popen(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, start_new_session=True)
            else:
                sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        except Exception as e:
            log.error(f"Failed to launch application '{command}': {e}")
            return False

    def open_url(self, url: str) -> bool:
        """Opens a URL in the user's default browser."""
        try:
            return webbrowser.open(url)
        except Exception as e:
            log.error(f"Failed to open URL '{url}': {e}")
            return False

    def media_control(self, action: str = "play-pause") -> bool:
        """Dispatches media playback controls via playerctl."""
        if shutil.which("playerctl"):
            sp.run(["playerctl", action], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    # ---------------------------------------------------------
    # Power Actions
    # ---------------------------------------------------------
    def power_off(self, delay_minutes: Optional[int] = None) -> bool:
        """Powers down system immediately or schedules shutdown."""
        if delay_minutes is None:
            if shutil.which("systemctl"):
                sp.run(["systemctl", "poweroff"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            else:
                sp.run(["shutdown", "-h", "now"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        else:
            if shutil.which("shutdown"):
                sp.run(["shutdown", "-h", f"+{delay_minutes}"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif shutil.which("systemctl"):
                sp.run(["systemctl", "poweroff"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        return True

    def power_reload(self, delay_minutes: Optional[int] = None) -> bool:
        """Reboots system immediately or schedules reboot."""
        if delay_minutes is None:
            if shutil.which("systemctl"):
                sp.run(["systemctl", "reboot"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            else:
                sp.run(["shutdown", "-r", "now"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        else:
            if shutil.which("shutdown"):
                sp.run(["shutdown", "-r", f"+{delay_minutes}"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif shutil.which("systemctl"):
                sp.run(["systemctl", "reboot"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        return True

    def get_active_window(self) -> Dict[str, Any]:
        """Returns JSON info of currently focused window via hyprctl."""
        if shutil.which("hyprctl"):
            try:
                res = sp.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=1.0)
                if res.returncode == 0 and res.stdout.strip():
                    import json
                    return json.loads(res.stdout)
            except Exception:
                pass
        return {}

    def focus_window(self, name: str) -> bool:
        """Focuses window matching name/class."""
        if shutil.which("hyprctl"):
            res = sp.run(["hyprctl", "dispatch", "focuswindow", name], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return res.returncode == 0
        return False

    def open_file(self, path: str) -> bool:
        """Opens file with default handler via xdg-open."""
        expanded = os.path.expanduser(os.path.expandvars(path))
        if shutil.which("xdg-open"):
            sp.Popen(["xdg-open", expanded], stdout=sp.DEVNULL, stderr=sp.DEVNULL, start_new_session=True)
            return True
        return False

    def set_brightness(self, command: str = "set", value: Optional[str] = None) -> bool:
        """Adjusts brightness via brightnessctl or serpantinum."""
        val = value or "50%"
        if not val.endswith("%") and not val.endswith("-") and not val.startswith("+"):
            val = f"{val}%"
        if shutil.which("brightnessctl"):
            if command == "set":
                arg = val
            elif command == "up":
                arg = f"+{val}" if not val.startswith("+") else val
            elif command == "down":
                clean = val.replace("%", "").replace("-", "")
                arg = f"{clean}%-"
            else:
                arg = val
            sp.run(["brightnessctl", "set", arg], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False

    def set_volume(self, command: str = "set", value: Optional[str] = None) -> bool:
        """Adjusts volume via wpctl (PipeWire) or pactl (PulseAudio)."""
        val = value or "50%"
        clean_num = "".join(c for c in val if c.isdigit())
        num = int(clean_num) if clean_num else 50
        if shutil.which("wpctl"):
            if command == "mute":
                sp.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "unmute":
                sp.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "up":
                sp.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{num}%+"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "down":
                sp.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{num}%-"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "set":
                sp.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{num}%"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        elif shutil.which("pactl"):
            if command == "mute":
                sp.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "unmute":
                sp.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "up":
                sp.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{num}%"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "down":
                sp.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{num}%"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            elif command == "set":
                sp.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{num}%"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            return True
        return False


_GLOBAL_DESKTOP_SERVICE: Optional[DesktopService] = None


def get_desktop_service(api=None) -> DesktopService:
    """Returns singleton DesktopService instance."""
    global _GLOBAL_DESKTOP_SERVICE
    if _GLOBAL_DESKTOP_SERVICE is None:
        _GLOBAL_DESKTOP_SERVICE = DesktopService(api=api)
    elif api is not None and _GLOBAL_DESKTOP_SERVICE.api is None:
        _GLOBAL_DESKTOP_SERVICE.api = api
    return _GLOBAL_DESKTOP_SERVICE
