import datetime
import re

from words2numsrus import NumberExtractor

from .default import extract_number

extractor = NumberExtractor()


def replace_yo_with_e(input_string):
    return input_string.replace("ё", "е")


def get_part_of_day():
    hour = datetime.datetime.now().hour
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


def find_num_in_list(lst):
    return extract_number(extractor.replace_groups(replace_yo_with_e(" ".join(lst))))


def find_num_in_string(lst):
    return extract_number(extractor.replace_groups(replace_yo_with_e(lst)))



