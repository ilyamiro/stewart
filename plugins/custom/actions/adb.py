import logging
import re
import subprocess
from num2words import num2words

from api import app
from data.constants import ADB_DEVICE_IP
from utils import run_stdout, notify

log = logging.getLogger("action: adb")


def __is_device_charging__():
    """Check if the device is charging based on dumpsys battery output."""
    try:
        output = run_stdout('adb', 'shell', 'dumpsys', 'battery')

        ac_powered = re.search(r'AC powered:\s*(\w+)', output)
        usb_powered = re.search(r'USB powered:\s*(\w+)', output)
        wireless_powered = re.search(r'Wireless powered:\s*(\w+)', output)

        if (ac_powered and ac_powered.group(1) == 'true') or \
                (usb_powered and usb_powered.group(1) == 'true') or \
                (wireless_powered and wireless_powered.group(1) == 'true'):
            return True
    except Exception as e:
        log.warning(f"Error checking charging state: {e}")
    return False


def battery_check(**kwargs):
    check_adb()
    try:
        charging = __is_device_charging__()
        output = run_stdout('adb', 'shell', 'dumpsys', 'battery')
        battery_match = re.search(r'level:\s*(\d+)', output)
        battery = int(battery_match.group(1)) if battery_match else 0

        phone_model = run_stdout("adb", "shell", "getprop", "ro.product.manufacturer").strip() + " " + \
                      run_stdout("adb", "shell", "getprop", "ro.product.marketname").strip().upper()

        suggestion = ""
        description = "Phone's battery percentage"

        if battery <= 10:
            suggestion = "Immediately connect device to the charger"
            description = "🪫Really low, charge immediately"
        elif 10 < battery <= 20:
            suggestion = "I really recommend you connect your device to the charger"
            description = "🪫Low, plug it in"
        elif 20 < battery <= 50:
            suggestion = "It will last for a few hours at least"
            description = "🔋Moderate charge"
        elif 50 < battery:
            suggestion = "Your device is charged enough"
            description = "🔋Enough charge"

        suggestion = "It is currently charging" if charging else suggestion
        description = "⚡ Charging" if charging else description

        app.say(f"Your phone's battery is at {num2words(battery)} percent. {suggestion}, sir")

        notify(
            f"{phone_model}: {battery}%",
            description,
            60
        )
    except Exception as e:
        log.error(f"Failed to check battery via adb: {e}")
        app.say("Could not retrieve phone battery information, sir.")


def connect_adb(device_ip: str = ADB_DEVICE_IP):
    try:
        subprocess.run(["adb", "connect", f"{device_ip}:5555"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.debug(f"Connected to {device_ip} via adb")
    except Exception as e:
        log.warning(f"Failed to connect to adb device {device_ip}: {e}")


def check_adb(device_ip: str = ADB_DEVICE_IP):
    try:
        output = run_stdout("adb", "devices")
        if device_ip in output:
            return True
        connect_adb(device_ip)
    except Exception as e:
        log.warning(f"Error checking adb devices: {e}")


app.add_func_for_search(battery_check)

if app.lang == "en":
    app.manager.add(
        app.Command(
            [
                "phone", "battery"
            ],
            "battery_check",
            equivalents=[
                ["phone", "charge"],
            ],
            tts=True
        )
    )
