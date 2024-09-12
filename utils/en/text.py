from datetime import datetime


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
