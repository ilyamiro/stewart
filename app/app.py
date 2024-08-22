# Standart library imports
import logging
import threading
import time
import os

# Third-party imports
from playsound import playsound

# Local imports
from audio.input import STT
from audio.output import ttsi

from logs import get_logger

from utils import yaml_load

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
        self.config = yaml_load(CONFIG_FILE)

        self.stt = STT()

        self.recognition_thread = threading.Thread(target=self.recognition)
        self.recognition_thread.start()

        logger.debug(f"Recognition thread started with name: {self.recognition_thread.name}")

    def handle(self):
        pass

    def multihandle(self):
        pass

    def recognition(self):
        while True:
            for word in self.stt.listen():
                result = self.remove_trigger_word(word)

    @staticmethod
    def remove_trigger_word(request):
        for trigger in [1]:
            if trigger in request:
                request = " ".join(request.split(trigger)[1:])[1:]
                return request
        return "blank"


a = App()