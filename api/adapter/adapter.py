import os
import platform
import socket
import getpass
import subprocess
import requests
import json


class Adapter:
    def __init__(self):
        self.data = {}

    @staticmethod
    def _get_linux_distro():
        try:
            with open('/etc/os-release') as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith('PRETTY_NAME='):
                        return line.strip().split('=')[1].strip('"')
        except Exception:
            return "Unknown Linux Distro"
        return "Unknown"

    @staticmethod
    def _get_public_ip_and_location():
        try:
            response = requests.get("https://ipinfo.io/json", timeout=1.5)
            if response.ok:
                loc_data = response.json()
                return {
                    "public_ip": loc_data.get("ip", "Unavailable"),
                    "country": loc_data.get("country", "Unavailable"),
                    "city": loc_data.get("city", "Unavailable")
                }
        except Exception:
            pass

        return {
            "public_ip": "Unavailable",
            "country": "Unavailable",
            "city": "Unavailable"
        }

    @staticmethod
    def _ping_host(host):
        try:
            result = subprocess.run(
                ["ping", "-c", "1", host],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _get_audio_devices_linux():
        try:
            result = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            devices = [line.split('\t')[1] for line in lines if line]
            return devices
        except Exception:
            return []

    def collect(self):
        self.data["user"] = getpass.getuser()
        self.data["home_folder"] = os.path.expanduser("~")
        self.data["os"] = platform.system()
        self.data["kernel_version"] = platform.release()
        self.data["arch"] = platform.machine()
        self.data["hostname"] = socket.gethostname()

        if platform.system() == "Linux":
            self.data["distro"] = self._get_linux_distro()
            self.data["audio_devices"] = self._get_audio_devices_linux()

        self.data["network"] = self._get_public_ip_and_location()

        self.data["connectivity"] = {
            "google.com": self._ping_host("google.com"),
            "youtube.com": self._ping_host("youtube.com"),
            "music.youtube.com": self._ping_host("music.youtube.com"),
            "openai.com": self._ping_host("openai.com")
        }

        return self.data


if __name__ == "__main__":
    adapter = Adapter()
    system_data = adapter.collect()
    print(json.dumps(system_data, indent=2))
