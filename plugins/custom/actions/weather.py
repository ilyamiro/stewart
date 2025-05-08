import random
import requests
import sys

from utils import numbers_to_strings, fetch_weather
from api import app


def generate_weather_sentence():
    data = fetch_weather()
    if not data:
        if app.lang == "en":
            return "I couldn't fetch the current weather, sir. Please try again later."
        elif app.lang == "ru":
            return "Я не смог получить текущую погоду, сэр. Пожалуйста, попробуйте позже."

    temperature = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    weather_description = data["weather"][0]["description"].capitalize()
    wind_speed = data["wind"]["speed"]

    if app.lang == "en":
        templates = []
        if "clear" in weather_description.lower():
            if temperature > 25:
                templates.append(
                    f"Wow, it's a scorcher! A clear sky and {temperature:.1f} degrees today. Feels like {feels_like:.1f} degrees – better grab your sunglasses and sunscreen! Winds are at {wind_speed} meters per second, so no breezes to cool you down.")
            elif temperature > 15:
                templates.append(
                    f"The sun's out and the sky's clear. It's a lovely {temperature:.1f} degrees, but it feels like {feels_like:.1f} degrees. Ideal weather for a walk outside, with winds just gently blowing at {wind_speed} meters per second.")
            elif temperature > 5:
                templates.append(
                    f"A beautiful clear sky, but it's a bit chilly at {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees, so you might want to layer up. The wind's making its presence known at {wind_speed} meters per second.")
            else:
                templates.append(
                    f"Clear skies, but it's cold out there! It's only {temperature:.1f} degrees, and it feels like {feels_like:.1f} degrees. The wind is kicking up at {wind_speed} meters per second, so don't forget your jacket!")
        elif "cloud" in weather_description.lower():
            if temperature > 20:
                templates.append(
                    f"Cloudy skies, but the temperature is nice at {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees though, so you might still want a light jacket. The wind is calm at {wind_speed} meters per second, so it's a good day for a stroll.")
            elif temperature > 10:
                templates.append(
                    f"Overcast today with {temperature:.1f} degrees, but it feels like {feels_like:.1f} degrees. The clouds are keeping the sun at bay, and the wind is blowing at {wind_speed} meters per second – nothing too strong.")
            else:
                templates.append(
                    f"Cloudy skies with a chilly {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees. The wind's picking up at {wind_speed} meters per second, so maybe stay inside with a hot drink!")
        elif "rain" in weather_description.lower():
            if temperature > 20:
                templates.append(
                    f"Don't forget your umbrella! It's {weather_description} with {temperature:.1f} degrees, but it feels like {feels_like:.1f} degrees. The wind's picking up a bit at {wind_speed} meters per second, so hold on tight!")
            elif temperature > 10:
                templates.append(
                    f"Rainy and mild at {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees, so maybe skip the shorts today. The wind's blowing at {wind_speed} meters per second – just enough to make things interesting.")
            else:
                templates.append(
                    f"Rain, rain, go away... It's {temperature:.1f} degrees and feels like {feels_like:.1f} degrees. Definitely a good day for a hot cup of tea, with winds of {wind_speed} meters per second making things a bit gloomy.")
        elif "snow" in weather_description.lower():
            if temperature > 0:
                templates.append(
                    f"Snow is falling and it's a bit warmer than usual at {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees, but still chilly. The wind is making snowflakes dance at {wind_speed} meters per second!")
            elif temperature > -5:
                templates.append(
                    f"Snowy and cold at {temperature:.1f} degrees, with a chilly {feels_like:.1f} degrees. Winds are whipping at {wind_speed} meters per second, so it's a perfect day for a snowball fight!")
            else:
                templates.append(
                    f"It's a winter wonderland out there with {temperature:.1f} degrees and {feels_like:.1f} degrees. Bundle up, because the wind's blowing at {wind_speed} meters per second – perfect for a hot cocoa indoors!")
        elif "thunderstorm" in weather_description.lower():
            if temperature > 25:
                templates.append(
                    f"Boom! A thunderstorm is brewing with a hot {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees. With wind speeds at {wind_speed} meters per second, I wouldn't stand too close to a tree!")
            elif temperature > 15:
                templates.append(
                    f"Thunderstorms rolling in at {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees, and the wind's blowing at {wind_speed} meters per second – it's going to get loud!")
            else:
                templates.append(
                    f"A storm is coming with {temperature:.1f} degrees and {feels_like:.1f} degrees. The wind's blowing at {wind_speed} meters per second, so stay indoors if you can. The thunder's really giving us a show!")
        elif "fog" in weather_description.lower():
            if temperature > 10:
                templates.append(
                    f"Everything's a little mysterious today with {weather_description}. The temperature's {temperature:.1f} degrees, but it feels like {feels_like:.1f} degrees. Winds are at a mild {wind_speed} meters per second – keeping things spooky.")
            elif temperature > 0:
                templates.append(
                    f"The fog's rolling in, making everything look eerie. It's {temperature:.1f} degrees, but it feels like {feels_like:.1f} degrees. Winds are whispering at {wind_speed} meters per second.")
            else:
                templates.append(
                    f"Foggy and cold out there at {temperature:.1f} degrees, and it feels like {feels_like:.1f} degrees. Wind speed's {wind_speed} meters per second – the perfect day to curl up with a book.")
        elif "haze" in weather_description.lower():
            if temperature > 25:
                templates.append(
                    f"Hot and hazy today with {temperature:.1f} degrees, feeling like {feels_like:.1f} degrees. Winds are calm at {wind_speed} meters per second, so it's a bit of a lazy day!")
            elif temperature > 15:
                templates.append(
                    f"The haze is giving everything a soft glow today. It's {temperature:.1f} degrees, and it feels like {feels_like:.1f} degrees. Wind's barely noticeable at {wind_speed} meters per second.")
            else:
                templates.append(
                    f"It's a hazy, cool day with {temperature:.1f} degrees. Feels like {feels_like:.1f} degrees, with the wind lazily blowing at {wind_speed} meters per second.")
        else:
            templates.append(
                f"Today's weather is {weather_description}. It's {temperature:.1f} degrees, but feels like {feels_like:.1f} degrees. Winds are moving at {wind_speed} meters per second – not too strong, but enough to make things feel a bit fresh.")
    elif app.lang == "ru":
        templates = []
        if "clear" in weather_description.lower():
            if temperature > 25:
                templates.append(
                    f"Ого, сегодня жарко! Ясное небо и {temperature:.1f} градусов. Ощущается как {feels_like:.1f} градусов – лучше взять солнцезащитные очки и крем! Ветер дует со скоростью {wind_speed} метров в секунду, так что прохлады не ждите.")
            elif temperature > 15:
                templates.append(
                    f"Солнце светит и небо чистое. Приятные {temperature:.1f} градусов, но ощущается как {feels_like:.1f} градусов. Идеальная погода для прогулки, с ветром, мягко дующим на скорости {wind_speed} метров в секунду.")
            elif temperature > 5:
                templates.append(
                    f"Прекрасное чистое небо, но немного прохладно при {temperature:.1f} градусах. Ощущается как {feels_like:.1f} градусов, так что, возможно, стоит одеться потеплее. Ветер даёт о себе знать на скорости {wind_speed} метров в секунду.")
            else:
                templates.append(
                    f"Чистое небо, но на улице холодно! Всего {temperature:.1f} градусов, и ощущается как {feels_like:.1f} градусов. Ветер усиливается до {wind_speed} метров в секунду, так что не забудьте куртку!")
        elif "cloud" in weather_description.lower():
            if temperature > 20:
                templates.append(
                    f"Облачное небо, но температура приятная – {temperature:.1f} градусов. Ощущается как {feels_like:.1f} градусов, так что вам может потребоваться легкая куртка. Ветер спокойный, {wind_speed} метров в секунду, так что хороший день для прогулки.")
            elif temperature > 10:
                templates.append(
                    f"Сегодня пасмурно, {temperature:.1f} градусов, но ощущается как {feels_like:.1f} градусов. Облака не пропускают солнце, а ветер дует со скоростью {wind_speed} метров в секунду – ничего слишком сильного.")
            else:
                templates.append(
                    f"Облачное небо и прохладные {temperature:.1f} градусов. Ощущается как {feels_like:.1f} градусов. Ветер усиливается до {wind_speed} метров в секунду, так что, возможно, стоит остаться дома с горячим напитком!")
        elif "rain" in weather_description.lower():
            if temperature > 20:
                templates.append(
                    f"Не забудьте зонтик! {weather_description} при {temperature:.1f} градусах, но ощущается как {feels_like:.1f} градусов. Ветер немного усиливается до {wind_speed} метров в секунду, так что держитесь крепче!")
            elif temperature > 10:
                templates.append(
                    f"Дождливо и тепло при {temperature:.1f} градусах. Ощущается как {feels_like:.1f} градусов, так что, возможно, сегодня стоит отказаться от шорт. Ветер дует со скоростью {wind_speed} метров в секунду – как раз достаточно, чтобы было интересно.")
            else:
                templates.append(
                    f"Дождь, дождь, уходи... {temperature:.1f} градусов и ощущается как {feels_like:.1f} градусов. Определенно хороший день для чашки горячего чая, с ветром {wind_speed} метров в секунду, делающим всё немного мрачным.")
        elif "snow" in weather_description.lower():
            if temperature > 0:
                templates.append(
                    f"Идёт снег, и температура немного выше обычного – {temperature:.1f} градусов. Ощущается как {feels_like:.1f} градусов, но всё равно прохладно. Ветер заставляет снежинки танцевать со скоростью {wind_speed} метров в секунду!")
            elif temperature > -5:
                templates.append(
                    f"Снежно и холодно при {temperature:.1f} градусах, с прохладными {feels_like:.1f} градусами. Ветер дует со скоростью {wind_speed} метров в секунду, так что идеальный день для снежной битвы!")
            else:
                templates.append(
                    f"На улице зимняя сказка с {temperature:.1f} градусами и {feels_like:.1f} градусами. Оденьтесь потеплее, потому что ветер дует со скоростью {wind_speed} метров в секунду – идеально для горячего какао дома!")
        elif "thunderstorm" in weather_description.lower():
            if temperature > 25:
                templates.append(
                    f"Бум! Гроза надвигается с жаркими {temperature:.1f} градусами. Ощущается как {feels_like:.1f} градусов. При скорости ветра {wind_speed} метров в секунду, я бы не стал стоять слишком близко к дереву!")
            elif temperature > 15:
                templates.append(
                    f"Грозы надвигаются при {temperature:.1f} градусах. Ощущается как {feels_like:.1f} градусов, и ветер дует со скоростью {wind_speed} метров в секунду – будет громко!")
            else:
                templates.append(
                    f"Надвигается буря с {temperature:.1f} градусами и {feels_like:.1f} градусами. Ветер дует со скоростью {wind_speed} метров в секунду, так что оставайтесь дома, если можете. Гром действительно устраивает нам шоу!")
        elif "fog" in weather_description.lower():
            if temperature > 10:
                templates.append(
                    f"Сегодня всё немного таинственно с {weather_description}. Температура {temperature:.1f} градусов, но ощущается как {feels_like:.1f} градусов. Ветер мягкий, {wind_speed} метров в секунду – сохраняет атмосферу загадочности.")
            elif temperature > 0:
                templates.append(
                    f"Туман надвигается, делая всё жутковатым. {temperature:.1f} градусов, но ощущается как {feels_like:.1f} градусов. Ветер шепчет со скоростью {wind_speed} метров в секунду.")
            else:
                templates.append(
                    f"Снаружи туманно и холодно, {temperature:.1f} градусов, и ощущается как {feels_like:.1f} градусов. Скорость ветра {wind_speed} метров в секунду – идеальный день, чтобы свернуться с книгой.")
        elif "haze" in weather_description.lower():
            if temperature > 25:
                templates.append(
                    f"Жарко и дымка сегодня, {temperature:.1f} градусов, ощущается как {feels_like:.1f} градусов. Ветер спокойный, {wind_speed} метров в секунду, так что это немного ленивый день!")
            elif temperature > 15:
                templates.append(
                    f"Дымка придаёт всему мягкое сияние сегодня. {temperature:.1f} градусов, и ощущается как {feels_like:.1f} градусов. Ветер едва заметен при {wind_speed} метров в секунду.")
            else:
                templates.append(
                    f"Сегодня дымка и прохладно, {temperature:.1f} градусов. Ощущается как {feels_like:.1f} градусов, с ветром, лениво дующим со скоростью {wind_speed} метров в секунду.")
        else:
            templates.append(
                f"Сегодняшняя погода: {weather_description}. {temperature:.1f} градусов, но ощущается как {feels_like:.1f} градусов. Ветер движется со скоростью {wind_speed} метров в секунду – не слишком сильно, но достаточно, чтобы чувствовалась свежесть.")

    return random.choice(templates)


def say_weather(**kwargs):
    weather_sentence = numbers_to_strings(generate_weather_sentence(), app.lang)
    app.say(weather_sentence)


def temperature(**kwargs):
    data = fetch_weather()
    temperature = round(data["main"]["temp"], 1)

    if app.lang == "en":
        responses = {
            "freezing": [
                f"Brrr! It's {temperature} degrees. Colder than a snowman's toes!",
                f"It's {temperature} degrees. Ice, ice, baby—stay warm out there!",
                f"At {temperature} degrees, it's officially frostbite season. Bundle up!"
            ],
            "cold": [
                f"It's {temperature} degrees. Definitely sweater weather!",
                f"With {temperature} degrees outside, you might need a coat—or two!",
                f"Brr! It's {temperature} degrees. Warm socks are a must today."
            ],
            "cool": [
                f"It's {temperature} degrees. A refreshing kind of cool.",
                f"At {temperature} degrees, it's a good day for a light jacket.",
                f"The temperature is {temperature} degrees. Comfortable but cool—grab a hoodie!"
            ],
            "mild": [
                f"It's {temperature} degrees. Perfect weather to step outside!",
                f"At {temperature} degrees, the weather's just right - enjoy it!",
                f"With {temperature} degrees, it's mild and lovely out there."
            ],
            "warm": [
                f"It's {temperature} degrees. Summer vibes incoming!",
                f"At {temperature} degrees, it's warm enough for some ice cream.",
                f"The temperature is {temperature} degrees. A sunny delight!"
            ],
            "hot": [
                f"Phew! It's {temperature} degrees. Like walking on the sun—stay cool!",
                f"At {temperature} degrees, it's hotter than your favorite spicy dish!",
                f"With {temperature} degrees, summer is in full blast—don't forget sunscreen!"
            ],
        }
    elif app.lang == "ru":
        responses = {
            "freezing": [
                f"Бррр! {temperature} градусов. Холоднее, чем пальцы снеговика!",
                f"Сейчас {temperature} градусов. Лёд, детка—оставайтесь в тепле!",
                f"При {temperature} градусах официально начинается сезон обморожений. Одевайтесь теплее!"
            ],
            "cold": [
                f"Сейчас {temperature} градусов. Определённо погода для свитера!",
                f"При {temperature} градусах на улице вам может понадобиться пальто—или два!",
                f"Брр! {temperature} градусов. Тёплые носки сегодня необходимы."
            ],
            "cool": [
                f"Сейчас {temperature} градусов. Освежающий вид прохлады.",
                f"При {temperature} градусах хороший день для лёгкой куртки.",
                f"Температура {temperature} градусов. Комфортно, но прохладно—возьмите худи!"
            ],
            "mild": [
                f"Сейчас {temperature} градусов. Идеальная погода, чтобы выйти на улицу!",
                f"При {temperature} градусах погода в самый раз - наслаждайтесь!",
                f"При {temperature} градусах на улице мягко и прекрасно."
            ],
            "warm": [
                f"Сейчас {temperature} градусов. Летние вибрации наступают!",
                f"При {temperature} градусах достаточно тепло для мороженого.",
                f"Температура {temperature} градусов. Солнечное наслаждение!"
            ],
            "hot": [
                f"Фух! {temperature} градусов. Как ходить по солнцу—оставайтесь в прохладе!",
                f"При {temperature} градусах жарче, чем ваше любимое острое блюдо!",
                f"При {temperature} градусах лето в полном разгаре—не забудьте солнцезащитный крем!"
            ],
        }

    if temperature <= 0:
        category = "freezing"
    elif 0 <= temperature <= 10:
        category = "cold"
    elif 11 <= temperature <= 15:
        category = "cool"
    elif 16 <= temperature <= 22:
        category = "mild"
    elif 23 <= temperature <= 30:
        category = "warm"
    else:
        category = "hot"

    response = random.choice(responses[category])
    app.say(numbers_to_strings(response))


app.add_func_for_search(temperature, say_weather)

if app.lang == "en":
    app.manager.add(
        app.Command(
            ["temperature", "outside"],
            "temperature",
            synonyms={
                "temperature": ["temp"],
            },
            tts=True,
        ),
        app.Command(
            ["weather"],
            "say_weather",
            tts=True
        )
    )
elif app.lang == "ru":
    app.manager.add(
        app.Command(
            ["температура", "улице"],
            "temperature",
            equivalents=[
                [
                    "сколько",
                    "градусов",
                    "улице"
                ]
            ],
            synonyms={
                "улице": [
                    "улица"
                    "снаружи"
                ],
                "градусов": [
                    "градус"
                ]
            },
            tts=True,
        ),
        app.Command(
            ["погода"],
            "say_weather",
            tts=True
        )
    )