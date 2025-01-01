from datetime import datetime
from num2words import num2words
import requests
import random


number_dict = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "twenty one": 21, "twenty two": 22, "twenty three": 23, "twenty four": 24, "twenty five": 25,
    "twenty six": 26, "twenty seven": 27, "twenty eight": 28, "twenty nine": 29, "thirty": 30,
    "thirty one": 31, "thirty two": 32, "thirty three": 33, "thirty four": 34, "thirty five": 35,
    "thirty six": 36, "thirty seven": 37, "thirty eight": 38, "thirty nine": 39, "forty": 40,
    "forty one": 41, "forty two": 42, "forty three": 43, "forty four": 44, "forty five": 45,
    "forty six": 46, "forty seven": 47, "forty eight": 48, "forty nine": 49, "fifty": 50,
    "fifty one": 51, "fifty two": 52, "fifty three": 53, "fifty four": 54, "fifty five": 55,
    "fifty six": 56, "fifty seven": 57, "fifty eight": 58, "fifty nine": 59, "sixty": 60,
    "sixty one": 61, "sixty two": 62, "sixty three": 63, "sixty four": 64, "sixty five": 65,
    "sixty six": 66, "sixty seven": 67, "sixty eight": 68, "sixty nine": 69, "seventy": 70,
    "seventy one": 71, "seventy two": 72, "seventy three": 73, "seventy four": 74, "seventy five": 75,
    "seventy six": 76, "seventy seven": 77, "seventy eight": 78, "seventy nine": 79, "eighty": 80,
    "eighty one": 81, "eighty two": 82, "eighty three": 83, "eighty four": 84, "eighty five": 85,
    "eighty six": 86, "eighty seven": 87, "eighty eight": 88, "eighty nine": 89, "ninety": 90,
    "ninety one": 91, "ninety two": 92, "ninety three": 93, "ninety four": 94, "ninety five": 95,
    "ninety six": 96, "ninety seven": 97, "ninety eight": 98, "ninety nine": 99, "hundred": 100
}


def find_num(context):
    for num in number_dict.keys().__reversed__():
        if num in context:
            return number_dict.get(num)
    return None


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


API_KEY = "b7aa64e8dc28ccf8945c685151aed1fc"
CITY = "Aarhus"


def fetch_weather():
    """
    Fetch weather data from the OpenWeather API.

    Returns:
    dict: Parsed JSON response from the API.
    """
    url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return None


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
