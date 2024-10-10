import logging
import os
import sys
import json
import threading
import ast
from pathlib import Path

import numpy as np
from vosk import KaldiRecognizer, Model, SpkModel
import pyaudio
import torch

from data.constants import PROJECT_FOLDER, CONFIG_FILE
from utils.utils import load_yaml

log = logging.getLogger("stt")
config = load_yaml(CONFIG_FILE)

with open(f"{PROJECT_FOLDER}/audio/input/vector.txt", "r", encoding="utf-8") as f:
    spk_sig = ast.literal_eval(f.read().replace("\n", ""))

SPK_MODEL_PATH = f"{PROJECT_FOLDER}/audio/input/models/vosk-model-speaker-recognition"
# utils = torch.load(f"{PROJECT_FOLDER}/audio/input/models/silero_utils.pth")

# (get_speech_timestamps,
#  save_audio,
#  read_audio,
#  VADIterator,
#  collect_chunks) = utils


def int2float(sound):
    abs_max = np.abs(sound).max()
    sound = sound.astype('float32')
    if abs_max > 0:
        sound *= 1 / 32768
    sound = sound.squeeze()  # depends on the use case
    return sound


def cosine_dist(x, y):
    """
    Is used to calculate the "similarity" between the input and the speaker signature
    """
    nx = np.array(x)
    ny = np.array(y)
    return 1 - np.dot(nx, ny) / np.linalg.norm(nx) / np.linalg.norm(ny)


class STT:
    def __init__(self, lang: str, size: str = "small"):
        self.pyaudio_instance = pyaudio.PyAudio()
        log.info("PyAudio instance created")

        self.stream = self.pyaudio_instance.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True,
                                                 frames_per_buffer=8192)
        log.debug("PyAudio stream instance successfully opened for input")

        self.model = Model(f"{PROJECT_FOLDER}/audio/input/models/vosk-model-{size}-{lang}")
        self.spk_model = SpkModel(SPK_MODEL_PATH)
        self.vad_model = torch.jit.load(f"{PROJECT_FOLDER}/audio/input/models/silero_vad.jit")

        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.recognizer.SetSpkModel(self.spk_model)

        log.debug("Vosk recognition system initialized")

        self.listen = self.listen_vad if config["voice"]["activity-detection"] else self.listen_no_vad

        self.voice_activity = not config["voice"]["activity-detection"]
        self.add_data = b""

    def listen_vad(self):
        if self.voice_activity:
            data = self.add_data + self.stream.read(4000, exception_on_overflow=False)
            self.add_data = b""
            result = self.process(data)
            if result:
                yield result
        else:
            data = self.stream.read(512, exception_on_overflow=False)
            if self.voice_activity_detected(data):
                self.add_data = data
                self.count_voice_activity(15)

    def listen_no_vad(self):
        data = self.stream.read(4000, exception_on_overflow=False)
        result = self.process(data)
        if result:
            yield result

    def process(self, data):
        if self.recognizer.AcceptWaveform(data):
            answer = json.loads(self.recognizer.Result())
            # TODO make the cosine distance boundary a config parameter
            if "spk" in answer:
                distance = cosine_dist(spk_sig, answer["spk"])
                if distance < 0.65 and answer["text"]:
                    log.info(f"Text recognized: {answer['text']}, speaker distance: {distance}")
                    return answer["text"]
                elif distance > 0.65:
                    log.info(
                        f"Speaker distance is greater than a threshold: {distance} > 0.65. result will not be processed")

    def voice_activity_detected(self, data):
        audio_int16 = np.frombuffer(data, np.int16)
        audio_float32 = int2float(audio_int16)
        vad_confidence = self.vad_model(torch.from_numpy(audio_float32), 16000).item()
        if vad_confidence > 0.85:
            log.info("Detected voice activity")
            return True
        return False

    def count_voice_activity(self, times):
        self.voice_activity = True
        thread = threading.Timer(times, self.voice_activity_set)
        thread.start()

    def voice_activity_set(self):
        self.voice_activity = False

    def create_new_recognizer(self):
        recognizer = KaldiRecognizer(self.model, 16000)
        recognizer.SetSpkModel(self.spk_model)
        log.info("New vosk recognizer instance created")
        return recognizer

    @staticmethod
    def set_grammar(path, recognizer):
        with open(path, "r", encoding="utf-8") as file:
            recognizer.SetGrammar(file.readline())
            return recognizer
