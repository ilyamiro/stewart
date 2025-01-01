import threading
import os
import logging
import inspect
from pathlib import Path

from voicesynth import Model, Synthesizer

from utils import parse_config_answers, load_yaml, load_lang, called_from

from data.constants import PROJECT_FOLDER, CONFIG_FILE

config = load_yaml(CONFIG_FILE)


LANG = load_lang()
SEX = config["audio"]["tts"]["sex"]
SPEAKER = config["audio"]["tts"][LANG][SEX]
MODEL = config["audio"]["tts"][LANG]["model"]
ENABLE = config["audio"]["tts"]["enable"]

log = logging.getLogger("tts")


class TTS:
    def __init__(self):
        self.model = Model(MODEL, f"{PROJECT_FOLDER}/audio/tts/models/{MODEL}.pt")
        self.model.set_speaker(SPEAKER)
        log.debug(f"text-to-speech model configured. lang: {LANG}, speaker {SPEAKER} set")

        self.synthesizer = Synthesizer(self.model)
        log.debug(f"Synthesizer configured")

        self.active = ENABLE

    def say(self, text, prosody=94):
        if self.active and text is not None:
            text = parse_config_answers(text)
            thread = threading.Thread(target=self.synthesizer.say, kwargs={"text": text, "path": f"{PROJECT_FOLDER}/audio/tts/audio.wav", "prosody_rate": prosody, "module": "playsound"})
            thread.start()

            called_from()

            log.debug(text)
        else:
            log.debug(f"No sound: {text}")

