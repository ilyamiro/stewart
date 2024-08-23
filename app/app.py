# Standart library imports
import logging
import threading
import time
import os
import json

# Third-party imports
from playsound import playsound

# Local imports
from audio.input import STT
from audio.output import ttsi

from logs import get_logger

from utils import yaml_load, json_load

from tree import Tree

DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = f"{DIR}/config.yaml"

logger = get_logger("app")


class App:
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
        self.lang = "ru"

        self.config = yaml_load(CONFIG_FILE)

        self.tree = Tree()

        # voice recognition
        self.stt = STT(self.lang)

        # history of requests
        self.history_file = f"{DIR}/history.json"

        self.recognition_thread = threading.Thread(target=self.recognition)
        self.recognition_thread.start()

        logger.debug(f"Recognition thread started with name: {self.recognition_thread.name}")

    def command_tree_init(self):

        def add_command(com: tuple, handler: str, parameters: dict = None, synthesize: list = None,
                        synonyms: dict = None, equivalents: list = None):
            # if not synonyms:
            #     synonyms = {}
            # if not synthesize:
            #     synthesize = []
            # if not parameters:
            #     parameters = {}
            # if not equivalents:
            #     equivalents = []
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
        if not request:
            ttsi.say(random.choice(self.config[f"answers-{self.lang}"]))

    def multihandle(self):
        pass

    def recognition(self):
        while True:
            for word in self.stt.listen():
                result = self.remove_trigger_word(word)
                if result != "blank":
                    self.handle(result)

    def remove_trigger_word(self, request):
        for trigger in self.config["configuration"]["triggers"]:
            if trigger in request:
                request = " ".join(request.split(trigger)[1:])[1:]
                return request
        return "blank"
