import threading
import os
import logging

from voicesynth import Model, Synthesizer

DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_NAME = "v4_ru"
SPEAKER = "eugene"


class TTS:
    def __init__(self):
        self.model = Model(MODEL_NAME, f"{DIR}/models/{MODEL_NAME}.pt")
        self.model.set_speaker(SPEAKER)

        logging.debug(f"TTS model configured. Name: {MODEL_NAME}, speaker {SPEAKER} set")

        self.synthesizer = Synthesizer(self.model)

        logging.debug(f"Synthesizer configured for a model {MODEL_NAME}")

        self.active = True

    def say(self, text):
        if self.active:
            thread = threading.Thread(target=self.synthesizer.say, kwargs={"text": text, "path": f"{DIR}/audio.wav", "prosody_rate": 94, "module": "playsound"})
            thread.start()

            logging.debug(f"TTS thread started: {text}")
