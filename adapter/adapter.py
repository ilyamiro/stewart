import os
import sys
import platform
import socket
import getpass
import logging
import subprocess
from pathlib import Path
from datetime import datetime

import requests
import yaml


class Scan:
    def __init__(self):
        self.data = {
            "meta": {
                "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "app_name": "stewart"
            },
            "system": {},
            "paths": {},
            "network": {},
            "audio": {}
        }

    @staticmethod
    def _get_platform_paths():
        system = platform.system()
        user_home = Path.home()

        paths = {
            "home": str(user_home),
            "config": "",
            "cache": "",
            "data": ""
        }

        if system == "Windows":
            roaming = os.environ.get("APPDATA")
            local = os.environ.get("LOCALAPPDATA")

            if not roaming:
                roaming = str(user_home / "AppData" / "Roaming")
            if not local:
                local = str(user_home / "AppData" / "Local")

            paths["config"] = str(Path(roaming) / APP_NAME)
            paths["data"] = str(Path(local) / APP_NAME / "Data")
            paths["cache"] = str(Path(local) / APP_NAME / "Cache")

        else:
            xdg_config = os.environ.get("XDG_CONFIG_HOME", str(user_home / ".config"))
            paths["config"] = str(Path(xdg_config) / APP_NAME)

            xdg_cache = os.environ.get("XDG_CACHE_HOME", str(user_home / ".cache"))
            paths["cache"] = str(Path(xdg_cache) / APP_NAME)

            xdg_data = os.environ.get("XDG_DATA_HOME", str(user_home / ".local" / "share"))
            paths["data"] = str(Path(xdg_data) / APP_NAME)

        for key, path_str in paths.items():
            if key == "home":
                continue
            try:
                Path(path_str).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logging.warning(f"Could not create {key} directory at {path_str}: {e}")

        return paths

    @staticmethod
    def _get_linux_distro():
        """Parses /etc/os-release for pretty name."""
        if platform.system() != "Linux":
            return "N/A"
        try:
            with open('/etc/os-release') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        return line.split('=')[1].strip().strip('"')
        except FileNotFoundError:
            return "Unknown Linux"
        except Exception:
            return "Linux (Generic)"

    @staticmethod
    def _get_audio_devices():
        """
        Scans for audio sinks.
        """
        devices = []
        if platform.system() == "Linux":
            try:
                res = subprocess.run(["pactl", "list", "short", "sinks"],
                                     capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    for line in res.stdout.strip().split('\n'):
                        if line:
                            parts = line.split('\t')
                            if len(parts) > 1:
                                devices.append(parts[1])
            except (FileNotFoundError, subprocess.TimeoutExpired):
                devices.append("pactl_not_found")
        return devices

    @staticmethod
    def _get_network_info():
        data = {"public_ip": None, "city": None, "country": None, "online": False}
        try:
            response = requests.get("https://ipinfo.io/json", timeout=2.0)
            if response.status_code == 200:
                js = response.json()
                data["public_ip"] = js.get("ip")
                data["city"] = js.get("city")
                data["country"] = js.get("country")
                data["online"] = True
        except requests.RequestException:
            pass
        return data

    def scan(self):
        self.data["system"]["user"] = getpass.getuser()
        self.data["system"]["os"] = platform.system()
        self.data["system"]["hostname"] = socket.gethostname()
        self.data["system"]["release"] = platform.release()
        self.data["system"]["architecture"] = platform.machine()
        self.data["system"]["distro"] = self._get_linux_distro()
        self.data["system"]["python_version"] = sys.version.split()[0]

        self.data["paths"] = self._get_platform_paths()

        self.data["audio"]["available_sinks"] = self._get_audio_devices()

        self.data["network"] = self._get_network_info()

        return self.data


