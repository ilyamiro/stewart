import io
import time

import numpy as np
import torch

torch.set_num_threads(1)
import torchaudio
import matplotlib
import matplotlib.pylab as plt

torchaudio.set_audio_backend("soundfile")
import pyaudio

model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                              model='silero_vad',
                              force_reload=True)

(get_speech_timestamps,
 save_audio,
 read_audio,
 VADIterator,
 collect_chunks) = utils

import os


# Taken from utils_vad.py
def validate(model,
             inputs: torch.Tensor):
    with torch.no_grad():
        outs = model(inputs)
    return outs


# Provided by Alexander Veysov
def int2float(sound):
    abs_max = np.abs(sound).max()
    sound = sound.astype('float32')
    if abs_max > 0:
        sound *= 1 / 32768
    sound = sound.squeeze()  # depends on the use case
    return sound


FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 16000
CHUNK = 8000

audio = pyaudio.PyAudio()

num_samples = 512

stream = audio.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK)
data = []

def print_(confidence):
    if confidence > 0.85:
        print("\033c", end="")
        print('Voice activity detected')
    else:
        print("\033c", end="")
        print("-------------")

print("Started Recording")
while True:
    audio_chunk = stream.read(num_samples)

    # in case you want to save the audio later
    data.append(audio_chunk)

    audio_int16 = np.frombuffer(audio_chunk, np.int16)

    audio_float32 = int2float(audio_int16)

    # get the confidences and add them to the list to plot them later
    new_confidence = model(torch.from_numpy(audio_float32), 16000).item()

    print_(new_confidence)


