import threading
import os
import logging
import inspect
from pathlib import Path
import random
import time

import numpy as np
from pydub import AudioSegment
from pydub.generators import WhiteNoise
from scipy.signal import chirp 
from scipy.io import wavfile
import io



from voicesynth import Model, Synthesizer

from utils import parse_config_answers, load_yaml, load_lang, called_from

from data.constants import PROJECT_DIR, CONFIG_FILE

config = load_yaml(CONFIG_FILE)


LANG = load_lang()

SEX = config["audio"]["tts"][LANG]["sex"]
SPEAKER = config["audio"]["tts"][LANG][SEX]
MODEL = config["audio"]["tts"][LANG]["model"]
ENABLE = config["audio"]["tts"]["enable"]

log = logging.getLogger("tts")


class TTS:
    def __init__(self):
        self.model = Model(MODEL, f"{PROJECT_DIR}/audio/tts/models/{MODEL}.pt")
        self.model.set_speaker(SPEAKER)
        log.debug(f"text-to-speech model configured. lang: {LANG}, speaker {SPEAKER} set")

        self.synthesizer = Synthesizer(self.model)
        log.debug(f"Synthesizer configured")

        self.active = ENABLE

    def say(self, text, no_audio=False, prosody=94, speaker=SPEAKER, path=f"{PROJECT_DIR}/audio/tts/audio.wav"):
        if not self.active:
            log.debug(f"No sound: {text}")
            return

        if not text:
            return

        if speaker in self.model.speakers:
            self.model.set_speaker(speaker)

        text = parse_config_answers(text)

        thread_target = self.synthesizer.say if not no_audio else self.synthesizer.synthesize
        thread_kwargs = {
            "text": text,
            "path": path,
            "prosody_rate": prosody,
        }
        if no_audio:
            thread_kwargs["module"] = "playsound"

        thread = threading.Thread(target=thread_target, kwargs=thread_kwargs)
        thread.start()

        called_from()

        log.debug(text)

