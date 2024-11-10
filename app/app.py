# Standart library imports
import logging
import random
import sys
import threading
import time
import os
import json
import signal
import inspect
from datetime import datetime
from pathlib import Path

# Third-party imports
from playsound import playsound
import g4f.Provider
from g4f.client import Client as GPTClient

# Local imports
from audio.input import STT
from utils import *
from data.constants import CONFIG_FILE, PROJECT_FOLDER, PLUGINS_FOLDER, COMMANDS_FILE

# disable playsound logger
logging.getLogger("playsound").setLevel(logging.ERROR)

log = logging.getLogger("app")


class App:
    """
    Main running instance of an application behind the GUI (plan)
    For further reference, VA = Voice Assistant
    """

    def __init__(self, api, tree):
        self.api = api
        self.tree = tree

    def play_startup(self):
        if self.config["start-up"]["sound-enable"]:
            playsound(self.config["start-up"]["sound-path"], block=False)
            log.info("Played startup sound")
        if self.config["start-up"]["voice-enable"]:
            self.api.say(parse_config_answers(self.config[f"start-up"]["answers"]))
            log.info("Played startup voice synthesis")

    @staticmethod
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # <!--------------- pre-init: start ---------------!>
            self.api.__run_hooks__(self.api.__pre_init_callbacks__)

            import_plugins(find_plugins(PLUGINS_FOLDER))

            self.config = filter_lang_config(load_yaml(CONFIG_FILE), self.api.lang)
            self.lang = self.api.lang

            log.info("Configuration file loaded")

            # play sounds
            self.play_startup()

            # <!--------------- cleanup directories ---------------!>

            # cleanup(f"{PROJECT_FOLDER}/data/music", 10)

            # <!--------------- pre-init: end ---------------!>

            func(self, *args, **kwargs)

            # <!--------------- post-init: start ---------------!>
            self.api.__run_hooks__(self.api.__post_init_callbacks__)

            # plugins
            # <!--------------- post-init: end ---------------!>

        return wrapper

    @decorator
    def start(self, start_time):
        log.debug("App initialization started")

        self.trigger_timed_needed = self.config["settings"]["trigger"]["trigger-mode"] != "disabled"

        # data tree initializing
        self.tree_init()

        log.info("Data tree initialized")

        # history of requests
        self.history = []
        self.request_monitor = MonitoredVariable()

        if not self.config["settings"]["text-mode"]:
            # voice recognition
            self.stt = STT(self.api.lang)

            # restricting recognition by adding grammar made of commands
            if self.config["audio"]["stt"]["speech-mode-restricted"]:
                self.grammar_recognition_restricted_create()
                self.stt.recognizer = self.stt.set_grammar(f"{PROJECT_FOLDER}/data/grammar/grammar-{self.lang}.txt",
                                                           self.stt.create_new_recognizer())

            log.debug("Speech to text instance initialized")

        self.recognition_thread = None
        self.running = True

        self.api.__save_config__()

        log.debug("Finished app initialization")

        log.debug(f"Start up time: {time.time() - start_time:.6f}")

    def run(self):
        if not self.config["settings"]["text-mode"]:
            self.recognition_thread = threading.Thread(target=self.recognition)
            # starting the voice recognition
            self.recognition_thread.start()

            log.debug(f"Recognition thread started with name: {self.recognition_thread.daemon}")
        else:
            while True:
                self.process_trigger_no_voice(input("Input: "))

    def handle(self, request, trigger=None):
        # TODO make detailed comments
        tracker.reset()
        if (not request or not self.remove_trigger_word(request)) and self.config["settings"]["trigger"]["trigger-mode"] != "disabled":
            self.request_monitor.value = trigger

            self.api.say(parse_config_answers(self.config[f"answers"]["default"]))
        else:
            self.history_update(request)
            self.request_monitor.value = request

            total, exec_time = track_time(lambda: self.api.__command_processor__(request))

            log.info(f"Commands subdivision time: {exec_time:.6f}")
            log.debug(f"Total commands: {total}")  # TODO Revise

            if len(total) == 1:
                result, exec_time = track_time(lambda: self.find_command(total[0], request))
                log.info(f"Command tree search time: {exec_time:.6f}")
                if result:
                    result, exec_time = track_time(lambda: self.execute_commands([result]))
                    log.info(f"Command execution time: {exec_time:.6f}")
                else:
                    self.api.__no_command_callback__(request)
            elif len(total) > 1:
                commands_to_execute = []
                for command in total:
                    commands_to_execute.append(self.find_command(command, request))

                amount_of_command_actions = len([x for x in commands_to_execute if x is not None])
                if amount_of_command_actions > 1:
                    if not issubset(total, self.tree.__inside_tts_list__):
                        self.api.say(parse_config_answers(self.config[f"answers"]["multi"]))

                    self.execute_commands(commands_to_execute, multi=True)
                elif amount_of_command_actions == 1:
                    self.execute_commands(commands_to_execute)
                else:
                    self.api.__no_command_callback__(request)

            elif not total:
                self.api.__no_command_callback__(request)

    def find_command(self, command, full):
        result = self.tree.find_command(command)
        log.info(f"Execution parameters: {result}")  # TODO fix that log

        if result and not all(element is None for element in result):  # if the command was found, process it
            result = list(result)
            result.extend([command, full])  # a list can be extended

            return result
        else:
            return None

    def execute_commands(self, commands, multi: bool = False):
        for command in commands:
            if command[2] and not multi:
                self.api.say(parse_config_answers(command[2]))
            self.do(command)

    def recognition(self):
        """
        Voice recognition
        """
        while self.running:
            if self.stt.stream.is_active():
                for word in self.stt.listen():
                    self.process_trigger(word)

    def process_trigger(self, request):
        if self.trigger_timed_needed:
            trigger, result = self.remove_trigger_word(request)
            if result != "blank":
                if self.config["settings"]["trigger"]["trigger-mode"] == "timed":
                    self.trigger_timed_needed = False
                    self.trigger_counter(self.config["trigger"]["trigger-time"])
                self.handle(result, trigger)
        else:
            self.handle(word)

    def process_trigger_no_voice(self, request):
        trigger, result = self.remove_trigger_word(request)
        if result != "blank":
            self.handle(result, trigger)
        else:
            self.handle(request)

    def remove_trigger_word(self, request):
        """
        Removes trigger words from the input
        """
        for trigger in self.config["settings"]["trigger"][f"triggers"]:
            if trigger in request:
                request = " ".join(request.split(trigger)[1:])[1:]
                return trigger, request
        return "blank", "blank"

    def trigger_counter(self, times):
        trigger_word_countdown_thread = threading.Timer(times, self.trigger_timed_needed)
        trigger_word_countdown_thread.start()
        log.info("Trigger countdown started")

    def trigger_change(self):
        self.trigger_timed_needed = True
        log.info("Trigger countdown ended")

    def tree_init(self):
        data = filter_lang_config(self.config["commands"], self.lang)

        commands = data["default"]
        commands_repeat = data["repeat"]

        for command in commands:
            equiv = command.get(f'equivalents', [])
            if equiv:
                for eq in equiv:
                    equiv[equiv.index(eq)] = tuple(eq)
            self.add_command(
                tuple(command[f"command"]),
                command["action"],
                command.get("parameters", {}),
                command.get(f"responses", {}),
                command.get(f"synonyms", {}),
                equiv,
                command.get("inside_tts", False)
            )

        for repeat in commands_repeat:
            for key in repeat[f"links"]:
                self.add_command(
                    (*repeat.get(f"command"), key),
                    repeat.get("action"),
                    {repeat.get("parameter"): repeat.get(f"links").get(key)},
                    [],
                    repeat.get(f"synonyms"),
                )

    def add_command(self, com: tuple, action: str, parameters: dict = None, responses: list = None,
                    synonyms: dict = None, equivalents: list = None, inside_tts: bool = False):
        self.tree.add_commands(
            {com: {"action": action, "parameters": parameters, "responses": responses, "synonyms": synonyms,
                   "equivalents": equivalents, "inside_tts": inside_tts}})

    def history_update(self, request):
        """
        Update history of requests
        """
        timestamp = datetime.now().isoformat()  # Get a timestamp
        new_event = {"timestamp": timestamp, "request": request}

        if len(self.history) > self.config["settings"]["max-history-length"]:
            self.history.pop(0)

        self.history.append(new_event)

    def do(self, request):
        """
        Start the action thread
        """
        func = self.find_exec(request[0])
        thread = threading.Thread(target=func,
                                  kwargs={"parameters": request[1], "command": request[3],
                                          "request": request[4]})
        thread.start()

    def find_exec(self, name):
        """
        Find a module that has a function that corresponds to an action that has to be done
        """
        if name in self.api.__search_functions__.keys():
            log.info(f"Action found: {name}")
            return self.api.__search_functions__.get(name)
        elif name in dir(self):
            return getattr(self, name)

    def grammar_recognition_restricted_create(self):
        """
        Creates a file of words that are used in commands
        This file is used for a vosk speech-to-text model to speed up the recognition speed and quality
        """
        with open(f"{PROJECT_FOLDER}/data/grammar/grammar-{self.lang}.txt", "w") as file:
            file.write('["' + " ".join(self.config["settings"]["trigger"].get(f"triggers")))
            file.write(self.config["audio"]["stt"].get(f"restricted-add-line"))
            file.write(self.tree.recognizer_string + '"]')

    # below methods are actions that need access to the main app instance
    # <!--------------------------------------------------------------------!>

    def grammar_restrict(self, **kwargs):
        """
        An action function inside an app class that enables or disables 'improved but limited' speech recognition
        """
        match kwargs["parameters"]["way"]:
            case "on":
                self.stt.recognizer = self.stt.create_new_recognizer()
            case "off":
                self.stt.recognizer = self.stt.set_grammar(
                    f"{PROJECT_FOLDER}/data/grammar/grammar-{self.lang}.txt",
                    self.stt.create_new_recognizer())

    def repeat(self, **kwargs):
        """
        An action function inside an app class that repeat an action performed the last time
        """
        self.handle(self.history[-1].get("request"))

    def stop(self, **kwargs):
        self.running = False
        os.kill(os.getpid(), signal.SIGKILL)

    def protocol(self, **kwargs):
        for command in kwargs["parameters"]["protocol"]:
            self.find_exec(command["action"])(parameters=command["parameters"])
