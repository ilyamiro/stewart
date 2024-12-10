import subprocess
import re
import os
import logging
import time

from data.constants import CONFIG_FILE, PROJECT_FOLDER, ADB_DEVICE_IP
from utils import load_yaml, run, run_stdout
from api import app, tree

log = logging.getLogger("core-plugin")

app.add_dir_for_search("plugins/core/actions", include_private=False)

app.update_config(
    {
        "core": {
            "music-download": False,
            "no-multi-first-words": {
                "en": ["find", "write", "answer", "play"],
                "ru": ["найди", "найти", "запиши", "скажи", "ответь"]
            },
            "usb-default": ["linux foundation", "webcam", "network", "finger"]
        }
    }
)

first_words = []
commands = []


def first_words_hook(**kwargs):
    first_words.append(kwargs.get("definition")[0])


def command_list_hook(**kwargs):
    commands.append(" ".join(kwargs.get("definition")))


def synonyms_hook(definition, details):
    synonyms = details.get("synonyms")
    if synonyms:
        for synonim in synonyms.keys():
            tree.set_synonym(definition, synonim, synonyms[synonim])
            tree.recognizer_string += f" {synonim}"
            if synonyms[synonim] in first_words:
                first_words.append(synonim)


tree.add_commands_addition_callback(first_words_hook)
tree.add_commands_addition_callback(synonyms_hook)
tree.add_commands_addition_callback(command_list_hook)


def handle_simple(request):
    list_of_commands = []
    for command in commands:
        if command in request:
            list_of_commands.append(command.split())
            request = request.replace(command, " ")

    return list_of_commands


def handle_commands(request):
    list_of_commands, current_command = [], []
    split_request = request.split()
    for word in split_request:
        if word in first_words:
            if current_command:
                list_of_commands.append(current_command)
            if word in app.get_config()["plugins"]["core"]["no-multi-first-words"]:
                current_command = split_request[split_request.index(word):]
                list_of_commands.append(current_command)
                current_command = []
                break
            current_command = [word]
        else:
            if current_command:
                current_command.append(word)

    if current_command:
        list_of_commands.append(current_command)

    return list_of_commands


app.set_command_processor(handle_commands)
