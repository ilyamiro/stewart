# Standart library imports
import logging
import random
import threading
import time
import os
import json

# Third-party imports
from playsound import playsound
import g4f.Provider
from g4f.client import Client as GPTClient

# Local imports
from audio.input import STT
from audio.output import ttsi

from logs import get_logger

from utils import *

from tree import Tree

DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = f"{DIR}/config.yaml"

logger = get_logger("app")


class App:
    """
    Main running instance of an application behind the GUI (plan)
    For further reference, VA = Voice Assistant
    """

    @staticmethod
    def sound_effect_decorator(func):
        """Sound effect decorator for initializing"""

        def wrapper(self, *args, **kwargs):
            playsound(f"{os.path.dirname(DIR)}/data/sounds/startup.wav", block=False)
            result = func(self, *args, **kwargs)
            ttsi.say("Конфигурация ядра завершена")
            return result

        return wrapper

    @sound_effect_decorator
    def __init__(self):
        # Configration file
        self.config = yaml_load(CONFIG_FILE)
        self.lang = self.config["lang"]["prefix"]

        logger.info("Configuration file loaded")

        self.trigger_needed = None
        if self.config["trigger"]["trigger-mode"] == "timed":
            self.trigger_needed = True

        # data tree initializing
        self.tree = Tree()
        self.tree_init()

        logger.info("Data tree initialized")

        # voice recognition
        self.stt = STT(self.lang)

        logger.debug("Speech to text instance initialized")

        # history of requests
        self.history_file = f"{DIR}/history.json"

        # gpt settings
        self.gpt_history = []
        self.gpt_client = GPTClient()
        self.gpt_provider = getattr(g4f.Provider, self.config["gpt"]["provider"])
        self.gpt_start = [{"role": "user", "content": self.config["gpt"][f"start-prompt-{self.lang}"]},
                          {"role": "system", "content": self.config["gpt"][f"start-answer-{self.lang}"]}]

        logger.info("Initialized GPT settings and a GPT client")

        # starting the voice recognition
        self.recognition_thread = threading.Thread(target=self.recognition)
        self.recognition_thread.start()

        logger.debug(f"Recognition thread started with name: {self.recognition_thread.name}")

    def recognition(self):
        while True:
            for word in self.stt.listen():
                result = self.remove_trigger_word(word)
                if result != "blank":
                    self.handle(result)

    def trigger_counter(self, times):
        pass

    def trigger_change(self):
        pass

    def tree_init(self):

        def add_command(com: tuple, handler: str, parameters: dict = None, synthesize: list = None,
                        synonyms: dict = None, equivalents: list = None):
            self.tree.add_commands(
                {com: {"handler": handler, "parameters": parameters, "synthesize": synthesize, "synonyms": synonyms,
                       "equivalents": equivalents}})

        commands = self.config["commands"]
        for command in commands:
            equiv = command.get(f'equivalents-{self.lang}', [])
            if equiv:
                for eq in equiv:
                    equiv[equiv.index(eq)] = tuple(eq)
            add_command(
                tuple(command[f"command-{self.lang}"]),
                command["action"],
                command.get("parameters", {}),
                command.get(f"responses-{self.lang}", {}),
                command.get(f"synonyms-{self.lang}", {}),
                equiv
            )

    def history_update(self, request):
        timestamp = datetime.now().isoformat()
        new_event = {"timestamp": timestamp, "request": request}

        try:
            with open(self.history_file, 'r') as f:
                history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = []

        history.append(new_event)

        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=4)

    def handle(self, request):
        if not request and self.config["trigger"]["trigger-mode"] != "disabled":
            # if the request does not contain anything and the trigger word is required,
            # it means that the user called for VA with a trigger word
            # (that got removed by self.remove_trigger_word)
            # and did not specify the command; therefore, we answer with a default phrase
            ttsi.say(random.choice(self.config[f"answers-{self.lang}"]["default"]))
        else:
            # checking whether the request contains multiple commands
            total = self.multihandle(request)
            if len(total) == 1:
                # if there is only one command, process it
                result = self.tree.find_command(total[0])
                if result:
                    result = list(result)
                    result.extend([total[0], request])
                    self.do_synth(result)
            elif len(total) > 1:
                pass
            elif not total and self.config["gpt"]["state"]:
                pass
                # If something was said by user after the trigger word, but no commands were recognized,
                # then this phrase is being sent to gpt model for answering

    def do(self, request):
        if request[2]:
            ttsi.say(random.choice(*request[2]))
        thread = threading.Thread(target=getattr(self.find_arch(request[0]), request[0]),
                                  kwargs={"parameters": request[1], "command": request[3],
                                          "request": request[4]})
        thread.start()

    def find_arch(self, request):
        pass

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

    def answer_gpt(self, query):
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
