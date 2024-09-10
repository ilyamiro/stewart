import threading
import os
import logging
import inspect

from voicesynth import Model, Synthesizer

from utils import yaml_load
from utils import parse_and_replace_config

from data.constants import CONFIG_FILE


DIR = os.path.dirname(os.path.abspath(__file__))

config = yaml_load(CONFIG_FILE)

LANG = config["lang"]["prefix"]
SEX = config["voice"]["sex"]
SPEAKER = config["voice"][LANG][SEX]
MODEL = config["voice"][LANG]["model"]

log = logging.getLogger("TTS")


class TTS:
    def __init__(self):
        self.model = Model(MODEL, f"{DIR}/models/{MODEL}.pt")
        self.model.set_speaker(SPEAKER)

        log.debug(f"TTS model configured. lang: {LANG}, speaker {SPEAKER} set")

        self.synthesizer = Synthesizer(self.model)

        log.debug(f"Synthesizer configured")

        self.active = True

    def say(self, text, prosody=94):
        if self.active:
            thread = threading.Thread(target=self.synthesizer.say, kwargs={"text": text, "path": f"{DIR}/audio.wav", "prosody_rate": prosody, "module": "playsound"})
            thread.start()

            # caller_frane = inspect.currentframe().f_back
            # caller_name = caller_frane.f_code.co_name

            log.debug(f"TTS thread started: {text}")
