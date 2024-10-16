# Standard Library Imports
import json
import ast
import os
import subprocess
import logging
import random
import platform
import sys
import inspect
import re
import time
from pathlib import Path
from importlib import import_module

# Third-Party Imports
import requests
import yaml
import g4f

from num2words import num2words
from plyer import notification

# Project Imports
from data.constants import CONFIG_FILE, PROJECT_FOLDER

# Initialize logging and notifications
log = logging.getLogger("utils")

# --------------- Classes ---------------


class FunctionCallVisitor(ast.NodeVisitor):
    def __init__(self, target_function_name):
        self.target_function_name = target_function_name
        self.is_called = False

    def visit_Call(self, node):
        # Check if the function name matches
        if isinstance(node.func, ast.Name) and node.func.id == self.target_function_name:
            self.is_called = True
        self.generic_visit(node)


class MonitoredVariable:
    def __init__(self, initial_value=None, callback=None):
        self._value = initial_value
        self._callback = callback  # Optional callback function

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        if self._callback:
            self._callback(new_value)  # Call the callback when value changes
        # print(f"Value changed from {self._value} to {new_value}")
        self._value = new_value

    def set_callback(self, new_callback):
        self._callback = new_callback


class ValueTracker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ValueTracker, cls).__new__(cls)
            cls._instance.value = [None, ]
        return cls._instance

    def set_value(self, text):
        if len(self.value) == 2:
            self.value.pop(0)
        self.value.append(text)

    def get_value(self):
        return self.value[-1]

    def reset(self):
        self.value = [None, ]


tracker = ValueTracker()


# --------------- Inspection Functions ---------------
def get_caller_dir():
    return os.path.dirname(inspect.stack()[1].filename)


def is_function_called_in_another(called, executed):
    # Get the source code of function2
    source_code = inspect.getsource(executed)

    # Parse the source code into an AST
    tree = ast.parse(source_code)

    # Create a visitor object to check for calls to function1
    visitor = FunctionCallVisitor(called.__name__)

    # Visit all the nodes in the AST
    visitor.visit(tree)

    # Return True if function1 is called in function2, False otherwise
    return visitor.is_called


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
        log.warning("Yaml file is non existent")


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
                # Check if the dict contains language-specific values
                if lang_prefix in value:
                    # If it's a language-specific dict, return the value for the given prefix
                    filtered[key] = value[lang_prefix]
                else:
                    # Recursively process the nested dictionary
                    nested_filtered = filter_recursive(value)
                    if nested_filtered:  # Only add if there are valid results
                        filtered[key] = nested_filtered
            else:
                filtered[key] = value
        return filtered

    lang_config = filter_recursive(file)
    return lang_config


# --------------- System & Subprocess Functions ---------------

def admin():
    current_platform = platform.system()

    if current_platform == "Windows":
        # Import ctypes only on Windows
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except (AttributeError, OSError, ctypes.WinError):
            return False
    elif current_platform in ["Linux", "Darwin"]:  # 'Darwin' is the identifier for macOS
        # Linux and macOS (root) check
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
        app_icon=f"{PROJECT_FOLDER}/data/images/stewart.png",
        app_name="Stewart",
        title=title,
        message=message,
        timeout=timeout
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
def remove_non_letters(input_string):
    # Use regex to replace all non-letter characters except spaces with an empty string
    cleaned_string = re.sub(r'[^a-zA-Z\s]', '', input_string)
    return cleaned_string


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
def find_plugins(directory):
    """
    Find all plugin directories under the main plugin folder.
    """
    skip_dirs = ["__pycache__"]
    subdirectories = []
    base_directory = Path(directory)  # Convert to a Path object

    for path in base_directory.rglob('*'):
        if path.is_dir() and path.name not in skip_dirs:
            # Append the relative path to the base directory
            subdirectories.append(str(path.relative_to(Path(PROJECT_FOLDER))))

    return subdirectories


def import_modules_from_directory(directory) -> None:
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


def import_plugins(directory):
    for plugin_dir in directory:
        # Import all modules from the plugin directory
        import_modules_from_directory(plugin_dir)


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
