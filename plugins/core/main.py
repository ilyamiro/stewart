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
            "music-download": True,
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


def first_words_hook(definition, details):
    first_words.append(definition[0])


def command_list_hook(definition, details):
    commands.append(" ".join(definition))


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
    split_request = request.split()  # splitting the request string into a list
    for word in split_request:  # iterating over the request list
        if word in first_words:
            # if a word is one of the words that commands start with,
            # that we would count that as a start of a command
            if current_command:
                # if there already is a current command being counted,
                # the new first words means the new command starts, so we add a last one
                list_of_commands.append(current_command)
            if word in app.get_config()["plugins"]["core"]["no-multi-first-words"]:
                # if a word implies any words after it, like Google search,
                # then everything after that word should be counted as a command itself
                current_command = split_request[split_request.index(word):]  # get the remaining part of the request
                list_of_commands.append(current_command)  # add the last command to the list
                current_command = []
                break  # terminate the cycle as there could not be any commands after this one
            current_command = [word]  # as this is the first words appearance,
            # it means the new command should start.
        else:
            # if a current command is not finished:
            if current_command:
                current_command.append(word)  # add the next word

    if current_command:  # add the last command as there is no next command that could end it.
        list_of_commands.append(current_command)

    return list_of_commands


app.set_command_processor(handle_commands)
