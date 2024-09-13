import logging
import os
import sys
import json

from vosk import KaldiRecognizer, Model
import pyaudio

# file directory
DIR = os.path.dirname(os.path.abspath(__file__))

log = logging.getLogger("stt")


class STT:
    def __init__(self, lang: str, size: str = "small"):
        self.pyaudio_instance = pyaudio.PyAudio()
        log.info("PyAudio instance created")

        self.stream = self.pyaudio_instance.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True,
                                                 frames_per_buffer=8000)
        log.debug("PyAudio stream instance successfully opened for input")

        self.model = Model(f"{DIR}/models/vosk-model-{size}-{lang}")
        self.recognizer = KaldiRecognizer(self.model, 16000)

        log.debug("Vosk recognition system initialized")

    def listen(self):
        data = self.stream.read(4000, exception_on_overflow=False)
        if self.recognizer.AcceptWaveform(data) and len(data) > 1 and self.stream.is_active():
            answer = json.loads(self.recognizer.Result())
            if answer["text"]:
                log.info(f"Text recognized: {answer['text']}")
                yield answer["text"]

    def create_new_recognizer(self):
        recognizer = KaldiRecognizer(self.model, 16000)
        log.info("New vosk recognizer instance created")
        return recognizer

    @staticmethod
    def set_grammar(path, recognizer):
        with open(path, "r", encoding="utf-8") as file:
            recognizer.SetGrammar(file.readline())
            return recognizer
