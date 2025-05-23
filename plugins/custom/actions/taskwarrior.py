import subprocess
import json
from datetime import datetime
from num2words import num2words
import math

from api import app
from utils import import_utils

import_utils(app.lang, globals())


def time_left(due_time: str) -> str:
    if not due_time:
        due_time = datetime.now()
    due = datetime.strptime(due_time, "%Y%m%dT%H%M%SZ")
    now = datetime.now()

    time_diff = due - now
    seconds_left = time_diff.total_seconds()

    is_past = seconds_left < 0
    seconds_left = abs(seconds_left)

    days_left = math.floor(seconds_left / (24 * 3600))
    hours_left = math.floor((seconds_left % (24 * 3600)) / 3600)
    minutes_left = math.floor((seconds_left % 3600) / 60)

    if days_left > 0:
        result = f"due in {num2words(days_left)} day{'s' if days_left > 1 else ''}"
    elif hours_left > 0:
        result = f"due in {num2words(hours_left)} hour{'s' if hours_left > 1 else ''}"
    elif minutes_left > 0:
        result = f"due in {num2words(minutes_left)} minute{'s' if minutes_left > 1 else ''}"
    else:
        result = "due in less than a minute"

    if is_past:
        result = result.replace("due in", "that was due")
        result += " ago"

    return result


def fetch_tasks():
    result = subprocess.run(["task", "export"], capture_output=True, text=True)

    if result.returncode == 0:
        tasks = json.loads(result.stdout)
        output = []
        for task in tasks:
            if task.get("id") != 0:
                output.append(task)

        return output


def tell_task(**kwargs):
    result = fetch_tasks()
    if not result:
        app.say("You don't have any active tasks, sir")
    else:
        beginning = "You have the following tasks"
        n = 1
        for task in result:
            beginning += f". {num2words(n)}. " + normalize(task.get("description")) + " " + time_left(task.get("due"))
            n += 1
        app.say(beginning)


def count_task(request):
    result = fetch_tasks()
    if not result:
        app.say("You don't have any active tasks, sir")
    else:
        app.say(f"You have {num2words(len(result))} active tasks, sir")


app.add_func_for_search(tell_task)

main_timeline = None

if app.lang == "en":
    app.manager.add(
        app.Command(
            keywords=["tell", "task"],
            action="tell_task",
            synonyms={"task": ["problem", "tasks"], },
            equivalents=[["what", "task"]],
            tts=True
        )
    )

    main_timeline = app.Timeline([
        [
            app.Trigger(["tell", "task"], equivalents=[["what", "task"]], synonyms={"task": ["problem", "tasks"], })
        ],
        [
            app.Trigger(["how", "many",], synonyms={"many": ["much"]}, callback=count_task)
        ]
    ])

elif app.lang == "ru":
    app.manager.add(
        app.Command(
            keywords=["список", "задач"],
            action="tell_task",
            synonyms={"задач": ["проблем", "заданий"], },
            tts=True
        )
    )

    main_timeline = app.Timeline([
        [
            app.Trigger(["список", "задач"], synonyms={"задач": ["проблем", "заданий"], })
        ],
        [
            app.Trigger(["сколько", ], synonyms={"сколько": ["количество"], }, callback=count_task)
        ]
    ])


scenario = app.Scenario("taskwarrior", main_timeline, max_gap=1)

app.add_scenario(scenario)

