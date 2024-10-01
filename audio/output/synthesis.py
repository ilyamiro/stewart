import threading
import os
import logging
import inspect
from pathlib import Path

from voicesynth import Model, Synthesizer

from utils import yaml_load
from utils import parse_and_replace_config

from data.constants import CONFIG_FILE, PROJECT_FOLDER

config = yaml_load(CONFIG_FILE)

LANG = config["lang"]["prefix"]
SEX = config["voice"]["sex"]
SPEAKER = config["voice"][LANG][SEX]
MODEL = config["voice"][LANG]["model"]
ENABLE = config["voice"]["enable"]

log = logging.getLogger("tts")


class TTS:
    def __init__(self):
        self.model = Model(MODEL, f"{PROJECT_FOLDER}/audio/output/models/{MODEL}.pt")
        self.model.set_speaker(SPEAKER)

        log.debug(f"TTS model configured. lang: {LANG}, speaker {SPEAKER} set")

        self.synthesizer = Synthesizer(self.model)

        log.debug(f"Synthesizer configured")

        self.active = ENABLE

    def say(self, text, prosody=94):
        if self.active:
            thread = threading.Thread(target=self.synthesizer.say, kwargs={"text": text, "path": f"{PROJECT_FOLDER}/audio/output/audio.wav", "prosody_rate": prosody, "module": "playsound"})
            thread.start()

            # caller_frane = inspect.currentframe().f_back
            # caller_name = caller_frane.f_code.co_name

            log.debug(f"TTS: {text}")
