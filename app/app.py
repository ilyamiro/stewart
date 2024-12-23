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

from playsound import playsound

from audio.input import STT
from utils import *
from data.constants import CONFIG_FILE, PROJECT_FOLDER, PLUGINS_FOLDER

logging.getLogger("playsound").setLevel(logging.ERROR)

log = logging.getLogger("app")


class App:
    """
    Main running instance of an application behind the GUI (plan)
    For further reference, VA = Voice Assistant
    """

    def __init__(self, api):
        self.api = api

    def play_startup(self):
        if self.config["start-up"]["sound-enable"]:
            playsound(self.config["start-up"]["sound-path"], block=False)
            log.info("Played startup sound")
        if self.config["start-up"]["voice-enable"]:
            self.api.say(parse_config_answers(random.choice(self.config[f"start-up"]["answers"])))
            log.info("Played startup voice synthesis")

    @staticmethod
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # <!--------------- pre-init: start ---------------!>
            self.api.__run_hooks__(self.api.__pre_init_callbacks__)

            plugins = find_plugins(PLUGINS_FOLDER)
            import_plugins(plugins)

            log.debug(f"Imported plugins: {plugins}")

            self.config = filter_lang_config(load_yaml(CONFIG_FILE), self.api.lang)
            self.lang = self.api.lang

            log.info("Configuration file loaded")

            # play sounds
            self.play_startup()

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

        self.tree_init()

        log.info("Data tree initialized")

        self.history = []
        self.scenario_active = []

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
            self.recognition_thread.start()

            log.debug(f"Recognition thread started with name: {self.recognition_thread.daemon}")
        else:
            while True:
                self.process_trigger_no_voice(input("Input: "))

    def handle(self, request):
        self.history_update(request)
        self.scan_scenarios()

        if (not request or not self.remove_trigger_word(request)) and self.config["settings"]["trigger"]["trigger-mode"] != "disabled" and not any(self.scenario_active):
            self.api.say(parse_config_answers(self.config[f"answers"]["default"]))
        else:
            result, execution_time = track_time(lambda: self.api.manager.find(request))
            log.info(f"Command search time: {execution_time:.6f}")

            if len(result) == 1:
                command = result[0]
                if command.responses:
                    self.api.say(random.choice(command.responses))
                self.do(command)
            elif len(result) > 1:
                for command in result:
                    self.do(command)
            elif not result:
                self.api.__no_command_callback__(request)

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
                self.handle(result)
        else:
            self.handle(word)

    def process_trigger_no_voice(self, request):
        trigger, result = self.remove_trigger_word(request)
        if result != "blank":
            self.handle(result)
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
        if equivalents is None:
            equivalents = []

        initial = self.api.manager.Command(
            keywords=list(com),
            action=action,
            parameters=parameters,
            responses=responses,
            synonyms=synonyms
        )
        commands = [initial]

        for eq in equivalents:
            commands.append(initial.copy(eq))

        self.api.manager.add(*commands)

    def history_update(self, request):
        """
        Update history of requests
        """
        if len(self.history) > self.config["settings"]["max-history-length"]:
            self.history.pop(0)

        self.history.append(request)

    def scan_scenarios(self):
        for request in self.history:
            for scenario in self.api.scenarios:
                self.scenario_active.append(scenario.check_scenario(request, self.history))

    def do(self, command):
        """
        Start the action thread
        """
        action = self.find_action(command[0].action)
        thread = threading.Thread(target=action,
                                  kwargs={"command": command[0], "context": command[1]})
        thread.start()

    def find_action(self, name):
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
