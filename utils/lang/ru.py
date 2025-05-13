import re
from num2words import num2words


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
