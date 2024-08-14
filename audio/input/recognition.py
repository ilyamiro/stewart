import logging
import os
import sys
import json

from vosk import KaldiRecognizer, Model
import pyaudio

# file directory
DIR = os.path.dirname(os.path.abspath(__file__))


class STT:
    """
    Speech recognition template class
    """
    def __init__(self):
        self.pyaudio_instance = pyaudio.PyAudio()
        logging.info("PyAudio instance created")

        self.stream = self.pyaudio_instance.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True, frames_per_buffer=8000)
        logging.debug("PyAudio stream instance opened for input with pyaudio.paInt16 format")

        self.model = Model(f"{DIR}/vosk-models/vosk-model-small-ru-0.22")
        self.recognizer = KaldiRecognizer(self.model, 16000)
        logging.info("Vosk model successfully configured and KaldiRecognizer created")

    def listen(self):
        """
        Generator fo handling user input. Has to yield recognized data
        Reads data from the audio input stream using PyAudio and uses 'recognize' function to yield a result
        """
        data = self.stream.read(4000, exception_on_overflow=False)
        if self.recognizer.AcceptWaveform(data) and len(data) > 1 and self.stream.is_active():
            # using json to load results of user input's analyzing
            answer = json.loads(self.recognizer.Result())
            # if user said something - it yields
            if answer['text']:
                logging.info(f"Text found in data: {answer['text']}")
                yield answer['text']
            else:
                logging.info("No text recognized")
