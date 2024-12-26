import time

from api import app


def callback(request):
    app.say("would you like me to fetch the weather, sir?")


def fetch_weather(request):
    app.say("It's cloudy today, with eight degrees celsius outside, sir")


test_trigger = app.Trigger(["weather",], callback, synonyms={"weather": ["clouds", "nature"]})
test_timeline = app.Timeline([
    [
        test_trigger
    ],
    [
        app.Trigger(["yes"], fetch_weather),
    ]
])

test_scenario = app.Scenario(
    "test scenario",
    timeline=test_timeline,
    max_gap=3
)

app.add_scenario(test_scenario)