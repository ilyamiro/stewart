from num2words import num2words
import re

from api import app, tree
from data.constants import PROJECT_FOLDER

from utils import run_stdout, notify


def __is_device_charging__():
    """Check if the device is charging based on dumpsys battery output."""
    output = run_stdout('adb', 'shell', 'dumpsys', 'battery')

    # Check for charging states using regular expressions
    ac_powered = re.search(r'AC powered:\s*(\w+)', output)
    usb_powered = re.search(r'USB powered:\s*(\w+)', output)
    wireless_powered = re.search(r'Wireless powered:\s*(\w+)', output)

    # Evaluate the charging status
    if (ac_powered and ac_powered.group(1) == 'true') or \
            (usb_powered and usb_powered.group(1) == 'true') or \
            (wireless_powered and wireless_powered.group(1) == 'true'):
        return True
    return False


def battery_check(**kwargs):
    charging = __is_device_charging__()
    battery = int(run_stdout("adb shell dumpsys battery | grep level | awk '{print $2}'", shell=True).strip())
    phone_model = run_stdout("adb", "shell", "getprop", "ro.product.manufacturer") + " " + run_stdout("adb", "shell",
                                                                                                      "getprop",
                                                                                                      "ro.product.marketname").upper()

    suggestion = ""
    description = "Phone's battery percentage",

    if battery <= 10:
        suggestion = "Immediately connect device to the charger"
        description = f"🪫Really low, charge immediately"
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


def connect_adb():
    run(f"./scripts/bash/connect_adb.sh", ADB_DEVICE_IP, "5555")
    log.debug(f"Connected to {ADB_DEVICE_IP} via adb")


def check_adb():
    connection = run_stdout(f"./scripts/bash/check_adb.sh", ADB_DEVICE_IP)
    if connection == "true":
        return
    else:
        connect_adb()


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

