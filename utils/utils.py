import json
import os.path
import subprocess
import logging
import random
import sys
import yaml
import re
import requests
from importlib import import_module

from num2words import num2words
import g4f

log = logging.getLogger("utils")


def yaml_load(path: str):
    if os.path.exists(path):
        with open(path) as file:
            return yaml.safe_load(file)


DIR = os.path.dirname(os.path.abspath(__file__))

config = yaml_load(os.path.dirname(DIR) + "/config.yaml")


def internet(host="https://google.com", timeout=3) -> bool:
    """
    check if there is an internet connection by trying to access the specified host.

    parameters:
    - host (str): The domain to check (default is "google.com").
    - timeout (int): The timeout for the request (default is 3 seconds).

    Returns:
    bool: True if the host is reachable, False otherwise.
    """

    try:
        requests.get(host, timeout=timeout)
        return True
    except requests.ConnectionError as e:
        log.info(f"Failed to establish internet connection with the host {host}: {e}")

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
                module_path = directory.replace("/", ".") + "." + module_name
                module = import_module(module_path)
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


def json_load(path: str):
    if os.path.exists(path):
        with open(path) as file:
            return json.load(file)


def numbers_to_strings(text: str):
    # Using regular expression to find all numbers in the string
    all_numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)

    # Converting the numbers from string to their respective data types
    all_numbers = [int(num) if num.isdigit() else float(num) for num in all_numbers]

    for number in all_numbers:
        word = num2words(int(number), lang="en")
        text = text.replace(str(number), " " + word)

    return text


def kelvin_to_c(k):
    return int(k - 273.15)


def gpt_request(query, messages, client, provider, model=g4f.models.default):
    print(query, messages, provider, model)
    return client.chat.completions.create(
        messages=[*messages, {"role": "user", "content": query}],
        provider=provider,
        stream=False,
        model=model
    ).choices[0].message.content


def parse_and_replace_config(string, module):
    pattern = re.compile(r"\[(.*?)]")

    matches = pattern.findall(string)

    for match in matches:
        if hasattr(module, match):
            func = getattr(module, match)
            if callable(func):
                string = string.replace(f'[{match}]', func())

    return string


def parse_config_answers(answers):
    return parse_and_replace_config(random.choice(answers), import_module(f"utils.text.{config.get('lang').get('prefix')}"))


def get_connected_usb_devices():
    defaults = config.get("command-spec").get("usb-default")

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


def import_all_from_module(module_name):
    # Dynamically import the module
    module = import_module(module_name)

    # Get all attributes from the module
    attributes = dir(module)

    # Filter out special attributes (those starting and ending with double underscores)
    public_attributes = [attr for attr in attributes if not attr.startswith('__')]

    # Import all public attributes into the global namespace
    for attr in public_attributes:
        globals()[attr] = getattr(module, attr)

