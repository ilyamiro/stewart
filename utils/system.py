import json
import os
import subprocess
import logging
import random
import shutil
import platform
import sys
import inspect
import re
import webbrowser
import time
from pathlib import Path
from importlib import import_module
from copy import deepcopy

import yaml
import urllib.parse

from data.constants import *

def num2words(*args, **kwargs):
    from num2words import num2words as _num2words
    return _num2words(*args, **kwargs)

log = logging.getLogger("utils")


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


LANGUAGE_ALIASES = {
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
    "русский": "ru",
    "en": "en",
    "eng": "en",
    "english": "en",
    "en_us": "en",
    "en_gb": "en",
    "es": "es",
    "spanish": "es",
    "fr": "fr",
    "french": "fr",
    "de": "de",
    "german": "de",
    "it": "it",
    "italian": "it",
}


def normalize_lang(lang: str) -> str:
    """Normalizes language name or code to a standardized 2-letter code (e.g. 'russian' -> 'ru')."""
    if not lang:
        return "en"
    clean = lang.strip().lower()
    return LANGUAGE_ALIASES.get(clean, clean)


def load_lang() -> str:
    env_lang = os.environ.get("STEWART_LANG")
    if env_lang:
        return normalize_lang(env_lang)

    for idx, arg in enumerate(sys.argv):
        if arg in ("--lang", "-l") and idx + 1 < len(sys.argv):
            return normalize_lang(sys.argv[idx + 1])
        if arg.startswith("--lang="):
            return normalize_lang(arg.split("=", 1)[1])

    from data.constants import get_lang_file
    lang_file = get_lang_file()
    if lang_file and os.path.exists(lang_file):
        try:
            with open(lang_file, "r", encoding="utf-8") as file:
                val = file.read().strip()
                if val:
                    return normalize_lang(val)
        except Exception:
            pass

    from data.constants import CONFIG_FILE
    if CONFIG_FILE and os.path.exists(CONFIG_FILE):
        try:
            import yaml
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                cfg = yaml.safe_load(file)
                if cfg and "lang" in cfg and "prefix" in cfg["lang"]:
                    return normalize_lang(cfg["lang"]["prefix"])
        except Exception:
            pass

    return "en"


def set_lang(lang: str) -> str:
    """Permanently sets the active language in USER_CONFIG_DIR / 'lang.txt'."""
    from data.constants import USER_CONFIG_DIR
    normalized = normalize_lang(lang)
    os.makedirs(USER_CONFIG_DIR, exist_ok=True)
    target = USER_CONFIG_DIR / "lang.txt"
    with open(target, "w", encoding="utf-8") as file:
        file.write(f"{normalized}\n")
    return str(target)


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
    """
    if platform.system() != "Linux":
        return

    if shutil.which("xhost") and os.environ.get("DISPLAY"):
        try:
            subprocess.run(["xhost", f"+local:{os.environ['USER']}"], check=True)
        except subprocess.CalledProcessError as e:
            log.info(f"Warning: Failed to run xhost: {e}")
    else:
        log.info("xhost not available or not running under X11/XWayland; skipping xhost setup.")


def notify(title: str, message: str, timeout: int = 10):
    try:
        from plyer import notification
        notification.notify(
            app_icon=f"{PROJECT_DIR}/data/images/stewart.png",
            app_name="Stewart",
            title=title,
            message=message,
            timeout=timeout,
        )
    except Exception as e:
        log.warning(f"Could not display notification: {e}")


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
        import requests
        requests.get(host, timeout=timeout)
        log.info("Network connection check: successful")
        return True
    except Exception as e:
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



def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    sanitized = sanitized.strip()
    return sanitized


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


def remove_non_letters(input_string):
    cleaned_string = re.sub(r'[^a-zA-Z\s]', '', input_string)
    return cleaned_string


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
    start_time = time.time()
    result = func(*args, **kwargs)
    end_time = time.time()

    execution_time = end_time - start_time
    return result, execution_time


def find_link(search):
    import requests
    from bs4 import BeautifulSoup
    url = "https://html.duckduckgo.com/html/"
    params = {'q': search}

    def fetch_first_link(session):
        res = session.post(url, data=params, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36'
        })
        soup = BeautifulSoup(res.text, "lxml")
        link = soup.select_one('.result__a')
        return link['href'] if link else "https://duckduckgo.com/"

    with requests.Session() as s:
        fetched = fetch_first_link(s)
        webbrowser.open(fetched, autoraise=True)


def fetch_weather():
    import json
    import os
    import shutil
    import subprocess
    import time
    from pathlib import Path

    serpantinum_cache = Path.home() / ".cache/serpantinum/weather/weather.json"
    data = None
    if serpantinum_cache.exists():
        try:
            mtime = os.path.getmtime(serpantinum_cache)
            if time.time() - mtime < 7200:
                with open(serpantinum_cache, "r", encoding="utf-8") as f:
                    data = json.load(f)
        except Exception:
            data = None

    if not data and shutil.which("serpantinum"):
        try:
            res = subprocess.run(
                ["serpantinum", "weather", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
        except Exception:
            data = None

    if data and "current_temp" in data:
        try:
            temp = float(data.get("current_temp", 0.0))
            forecast0 = (data.get("forecast") or [{}])[0]
            feels_like = float(forecast0.get("feels_like", temp))
            wind = float(forecast0.get("wind", 0.0))
            humidity = float(forecast0.get("humidity", 50.0))
            temp_min = float(forecast0.get("min", temp))
            temp_max = float(forecast0.get("max", temp))
            raw_desc = str(forecast0.get("desc", "Clear")).strip()
            desc_lower = raw_desc.lower()

            if any(w in desc_lower for w in ("cloud", "облач", "пасмур")):
                weather_desc = "clouds"
            elif any(w in desc_lower for w in ("rain", "дожд")):
                weather_desc = "rain"
            elif any(w in desc_lower for w in ("snow", "снег")):
                weather_desc = "snow"
            elif any(w in desc_lower for w in ("storm", "гроза")):
                weather_desc = "thunderstorm"
            elif any(w in desc_lower for w in ("mist", "fog", "туман")):
                weather_desc = "fog"
            elif any(w in desc_lower for w in ("sun", "clear", "солн", "ясн")):
                weather_desc = "clear sky"
            else:
                weather_desc = raw_desc.lower()

            return {
                "main": {
                    "temp": temp,
                    "feels_like": feels_like,
                    "temp_min": temp_min,
                    "temp_max": temp_max,
                    "humidity": humidity,
                },
                "weather": [
                    {
                        "description": weather_desc,
                        "main": raw_desc,
                    }
                ],
                "wind": {
                    "speed": wind,
                }
            }
        except Exception:
            pass

    import requests
    params = {
        "lat": MY_CITY_LAT,
        "lon": MY_CITY_LON,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "en"
    }

    try:
        response = requests.get(OPENWEATHER_API, params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

