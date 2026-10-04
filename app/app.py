import logging
import random
import sys
import threading
import time
import os
import json
import signal
import inspect
import concurrent.futures
from datetime import datetime
from pathlib import Path

from utils import *
from data.constants import CONFIG_FILE, PROJECT_DIR, PLUGINS_DIR

log = logging.getLogger("app")


class App:
    def __init__(self, api):
        self.api = api
        self._action_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="stewart-action")

    @staticmethod
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            self.api.load_plugins()

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

        log.debug("Finished app initialization")

        log.debug(f"Start up time: {time.time() - start_time:.6f}")

    def run(self, stt=None, last_time=None):
        self.running = True

        if not self.config["settings"]["text-mode"]:
            self.stt = stt
            self.last_time = time.time() if not last_time else last_time

            if self.config["audio"]["stt"]["speech-mode-restricted"] and getattr(self.stt, "backend", "vosk") == "vosk":
                self.grammar_recognition_restricted_create()
                self.stt.recognizer = self.stt.set_grammar(f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt",
                                                           self.stt.create_new_recognizer())

            # Prime and contextualize Whisper STT with active command tree vocabulary & hotwords
            if self.stt and hasattr(self.stt, "set_command_vocabulary"):
                triggers = self.config.get("settings", {}).get("trigger", {}).get("triggers", ["stewart"])
                self.stt.set_command_vocabulary(self.api.manager, triggers=triggers)

            log.debug("Speech to text instance initialized")

            if hasattr(self.stt, "flush"):
                self.stt.flush()

            self.recognition()
        else:
            try:
                while self.running:
                    user_input = input("Input: ").strip()
                    if not user_input:
                        continue
                    if user_input.lower() in ("exit", "quit", ":q"):
                        log.info("Exiting text mode.")
                        self.running = False
                        break
                    if user_input.lower().startswith("lang ") or user_input.lower().startswith(":lang "):
                        new_lang = user_input.split()[-1].lower()
                        from utils.system import set_lang
                        target = set_lang(new_lang)
                        print(f"Default language set to '{new_lang}' in {target}. Please restart Stewart to apply.")
                        continue
                    self.process_trigger_no_voice(user_input)
            except (EOFError, KeyboardInterrupt):
                log.info("Exiting text mode.")
                self.running = False

    def recognition(self):
        threshold = int(self.config["settings"]["inactivity-threshold"])
        was_speaking = False
        while self.running:
            if time.time() - self.last_time > threshold:
                log.debug(
                    f"Going into sleep mode due to inactivity for {threshold} seconds (~{threshold / 60} minutes)")
                self.running = False
            data = self.stt.stream.read(1024, exception_on_overflow=False)

            # Prevent assistant from hearing its own voice while speaking responses
            if getattr(self.api, "is_speaking", False):
                was_speaking = True
                continue
            elif was_speaking:
                was_speaking = False
                if hasattr(self.stt, "flush"):
                    self.stt.flush()
                continue

            for word in self.stt.listen(data):
                log.info(f"Speech recognized: '{word}'")
                self.process_trigger(word)


    def handle(self, request):
        if not request:
            if self.config["settings"]["trigger"]["trigger-mode"] != "disabled" and not self.scenario_active:
                self.api.__no_command_default__(context=None, history=None)
            return

        self.api.eventLogger.record(self.api.Event(
            "user_request",
            {"request": request}
        ))

        self.scan_scenarios(request)

        result, execution_time = track_time(lambda: self.api.manager.find(request))
        if result:
            self.last_time = time.time()

            # Execute action IMMEDIATELY without waiting for TTS, logging, or event recording
            if len(result) == 1:
                command = result[0]
                self.do(command)

                # Process TTS / responses after action has been launched
                if command[0].responses and not command[0].tts:
                    answer = random.choice(command[0].responses)
                    self.api.say(answer)
                elif not command[0].responses and not command[0].tts:
                    answer = random.choice(self.config["answers"]["multi"])
                    self.api.say(answer)
            else:
                for command in result:
                    self.do(command)

                if all(not command[0].tts for command in result):
                    answer = random.choice(self.config["answers"]["multi"])
                    self.api.say(answer)

            result_visual = {" ".join(cmd[0].keywords): cmd[1] for cmd in result}
            log.info(f"Command search time: {execution_time:.6f}")
            log.debug(f"Recognized commands: {result_visual}")

            self.api.eventLogger.record(self.api.Event(
                "command_detected",
                {
                    "user_request": request,
                    "commands": result_visual,
                }
            ))

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
                log.debug(f"Input '{request}' did not match wake word")
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
        Removes trigger words from the input with phonetic tolerance,
        split-word repairing, and conversational greeting stripping.
        """
        req_clean = request.strip().lower()
        if not req_clean:
            return "blank", "blank"

        greetings = {"hey", "hi", "ok", "okay", "привет", "хей", "эй", "слушай"}
        tokens = req_clean.split()
        if not tokens:
            return "blank", "blank"

        if tokens[0] in greetings and len(tokens) > 1:
            tokens = tokens[1:]

        # Split wake-word merge (e.g. 'stew art' -> 'stewart')
        if len(tokens) >= 2 and tokens[0] == "stew" and tokens[1] in ("art", "ward", "ert"):
            tokens = ["stewart"] + tokens[2:]

        configured_triggers = self.config.get("settings", {}).get("trigger", {}).get("triggers", [])
        all_triggers = list(configured_triggers)
        for standard in ("стюарт", "стюард", "stewart", "steward", "stuart", "stewert"):
            if standard not in all_triggers:
                all_triggers.append(standard)

        # 1. Exact match on first token
        for trigger in all_triggers:
            trig_clean = trigger.strip().lower()
            if tokens[0] == trig_clean:
                return trig_clean, " ".join(tokens[1:]).strip()

        # 2. Check whole string starts with multi-word or exact trigger
        cleaned_str = " ".join(tokens)
        for trigger in all_triggers:
            trig_clean = trigger.strip().lower()
            if cleaned_str == trig_clean:
                return trig_clean, ""
            if cleaned_str.startswith(trig_clean + " "):
                return trig_clean, cleaned_str[len(trig_clean) + 1:].strip()
            if trig_clean in cleaned_str:
                parts = cleaned_str.split(trig_clean, 1)
                return trig_clean, parts[1].strip()

        # 3. Fuzzy match on first token
        from audio.input.corrector import fast_damerau_levenshtein
        first = tokens[0]
        for trigger in all_triggers:
            trig_clean = trigger.strip().lower()
            if abs(len(first) - len(trig_clean)) <= 2:
                d = fast_damerau_levenshtein(first, trig_clean, max_dist=2)
                if d <= 1 or (len(trig_clean) >= 6 and d <= 2):
                    return trig_clean, " ".join(tokens[1:]).strip()

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

        # Synchronize tools from all loaded plugins and actions
        if hasattr(self.api, "tool_registry"):
            self.api.tool_registry.sync_from_app(self.api)
        # Initialize router (model loading/auto-training)
        if hasattr(self.api, "router"):
            self.api.router.config = self.config
            self.api.router.initialize()

        log.info("Command manager and tool router initialized")

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

    def scan_scenarios(self, request, intent=None):
        if not self.api.scenarios:
            self.scenario_active = []
            return

        user_requests = [event for event in self.api.eventLogger.history if event.type == "user_request"]

        updated_scenarios = []

        for scenario in self.api.scenarios:
            if scenario.check_scenario(request, user_requests, intent=intent):
                updated_scenarios.append(scenario)

        self.scenario_active = updated_scenarios

    def do(self, command):
        """
        Start the action thread via pre-warmed thread pool executor
        """
        cmd_obj = command[0]
        action = getattr(cmd_obj, "_action_callable", None)
        if action is None:
            action = self.find_action(cmd_obj.action)
            cmd_obj._action_callable = action
        if not action:
            return
        self._action_executor.submit(
            action,
            command=cmd_obj,
            context=command[1],
            history=self.api.eventLogger.history
        )

    def find_action(self, name):
        """
        Find a module that has a function that corresponds to an action that has to be done
        """
        action = self.api.__actions__.get(name)
        if action is not None:
            return action
        log.info(f"Action not found: {name}")
        return None

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
            if getattr(self.stt, "backend", "vosk") == "vosk":
                match kwargs["command"].parameters["way"]:
                    case "on":
                        self.stt.recognizer = self.stt.create_new_recognizer()
                    case "off":
                        self.stt.recognizer = self.stt.set_grammar(
                            f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt",
                            self.stt.create_new_recognizer())
            else:
                log.info("Whisper backend active; open vocabulary is supported natively.")
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
        # run("loginctl", "lock-session")
        self.running = False

    def protocol(self, **kwargs):
        for command in kwargs["command"].parameters["protocol"]:
            self.find_action(command["action"])(command=self.api.Command(
                keywords=kwargs["command"].keywords,
                action=command["action"],
                parameters=command["parameters"]
            ))
