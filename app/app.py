import logging
import random
import sys
import threading
import time
import os
import re
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


    def stream_persona_speech(self, request: str, tool_name: Optional[str] = None, tool_result: Optional[Any] = None) -> bool:
        """
        Streams persona tokens and immediately dispatches the first clause to Kokoro TTS
        upon encountering punctuation (. , ! ? ; \n), achieving sub-200ms perceptual latency.
        Remaining clauses are synthesized in background while ongoing speech is playing.
        """
        router = getattr(self.api, "router", None)
        if not router or not getattr(router, "persona_enabled", False):
            return False

        delimiters = re.compile(r"([.,!?;—\n]+)")
        buffer = ""
        dispatched_count = 0
        full_response = []

        try:
            token_stream = router.stream_persona_response(
                user_query=request,
                tool_name=tool_name,
                tool_result=tool_result,
                lang=self.lang
            )

            for token in token_stream:
                buffer += token
                full_response.append(token)
                parts = delimiters.split(buffer)
                if len(parts) > 1:
                    first_clause = (parts[0] + parts[1]).strip()
                    first_clause = re.sub(r"<tool_call>.*?</tool_call>", "", first_clause, flags=re.DOTALL)
                    first_clause = re.sub(r"<tool_response>.*?</tool_response>", "", first_clause, flags=re.DOTALL).strip(' "`\'')
                    if first_clause:
                        log.debug(f"Persona first-clause streamed to TTS: '{first_clause}'")
                        self.api.say(first_clause)
                        dispatched_count += 1
                    buffer = "".join(parts[2:])

            remaining = buffer.strip()
            remaining = re.sub(r"<tool_call>.*?</tool_call>", "", remaining, flags=re.DOTALL)
            remaining = re.sub(r"<tool_response>.*?</tool_response>", "", remaining, flags=re.DOTALL).strip(' "`\'')
            if remaining:
                log.debug(f"Persona trailing clause streamed to TTS: '{remaining}'")
                self.api.say(remaining)
                dispatched_count += 1

            complete_text = "".join(full_response).strip()
            if complete_text:
                log.info(f"Persona generated response (streamed): '{complete_text}'")

            return dispatched_count > 0
        except Exception as e:
            log.warning(f"Persona streaming voice error: {e}", exc_info=True)
            # Fallback to non-streaming if stream failed before any dispatch
            if dispatched_count == 0:
                try:
                    ans = router.generate_persona_response(
                        request,
                        tool_name=tool_name,
                        tool_result=tool_result,
                        lang=self.lang
                    )
                    if ans:
                        self.api.say(ans)
                        return True
                except Exception as fe:
                    log.debug(f"Persona non-streaming fallback failed: {fe}")
            return dispatched_count > 0

    def ask_voice_confirmation(self, prompt: str, timeout: float = 8.0) -> bool:
        """
        Asks the user for confirmation using TTS voice, then waits for a spoken affirmative or negative response.
        Works in both voice mode (via STT) and text-mode (via console input).
        """
        if not prompt:
            prompt = "Do you confirm this action, Sir?"

        log.info(f"Asking voice confirmation: '{prompt}'")
        self.api.say(prompt)

        # Wait until TTS has finished speaking before listening to avoid hearing assistant's own voice
        while getattr(self.api, "is_speaking", False):
            time.sleep(0.05)

        is_text_mode = getattr(self.config.get("settings", {}), "text-mode", False) if isinstance(self.config.get("settings"), dict) else False
        if is_text_mode or not hasattr(self, "stt") or not self.stt:
            try:
                ans = input(f"[Voice Confirmation] {prompt} [yes/no]: ").strip().lower()
                return ans in ("y", "yes", "sure", "proceed", "do it", "confirm", "yeah", "yep", "да", "давай", "подтверждаю")
            except Exception:
                return False

        # Voice mode listening
        affirmatives = {"yes", "sure", "proceed", "do it", "confirm", "yeah", "yep", "ok", "okay", "да", "давай", "подтверждаю", "конечно", "делай"}
        negatives = {"no", "cancel", "stop", "don't", "abort", "нет", "отмена", "не надо", "стоп"}

        if hasattr(self.stt, "flush"):
            self.stt.flush()

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                data = self.stt.stream.read(1024, exception_on_overflow=False)
                for phrase in self.stt.listen(data):
                    clean_phrase = phrase.strip().lower()
                    log.info(f"Confirmation speech heard: '{clean_phrase}'")
                    words = set(clean_phrase.split())
                    if words.intersection(affirmatives):
                        log.info("Voice confirmation: GRANTED")
                        return True
                    if words.intersection(negatives):
                        log.info("Voice confirmation: DENIED")
                        return False
            except Exception as e:
                log.warning(f"Error during voice confirmation listening: {e}")
                break

        log.info("Voice confirmation: TIMEOUT (denied by default)")
        return False

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
                cmd_obj = command[0]

                # Voice confirmation flow for invasive actions
                if getattr(cmd_obj, "needs_confirmation", False) or cmd_obj.action == "confirmation":
                    conf_prompt = cmd_obj.parameters.get("prompt", cmd_obj.parameters.get("text", ""))
                    confirmed = self.ask_voice_confirmation(conf_prompt)
                    if confirmed:
                        orig_req = cmd_obj.parameters.get("original_request", request)
                        router = getattr(self.api, "router", None)
                        if router and hasattr(router, "agy_caller"):
                            exec_res = router.agy_caller.execute_request(orig_req, confirmed=True)
                            if exec_res:
                                self.api.say(str(exec_res))
                        else:
                            self.api.say("Confirmed, proceeding Sir.")
                    else:
                        self.api.say("Understood, cancelled Sir.")
                    return

                action_res = self.do(command, request=request)


                # Process TTS / responses after action has been launched via first-chunk streaming
                cmd_name = command[0].action if hasattr(command[0], "action") else None
                spoken = self.stream_persona_speech(request, tool_name=cmd_name, tool_result=action_res)

                if not spoken:
                    if command[0].responses and not command[0].tts:
                        answer = random.choice(command[0].responses)
                        self.api.say(answer)
                    elif not command[0].responses and not command[0].tts:
                        answer = random.choice(self.config["answers"]["multi"])
                        self.api.say(answer)
            else:
                for command in result:
                    self.do(command, request=request)

                spoken = self.stream_persona_speech(request, tool_name="multi_action")

                if not spoken and all(not command[0].tts for command in result):
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
            spoken = self.stream_persona_speech(request)

            if not spoken:
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

    def do(self, command, request=""):
        """
        Start the action thread via pre-warmed thread pool executor
        """
        cmd_obj = command[0]
        ctx = command[1] if (len(command) > 1 and command[1]) else request
        action = getattr(cmd_obj, "_action_callable", None)
        if action is None:
            action = self.find_action(cmd_obj.action)
            cmd_obj._action_callable = action
        if not action:
            return {"status": "error", "error": f"Action '{cmd_obj.action}' not found"}
        future = self._action_executor.submit(
            action,
            command=cmd_obj,
            context=ctx,
            history=self.api.eventLogger.history
        )
        is_query = (getattr(cmd_obj, "is_query", False) or
                    getattr(action, "is_query", False) or
                    cmd_obj.action.startswith(("studieplus_", "study_", "gmail_")))
        if is_query:
            try:
                # Wait up to 10 seconds for query results so persona model can speak them
                query_result = future.result(timeout=10.0)
                return query_result if query_result is not None else {"status": "success", "action": cmd_obj.action}
            except Exception as e:
                log.warning(f"Query action '{cmd_obj.action}' error or timeout: {e}")
                return {"status": "error", "error": str(e)}

        return {"status": "success", "action": cmd_obj.action, "context": command[1]}

    def find_action(self, name):
        """
        Find a module that has a function that corresponds to an action that has to be done
        """
        action = self.api.__actions__.get(name)
        if action is not None:
            return action
        if hasattr(self.api, "tool_registry") and self.api.tool_registry:
            tool = self.api.tool_registry.get(name)
            if tool:
                return tool.func
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
