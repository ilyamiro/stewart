import logging
import random
import sys
import threading
import time
import os
import re
import json
import signal
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
            self.config = self.api.config
            self.lang = self.api.lang
            func(self, *args, **kwargs)
            self.api.__run_hooks__(self.api.__post_init_callbacks__)
            self.api.add_func_for_search(self.protocol, self.stop, self.repeat, self.grammar_restrict, self.sleep)
        return wrapper

    @decorator
    def start(self, start_time):
        self.trigger_timed_needed = self.config["settings"]["trigger"]["trigger-mode"] != "disabled"
        self.tree_init()

    def run(self, stt=None, last_time=None):
        self.running = True

        if not self.config["settings"]["text-mode"]:
            self.stt = stt
            self.last_time = time.time() if not last_time else last_time

            if self.config["audio"]["stt"]["speech-mode-restricted"] and getattr(self.stt, "backend", "vosk") == "vosk":
                self.grammar_recognition_restricted_create()
                self.stt.recognizer = self.stt.set_grammar(
                    f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt",
                    self.stt.create_new_recognizer()
                )

            if self.stt and hasattr(self.stt, "set_command_vocabulary"):
                triggers = self.config.get("settings", {}).get("trigger", {}).get("triggers", ["stewart"])
                self.stt.set_command_vocabulary(self.api.manager, triggers=triggers)

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
                self.running = False

    def recognition(self):
        threshold = int(self.config["settings"]["inactivity-threshold"])
        was_speaking = False
        while self.running:
            if time.time() - self.last_time > threshold:
                self.running = False
            data = self.stt.stream.read(1024, exception_on_overflow=False)

            if getattr(self.api, "is_speaking", False):
                was_speaking = True
                continue
            elif was_speaking:
                was_speaking = False
                if hasattr(self.stt, "flush"):
                    self.stt.flush()
                continue

            for word in self.stt.listen(data):
                self.process_trigger(word)

    def ask_voice_confirmation(self, prompt: str, timeout: float = 8.0) -> bool:
        if not prompt:
            prompt = "Do you confirm this action, Sir?"

        print(f'Stewart: "{prompt}"')
        self.api.say(prompt)

        while getattr(self.api, "is_speaking", False):
            time.sleep(0.05)

        chime_file = None
        try:
            from data.constants import DEFAULT_DATA_DIR
            for cand in [Path(__file__).resolve().parent.parent / "data/sounds/beep.wav", DEFAULT_DATA_DIR / "sounds/beep.wav"]:
                if cand.exists():
                    chime_file = str(cand)
                    break
            if chime_file:
                from audio.tts.synthesis import play_audio
                play_audio(chime_file)
        except Exception:
            pass

        is_text_mode = getattr(self.config.get("settings", {}), "text-mode", False) if isinstance(self.config.get("settings"), dict) else False
        if is_text_mode or not hasattr(self, "stt") or not self.stt:
            try:
                ans = input(f"[Voice Confirmation] {prompt} [yes/no]: ").strip().lower()
                return ans in ("y", "yes", "sure", "proceed", "do it", "confirm", "yeah", "yep", "да", "давай", "подтверждаю")
            except Exception:
                return False

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
                    words = set(clean_phrase.split())
                    if words.intersection(affirmatives):
                        if chime_file:
                            try:
                                play_audio(chime_file)
                            except Exception:
                                pass
                        return True
                    if words.intersection(negatives):
                        return False
            except Exception:
                break

        return False

    def handle(self, request):
        if not request:
            if self.config["settings"]["trigger"]["trigger-mode"] != "disabled":
                self.api.__no_command_default__(context=None, history=None)
            return

        self.api.eventLogger.record(self.api.Event(
            "user_request",
            {"request": request}
        ))

        result, execution_time = track_time(lambda: self.api.manager.find(request))
        if result:
            self.last_time = time.time()

            if len(result) == 1:
                command = result[0]
                cmd_obj = command[0]

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

                if cmd_obj.action == "speak":
                    text_to_speak = cmd_obj.parameters.get("text") or (cmd_obj.responses[0] if cmd_obj.responses else "")
                    if text_to_speak:
                        print(f'Stewart: "{text_to_speak}"')
                        self.api.say(text_to_speak)
                    return

                print(f"✓ ⚡ Executing: {cmd_obj.action} ({' '.join(cmd_obj.keywords)})")
                action_res = self.do(command, request=request)

                if command[0].responses and not command[0].tts:
                    answer = random.choice(command[0].responses)
                    print(f'Stewart: "{answer}"')
                    self.api.say(answer)
                elif not command[0].tts:
                    answers_list = self.config.get("answers", {}).get("multi", ["Done, Sir."])
                    answer = random.choice(answers_list)
                    print(f'Stewart: "{answer}"')
                    self.api.say(answer)
            else:
                for command in result:
                    print(f"✓ ⚡ Executing: {command[0].action} ({' '.join(command[0].keywords)})")
                    self.do(command, request=request)

                if all(not command[0].tts for command in result):
                    answers_list = self.config.get("answers", {}).get("multi", ["Done, Sir."])
                    answer = random.choice(answers_list)
                    print(f'Stewart: "{answer}"')
                    self.api.say(answer)

            result_visual = {" ".join(cmd[0].keywords): cmd[1] for cmd in result}
            self.api.eventLogger.record(self.api.Event(
                "command_detected",
                {
                    "user_request": request,
                    "commands": result_visual,
                }
            ))

        else:
            router = getattr(self.api, "router", None)
            if router:
                routed = router.route(request, history=self.api.eventLogger.history)
                if routed:
                    for cmd_pair in routed:
                        cmd = cmd_pair[0]
                        if cmd.action == "speak":
                            text_to_speak = cmd.parameters.get("text", "")
                            if text_to_speak:
                                self.api.say(text_to_speak)
                        else:
                            self.do(cmd_pair, request=request)
                else:
                    self.api.__no_command_callback__(context=request, history=self.api.eventLogger.history)
            else:
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
        req_clean = request.strip().lower()
        if not req_clean:
            return "blank", "blank"

        greetings = {"hey", "hi", "ok", "okay", "привет", "хей", "эй", "слушай"}
        tokens = req_clean.split()
        if not tokens:
            return "blank", "blank"

        if tokens[0] in greetings and len(tokens) > 1:
            tokens = tokens[1:]

        if len(tokens) >= 2 and tokens[0] == "stew" and tokens[1] in ("art", "ward", "ert"):
            tokens = ["stewart"] + tokens[2:]

        configured_triggers = self.config.get("settings", {}).get("trigger", {}).get("triggers", [])
        all_triggers = list(configured_triggers)
        for standard in ("стюарт", "стюард", "stewart", "steward", "stuart", "stewert"):
            if standard not in all_triggers:
                all_triggers.append(standard)

        for trigger in all_triggers:
            trig_clean = trigger.strip().lower()
            if tokens[0] == trig_clean:
                return trig_clean, " ".join(tokens[1:]).strip()

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

    def trigger_change(self):
        self.trigger_timed_needed = True

    def tree_init(self):
        commands = self.config["commands"]["default"]
        commands_repeat = self.config["commands"]["repeat"]

        for command in commands:
            self.add_command(
                command["command"],
                command["action"],
                command.get("parameters", {}),
                command.get("responses", []),
                command.get("synonyms", {}),
                command.get("equivalents", []),
                command.get("tts", False),
                command.get("continues", False)
            )

        for repeat in commands_repeat:
            param_key = repeat.get("parameter")
            if not param_key:
                action_name = repeat.get("action", "")
                if action_name == "browser":
                    param_key = "url"
                elif action_name in ("hotkey", "key"):
                    param_key = "hotkey"
                else:
                    param_key = "command"

            for key in repeat.get("links", {}):
                add = [key,] if key.count(" ") == 0 else key.split()
                self.add_command(
                    [*repeat.get("command", []), *add],
                    repeat.get("action"),
                    {param_key: repeat.get("links", {}).get(key)},
                    [],
                    repeat.get("synonyms"),
                )

        if hasattr(self.api, "tool_registry"):
            self.api.tool_registry.sync_from_app(self.api)
        if hasattr(self.api, "router"):
            self.api.router.config = self.config
            self.api.router.initialize()

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

    def do(self, command, request=""):
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
                query_result = future.result(timeout=10.0)
                return query_result if query_result is not None else {"status": "success", "action": cmd_obj.action}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return {"status": "success", "action": cmd_obj.action, "context": command[1]}

    def find_action(self, name):
        if name == "speak":
            return lambda command=None, context=None, history=None: self.api.say(command.parameters.get("text", "") if command else (context or ""))
        action = self.api.__actions__.get(name)
        if action is not None:
            return action
        if hasattr(self.api, "tool_registry") and self.api.tool_registry:
            tool = self.api.tool_registry.get(name)
            if tool:
                return tool.func
        return None

    def grammar_recognition_restricted_create(self):
        with open(f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt", "w") as file:
            file.write('["' + " ".join(self.config["settings"]["trigger"].get("triggers")))
            file.write(self.config["audio"]["stt"].get("restricted-add-line"))
            file.write(" " + self.api.manager.construct_recognizer_string() + '"]')

    def grammar_restrict(self, **kwargs):
        if not self.config["settings"]["text-mode"]:
            if getattr(self.stt, "backend", "vosk") == "vosk":
                match kwargs["command"].parameters["way"]:
                    case "on":
                        self.stt.recognizer = self.stt.create_new_recognizer()
                    case "off":
                        self.stt.recognizer = self.stt.set_grammar(
                            f"{PROJECT_DIR}/data/grammar/grammar-{self.lang}.txt",
                            self.stt.create_new_recognizer()
                        )
        else:
            self.api.say("voice recognition is not active, sir")

    def repeat(self, **kwargs):
        self.handle(self.history[-1].get("request"))

    @staticmethod
    def stop(**kwargs):
        os.kill(os.getpid(), signal.SIGKILL)

    def sleep(self, **kwargs):
        self.running = False

    def protocol(self, **kwargs):
        for command in kwargs["command"].parameters["protocol"]:
            self.find_action(command["action"])(command=self.api.Command(
                keywords=kwargs["command"].keywords,
                action=command["action"],
                parameters=command["parameters"]
            ))
