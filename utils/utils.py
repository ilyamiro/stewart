import json
import os.path
import subprocess
import logging
import sys
import yaml
import re
from importlib import import_module

from num2words import num2words
from words2numsrus import NumberExtractor

extractor = NumberExtractor()

logger = logging.getLogger("utils")


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
                logger.info(f"Failed to import {module_name}: {e}")
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
        word = num2words(int(number), lang="ru")
        text = text.replace(str(number), word)

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


