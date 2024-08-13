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
        self.stream = self.pyaudio_instance.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True, frames_per_buffer=8000)

        self.model = Model(f"{DIR}/vosk-models/vosk-model-small-ru-0.22")
        self.recognizer = KaldiRecognizer(16000, self.model)

    def listen(self):
        """
        Generator fo handling user input. Has to yield recognized data
        Reads data from the audio input stream using PyAudio and uses 'recognize' function to yield a result
        """
        data = self.stream.read(4000, exception_on_overflow=False)
        if self.current.AcceptWaveform(data) and len(data) > 1 and self.stream.is_active():
            # using json to load results of user input's analyzing
            answer = json.loads(self.current.Result())
            # if user said something - it yields
            if answer['text']:
                yield answer['text']
