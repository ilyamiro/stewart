import re
from num2words import num2words
from utils.system import fetch_weather


def numbers_to_strings(text: str):
    all_numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    all_numbers = [int(num) if num.isdigit() else float(num) for num in all_numbers]

    for number in all_numbers:
        word = num2words(float(number), lang="ru")
        text = text.replace(str(number), word)

    return text


def find_num(text):
    word_to_num = {
        "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5,
        "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
        "десять": 10, "одиннадцать": 11, "двенадцать": 12,
        "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
        "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
        "девятнадцать": 19, "двадцать": 20, "тридцать": 30,
        "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
        "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
        "сто": 100
    }

    numbers = []

    matches = re.findall(r'\b(' + '|'.join(word_to_num.keys()) + r')\b', text.lower())
    for match in matches:
        numbers.append(word_to_num[match])

    matches = re.findall(r'\b([1-9][0-9]?)\b', text)
    for match in matches:
        numbers.append(int(match))

    return numbers


def get_part_of_day():
    hour = datetime.now().hour
    if 0 < hour <= 3:
        return "доброй ночи"
    elif 3 < hour <= 12:
        return "доброе утро"
    elif 12 < hour <= 16:
        return "добрый день"
    elif 16 < hour <= 23:
        return "добрый вечер"


def get_weather_description():
    """
    Returns a weather description with an assistant's reaction for the day.
    """
    weather_data = fetch_weather()
    if weather_data:
        weather_description = weather_data["weather"][0]["description"]

        reactions = {
            "clear sky": [
                "Сегодня солнечно, сэр. Идеальный день, чтобы все успеть!",
                "Сэр, сегодня ясное небо. Наслаждайтесь солнечным светом!",
                "Солнце светит, сэр."
            ],
            "rain": [
                "Сегодня идет дождь, сэр. Не забудьте зонт, если пойдете на улицу.",
                "Дождливая погода сегодня, сэр. Отличный день, чтобы быть продуктивным дома!",
                "На улице мокро, сэр. Может быть, вам подойдет горячий напиток?"
            ],
            "clouds": [
                "Сегодня пасмурно, сэр.",
                "Облачно сегодня, сэр.",
                "Небо затянуто облаками, сэр."
            ],
            "snow": [
                "Сегодня снежно, сэр. Пожалуйста, оставайтесь в тепле.",
                "Идет снег, сэр.",
                "Сэр, на улице идет снег."
            ],
            "thunderstorm": [
                "Сегодня гроза, сэр. Пожалуйста, будьте осторожны, если собираетесь выйти.",
                "Приближается гроза, сэр. Подготовить список занятий в помещении?",
                "Грозовая погода сегодня, сэр. Хороший день, чтобы устроиться поуютнее дома."
            ],
            "fog": [
                "Сегодня туманно, сэр. Видимость может быть низкой.",
                "Сегодня довольно туманно, сэр.",
                "Сэр, туман сегодня густой."
            ]
        }

        for key, response_list in reactions.items():
            if key in weather_description.lower():
                return random.choice(response_list)

        return f"Погода сегодня {weather_description}, сэр."
    else:
        return "Я не могу получить информацию о погоде прямо сейчас, сэр."


def normalize(text: str) -> str:
    """
    Normalize the input text by converting numbers to words, removing unwanted characters,
    reducing spaces, and converting to lowercase.

    Parameters:
    - text (str): The input text to normalize.

    Returns:
    str: Normalized text.
    """
    text = numbers_to_strings(text)
    text = re.sub(r"[^a-zA-Z.\s]", "", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    return text