import os
import sys
import json
import threading
import ast
import logging
from pathlib import Path

import numpy as np
import pyaudio
import torch
from vosk import KaldiRecognizer, Model, SpkModel

from data.constants import PROJECT_FOLDER, CONFIG_FILE
from utils.utils import load_yaml

# Logging setup
log = logging.getLogger("stt")

# Configuration and model paths
config = load_yaml(CONFIG_FILE)
SPK_MODEL_PATH = f"{PROJECT_FOLDER}/audio/input/models/vosk-model-speaker-recognition"
MODEL_BASE_PATH = f"{PROJECT_FOLDER}/audio/input/models"

# Load speaker signature
with open(f"{PROJECT_FOLDER}/audio/input/vector.txt", "r", encoding="utf-8") as f:
    spk_sig = ast.literal_eval(f.read().replace("\n", ""))


# Utility functions
def int2float(sound):
    """
    Convert sound array to float32 format.

    Ensures values are normalized between -1 and 1.
    """
    sound = sound.astype('float32')
    abs_max = np.abs(sound).max()
    if abs_max > 0:
        sound *= 1 / 32768
    return sound.squeeze()


def cosine_dist(x, y):
    """
    Calculate cosine similarity distance.

    Returns value between 0 and 1 for speaker matching.
    """
    return 1 - np.dot(np.array(x), np.array(y)) / (np.linalg.norm(x) * np.linalg.norm(y))


class STT:
    def __init__(self, lang: str, size: str = "small"):

        # -------- Audio Stream Initialization --------
        self.lang = lang
        self.size = size
        self.pyaudio_instance = pyaudio.PyAudio()
        self.stream = self._initialize_audio_stream()

        # -------- Model Loading --------
        self.model_path = f"{MODEL_BASE_PATH}/vosk-model-{size}-{lang}"
        self.model = self._load_model()
        self.spk_model = self._load_speaker_model()
        self.vad_model = self._load_vad_model()

        # -------- Recognizer Initialization --------
        self.recognizer = self.create_new_recognizer()

        # -------- Listener Configuration --------
        self.listen = self.listen_vad if config["audio"]["stt"]["activity-detection"] else self.listen_no_vad
        self.voice_activity = not config["audio"]["stt"]["activity-detection"]
        self.add_data = b""

    # -------- Initialization Helpers --------
    def _initialize_audio_stream(self):
        """
        Set up PyAudio stream for audio input.

        Uses a mono, 16kHz, 16-bit format.
        """
        stream = self.pyaudio_instance.open(
            rate=16000, channels=1, format=pyaudio.paInt16, input=True, frames_per_buffer=8192
        )
        log.debug("PyAudio stream instance successfully opened for input")
        return stream

    def _load_model(self):
        """
        Load Vosk model for speech recognition.

        Uses model path based on language and size.
        """
        model = Model(self.model_path)
        log.debug("Vosk model loaded")
        return model

    @staticmethod
    def _load_speaker_model():
        """
        Load speaker recognition model.

        Path is specified by project configuration.
        """
        spk_model = SpkModel(SPK_MODEL_PATH)
        log.debug("Speaker model loaded")
        return spk_model

    @staticmethod
    def _load_vad_model():
        """
        Load voice activity detection (VAD) model.

        Uses pre-trained Silero VAD model.
        """
        vad_model = torch.jit.load(f"{MODEL_BASE_PATH}/silero_vad.jit")
        log.debug("VAD model loaded")
        return vad_model

    def listen_no_vad(self):
        """
        Listen without voice activity detection.

        Reads data in 4k chunks and processes it.
        """
        data = self.stream.read(4000, exception_on_overflow=False)
        result = self.process(data)
        if result:
            yield result

    def listen_vad(self):
        """
        Listen with voice activity detection (VAD).

        Processes chunks or waits for voice activity.
        """
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

    def process(self, data):
        """
        Process audio data and check speaker distance.

        Filters results based on speaker similarity.
        """
        if self.recognizer.AcceptWaveform(data):
            answer = json.loads(self.recognizer.Result())
            if "spk" in answer:
                distance = cosine_dist(spk_sig, answer["spk"])
                if distance < 0.65 and answer["text"]:
                    log.info(f"Text recognized: {answer['text']}, speaker distance: {distance}")
                    return answer["text"]
                else:
                    log.info(f"Speaker distance ({distance}) exceeds threshold. Ignoring result.")

    # -------- Voice Activity Detection --------
    def voice_activity_detected(self, data):
        """
        Detect voice activity using VAD model.

        Returns True if confidence is above threshold.
        """
        audio_int16 = np.frombuffer(data, np.int16)
        audio_float32 = int2float(audio_int16)
        vad_confidence = self.vad_model(torch.from_numpy(audio_float32), 16000).item()
        if vad_confidence > 0.85:
            log.info("Detected voice activity")
            return True
        return False

    def count_voice_activity(self, times):
        """
        Start timer for voice activity period.

        Resets voice activity after set duration.
        """
        self.voice_activity = True
        thread = threading.Timer(times, self.voice_activity_set)
        thread.start()

    def voice_activity_set(self):
        """
        Reset voice activity status.

        Used after timer elapses.
        """
        self.voice_activity = False

    def create_new_recognizer(self):
        """
        Initialize a new Vosk recognizer.

        Sets speaker model for speaker identification.
        """
        recognizer = KaldiRecognizer(self.model, 16000)
        recognizer.SetSpkModel(self.spk_model)
        log.info("New vosk recognizer instance created")
        return recognizer

    @staticmethod
    def set_grammar(path, recognizer):
        """
        Set grammar for recognizer from file.

        Path specifies file with grammar rules.
        """
        with open(path, "r", encoding="utf-8") as file:
            recognizer.SetGrammar(file.readline())
        return recognizer
