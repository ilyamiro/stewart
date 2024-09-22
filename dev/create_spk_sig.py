import os
import sys
import wave
import json
import numpy as np
import pyaudio
from collections import deque
from vosk import Model, KaldiRecognizer, SpkModel


def int_to_float(sound):
    """Convert integer sound data to float format."""
    abs_max = np.abs(sound).max()
    sound = sound.astype('float32')

    if abs_max > 0:
        sound *= 1 / 32768

    return sound.squeeze()  # Adjust based on the use case


# Path to the speaker recognition model
SPK_MODEL_PATH = "models/vosk-model-speaker-recognition"

# Check if the speaker model exists
if not os.path.exists(SPK_MODEL_PATH):
    print(f"Please download the speaker model from "
          f"https://alphacephei.com/vosk/models and unpack it as {SPK_MODEL_PATH} "
          f"in the current folder.")
    sys.exit(1)

# Initialize Vosk models
model = Model("models/vosk-model-small-en")
spk_model = SpkModel(SPK_MODEL_PATH)
rec = KaldiRecognizer(model, 16000)
rec.SetSpkModel(spk_model)

# Initialize PyAudio
pyaudio_instance = pyaudio.PyAudio()
stream = pyaudio_instance.open(rate=16000,
                               channels=1,
                               format=pyaudio.paInt16,
                               input=True,
                               frames_per_buffer=8000)

# Buffer to store x-vectors for speaker recognition
xvector_buffer = deque(maxlen=50)

# Main loop for audio processing
while True:
    data = stream.read(4000, exception_on_overflow=False)

    # Accept the waveform and process it
    if rec.AcceptWaveform(data) and len(data) > 1 and stream.is_active():
        res = json.loads(rec.Result())
        print("Text:", res.get("text", ""))  # Use .get() for safer access

        # Append speaker x-vector to the buffer
        if "spk" in res:
            xvector_buffer.append(res["spk"])

        # Calculate and save speaker signature if buffer is full
        if len(xvector_buffer) == xvector_buffer.maxlen:
            speaker_signature = np.mean(np.array(xvector_buffer), axis=0)
            with open("vector.txt", "w") as file:
                file.write(str(res["spk"]))
            break
