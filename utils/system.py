import json
import spacy
import os
import subprocess
import logging
import random
import platform
import sys
import inspect
import re
import webbrowser
import time
from pathlib import Path
from importlib import import_module
from copy import deepcopy

import requests
import yaml
import g4f
from bs4 import BeautifulSoup
import lxml

import requests

from num2words import num2words
from plyer import notification

from data.constants import *

log = logging.getLogger("utils")

nlp = spacy.load("en_core_web_sm")


# --------------- Inspection Functions ---------------
def get_caller_dir():
    return os.path.dirname(inspect.stack()[1].filename)


def is_function_called_in_another(called, executed):
    source_code = inspect.getsource(executed)

    tree = ast.parse(source_code)

    visitor = FunctionCallVisitor(called.__name__)

    visitor.visit(tree)

    return visitor.is_called


def called_from():
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    caller_of_caller_frame = caller_frame.f_back

    function_name = caller_frame.f_code.co_name
    caller_function_name = caller_of_caller_frame.f_code.co_name

    caller_line_number = caller_of_caller_frame.f_lineno
    caller_filename = caller_of_caller_frame.f_code.co_filename

    log.info(
        f"'{function_name}' was called by {caller_function_name} on line {caller_line_number} in {caller_filename}.")


# --------------- Configuration Functions ---------------
def load_yaml(path: str):
    """
    Load YAML configuration from a file.

    Parameters:
    - path (str): The path to the YAML file.

    Returns:
    dict: Parsed YAML data.
    """
    caller = get_caller_dir()

    full_path = path if os.path.exists(path) else os.path.join(caller, path)

    if os.path.exists(full_path):
        with open(path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    else:
        log.warning(f"File {full_path} does not exist")


config = load_yaml(CONFIG_FILE)


def load_json(path: str):
    """
    Load JSON configuration from a file.

    Parameters:
    - path (str): The path to the JSON file.

    Returns:
    dict: Parsed JSON data.
    """
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)


def load_lang():
    if os.path.exists(LANG_FILE):
        with open(LANG_FILE, "r", encoding="utf-8") as file:
            return file.read()


def filter_lang_config(file, lang_prefix):
    """
    Filters the configuration for a specific language prefix. If a key contains a nested language dictionary,
    it returns the values associated with the specified language prefix directly under the key.

    :param file: The full config loaded from the YAML file
    :param lang_prefix: The language prefix to filter (e.g. 'ru', 'en')
    :return: Filtered config with values from the specified language prefix
    """

    def filter_recursive(data):
        filtered = {}
        for key, value in data.items():
            if isinstance(value, dict):
                if lang_prefix in value:
                    filtered[key] = value[lang_prefix]
                else:
                    nested_filtered = filter_recursive(value)
                    if nested_filtered:
                        filtered[key] = nested_filtered
            else:
                filtered[key] = value
        return filtered

    lang_config = filter_recursive(file)
    return lang_config


# --------------- System & Subprocess Functions ---------------

def set_caching_directory():
    home_dir = os.path.expanduser("~")

    cache_dir = os.path.join(home_dir, ".cache")

    stewart_dir = os.path.join(cache_dir, "stewart")

    if not os.path.exists(cache_dir):
        log.info(f"Creating .cache directory at {cache_dir}")
        os.makedirs(cache_dir)

    if not os.path.exists(stewart_dir):
        log.info(f"Creating caching directory at {stewart_dir}")
        os.makedirs(stewart_dir)
    else:
        log.info(f"Using existing caching directory at {stewart_dir}")

    return stewart_dir


def admin():
    current_platform = platform.system()

    if current_platform == "Windows":
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except (AttributeError, OSError, ctypes.WinError):
            return False
    elif current_platform in ["Linux", "Darwin"]:
        return os.geteuid() == 0
    else:
        raise NotImplementedError(f"Unsupported platform: {current_platform}")


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


def run_stdout(*args, shell: bool = False):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        shell=shell
    ).stdout


def system_setup():
    """
    Perform platform-specific system setup.
    Currently configured for Linux systems to start 'jack_control'.
    """
    current = platform.system()

    if current == "Linux":
        run("jack_control", "start")
        run("xhost", "+local:$USER")
        set_caching_directory()


def cleanup(directory, limit: int):
    if not os.path.isdir(directory):
        log.info(f"Failed to cleanup a directory: {directory}. It's not a directory")
        return

    files = [os.path.join(directory, file) for file in os.listdir(directory) if
             os.path.isfile(os.path.join(directory, file))]

    if len(files) > limit:
        files.sort(key=os.path.getctime, reverse=True)

        while len(files) > limit:
            try:
                os.remove(files[0])
                files.pop(0)
            except Exception as e:
                print(f"Error deleting file (cleanup) {last_created_file} in a {directory}: {e}")


def notify(title: str, message: str, timeout: int = 10):
    notification.notify(
        app_icon=f"{PROJECT_DIR}/data/images/stewart.png",
        app_name="Stewart",
        title=title,
        message=message,
        timeout=timeout,

    )


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
def issubset(list_of_lists1, list_of_lists2):
    for sublist2 in list_of_lists2:
        for sublist1 in list_of_lists1:
            if any(sublist2 == sublist1[i:i + len(sublist2)] for i in range(len(sublist1) - len(sublist2) + 1)):
                return True
    return False


def extract_links(text):
    markdown_pattern = r'\[([^\]]+)\]\((http[s]?://[^\)]+)\)'
    url_pattern = r'http[s]?://[^\s()]+(?:\([^\)]*\))?'

    markdown_links = re.findall(markdown_pattern, text)

    normal_links = re.findall(url_pattern, text)

    all_links = [link[1] for link in markdown_links] + normal_links

    return all_links


def extract_entities(text):
    doc = nlp(text)

    entities = [ent.text for ent in doc.ents]

    return entities


def remove_non_letters(input_string):
    cleaned_string = re.sub(r'[^a-zA-Z\s]', '', input_string)
    return cleaned_string


def normalize(text: str) -> str:
    """
    Normalize the input text by converting numbers to words, removing unwanted characters,
    reducing spaces, and converting to lowercase.

    Parameters:
    - text (str): The input text to normalize.

    Returns:
    str: Normalized text.
    """
    # Convert numbers to words
    text = numbers_to_strings(text)

    text = re.sub(r"[^a-zA-Z.\s]", "", text)

    text = text.lower()

    text = re.sub(r"\s+", " ", text)

    text = text.strip()

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


# --------------- Config Parsing & Handling Functions ---------------
def parse_config_answers(string, module=None):
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


def track_time(func, *args, **kwargs):
    """
    This function tracks the execution time of a given function.

    Parameters:
        func: The function to track.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the function execution and the time taken.
    """
    start_time = time.time()  # Record the start time
    result = func(*args, **kwargs)  # Execute the function
    end_time = time.time()  # Record the end time

    execution_time = end_time - start_time  # Calculate execution time
    return result, execution_time


def find_link(search):
    url = "https://www.google.com/search?"
    params = {'q': search}

    def fetch_first_link(a, symbol):
        params['q'] = params['q'].format(symbol)
        res = a.get(url, params=params, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36'
        })
        soup = BeautifulSoup(res.text, "lxml")
        link = soup.select_one("a:has(h3)")
        return link['href'] if link else "https://google.com/"

    with requests.Session() as s:
        webbrowser.open(fetch_first_link(s, search), autoraise=True)


def fetch_weather():
    params = {
        "lat": MY_CITY_LAT,
        "lon": MY_CITY_LON,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": config["lang"]["prefix"]
    }

    try:
        response = requests.get(OPENWEATHER_API, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None



