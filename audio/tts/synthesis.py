import threading
import os
import re
import logging
import inspect
from pathlib import Path
from importlib import import_module
import random
import time

import numpy as np
from voicesynth import Model, Synthesizer
from pydub import AudioSegment
from pydub.generators import WhiteNoise
from scipy.signal import chirp 
from scipy.io import wavfile
import io

from utils import load_yaml, load_lang, called_from
from data.constants import PROJECT_DIR, CONFIG_FILE

log = logging.getLogger("tts")


class TTS:
    def __init__(self, config, lang):
        self.lang = lang

        SEX = config["audio"]["tts"][lang]["sex"]
        SPEAKER = config["audio"]["tts"][lang][SEX]
        MODEL = config["audio"]["tts"][lang]["model"]
        ENABLE = config["audio"]["tts"]["enable"]

        if not os.path.exists(f"{PROJECT_DIR}/audio/tts/models"):
            os.makedirs(f"{PROJECT_DIR}/audio/tts/models")

        self.model = Model(MODEL, f"{PROJECT_DIR}/audio/tts/models/{MODEL}.pt")
        self.model.set_speaker(SPEAKER)
        log.debug(f"text-to-speech model configured. lang: {lang}, speaker {SPEAKER} set")

        self.synthesizer = Synthesizer(self.model)
        log.debug(f"Synthesizer configured")

        self.active = ENABLE

    def say(self, text, no_audio=False, prosody=94, speaker=None, path=f"{PROJECT_DIR}/audio/tts/audio.wav"):
        func = self.synthesizer.say if not no_audio else self.synthesizer.synthesize
        text = self.parse_config_answers(text)

        if speaker and speaker in self.model.speakers:
            self.model.set_speaker(speaker)

        kwargs = {
            "text": text,
            "path": path,
            "prosody_rate": prosody,
        }
        if not no_audio:
            kwargs["module"] = "playsound"

        func(**kwargs)
        called_from()

        log.debug(text)

    def parse_config_answers(self, string, module=None):
        if not module:
            module = import_module(f"utils.lang.{self.lang}")

        pattern = re.compile(r"\[(.*?)]")
        matches = pattern.findall(string)

        for match in matches:
            if hasattr(module, match):
                func = getattr(module, match)
                if callable(func):
                    string = string.replace(f'[{match}]', func())

        return string
