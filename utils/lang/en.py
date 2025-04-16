import re
import threading
import requests
import random
from datetime import datetime

from num2words import num2words

from utils.system import fetch_weather


def find_num(text):
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100
    }

    numbers = []

    matches = re.findall(r'\b(' + '|'.join(word_to_num.keys()) + r')\b', text, re.IGNORECASE)
    for match in matches:
        numbers.append(word_to_num[match.lower()])

    matches = re.findall(r'\b([1-9][0-9]?)\b', text)
    for match in matches:
        numbers.append(int(match))

    return numbers


def format_time_passed(seconds):
    if seconds < 60:
        return f"{int(seconds)} seconds"
    elif seconds < 3600:
        return f"{int(seconds // 60)} minutes"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours} hours and {minutes} minutes"


def get_part_of_day():
    hour = datetime.now().hour
    if 0 < hour <= 3:
        return "night"
    elif 3 < hour <= 12:
        return "morning"
    elif 12 < hour <= 16:
        return "afternoon"
    elif 16 < hour <= 23:
        return "evening"


def get_weather_description():
    """
    Returns a weather description with an assistant's reaction for the day.

    Example: "It's sunny today, sir. A perfect day to get things done!"
    """
    weather_data = fetch_weather()
    if weather_data:
        weather_description = weather_data["weather"][0]["description"]

        reactions = {
            "clear sky": [
                "It's sunny today, sir. A perfect day to get things done!",
                "Sir, it’s clear skies today. Enjoy the sunshine!",
                "The sun is out, sir"
            ],
            "rain": [
                "It's raining today, sir. Don't forget your umbrella if you're heading out. ",
                "Rainy weather today, sir. A good day to stay productive indoors!",
                "It’s wet outside, sir. Perhaps a warm drink would suit you?"
            ],
            "clouds": [
                "It's cloudy today, sir",
                "Cloudy weather today, sir",
                "It’s overcast today, sir"
            ],
            "snow": [
                "Snowy conditions today, sir. Please stay warm.",
                "It’s snowing today, sir.",
                "Sir, the snow is falling outside"
            ],
            "thunderstorm": [
                "It’s stormy today, sir. Please stay safe if you're heading out.",
                "Thunderstorms are rolling in, sir. Shall I prepare an indoor activity list?",
                "Stormy weather today, sir. A good day to stay cozy indoors."
            ],
            "fog": [
                "Foggy weather today, sir. Visibility might be low outside.",
                "It’s quite foggy today, sir",
                "Sir, the fog is dense today. "
            ]
        }

        for key, response_list in reactions.items():
            if key in weather_description.lower():
                return random.choice(response_list)

        return f"The weather is {weather_description} today, sir. "
    else:
        return "I'm unable to fetch the weather information right now, sir."


def get_weather_temperature():
    """
    Returns a temperature description with an assistant's reaction.

    Example: "It's 8 degrees onboard, sir. A bit chilly, don't you think?"
    """
    weather_data = fetch_weather()
    if weather_data:
        temperature = round(weather_data["main"]["temp"])
        description = num2words(temperature)

        if temperature <= 0:
            return f"It's {description} degrees onboard, sir. Freezing cold! Stay warm."
        elif 0 < temperature <= 10:
            return f"It's {description} degrees onboard, sir. Quite chilly today."
        elif 10 < temperature <= 20:
            return f"It's {description} degrees onboard, sir. Mild weather, quite comfortable."
        elif 20 < temperature <= 30:
            return f"It's {description} degrees onboard, sir. Warm and pleasant."
        else:
            return f"It's {description} degrees onboard, sir. Quite hot today, stay hydrated."
    else:
        return "I'm unable to fetch the temperature information right now, sir."


def seconds_readable(total_seconds):
    days = total_seconds // 86400
    total_seconds %= 86400
    hours = total_seconds // 3600
    total_seconds %= 3600
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    readable_time = []
    if days > 0:
        readable_time.append(f"{num2words(days)} day{'s' if days > 1 else ''}")
    if hours > 0:
        readable_time.append(f"{num2words(hours)} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        readable_time.append(f"{num2words(minutes)} minute{'s' if minutes > 1 else ''}")
    if seconds > 0 or not readable_time:  # Include seconds if total is 0 or less
        readable_time.append(f"{num2words(seconds)} second{'s' if seconds > 1 else ''}")

    return " and ".join(readable_time)