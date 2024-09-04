import json
import os.path
import subprocess
import logging
import sys
import yaml
import re
import requests
from importlib import import_module

from num2words import num2words
from words2numsrus import NumberExtractor
import g4f

extractor = NumberExtractor()

log = logging.getLogger("utils")



def internet(host="https://google.com", timeout=3):
    """
    check if there is an internet connection by trying to access the specified host.

    parameters:
    - host (str): The domain to check (default is "google.com").
    - timeout (int): The timeout for the request (default is 3 seconds).

    Returns:
    bool: True if the host is reachable, False otherwise.
    """
    urls = [host, f"http://{host}", f"https://{host}"]  # ensure the host is typed in correctly

    for url in urls:
        try:
            requests.get(url, timeout=timeout)
            return True
        except requests.ConnectionError as e:
            log.info(f"Failed to establish internet connection with the following error: {e}")

    return False


def import_modules_from_directory(directory):
    modules = []

    # List all files in the directory
    for filename in os.listdir(directory):
        # Check if the file is a Python file
        if filename.endswith('.py'):
            # Remove the .py extension to get the module name
            module_name = filename[:-3]
            # Import the module dynamically
            try:
                module = import_module(directory.replace("/", ".") + "." + module_name)
                modules.append(module)
            except ImportError as e:
                log.info(f"Failed to import {module_name}: {e}")
    return modules


def run(*args, stdout: bool = False):
    subprocess.run(
        args,
        stdout=subprocess.DEVNULL if not stdout else None,
        stderr=subprocess.STDOUT
    )


def system_setup():
    if sys.platform == "linux":
        run("jack_control", "start")


def yaml_load(path: str):
    if os.path.exists(path):
        with open(path) as file:
            return yaml.safe_load(file)


def json_load(path: str):
    if os.path.exists(path):
        with open(path) as file:
            return json.load(file)


def get_part_of_day(hour):
    if 3 <= hour < 12:
        return "доброе утро"
    elif 12 <= hour < 16:
        return "доброго дня"
    elif 16 <= hour < 23:
        return "доброго вечера"
    else:
        return "доброй ночи"


def get_hour_suffix(hour):
    if 11 < hour < 20:
        return "ов"
    else:
        last_digit = hour % 10
        if last_digit == 1:
            return ""
        elif 1 < last_digit < 5:
            return "а"
        else:
            return "ов"


def get_minute_suffix(minutes):
    if 10 < minutes < 20:
        return ""
    else:
        last_digit = minutes % 10
        if last_digit == 1:
            return "а"
        elif 1 < last_digit < 5:
            return "ы"
        else:
            return ""


def get_second_suffix(seconds):
    if 10 < seconds < 20:
        return ""
    else:
        last_digit = seconds % 10
        if last_digit == 1:
            return "а"
        elif 1 < last_digit < 5:
            return "ы"
        else:
            return ""


def get_currency_suffix(amount):
    last_two_digits = amount % 100
    last_digit = amount % 10

    if 10 < last_two_digits < 20:
        return "ей"
    elif last_digit == 1:
        return "ь"
    elif 1 < last_digit < 5:
        return "я"
    else:
        return "ей"


def get_degree_suffix(degrees):
    last_digit = degrees % 10

    if 10 < degrees < 20:
        return "ов"
    elif last_digit == 1:
        return ""
    elif 1 < last_digit < 5:
        return "а"
    else:
        return "ов"


def numbers_to_strings(text: str):
    # Using regular expression to find all numbers in the string
    all_numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)

    # Converting the numbers from string to their respective data types
    all_numbers = [int(num) if num.isdigit() else float(num) for num in all_numbers]

    for number in all_numbers:
        word = num2words(int(number), lang="en")
        text = text.replace(str(number), " " + word)

    return text


def replace_yo_with_e(input_string):
    return input_string.replace("ё", "е")


def kelvin_to_c(k):
    return int(k - 273.15)


def extract_number(input_string):
    matches = re.findall(r'\d+', input_string)

    if matches:
        if len(matches) == 1:
            return int(matches[0])
        else:
            return tuple(map(int, matches))
    else:
        return None


def find_num_in_list(lst):
    return extract_number(extractor.replace_groups(replace_yo_with_e(" ".join(lst))))


def find_num_in_string(lst):
    return extract_number(extractor.replace_groups(replace_yo_with_e(lst)))


def gpt_request(query, messages, client, provider=g4f.Provider.You):
    return client.chat.completions.create(
        messages=[*messages, {"role": "user", "content": query}],
        provider=provider,
        stream=False,
        model=g4f.models.default
    ).choices[0].message.content


def get_connected_usb_devices():
    defaults = ["linux foundation", "webcam", "network", "finger"]

    devices = []

    # Run the lsusb command and capture its output
    result = subprocess.run(['lsusb'], capture_output=True, text=True)

    # Extract the device names using sed
    device_names = subprocess.run(['sed', '-E', 's/^.*ID [0-9a-fA-F:]+ +//'], input=result.stdout, capture_output=True,
                                  text=True)

    # Store the output in a variable
    device_names_output = numbers_to_strings(device_names.stdout.strip().lower()).split("\n")

    for device in device_names_output:
        if not any(spec in device for spec in defaults):
            # If no word is found, add the phrase to the filtered list
            devices.append(device)

    return devices


