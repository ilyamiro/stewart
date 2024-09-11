import os
import sys
import wave
import json
import numpy as np
import pyaudio
#
from vosk import Model, KaldiRecognizer, SpkModel

def int2float(sound):
    abs_max = np.abs(sound).max()
    sound = sound.astype('float32')
    if abs_max > 0:
        sound *= 1/32768
    sound = sound.squeeze()  # depends on the use case
    return sound


SPK_MODEL_PATH = "model-spk"

if not os.path.exists(SPK_MODEL_PATH):
    print("Please download the speaker model from "
          "https://alphacephei.com/vosk/models and unpack as {SPK_MODEL_PATH} "
          "in the current folder.")
    sys.exit(1)

model = Model(f"audio/input/models/vosk-model-small-en")
# spk_model = SpkModel(SPK_MODEL_PATH)
rec = KaldiRecognizer(model, 16000)
# rec.SetSpkModel(spk_model)
#

spk_sig = [-0.857388, 1.267901, 0.666186, 0.326028, -0.737559, 0.521541, -0.209563, -0.79837, 0.569508, 0.381716, 2.089892, -0.043537, -0.604797, -1.723225, 0.279634, 0.143845, -0.262894, 0.293458, 0.850604, -1.435306, -0.647531, 2.359369, 2.217211, -1.014582, -0.078705, 0.447314, -0.680023, -0.114505, 1.265276, 0.70798, 0.488847, -1.670824, -0.457945, -0.129431, -0.626302, -0.505419, 0.618178, 0.143382, -0.199264, 0.030403, 0.658246, 1.666422, -0.756901, -1.423942, -0.597592, 0.991916, -1.24184, -0.311744, 0.76946, -0.325768, -0.233096, 1.506559, 0.190446, 0.724308, -1.25527, 0.474903, 1.676857, -0.142437, 0.880388, -0.713081, -0.168784, -0.102847, -0.04719, -1.66154, -1.109308, -1.771462, -2.121895, 0.955677, -0.199293, 1.20099, 0.091956, -0.483682, -0.602744, 0.36566, 0.656577, 1.661189, -1.460805, -0.30318, 1.564216, 0.276965, 0.868866, -2.65589, -0.963156, -1.485952, -0.131087, -0.199232, -1.664947, 0.609063, -0.83675, 0.238065, -0.074272, -1.578898, 0.417254, -1.716341, 0.013029, -0.160283, 0.964061, 0.440946, 1.18175, 0.512477, -1.252912, -1.946625, -0.71925, -1.138703, 0.267289, -0.125581, 0.795256, 0.140335, -0.981874, -0.841791, -1.798091, 0.702305, 1.708112, -1.072151, 1.432951, 0.779821, -1.527061, 0.139678, 0.311706, -0.046188, -1.82091, -0.377667, 1.360205, 0.196167, -0.649477, 0.793452, -0.15054, -0.233445]


def cosine_dist(x, y):
    nx = np.array(x)
    ny = np.array(y)
    return 1 - np.dot(nx, ny) / np.linalg.norm(nx) / np.linalg.norm(ny)


pyaudio_instance = pyaudio.PyAudio()

stream = pyaudio_instance.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True,
                               frames_per_buffer=8000)
#

while True:
    data = stream.read(4000, exception_on_overflow=False)
    if rec.AcceptWaveform(data) and len(data) > 1 and stream.is_active():
        res = json.loads(rec.Result())
        print("Text:", res["text"])
        if "spk" in res:
            print("X-vector:", res["spk"])
            print("Speaker distance:", cosine_dist(spk_sig, res["spk"]),
                "based on", res["spk_frames"], "frames")



# import torch
#
# model, example_texts, languages, punct, apply_te = torch.hub.load(repo_or_dir='snakers4/silero-models',
#                                                                   model='silero_te')
#
# input_text = input('Enter input text\n')
# print(apply_te(input_text, lan='en'))