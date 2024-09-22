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
from mutagen import File
import torch

from data.constants import PROJECT_FOLDER, CONFIG_FILE
from utils.utils import yaml_load

log = logging.getLogger("stt")
config = yaml_load(CONFIG_FILE)

with open(f"{PROJECT_FOLDER}/audio/input/vector.txt", "r", encoding="utf-8") as f:
    spk_sig = ast.literal_eval(f.read().replace("\n", ""))

SPK_MODEL_PATH = f"{PROJECT_FOLDER}/audio/input/models/vosk-model-speaker-recognition"
utils = torch.load(f"{PROJECT_FOLDER}/audio/input/models/silero_utils.pth")

(get_speech_timestamps,
 save_audio,
 read_audio,
 VADIterator,
 collect_chunks) = utils


def get_audio_format_from_mutagen(byte_data):
    audio_file = File(byte_data)
    if audio_file:
        return audio_file.mime[0]  # MIME type provides format information
    return 'Unknown format'


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

        self.audio_chunk = b""

    def listen(self):
        data = self.stream.read(4000, exception_on_overflow=False)

        # audio_int16 = np.frombuffer(data, np.int16)
        # audio_float32 = int2float(audio_int16)
        # vad_confidence = self.vad_model(torch.from_numpy(audio_float32), 16000).item()
        # if vad_confidence > 0.85:
        #     self.audio_chunk += data
        #     if len(self.audio_chunk) >= 4096 * 2:
        if self.recognizer.AcceptWaveform(data):
            answer = json.loads(self.recognizer.Result())
            # TODO make the cosine distance boundary a config parameter
            if "spk" in answer:
                distance = cosine_dist(spk_sig, answer["spk"])
                if distance < 0.65 and answer["text"]:
                    log.info(f"Text recognized: {answer['text']}, speaker distance: {distance}")
                    yield answer["text"]
                elif distance > 0.45:
                    log.info(
                        f"Speaker distance is greater than a boundary: {distance} > 0.45. result will not be processed")

            # self.audio_chunk = b""
        #
        # else:
        #     self.audio_chunk = b""

    # def count_voice_activity(self, times):
    #     thread = threading.Timer(times, self.voice_activity_set)
    #     thread.start()
    #
    # def voice_activity_set(self):
    #     self.voice_detected = False

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
