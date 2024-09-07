import pyaudio

import openwakeword
from openwakeword.model import Model

pya = pyaudio.PyAudio()
stream = pya.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True,
                  frames_per_buffer=8000)

# One-time download of all pre-trained models (or only select models)
openwakeword.utils.download_models()

# Instantiate the model(s)
model = Model(
    wakeword_models=["path/to/model.tflite"],
    enable_speex_noise_suppression=True
    # can also leave this argument empty to load all of the included pre-trained models
)

# Get audio data containing 16-bit 16khz PCM audio data from a file, microphone, network stream, etc.
# For the best efficiency and latency, audio frames should be multiples of 80 ms, with longer frames
# increasing overall efficiency at the cost of detection latency

# Get predictions for the frame

#
# while True:
#     data = stream.read(4000, exception_on_overflow=False)
#     if len(data) > 1:
#         prediction = model.predict(data)
#         print(prediction)
