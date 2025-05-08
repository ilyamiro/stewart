import re
from num2words import num2words


def numbers_to_strings(text: str):
    all_numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    all_numbers = [int(num) if num.isdigit() else float(num) for num in all_numbers]

    for number in all_numbers:
        word = num2words(float(number), lang="ru")
        text = text.replace(str(number), word)

    return text
