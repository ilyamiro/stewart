# Standard Library Imports
import json
import os
import subprocess
import logging
import random
import sys
import inspect
import re
from pathlib import Path
from importlib import import_module

# Third-Party Imports
import requests
import yaml
from num2words import num2words
import g4f
import gi

# Initialize Notification Module
gi.require_version('Notify', '0.7')
from gi.repository import Notify

# Project Imports
from data.constants import CONFIG_FILE, PROJECT_FOLDER

# Initialize logging and notifications
log = logging.getLogger("utils")
Notify.init("Stewart")


# --------------- Configuration Functions ---------------
def yaml_load(path: str):
    """
    Load YAML configuration from a file.

    Parameters:
    - path (str): The path to the YAML file.

    Returns:
    dict: Parsed YAML data.
    """
    if os.path.exists(path):
        with open(path) as file:
            return yaml.safe_load(file)


config = yaml_load(CONFIG_FILE)


def json_load(path: str):
    """
    Load JSON configuration from a file.

    Parameters:
    - path (str): The path to the JSON file.

    Returns:
    dict: Parsed JSON data.
    """
    if os.path.exists(path):
        with open(path) as file:
            return json.load(file)


# --------------- System & Subprocess Functions ---------------
def run(*args, stdout: bool = False):
    """
    Run a system command using subprocess.

    Parameters:
    - args: Command-line arguments for subprocess.
    - stdout (bool): If True, output is shown. Otherwise, it's suppressed.
    """
    subprocess.run(
        args,
        stdout=subprocess.DEVNULL if not stdout else None,
        stderr=subprocess.STDOUT
    )


def system_setup():
    """
    Perform platform-specific system setup.
    Currently configured for Linux systems to start 'jack_control'.
    """
    if sys.platform == "linux":
        run("jack_control", "start")
        run("xhost", "+local:$USER")


def cleanup(directory, limit: int):
    if not os.path.isdir(directory):
        log.info(f"Failed to cleanup a directory: {directory}. It's not a directory")
        return

    files = [os.path.join(directory, file) for file in os.listdir(directory) if
             os.path.isfile(os.path.join(directory, file))]

    if len(files) > limit:
        files.sort(key=os.path.getctime, reverse=True)

        last_created_file = files[0]
        try:
            os.remove(last_created_file)
        except Exception as e:
            print(f"Error deleting file (cleanup) {last_created_file} in a {directory}: {e}")


# --------------- Internet & System Functions ---------------
def internet(host="https://google.com", timeout=3) -> bool:
    """
    Check if the system has an active internet connection by attempting to reach a host.

    Parameters:
    - host (str): The URL to test connectivity (default is Google).
    - timeout (int): Timeout in seconds for the request.

    Returns:
    bool: True if the host is reachable, otherwise False.
    """
    try:
        requests.get(host, timeout=timeout)
        log.info("Network connection check: successful")
        return True
    except requests.ConnectionError as e:
        log.info(f"Failed to establish internet connection with the host {host}: {e}")
    return False


def get_capslock_state():
    """
    Get capslock state: ON/OFF
    :return:
    """
    if sys.platform.startswith("win"):
        import ctypes
        hllDll = ctypes.WinDLL("User32.dll")
        VK_CAPITAL = 0x14
        return hllDll.GetKeyState(VK_CAPITAL)
    elif sys.platform == "linux":
        capslock_state = subprocess.check_output("xset q | awk '/LED/{ print $10 }' | grep -o '.$'", shell=True).decode(
            "ascii")
        return True if capslock_state[0] == "1" else False


def clear():
    if sys.platform.startswith("win"):
        os.system("cls")
    else:
        print("\033c")


# --------------- Text Processing & Utility Functions ---------------
def numbers_to_strings(text: str):
    """
    Convert numbers found in the given text to their word representations.

    Parameters:
    - text (str): Input text containing numbers.

    Returns:
    str: Text with numbers converted to words.
    """
    all_numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    all_numbers = [int(num) if num.isdigit() else float(num) for num in all_numbers]

    for number in all_numbers:
        word = num2words(int(number), lang="en")
        text = text.replace(str(number), " " + word)

    return text


def kelvin_to_c(k):
    """
    Convert the temperature from Kelvin to Celsius.

    Parameters:
    - k (float): Temperature in Kelvin.

    Returns:
    int: Temperature in Celsius.
    """
    return int(k - 273.15)


def extract_number(input_string: str):
    """
    Extract the first number (or numbers) found in a string.

    Parameters:
    - input_string (str): The input string.

    Returns:
    int or tuple: Extracted number(s) from the string, or None if not found.
    """
    matches = re.findall(r'\d+', input_string)
    if matches:
        if len(matches) == 1:
            return int(matches[0])
        return tuple(map(int, matches))
    return None


# --------------- Module Management Functions ---------------
def import_modules_from_directory(directory):
    """
    Dynamically import all Python modules from a given directory.

    Parameters:
    - directory (str): The directory to search for modules.

    Returns:
    list: List of imported modules.
    """
    modules = []
    for filename in os.listdir(directory):
        if filename.endswith('.py'):
            module_name = filename[:-3]
            try:
                module_path = directory.replace("/", ".") + "." + module_name
                module = import_module(module_path)
                modules.append(module)
            except ImportError as e:
                log.info(f"Failed to import {module_name}: {e}")
    return modules


def import_functions_from_a_module(module):
    members = inspect.getmembers(module)
    functions = [member[0] for member in members if inspect.isfunction(member[1])]
    return functions


def import_all_from_module(module_name):
    """
    Import all public attributes from a given module into the global namespace.

    Parameters:
    - module_name (str): The module from which to import.
    """
    module = import_module(module_name)
    public_attributes = [attr for attr in dir(module) if not attr.startswith('__')]

    for attr in public_attributes:
        globals()[attr] = getattr(module, attr)


# --------------- GPT & AI Request Functions ---------------
def gpt_request(query, messages, client, provider, model=g4f.models.default):
    """
    Make a GPT-3 or GPT-4 request via a specified client and provider.

    Parameters:
    - query (str): The user's query.
    - messages (list): List of previous messages in the conversation.
    - client: The client to use for making the request.
    - provider: The provider to be used for the request.
    - model: Model to use for the request (default is g4f.models.default).

    Returns:
    str: The generated response from GPT.
    """
    return client.chat.completions.create(
        messages=[*messages, {"role": "user", "content": query}],
        provider=provider,
        stream=False,
        model=model
    ).choices[0].message.content


# --------------- Config Parsing & Handling Functions ---------------
def parse_and_replace_config(string, module=None):
    """
    Parse placeholders in a string and replace them with data from the configuration module.

    Parameters:
    - string (str): The input string containing placeholders.
    - module: The module containing replacement functions. If not provided, default to language-specific module.

    Returns:
    str: The modified string with placeholders replaced.
    """
    if not module:
        module = import_module(f"utils.lang.{config.get('lang').get('prefix')}")

    pattern = re.compile(r"\[(.*?)]")
    matches = pattern.findall(string)

    for match in matches:
        if hasattr(module, match):
            func = getattr(module, match)
            if callable(func):
                string = string.replace(f'[{match}]', func())

    return string


def parse_config_answers(answers):
    """
    Randomly select an answer and parse it to replace placeholders.

    Parameters:
    - answers (list): List of possible answers.

    Returns:
    str: Parsed answer with placeholders replaced.
    """
    return parse_and_replace_config(random.choice(answers))
