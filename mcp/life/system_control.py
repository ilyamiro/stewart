"""
Unified PC, Compositor (Hyprland / Niri), and Serpantinum Desktop Shell Controller.
Provides IPC-style system control for opening apps, media management (YouTube Music / playerctl),
window & workspace management, screenshot capturing, Serpantinum shell widgets, and hardware controls.
"""

import os
import re
import shlex
import shutil
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_serpantinum_bin() -> str:
    """Finds the best path to execute serpantinum commands."""
    serp_dispatch = Path.home() / ".config" / "hypr" / "serp-dispatch.sh"
    if serp_dispatch.is_file() and os.access(serp_dispatch, os.X_OK):
        return str(serp_dispatch)
    
    dev_bin = Path.home() / "Projects" / "serpantinum" / "bin" / "serpantinum"
    if dev_bin.is_file() and os.access(dev_bin, os.X_OK):
        return str(dev_bin)
    
    found = shutil.which("serpantinum")
    if found:
        return found
    return "serpantinum"


def detect_compositor() -> str:
    """Detects active Wayland compositor: hyprland, niri, sway, or unknown."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if os.environ.get("NIRI_SOCKET"):
        return "niri"
    
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()
    if "hyprland" in desktop:
        return "hyprland"
    if "niri" in desktop:
        return "niri"
    if "sway" in desktop or os.environ.get("SWAYSOCK"):
        return "sway"
    
    try:
        res = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, timeout=1)
        if res.returncode == 0:
            return "hyprland"
    except Exception:
        pass
    
    try:
        res = subprocess.run(["niri", "msg", "-j", "windows"], capture_output=True, timeout=1)
        if res.returncode == 0:
            return "niri"
    except Exception:
        pass
    
    return "unknown"


class DesktopEntryManager:
    """Discovers, indexes, and launches .desktop application entries across system and user profiles."""

    def __init__(self):
        self._cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._last_scan: float = 0.0

    def get_search_directories(self) -> List[Path]:
        user = os.environ.get("USER", "ilyamiro")
        dirs = [
            Path.home() / ".local" / "share" / "applications",
            Path("/etc/profiles/per-user") / user / "share" / "applications",
            Path("/run/current-system/sw/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
            Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
        ]
        xdg_dirs = os.environ.get("XDG_DATA_DIRS", "").split(":")
        for d in xdg_dirs:
            if d.strip():
                dirs.append(Path(d.strip()) / "applications")
        return [d for d in dirs if d.is_dir()]

    def scan_desktop_files(self, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        now = datetime.now().timestamp()
        if self._cache is not None and not force_refresh and (now - self._last_scan < 60):
            return self._cache

        apps: Dict[str, Dict[str, Any]] = {}
        for app_dir in self.get_search_directories():
            try:
                for entry in app_dir.glob("*.desktop"):
                    if entry.name in apps:
                        continue
                    try:
                        content = entry.read_text(encoding="utf-8", errors="ignore")
                        name = None
                        generic_name = ""
                        exec_cmd = None
                        no_display = False
                        is_terminal = False
                        comment = ""
                        categories = ""
                        keywords = ""

                        in_main_section = False
                        for line in content.splitlines():
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if line.startswith("[") and line.endswith("]"):
                                in_main_section = (line == "[Desktop Entry]")
                                continue
                            if not in_main_section:
                                continue

                            if line.startswith("Name=") and not name:
                                name = line.split("=", 1)[1].strip()
                            elif line.startswith("GenericName=") and not generic_name:
                                generic_name = line.split("=", 1)[1].strip()
                            elif line.startswith("Exec=") and not exec_cmd:
                                exec_cmd = line.split("=", 1)[1].strip()
                            elif line.startswith("NoDisplay="):
                                no_display = line.split("=", 1)[1].strip().lower() == "true"
                            elif line.startswith("Terminal="):
                                is_terminal = line.split("=", 1)[1].strip().lower() == "true"
                            elif line.startswith("Comment=") and not comment:
                                comment = line.split("=", 1)[1].strip()
                            elif line.startswith("Categories=") and not categories:
                                categories = line.split("=", 1)[1].strip()
                            elif line.startswith("Keywords=") and not keywords:
                                keywords = line.split("=", 1)[1].strip()

                        if exec_cmd:
                            apps[entry.name] = {
                                "id": entry.name,
                                "name": name or entry.stem,
                                "generic_name": generic_name,
                                "exec": exec_cmd,
                                "no_display": no_display,
                                "terminal": is_terminal,
                                "comment": comment,
                                "categories": categories,
                                "keywords": keywords,
                                "path": str(entry)
                            }
                    except Exception:
                        continue
            except Exception:
                continue

        self._cache = apps
        self._last_scan = now
        return apps

    def find_app(self, query: str) -> Optional[Dict[str, Any]]:
        apps = self.scan_desktop_files()
        q = query.lower().strip()
        if not q:
            return None

        candidates = []
        for aid, app in apps.items():
            name = app["name"].lower()
            gen = app["generic_name"].lower()
            stem = aid.lower().replace(".desktop", "")
            kw = app.get("keywords", "").lower()
            cat = app.get("categories", "").lower()
            comment = app.get("comment", "").lower()

            score = 0
            if q == stem or q == aid.lower():
                score = 100
            elif q == name:
                score = 95
            elif name.startswith(q) or stem.startswith(q):
                score = 85
            elif any(part.startswith(q) for part in name.split()) or any(part.startswith(q) for part in stem.split(".")):
                score = 75
            elif q in name or q in stem:
                score = 65
            elif q in gen:
                score = 50
            elif q in kw or q in cat:
                score = 40
            elif q in comment:
                score = 30

            if score > 0:
                if app["no_display"]:
                    score -= 35
                candidates.append((score, app))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1] if candidates else None

    def list_apps(self, query: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        apps = self.scan_desktop_files()
        q = (query or "").lower().strip()
        matched = []
        for aid, app in apps.items():
            if app["no_display"] and not q:
                continue
            if not q:
                matched.append(app)
            else:
                name = app["name"].lower()
                gen = app["generic_name"].lower()
                stem = aid.lower().replace(".desktop", "")
                if q in name or q in stem or q in gen or q in app.get("keywords", "").lower() or q in app.get("comment", "").lower():
                    matched.append(app)

        matched.sort(key=lambda x: x["name"].lower())
        results = [
            {
                "id": a["id"],
                "name": a["name"],
                "generic_name": a["generic_name"],
                "comment": a["comment"],
                "terminal": a["terminal"]
            }
            for a in matched[:limit]
        ]
        return {
            "status": "success",
            "query": query,
            "total_matches": len(matched),
            "returned_count": len(results),
            "apps": results
        }

    def clean_exec(self, exec_cmd: str, args: Optional[str] = None) -> str:
        cleaned = re.sub(r'@@[uU]?', '', exec_cmd)
        cleaned = re.sub(r'@@', '', cleaned)
        if args:
            cleaned = re.sub(r'%[fFuU]', args, cleaned)
        else:
            cleaned = re.sub(r'%[fFuU]', '', cleaned)
        cleaned = re.sub(r'%[dDnNickv]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if args and args not in cleaned:
            cleaned += f" {args}"
        return cleaned

    def log_launch_rank(self, app_id: str):
        """Notifies Serpantinum launcher app ranking daemon."""
        rank_script = Path.home() / "Projects" / "serpantinum" / "src" / "quickshell" / "launcher" / "app_rank.py"
        if not rank_script.is_file():
            rank_script = Path.home() / ".config" / "quickshell" / "launcher" / "app_rank.py"
        if rank_script.is_file():
            name = app_id.replace(".desktop", "")
            try:
                subprocess.Popen(
                    ["python3", str(rank_script), "--log-launch", "--name", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True
                )
            except Exception:
                pass


def parse_ipc_command(cmd_str: str) -> Dict[str, Any]:
    """
    Parses IPC commands like:
      - "(system / open / terminal)"
      - "system / open / browser / https://music.youtube.com"
      - "system / media / youtube_music / lofi synthwave"
      - "system / window / move / right"
      - "system / workspace / 2"
      - "open terminal"
      - "screenshot full"
    """
    cleaned = cmd_str.strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()

    url_match = re.search(r"https?://\S+", cleaned)
    extracted_url = None
    if url_match:
        extracted_url = url_match.group(0)
        cleaned = cleaned[:url_match.start()] + "__URL_PLACEHOLDER__" + cleaned[url_match.end():]

    if "/" in cleaned:
        raw_tokens = [t.strip() for t in cleaned.split("/") if t.strip()]
    else:
        raw_tokens = shlex.split(cleaned)

    tokens = []
    for t in raw_tokens:
        if "__URL_PLACEHOLDER__" in t and extracted_url:
            tokens.append(t.replace("__URL_PLACEHOLDER__", extracted_url))
        else:
            tokens.append(t)

    if not tokens:
        return {"action": "status"}

    if tokens[0].lower() in ("system", "pc", "desktop", "serpantinum", "life"):
        tokens = tokens[1:]

    if not tokens:
        return {"action": "status"}

    action = tokens[0].lower()
    target = tokens[1] if len(tokens) > 1 else ""
    args = " ".join(tokens[2:]) if len(tokens) > 2 else ""

    if action in ("app", "launch", "run", "start"):
        action = "open"
    elif action in ("apps", "list_apps", "desktop_apps", "search_apps"):
        action = "apps"
    elif action in ("ytm", "youtube_music", "music", "song", "player"):
        action = "media"
        if not target or target not in ("play", "pause", "play_pause", "next", "prev", "previous", "status", "volume"):
            args = (target + " " + args).strip()
            target = "youtube_music"
    elif action in ("shot", "capture", "snip"):
        action = "screenshot"
    elif action in ("win", "windows"):
        action = "window"
    elif action in ("ws", "workspaces"):
        action = "workspace"
    elif action in ("vol", "sound"):
        action = "volume"
    elif action in ("bright", "backlight"):
        action = "brightness"

    return {"action": action, "target": target, "args": args}


class SystemControl:
    """Unified system & compositor automation interface."""

    def __init__(self):
        self.compositor = detect_compositor()
        self.serpantinum_bin = get_serpantinum_bin()
        self.desktop_mgr = DesktopEntryManager()

    def run_cmd(self, cmd: List[str], timeout: float = 5.0) -> subprocess.CompletedProcess:
        """Executes a command synchronously with error capture."""
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False
        )

    def spawn_bg(self, cmd: List[str]) -> bool:
        """Launches a GUI application or command in the background detached."""
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True
            )
            return True
        except Exception:
            return False

    def exec_app(self, app_cmd: str) -> Dict[str, Any]:
        """Launches an application via compositor or detached process."""
        comp = self.compositor
        if comp == "hyprland":
            res = self.run_cmd(["hyprctl", "dispatch", "exec", app_cmd])
            if res.returncode == 0:
                return {"status": "success", "compositor": comp, "message": f"Dispatched exec '{app_cmd}' via Hyprland"}
        elif comp == "niri":
            tokens = shlex.split(app_cmd)
            res = self.run_cmd(["niri", "msg", "action", "spawn", "--"] + tokens)
            if res.returncode == 0:
                return {"status": "success", "compositor": comp, "message": f"Dispatched spawn '{app_cmd}' via Niri"}

        tokens = shlex.split(app_cmd)
        if self.spawn_bg(tokens):
            return {"status": "success", "compositor": comp, "message": f"Spawned background process '{app_cmd}'"}
        return {"status": "error", "message": f"Failed to spawn '{app_cmd}'"}


    def open_terminal(self, custom_command: Optional[str] = None) -> Dict[str, Any]:
        term = "kitty"
        if custom_command:
            cmd = f"{term} {custom_command}"
        else:
            cmd = term
        return self.exec_app(cmd)

    def open_browser(self, url: Optional[str] = None) -> Dict[str, Any]:
        browser = "firefox"
        if url:
            if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file://"):
                url = "https://" + url
            cmd = f"{browser} {shlex.quote(url)}"
        else:
            cmd = browser
        return self.exec_app(cmd)

    def open_youtube_music(self, query: Optional[str] = None) -> Dict[str, Any]:
        """Opens YouTube Music or searches for tracks/albums."""
        if query and query.strip():
            encoded = urllib.parse.quote_plus(query.strip())
            url = f"https://music.youtube.com/search?q={encoded}"
            res = self.open_browser(url)
            res["message"] = f"Opened YouTube Music search for '{query.strip()}' in Firefox"
            return res
        
        url = "https://music.youtube.com"
        res = self.open_browser(url)
        res["message"] = "Opened YouTube Music in Firefox"
        return res

    def open_files(self, path: Optional[str] = None) -> Dict[str, Any]:
        target_path = path or str(Path.home())
        return self.exec_app(f"nautilus {shlex.quote(target_path)}")

    def open_telegram(self) -> Dict[str, Any]:
        bin_name = "Telegram" if shutil.which("Telegram") else "telegram-desktop"
        return self.exec_app(bin_name)

    def open_obsidian(self, args: Optional[str] = None) -> Dict[str, Any]:
        if args:
            return self.exec_app(f"obsidian {args}")
        return self.exec_app("obsidian")

    def open_app(self, target: str, args: str = "") -> Dict[str, Any]:
        """
        Launches an application by name or desktop entry.
        First checks standard quick aliases (terminal, browser, youtube_music, files, telegram, obsidian).
        If not a quick alias, or if target matches a desktop entry, resolves and launches the desktop entry.
        """
        tgt = target.lower().strip()
        if tgt in ("terminal", "kitty", "console", "term"):
            return self.open_terminal(custom_command=args if args else None)
        elif tgt in ("browser", "web"):
            return self.open_browser(url=args if args else None)
        elif tgt in ("youtube_music", "ytm"):
            return self.open_youtube_music(query=args if args else None)
        elif tgt in ("files", "file_manager", "nautilus", "explorer"):
            return self.open_files(path=args if args else None)
        elif tgt in ("telegram", "tg"):
            return self.open_telegram()
        elif tgt in ("obsidian", "notes"):
            return self.open_obsidian(args=args if args else None)

        desktop_app = self.desktop_mgr.find_app(target)
        if desktop_app:
            app_id = desktop_app["id"]
            app_name = desktop_app["name"]
            is_term = desktop_app.get("terminal", False)
            raw_exec = desktop_app["exec"]

            self.desktop_mgr.log_launch_rank(app_id)

            gtk_launch = shutil.which("gtk-launch")
            if gtk_launch and not is_term and not args:
                cmd_str = f"gtk-launch {shlex.quote(app_id)}"
                res = self.exec_app(cmd_str)
                res["app_name"] = app_name
                res["desktop_id"] = app_id
                res["message"] = f"Launched '{app_name}' ({app_id}) via gtk-launch"
                return res

            cleaned_exec = self.desktop_mgr.clean_exec(raw_exec, args=args if args else None)
            if is_term:
                final_cmd = f"kitty -e {cleaned_exec}"
            else:
                final_cmd = cleaned_exec

            res = self.exec_app(final_cmd)
            res["app_name"] = app_name
            res["desktop_id"] = app_id
            res["exec_cmd"] = final_cmd
            res["message"] = f"Launched '{app_name}' ({app_id})"
            return res

        fallback_cmd = f"{target} {args}".strip()
        res = self.exec_app(fallback_cmd)
        res["message"] = f"Executed '{fallback_cmd}'"
        return res

    def list_desktop_apps(self, query: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """Lists or searches indexed desktop entries."""
        return self.desktop_mgr.list_apps(query=query, limit=limit)


    def media_control(self, action: str, args: str = "") -> Dict[str, Any]:
        """Controls media playback via playerctl or launches YouTube Music."""
        action = action.lower().replace("-", "_")

        if action in ("youtube_music", "ytm", "music"):
            return self.open_youtube_music(args)

        playerctl = shutil.which("playerctl")
        if not playerctl:
            return {"status": "error", "message": "playerctl binary not found in system"}

        if action in ("play_pause", "toggle"):
            res = self.run_cmd(["playerctl", "play-pause"])
            return {"status": "success", "action": "play_pause", "output": res.stdout or "Toggled play/pause"}
        elif action in ("play", "start", "resume"):
            res = self.run_cmd(["playerctl", "play"])
            return {"status": "success", "action": "play", "output": res.stdout or "Playing"}
        elif action in ("pause", "stop"):
            res = self.run_cmd(["playerctl", "pause"])
            return {"status": "success", "action": "pause", "output": res.stdout or "Paused"}
        elif action in ("next", "skip"):
            res = self.run_cmd(["playerctl", "next"])
            return {"status": "success", "action": "next", "output": res.stdout or "Skipped to next track"}
        elif action in ("previous", "prev"):
            res = self.run_cmd(["playerctl", "previous"])
            return {"status": "success", "action": "previous", "output": res.stdout or "Previous track"}
        elif action in ("status", "info", "now_playing"):
            stat_res = self.run_cmd(["playerctl", "status"])
            meta_res = self.run_cmd(["playerctl", "metadata", "--format", "{{ artist }} - {{ title }} [{{ album }}]"])
            return {
                "status": "success",
                "playback_status": (stat_res.stdout or "No active player").strip(),
                "now_playing": (meta_res.stdout or "None").strip()
            }
        elif action == "volume":
            vol_arg = args or "+5%"
            res = self.run_cmd(["playerctl", "volume", vol_arg])
            return {"status": "success", "action": "volume", "output": res.stdout or f"Volume set {vol_arg}"}
        else:
            return {"status": "error", "message": f"Unknown media action: {action}"}


    def window_control(self, action: str, target: str = "", args: str = "") -> Dict[str, Any]:
        """Manages windows: move, focus, close, float, fullscreen, or list."""
        comp = self.compositor
        action = action.lower()
        direction = target.lower() or args.lower() or "right"

        dir_hypr = {"left": "l", "right": "r", "up": "u", "down": "d", "l": "l", "r": "r", "u": "u", "d": "d"}

        if comp == "hyprland":
            if action in ("move", "movewindow"):
                dh = dir_hypr.get(direction, "r")
                res = self.run_cmd(["hyprctl", "dispatch", "movewindow", dh])
                return {"status": "success", "compositor": comp, "action": f"move window {dh}", "output": res.stdout}
            elif action in ("focus", "focuswindow"):
                if direction in dir_hypr:
                    dh = dir_hypr[direction]
                    res = self.run_cmd(["hyprctl", "dispatch", "movefocus", dh])
                else:
                    res = self.run_cmd(["hyprctl", "dispatch", "focuswindow", target or args])
                return {"status": "success", "compositor": comp, "action": f"focus window {direction}", "output": res.stdout}
            elif action in ("close", "kill"):
                res = self.run_cmd(["hyprctl", "dispatch", "killactive"])
                return {"status": "success", "compositor": comp, "action": "close active window", "output": res.stdout}
            elif action in ("float", "togglefloating"):
                res = self.run_cmd(["hyprctl", "dispatch", "togglefloating"])
                return {"status": "success", "compositor": comp, "action": "toggle floating", "output": res.stdout}
            elif action in ("fullscreen", "full"):
                res = self.run_cmd(["hyprctl", "dispatch", "fullscreen", "1"])
                return {"status": "success", "compositor": comp, "action": "toggle fullscreen", "output": res.stdout}
            elif action in ("active", "current"):
                res = self.run_cmd(["hyprctl", "activewindow", "-j"])
                return {"status": "success", "compositor": comp, "active_window": res.stdout}
            elif action in ("list", "clients"):
                res = self.run_cmd(["hyprctl", "clients", "-j"])
                return {"status": "success", "compositor": comp, "windows": res.stdout}

        elif comp == "niri":
            if action in ("move", "movewindow"):
                act = "move-column-left" if direction in ("left", "l") else "move-column-right"
                res = self.run_cmd(["niri", "msg", "action", act])
                return {"status": "success", "compositor": comp, "action": act, "output": res.stdout}
            elif action in ("focus", "focuswindow"):
                act = "focus-column-left" if direction in ("left", "l") else "focus-column-right"
                res = self.run_cmd(["niri", "msg", "action", act])
                return {"status": "success", "compositor": comp, "action": act, "output": res.stdout}
            elif action in ("close", "kill"):
                res = self.run_cmd(["niri", "msg", "action", "close-window"])
                return {"status": "success", "compositor": comp, "action": "close-window", "output": res.stdout}
            elif action in ("fullscreen", "full"):
                res = self.run_cmd(["niri", "msg", "action", "fullscreen-window"])
                return {"status": "success", "compositor": comp, "action": "fullscreen-window", "output": res.stdout}
            elif action in ("active", "current"):
                res = self.run_cmd(["niri", "msg", "-j", "focused-window"])
                return {"status": "success", "compositor": comp, "active_window": res.stdout}
            elif action in ("list", "clients"):
                res = self.run_cmd(["niri", "msg", "-j", "windows"])
                return {"status": "success", "compositor": comp, "windows": res.stdout}

        return {"status": "error", "message": f"Window action '{action}' not supported for compositor '{comp}'"}

    def workspace_control(self, ws_number: str, move_window: bool = False) -> Dict[str, Any]:
        """Switches workspace or moves active window to workspace."""
        ws = ws_number.strip()
        if not ws.isdigit():
            m = re.search(r"\d+", ws)
            if m:
                ws = m.group(0)
            else:
                ws = "1"

        cmd = [self.serpantinum_bin, "msg", "workspace", ws]
        if move_window:
            cmd.append("move")
        res = self.run_cmd(cmd)
        action_desc = f"Moved active window to workspace {ws}" if move_window else f"Switched to workspace {ws}"
        return {
            "status": "success",
            "compositor": self.compositor,
            "workspace": ws,
            "moved_window": move_window,
            "message": action_desc,
            "output": res.stdout
        }


    def take_screenshot(
        self,
        mode: str = "full",
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Takes a screenshot.
        mode can be:
          - 'full': instant programmatic capture of whole screen saved to Pictures/Screenshots
          - 'area': interactive area selection via serpantinum
          - 'edit': interactive screenshot with annotation (Satty)
          - 'record': start/stop screen recording
          - 'scan_qr': scan QR code from screen
        """
        mode = (mode or "full").lower()
        save_dir = Path.home() / "Pictures" / "Screenshots"
        save_dir.mkdir(parents=True, exist_ok=True)

        if mode == "full":
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_file = Path(output_path).expanduser().resolve() if output_path else (save_dir / f"screenshot_{timestamp}.png")
            target_file.parent.mkdir(parents=True, exist_ok=True)

            grim = shutil.which("grim")
            if grim:
                res = self.run_cmd(["grim", str(target_file)])
                if res.returncode == 0 and target_file.is_file():
                    if shutil.which("wl-copy"):
                        self.spawn_bg(["wl-copy", "--type", "image/png"],)
                        with open(target_file, "rb") as f:
                            subprocess.run(["wl-copy", "--type", "image/png"], stdin=f, check=False)
                    return {
                        "status": "success",
                        "mode": "full",
                        "file_path": str(target_file),
                        "size_bytes": target_file.stat().st_size,
                        "message": f"Full screenshot saved to {target_file} and copied to clipboard."
                    }
            
            res = self.run_cmd([self.serpantinum_bin, "screenshot", "--full"])
            return {
                "status": "success",
                "mode": "full",
                "message": "Full screenshot captured via serpantinum screenshot --full",
                "output": res.stdout
            }

        elif mode in ("edit", "satty"):
            self.spawn_bg([self.serpantinum_bin, "screenshot", "--edit"])
            return {"status": "success", "mode": "edit", "message": "Launched interactive screenshot editor (satty)"}

        elif mode in ("area", "slurp", "interactive"):
            self.spawn_bg([self.serpantinum_bin, "screenshot"])
            return {"status": "success", "mode": "area", "message": "Triggered interactive area screenshot"}

        elif mode == "record":
            res = self.run_cmd([self.serpantinum_bin, "screenshot", "--record"])
            return {"status": "success", "mode": "record", "message": "Toggled screen recording", "output": res.stdout}

        elif mode in ("qr", "scan_qr"):
            res = self.run_cmd([self.serpantinum_bin, "screenshot", "--scan-qr"])
            return {"status": "success", "mode": "scan_qr", "output": res.stdout or res.stderr}

        return {"status": "error", "message": f"Unknown screenshot mode: {mode}"}


    def serpantinum_control(self, action: str, target: str = "", args: str = "") -> Dict[str, Any]:
        """Interacts directly with Serpantinum desktop shell UI components."""
        action = action.lower()
        bin_path = self.serpantinum_bin

        if action in ("toggle", "open"):
            widget = target or args or "launcher"
            res = self.run_cmd([bin_path, "msg", action, widget])
            return {"status": "success", "shell_action": f"{action} {widget}", "output": res.stdout}
        elif action == "close":
            res = self.run_cmd([bin_path, "msg", "close"])
            return {"status": "success", "shell_action": "close", "output": res.stdout}
        elif action == "reload":
            res = self.run_cmd([bin_path, "reload"])
            return {"status": "success", "shell_action": "reload", "output": res.stdout}
        elif action == "lock":
            res = self.run_cmd([bin_path, "lock"])
            return {"status": "success", "shell_action": "lock", "output": res.stdout}
        elif action in ("weather", "current_weather"):
            res = self.run_cmd([bin_path, "weather", "--json"])
            return {"status": "success", "weather": res.stdout}
        elif action == "volume":
            sub = target or args or "mute-toggle"
            res = self.run_cmd([bin_path, "volume", sub])
            return {"status": "success", "volume_action": sub, "output": res.stdout}
        elif action == "brightness":
            sub = target or args or "raise"
            res = self.run_cmd([bin_path, "brightness", sub])
            return {"status": "success", "brightness_action": sub, "output": res.stdout}
        else:
            return {"status": "error", "message": f"Unknown shell action: {action}"}


    def get_status(self) -> Dict[str, Any]:
        """Returns overview of desktop environment, active window, workspaces, and media."""
        comp = self.compositor
        info: Dict[str, Any] = {
            "status": "success",
            "compositor": comp,
            "serpantinum_bin": self.serpantinum_bin
        }

        try:
            stat_res = self.run_cmd(["playerctl", "status"], timeout=1)
            meta_res = self.run_cmd(["playerctl", "metadata", "--format", "{{ artist }} - {{ title }}"], timeout=1)
            info["media"] = {
                "status": (stat_res.stdout or "stopped").strip(),
                "track": (meta_res.stdout or "").strip()
            }
        except Exception:
            info["media"] = "unavailable"

        if comp == "hyprland":
            try:
                w_res = self.run_cmd(["hyprctl", "activewindow", "-j"], timeout=1)
                info["active_window"] = w_res.stdout.strip()
                ws_res = self.run_cmd(["hyprctl", "workspaces", "-j"], timeout=1)
                info["workspaces"] = ws_res.stdout.strip()
            except Exception as e:
                info["window_error"] = str(e)
        elif comp == "niri":
            try:
                w_res = self.run_cmd(["niri", "msg", "-j", "focused-window"], timeout=1)
                info["active_window"] = w_res.stdout.strip()
            except Exception as e:
                info["window_error"] = str(e)

        return info


_controller = SystemControl()


def execute_system_control(
    action: Optional[str] = None,
    target: Optional[str] = None,
    args: Optional[str] = None,
    command: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main dispatch function for desktop & system control.
    Supports either explicit parameters or raw IPC tuples/strings like '(system / open / terminal)'.
    """
    ctrl = _controller

    if command:
        parsed = parse_ipc_command(command)
        action = action or parsed.get("action")
        target = target or parsed.get("target")
        args = args or parsed.get("args")

    action = (action or "status").lower().strip()
    target = (target or "").strip()
    args = (args or "").strip()

    if action in ("open", "launch", "run", "start"):
        if not target:
            return {"status": "error", "message": "Missing target application to open"}
        return ctrl.open_app(target, args=args)

    elif action in ("apps", "list_apps", "desktop_apps", "search_apps"):
        return ctrl.list_desktop_apps(query=target or args)

    elif action in ("media", "music", "player", "playback", "youtube_music"):
        act = target if target else "play_pause"
        return ctrl.media_control(act, args=args)

    elif action in ("window", "windows", "win"):
        act = target or "active"
        return ctrl.window_control(act, target=args)

    elif action in ("move", "focus", "close", "float", "fullscreen"):
        return ctrl.window_control(action, target=target, args=args)

    elif action in ("workspace", "ws"):
        move_win = "move" in args.lower() or "move" in target.lower()
        ws_num = target if target and target.isdigit() else (args if args else "1")
        return ctrl.workspace_control(ws_num, move_window=move_win)

    elif action in ("screenshot", "screen", "capture", "snip"):
        mode = target or (args if args in ("full", "area", "edit", "record", "scan_qr") else "full")
        out_path = args if args and not args in ("full", "area", "edit", "record", "scan_qr") else None
        return ctrl.take_screenshot(mode=mode, output_path=out_path)

    elif action in ("shell", "serpantinum", "ui"):
        act = target or "toggle"
        return ctrl.serpantinum_control(act, args=args)

    elif action in ("volume", "vol", "sound"):
        act = target or args or "mute-toggle"
        return ctrl.serpantinum_control("volume", target=act)

    elif action in ("brightness", "backlight"):
        act = target or args or "raise"
        return ctrl.serpantinum_control("brightness", target=act)

    elif action in ("lock", "reload"):
        return ctrl.serpantinum_control(action)

    elif action in ("status", "info"):
        return ctrl.get_status()

    elif action == "raw":
        raw_cmd = f"{target} {args}".strip()
        comp = ctrl.compositor
        if comp == "hyprland" and raw_cmd.startswith("dispatch "):
            raw_tokens = raw_cmd.split(" ", 1)[1].split(" ")
            res = ctrl.run_cmd(["hyprctl", "dispatch"] + raw_tokens)
            return {"status": "success", "compositor": comp, "output": res.stdout}
        elif comp == "niri" and raw_cmd.startswith("action "):
            raw_tokens = raw_cmd.split(" ", 1)[1].split(" ")
            res = ctrl.run_cmd(["niri", "msg", "action"] + raw_tokens)
            return {"status": "success", "compositor": comp, "output": res.stdout}
        else:
            res = ctrl.run_cmd(shlex.split(raw_cmd))
            return {"status": "success", "output": res.stdout, "stderr": res.stderr}

    else:
        if action in ("launcher", "clipboard", "music", "system", "wallpaper", "calendar", "network"):
            return ctrl.serpantinum_control("toggle", target=action)
        return ctrl.exec_app(f"{action} {target} {args}".strip())
