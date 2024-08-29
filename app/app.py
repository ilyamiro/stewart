# Standart library imports
import logging
import random
import threading
import time
import os
import json
import inspect

# Third-party imports
from playsound import playsound
import g4f.Provider
from g4f.client import Client as GPTClient

# Local imports
from audio.input import STT
from audio.output import ttsi
from utils import *
from tree import Tree

DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(DIR)

CONFIG_FILE = f"{os.path.dirname(DIR)}/config.yaml"

logger = logging.getLogger("App")


class App:
    """
    Main running instance of an application behind the GUI (plan)
    For further reference, VA = Voice Assistant
    """

    @staticmethod
    def sound_effect_decorator(func):
        """Sound effect decorator for initializing"""

        def wrapper(self, *args, **kwargs):
            self.config = yaml_load(CONFIG_FILE)
            self.lang = self.config["lang"]["prefix"]
            logger.info("Configuration file loaded")

            playsound(f"{os.path.dirname(DIR)}/data/sounds/startup.wav", block=False)
            func(self, *args, **kwargs)
            ttsi.say(random.choice(self.config[f"answers-{self.lang}"]["startup"]))

        return wrapper

    @sound_effect_decorator
    def __init__(self):
        # TODO: add function "set trigger mode"
        #  in which if the trigger is set to "disabled", self.trigger_timed_needed has to be set to True
        self.trigger_timed_needed = self.config["trigger"]["trigger-mode"] != "disabled"

        # data tree initializing
        self.tree = Tree()
        self.tree_init()

        logger.info("Data tree initialized")

        # import modules for command processing
        self.modules = import_modules_from_directory(self.config['module']['dir'])

        # voice recognition
        self.stt = STT(self.lang)

        # restricting recognition by adding grammar made of commands
        self.grammar_recognition_restricted_create()
        self.stt.set_grammar(f"{os.path.dirname(DIR)}/data/grammar/grammar-{self.lang}.txt")

        logger.debug("Speech to text instance initialized")

        # history of requests
        self.history = []

        # gpt settings
        self.gpt_history = []
        self.gpt_client = GPTClient()
        self.gpt_provider = getattr(g4f.Provider, self.config["gpt"]["provider"])
        self.gpt_start = [{"role": "user", "content": self.config["gpt"][f"start-prompt-{self.lang}"]},
                          {"role": "system", "content": self.config["gpt"][f"start-answer-{self.lang}"]}]

        logger.info("Initialized GPT settings and a GPT client")

        self.recognition_thread = threading.Thread(target=self.recognition)

        logger.debug("Successfully finished main app instance initialization")

    def start(self):
        # starting the voice recognition
        self.recognition_thread.start()

        logger.debug(f"Recognition thread started with name: {self.recognition_thread.name}")

    def grammar_recognition_restricted_create(self):
        with open(f"{PARENT_DIR}/data/grammar/grammar-{self.lang}.txt", "w") as file:
            file.write('["' + " ".join(self.config['trigger'].get(f"triggers-{self.lang}")))
            file.write(self.config["speech"].get(f"restricted-add-line-{self.lang}"))
            file.write(self.tree.recognizer_string + '"]')

    def grammar_restrict(self, **kwargs):
        if kwargs["parameters"]["way"] == "on":
            self.stt.create_new_recognizer()
        if kwargs["parameters"]["way"] == "off":
            self.stt.set_grammar(f"{os.path.dirname(DIR)}/data/grammar/grammar-{self.lang}.txt")

    def repeat(self, **kwargs):
        self.handle(self.history[-1].get("request"))

    def recognition(self):
        while True:
            for word in self.stt.listen():
                if self.trigger_timed_needed:
                    result = self.remove_trigger_word(word)
                    if result != "blank":
                        if self.config["trigger"]["trigger-mode"] == "timed":
                            self.trigger_timed_needed = False
                            self.trigger_counter(self.config["trigger"]["trigger-time"])
                        self.handle(result)
                else:
                    self.handle(word)

    def remove_trigger_word(self, request):
        for trigger in self.config["trigger"][f"triggers-{self.lang}"]:
            if trigger in request:
                request = " ".join(request.split(trigger)[1:])[1:]
                return request
        return "blank"

    def trigger_counter(self, times):
        trigger_word_countdown_thread = threading.Timer(times, self.trigger_change)
        trigger_word_countdown_thread.start()
        logger.info("Trigger countdown started")

    def trigger_change(self):
        self.trigger_timed_needed = True
        logger.info("Trigger countdown ended")

    def tree_init(self):
        commands = self.config["commands"]
        commands_repeat = self.config["commands-repeat"]

        for command in commands:
            equiv = command.get(f'equivalents-{self.lang}', [])
            if equiv:
                for eq in equiv:
                    equiv[equiv.index(eq)] = tuple(eq)
            self.add_command(
                tuple(command[f"command-{self.lang}"]),
                command["action"],
                command.get("parameters", {}),
                command.get(f"responses-{self.lang}", {}),
                command.get(f"synonyms-{self.lang}", {}),
                equiv
            )

        for repeat in commands_repeat:
            for key in repeat[f"links-{self.lang}"]:
                self.add_command(
                    (*repeat.get(f"command-{self.lang}"), key),
                    repeat.get("action"),
                    {repeat.get("parameter"): repeat.get(f"links-{self.lang}").get(key)},
                    [],
                    repeat.get(f"synonyms-{self.lang}"),
                )

    def add_command(self, com: tuple, action: str, parameters: dict = None, synthesize: list = None,
                    synonyms: dict = None, equivalents: list = None):
        self.tree.add_commands(
            {com: {"action": action, "parameters": parameters, "synthesize": synthesize, "synonyms": synonyms,
                   "equivalents": equivalents}})

    def history_update(self, request):
        timestamp = datetime.now().isoformat()
        new_event = {"timestamp": timestamp, "request": request}

        if len(self.history) > self.config.get("max-history-length"):
            self.history.pop(0)

        self.history.append(new_event)

    def handle(self, request):
        if not request and self.config["trigger"]["trigger-mode"] != "disabled":
            # if the request does not contain anything and the trigger word is required,
            # it means that the user called for VA with a trigger word
            # (that got removed by self.remove_trigger_word)
            # and did not specify the command; therefore, we answer with a default phrase
            ttsi.say(random.choice(self.config[f"answers-{self.lang}"]["default"]))
        else:
            self.history_update(request)
            # checking whether the request contains multiple commands
            total = self.multihandle(request)
            if len(total) == 1:
                # if there is only one command, process it
                self.process_command(total[0], request)
            elif len(total) > 1:
                # if there are multiple commands, we can't play multiple audios at once as they would overlap.
                # so, we just play a confirmative phrase, like "Doing that now, sir" or else.
                ttsi.say(random.choice(self.config[f"answers-{self.lang}"]["multi"]))
                # processing each command separately
                for command in total:
                    self.process_command(command, request, multi=True)
            elif not total and self.config["gpt"]["state"]:
                answer = self.gpt_answer(request)
                ttsi.say(answer)
                # If something was said by user after the trigger word, but no commands were recognized,
                # then this phrase is being sent to gpt model for answering

    def process_command(self, command, full, multi: bool = False):
        result = self.tree.find_command(command)
        if result:
            result = list(result)
            result.extend([command, full])
            if result[2] and not multi:
                ttsi.say(random.choice(result[2]))
            self.do(result)

    def do(self, request):
        print(request)
        thread = threading.Thread(target=getattr(self.find_arch(request[0]), request[0]),
                                  kwargs={"parameters": request[1], "command": request[3],
                                          "request": request[4]})
        thread.start()

    def find_arch(self, name):
        for module in self.modules:
            members = inspect.getmembers(module)
            functions = [member[0] for member in members if inspect.isfunction(member[1])]
            if name in functions:
                return module
        if name in dir(self):
            return self

    def multihandle(self, request):
        list_of_commands, current_command = [], []
        split_request = request.split()
        for word in split_request:
            if word in self.tree.first_words:
                if current_command:
                    list_of_commands.append(current_command)
                if word in self.config["command-spec"][f"no-multi-first-words-{self.lang}"]:
                    current_command = split_request[split_request.index(word):]
                    list_of_commands.append(current_command)
                    current_command = []
                    break
                current_command = [word]
            else:
                if current_command and word != self.config["command-spec"][f"connect-word-{self.lang}"]:
                    current_command.append(word)
                elif not current_command and word != self.config["command-spec"][f"connect-word-{self.lang}"]:
                    pass
        if current_command:
            list_of_commands.append(current_command)
        return list_of_commands

    def gpt_answer(self, query):
        answer = self.gpt_client.chat.completions.create(
            messages=[*self.gpt_start, *self.gpt_history, {"role": "user", "content": query}],
            provider=self.gpt_provider,
            stream=False,
            model=g4f.models.default
        ).choices[0].message.content

        self.gpt_history.extend([{"role": "user", "content": query}, {"role": "system", "content": answer}])
        if len(self.gpt_history) >= 8:
            self.gpt_history = self.gpt_history[2:]

        answer = numbers_to_strings(answer)
        return answer
