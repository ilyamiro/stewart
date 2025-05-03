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

from utils import *
from data.constants import CONFIG_FILE, PROJECT_DIR, PLUGINS_DIR

log = logging.getLogger("app")


class App:
    def __init__(self, api):
        self.api = api

    @staticmethod
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            plugins = find_plugins(PLUGINS_DIR)
            import_plugins(plugins)

            log.debug(f"Imported plugins: {plugins}")

            self.api.__run_hooks__(self.api.__pre_init_callbacks__)

            log.debug(f"Ran {len(self.api.__pre_init_callbacks__)} pre-init hooks: {self.api.__pre_init_callbacks__}")

            self.config = self.api.config
            self.lang = self.api.lang

            log.info("Configuration file loaded")

            func(self, *args, **kwargs)

            self.api.__run_hooks__(self.api.__post_init_callbacks__)

            log.debug(f"Ran {len(self.api.__post_init_callbacks__)} post-init hooks: {self.api.__post_init_callbacks__}")

            self.api.add_func_for_search(self.protocol, self.stop, self.repeat, self.grammar_restrict, self.sleep)

        return wrapper

    @decorator
    def start(self, start_time):
        log.debug("App initialization started")

        self.trigger_timed_needed = self.config["settings"]["trigger"]["trigger-mode"] != "disabled"

        self.tree_init()

        log.debug(f"Active scenarios: {[scenario.name for scenario in self.api.scenarios]}")

        self.scenario_active = []

        # self.api.__save_config__()

        log.debug("Finished app initialization")

        log.debug(f"Start up time: {time.time() - start_time:.6f}")

    def run(self, stt=None, last_time=None):
        self.running = True

        if not self.config["settings"]["text-mode"]:
            self.stt = stt
            self.last_time = time.time() if not last_time else last_time

            if self.config["audio"]["stt"]["speech-mode-restricted"]:
                self.grammar_recognition_restricted_create()
                self.stt.recognizer = self.stt.set_grammar(f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt",
                                                           self.stt.create_new_recognizer())

            log.debug("Speech to text instance initialized")

            self.recognition()
        else:
            while self.running:
                self.process_trigger_no_voice(input("Input: "))

    def recognition(self):
        threshold = int(config["settings"]["inactivity-threshold"])
        while self.running:
            if time.time() - self.last_time > threshold:
                log.debug(
                    f"Going into sleep mode due to inactivity for {threshold} seconds (~{threshold / 60} minutes)")
                self.running = False
            data = self.stt.stream.read(4000, exception_on_overflow=False)
            for word in self.stt.listen(data):
                self.process_trigger(word)

    def handle(self, request):
        self.api.eventLogger.record(self.api.Event(
            "user_request",
            {"request": request}
        ))

        self.scan_scenarios(request)

        if (not request or not self.remove_trigger_word(request)) and self.config["settings"]["trigger"]["trigger-mode"] != "disabled" and not self.scenario_active:
            answer = random.choice(self.config[f"answers"]["default"])
            self.api.say(parse_config_answers(answer))

            self.api.eventLogger.record(self.api.Event(
                "wake_word_used",
                {"answer": answer}
            ))
        else:
            result, execution_time = track_time(lambda: self.api.manager.find(request))
            if result:
                self.last_time = time.time()

                result_visual = {" ".join(cmd[0].keywords): cmd[1] for cmd in result}
                log.info(f"Command search time: {execution_time:.6f}")
                log.debug(f"Recognized commands: {result_visual}")

                answer = None

                if len(result) == 1:
                    command = result[0]
                    if command[0].responses and not command[0].tts:
                        answer = random.choice(command[0].responses)
                    elif not command[0].responses and not command[0].tts:
                        answer = random.choice(self.config["answers"]["multi"])

                    self.api.say(answer)

                    self.api.eventLogger.record(self.api.Event(
                        "command_detected",
                        {
                            "user_request": request,
                            "commands": result_visual,
                        }
                    ))

                    self.do(command)
                elif len(result) > 1:
                    if all(not command[0].tts for command in result):
                        answer = random.choice(self.config["answers"]["multi"])
                        self.api.say(answer)

                        self.api.eventLogger.record(self.api.Event(
                            "command_detected",
                            {
                                "user_request": request,
                                "commands": result_visual,
                            }
                        ))
                    for command in result:
                        self.do(command)

            elif not result and not self.scenario_active:
                self.api.__no_command_callback__(context=request, history=self.api.eventLogger.history)

        self.api.eventLogger.length(self.config["settings"]["max-history-length"])

    def process_trigger(self, request):
        if self.trigger_timed_needed:
            trigger, result = self.remove_trigger_word(request)
            if result != "blank":
                if self.config["settings"]["trigger"]["trigger-mode"] == "timed":
                    self.trigger_timed_needed = False
                    self.trigger_counter(int(self.config["settings"]["trigger"]["trigger-time"]))
                self.handle(result)
        else:
            self.handle(request)

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
        commands = self.config["commands"]["default"]
        commands_repeat = self.config["commands"]["repeat"]

        for command in commands:
            self.add_command(
                command[f"command"],
                command["action"],
                command.get("parameters", {}),
                command.get(f"responses", {}),
                command.get(f"synonyms", {}),
                command.get("equivalents", []),
                command.get("tts", False),
                command.get("continues", False)
            )

        for repeat in commands_repeat:
            for key in repeat[f"links"]:
                add = [key,] if key.count(" ") == 0 else key.split()
                self.add_command(
                    [*repeat.get(f"command"), *add],
                    repeat.get("action"),
                    {repeat.get("parameter"): repeat.get(f"links").get(key)},
                    [],
                    repeat.get(f"synonyms"),
                )

        log.info("Command manager initialized")

    def add_command(self, com: list, action: str, parameters: dict = None, responses: list = None,
                    synonyms: dict = None, equivalents: list = None, tts: bool = False, continues: bool = False):
        if equivalents is None:
            equivalents = []

        command = self.api.manager.Command(
            keywords=com,
            action=action,
            parameters=parameters,
            responses=responses,
            synonyms=synonyms,
            equivalents=equivalents,
            tts=tts,
            continues=continues
        )

        self.api.manager.add(command)

    def scan_scenarios(self, request):
        user_requests = [event for event in self.api.eventLogger.history if event.type == "user_request"]

        updated_scenarios = []

        for scenario in self.api.scenarios:
            if scenario.check_scenario(request, user_requests):
                updated_scenarios.append(scenario)

        self.scenario_active = updated_scenarios

    def do(self, command):
        """
        Start the action thread
        """
        action = self.find_action(command[0].action)
        thread = threading.Thread(target=action,
                                  kwargs={"command": command[0], "context": command[1], "history": self.api.eventLogger.history},
                                  daemon=True
                                  )
        thread.start()

    def find_action(self, name):
        """
        Find a module that has a function that corresponds to an action that has to be done
        """
        if name in self.api.__actions__.keys():
            log.info(f"Action found: {name}")
            return self.api.__actions__.get(name)
        else:
            log.info(f"Action not found: {name}")
            return self.api.__blank__

    def grammar_recognition_restricted_create(self):
        """
        Creates a file of words that are used in commands
        This file is used for a vosk speech-to-text model to speed up the recognition speed and quality
        """
        with open(f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt", "w") as file:
            file.write('["' + " ".join(self.config["settings"]["trigger"].get(f"triggers")))
            file.write(self.config["audio"]["stt"].get(f"restricted-add-line"))
            file.write(" " + self.api.manager.construct_recognizer_string() + '"]')

    # below methods are actions that need access to the main app instance
    # <!--------------------------------------------------------------------!>

    def grammar_restrict(self, **kwargs):
        """
        An action function inside an app class that enables or disables 'improved but limited' speech recognition
        """
        if not self.config["settings"]["text-mode"]:
            match kwargs["command"].parameters["way"]:
                case "on":
                    self.stt.recognizer = self.stt.create_new_recognizer()
                case "off":
                    self.stt.recognizer = self.stt.set_grammar(
                        f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt",
                        self.stt.create_new_recognizer())
        else:
            self.api.say("voice recognition is not active, sir")

    def repeat(self, **kwargs):
        """
        An action function inside an app class that repeat an action performed the last time
        """
        self.handle(self.history[-1].get("request"))

    @staticmethod
    def stop(**kwargs):
        os.kill(os.getpid(), signal.SIGKILL)

    def sleep(self, **kwargs):
        self.running = False
        time.sleep(0.5)

    def protocol(self, **kwargs):
        for command in kwargs["command"].parameters["protocol"]:
            self.find_action(command["action"])(command=self.api.Command(
                keywords=kwargs["command"].keywords,
                action=command["action"],
                parameters=command["parameters"]
            ))
