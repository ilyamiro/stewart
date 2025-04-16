import subprocess
import random
import datetime
from num2words import num2words
import time
import re
import os
from api import app


def get_battery_info():
    """Collect comprehensive battery information using system tools."""
    try:
        info = {}

        # Get the battery device path
        devices = subprocess.check_output(["upower", "--enumerate"], text=True).strip().split('\n')
        battery_path = None
        for device in devices:
            if "battery" in device.lower():
                battery_path = device
                break

        if not battery_path:
            return {"error": "No battery found on this system."}

        # Get detailed information about the battery
        battery_info = subprocess.check_output(["upower", "--show-info", battery_path], text=True)

        # Parse the battery information
        for line in battery_info.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                info[key.strip()] = value.strip()

        # Try to get more detailed information from sysfs
        try:
            battery_path = '/sys/class/power_supply/BAT0'
            if os.path.exists(battery_path):
                # Get cycle count
                cycle_path = os.path.join(battery_path, 'cycle_count')
                if os.path.exists(cycle_path):
                    with open(cycle_path, 'r') as f:
                        info['cycle_count'] = f.read().strip()

                # Get voltage
                voltage_path = os.path.join(battery_path, 'voltage_now')
                if os.path.exists(voltage_path):
                    with open(voltage_path, 'r') as f:
                        voltage = int(f.read().strip()) / 1000000  # Convert from µV to V
                        info['voltage'] = f"{voltage:.2f} volts"

                # Get current power consumption
                power_path = os.path.join(battery_path, 'power_now')
                if os.path.exists(power_path):
                    with open(power_path, 'r') as f:
                        power = int(f.read().strip()) / 1000000  # Convert from µW to W
                        info['power_now'] = f"{power:.2f} watts"

                # Get temperature if available
                temp_path = os.path.join(battery_path, 'temp')
                if os.path.exists(temp_path):
                    with open(temp_path, 'r') as f:
                        temp = int(f.read().strip()) / 10  # Usually in tenths of degree C
                        info['temperature'] = f"{temp:.1f} degrees"
        except Exception:
            # Sysfs detailed info is optional
            pass

        try:
            # Some systems allow accessing SMART info of batteries
            smart_info = subprocess.check_output(["smartctl", "-a", "/dev/nvme0"], text=True, stderr=subprocess.DEVNULL)
            if "Temperature:" in smart_info:
                for line in smart_info.split('\n'):
                    if "Temperature:" in line:
                        match = re.search(r'Temperature:\s+(\d+)\s+Celsius', line)
                        if match:
                            info['system_temperature'] = f"{match.group(1)}°C"
        except (subprocess.SubprocessError, FileNotFoundError):
            # SMART info is optional
            pass

        # Get charge rate
        if 'energy-rate' in info:
            info['charging_rate'] = info['energy-rate']

        # Calculate remaining time more accurately if possible
        if 'percentage' in info and 'energy-rate' in info:
            try:
                percentage = float(info['percentage'].replace('%', ''))
                rate = float(info['energy-rate'].split()[0])
                capacity = float(info.get('energy-full', '0').split()[0])

                if info.get('state') == 'discharging' and rate > 0:
                    remaining_capacity = capacity * percentage / 100
                    hours_remaining = remaining_capacity / rate
                    info['calculated_remaining_time'] = format_time(hours_remaining)
                elif info.get('state') == 'charging' and rate > 0:
                    remaining_to_fill = capacity * (100 - percentage) / 100
                    hours_to_full = remaining_to_fill / rate
                    info['calculated_time_to_full'] = format_time(hours_to_full)
            except (ValueError, ZeroDivisionError):
                pass

        return info
    except Exception as e:
        return {"error": f"Failed to get battery information: {str(e)}"}


def format_time(hours):
    """Format hours into a human-readable time string."""
    hours_int = int(hours)
    minutes = int((hours - hours_int) * 60)

    if hours_int == 0:
        return f"{minutes} minutes"
    elif hours_int == 1 and minutes == 0:
        return "1 hour"
    elif hours_int == 1:
        return f"1 hour and {minutes} minutes"
    elif minutes == 0:
        return f"{hours_int} hours"
    else:
        return f"{hours_int} hours and {minutes} minutes"


def number_to_words(text):
    """Convert numbers in text to words."""
    # Regex to find numbers (whole or decimal) that aren't part of words
    pattern = r'(?<!\w)(\d+(\.\d+)?)(?!\w)'

    def replace_number(match):
        num = match.group(1)
        if '.' in num:
            return num2words(float(num))
        else:
            return num2words(int(num))

    # Replace all standalone numbers with their word form
    converted_text = re.sub(pattern, replace_number, text)
    return converted_text


def generate_battery_report(battery_info):
    """Generate a dynamic voice assistant-like report about battery health."""

    if "error" in battery_info:
        return f"I'm sorry, but I couldn't check your battery. {battery_info['error']}"

    # Extract key information
    percentage = battery_info.get("percentage", "unknown").replace('%', '')
    state = battery_info.get("state", "unknown")
    time_to_empty = battery_info.get("time to empty", "unknown")
    time_to_full = battery_info.get("time to full", "unknown")

    # Use calculated times if available as they're more accurate
    if 'calculated_remaining_time' in battery_info:
        time_to_empty = battery_info['calculated_remaining_time']
    if 'calculated_time_to_full' in battery_info:
        time_to_full = battery_info['calculated_time_to_full']

    energy_full = battery_info.get("energy-full", "unknown")
    energy_full_design = battery_info.get("energy-full-design", "unknown")
    energy_rate = battery_info.get("energy-rate", "unknown")
    voltage = battery_info.get("voltage", "unknown")
    power_now = battery_info.get("power_now", "unknown")
    cycle_count = battery_info.get("cycle_count", "unknown")
    temperature = battery_info.get("temperature", "unknown")
    system_temperature = battery_info.get("system_temperature", "unknown")

    # Calculate battery health if possible
    health_percentage = "unknown"
    if energy_full and energy_full_design and "Wh" in energy_full and "Wh" in energy_full_design:
        try:
            current = float(energy_full.split()[0])
            design = float(energy_full_design.split()[0])
            health_percentage = str(round((current / design) * 100))
        except (ValueError, IndexError):
            pass

    # Generate varied greetings
    greetings = [
        "Hey there! I've just analyzed your battery status.",
        "I've completed a comprehensive battery analysis for you.",
        "I've run a detailed diagnostic of your laptop's power system.",
        "Battery analysis complete! Here's what I found.",
        "I've finished analyzing your battery's current condition."
    ]

    # Generate varied phrases for battery percentage
    percentage_phrases = [
        f"Your battery is currently at {percentage} percent.",
        f"Battery level shows {percentage} percent remaining.",
        f"You have {percentage} percent battery left.",
        f"The battery is charged to {percentage} percent.",
        f"Your current charge level is {percentage} percent."
    ]

    # Generate varied phrases for battery state
    state_phrases = {
        "charging": [
            "Your laptop is currently charging.",
            "The battery is actively charging right now.",
            "Power is flowing into your battery at this moment.",
            "Your device is plugged in and accumulating charge.",
            "The battery is receiving power and charging up."
        ],
        "discharging": [
            "Your battery is currently discharging.",
            "Your laptop is running on battery power.",
            "You're using battery power right now.",
            "The battery is being drained at the moment.",
            "Your device is not connected to power and using its battery."
        ],
        "fully-charged": [
            "Your battery is fully charged.",
            "The battery has reached full capacity.",
            "You've got a full charge on your battery.",
            "Your laptop battery is at maximum charge.",
            "The battery is completely charged up."
        ]
    }

    # Generate varied phrases for power consumption
    power_phrases = []
    if energy_rate != "unknown" or power_now != "unknown":
        power_value = energy_rate if energy_rate != "unknown" else power_now
        power_value = power_value.replace("W", "watts")
        power_phrases = [
            f"Your current power consumption is {power_value}.",
            f"The battery is using {power_value} right now.",
            f"Your laptop is drawing {power_value} at the moment.",
            f"The current power usage is {power_value}.",
            f"Your system is consuming {power_value}."
        ]

    # Generate varied phrases for battery health
    health_phrases = []
    if health_percentage != "unknown":
        if int(health_percentage) > 80:
            health_phrases = [
                f"Your battery is in excellent condition at {health_percentage} percent of its original capacity.",
                f"Battery health is great! It's still at {health_percentage} percent of the original capacity.",
                f"Good news! Your battery is holding {health_percentage} percent of its design capacity.",
                f"The battery is performing well with {health_percentage} percent of its original capacity remaining.",
                f"Your battery has maintained {health_percentage} percent of its initial capacity, which is excellent."
            ]
        elif int(health_percentage) > 50:
            health_phrases = [
                f"Your battery is at {health_percentage} percent of its original capacity, which is still decent.",
                f"Battery health is showing some wear at {health_percentage} percent of original capacity.",
                f"Your battery has {health_percentage} percent of its design capacity left.",
                f"The battery has degraded somewhat, retaining {health_percentage} percent of initial capacity.",
                f"Battery health check shows {health_percentage} percent capacity compared to when it was new."
            ]
        else:
            health_phrases = [
                f"Your battery has significantly degraded to {health_percentage} percent of its original capacity.",
                f"Battery health is concerning, with only {health_percentage} percent of original capacity remaining.",
                f"I'm seeing significant battery wear, with {health_percentage} percent of design capacity left.",
                f"The battery has worn down to {health_percentage} percent of its initial capacity. You might want to consider a replacement.",
                f"Battery capacity has deteriorated to {health_percentage} percent of what it was when new."
            ]

    # Generate phrases for cycle count if available
    cycle_phrases = []
    if cycle_count != "unknown":
        if int(cycle_count) < 100:
            cycle_phrases = [
                f"Your battery has only been through {cycle_count} charge cycles, which is quite low.",
                f"With just {cycle_count} charge cycles, your battery is still relatively fresh.",
                f"The battery has experienced {cycle_count} charge cycles so far.",
                f"You've only put {cycle_count} charge cycles on this battery.",
                f"Battery charge cycle count is {cycle_count}, which is quite new."
            ]
        elif int(cycle_count) < 300:
            cycle_phrases = [
                f"Your battery has been through {cycle_count} charge cycles, which is moderate usage.",
                f"With {cycle_count} charge cycles, your battery has seen reasonable use.",
                f"The battery has experienced {cycle_count} charge cycles, which is within normal range.",
                f"You've put {cycle_count} charge cycles on this battery so far.",
                f"Battery charge cycle count is {cycle_count}, showing moderate usage."
            ]
        else:
            cycle_phrases = [
                f"Your battery has been through {cycle_count} charge cycles, which is quite high.",
                f"With {cycle_count} charge cycles, your battery has seen substantial use.",
                f"The battery has experienced {cycle_count} charge cycles, which is on the higher end.",
                f"You've put {cycle_count} charge cycles on this battery, indicating extensive use.",
                f"Battery charge cycle count is {cycle_count}, which suggests it's well-used."
            ]

    # Generate temperature phrases if available
    temp_phrases = []
    if temperature != "unknown":
        temp_value = temperature.replace('°C', '')
        if float(temp_value) < 30:
            temp_phrases = [
                f"Your battery temperature is {temperature}, which is quite cool.",
                f"The battery is running at a cool {temperature}.",
                f"Battery temperature reading is {temperature}, well within safe limits.",
                f"Your battery is keeping cool at {temperature}.",
                f"The current battery temperature is a comfortable {temperature}."
            ]
        elif float(temp_value) < 40:
            temp_phrases = [
                f"Your battery temperature is {temperature}, which is normal.",
                f"The battery is running at a normal temperature of {temperature}.",
                f"Battery temperature reading is {temperature}, which is within typical operating range.",
                f"Your battery temperature is at {temperature}, a typical operating temperature.",
                f"The current battery temperature is {temperature}, which is normal."
            ]
        else:
            temp_phrases = [
                f"Your battery temperature is {temperature}, which is on the warmer side.",
                f"The battery is running at {temperature}, which is warmer than ideal.",
                f"Battery temperature reading is {temperature}. You might want to check for airflow issues.",
                f"Your battery is running a bit hot at {temperature}.",
                f"The current battery temperature is {temperature}, which is elevated."
            ]

    # Generate voltage phrases if available
    voltage_phrases = []
    if voltage != "unknown":
        voltage_phrases = [
            f"Your battery is operating at {voltage}.",
            f"The current battery voltage is {voltage}.",
            f"Battery voltage reading shows {voltage}.",
            f"The power system is running at {voltage}.",
            f"Your battery voltage is currently {voltage}."
        ]

    # Compose the report
    report = []
    report.append(random.choice(greetings))

    if percentage != "unknown":
        report.append(random.choice(percentage_phrases))

    if state in state_phrases:
        report.append(random.choice(state_phrases[state]))

        # Add time estimates where applicable
        if state == "discharging" and time_to_empty != "unknown":
            time_phrases = [
                f"At this rate, you have about {time_to_empty} left.",
                f"Based on current usage, you've got roughly {time_to_empty} before you'll need to plug in.",
                f"I estimate about {time_to_empty} of battery life remaining.",
                f"Your battery should last approximately {time_to_empty} more.",
                f"You have around {time_to_empty} before your battery runs out."
            ]
            report.append(random.choice(time_phrases))
        elif state == "charging" and time_to_full != "unknown":
            time_phrases = [
                f"Your battery will be fully charged in approximately {time_to_full}.",
                f"It will take about {time_to_full} to reach a full charge.",
                f"The battery needs around {time_to_full} to charge completely.",
                f"I estimate about {time_to_full} until the battery is fully charged.",
                f"Your laptop should be fully charged in about {time_to_full}."
            ]
            report.append(random.choice(time_phrases))

    # Add power consumption info if available
    if power_phrases:
        report.append(random.choice(power_phrases))

    # Add battery health info if available
    if health_phrases:
        report.append(random.choice(health_phrases))

    # Add cycle count info if available
    if cycle_phrases:
        report.append(random.choice(cycle_phrases))

    # Add temperature info if available
    if temp_phrases:
        report.append(random.choice(temp_phrases))

    # Add voltage info if available
    if voltage_phrases:
        report.append(random.choice(voltage_phrases))

    return number_to_words(" ".join(report))


def battery_health(**kwargs):
    battery_info = get_battery_info()
    tts_text = generate_battery_report(battery_info)
    app.say(tts_text)


app.add_func_for_search(battery_health)

app.manager.add(
    app.Command(
        keywords=["check", "battery"],
        action="battery_health",
        synonyms={"check": ["analyze", "monitor", "test"]},
        tts=True
    )
)



