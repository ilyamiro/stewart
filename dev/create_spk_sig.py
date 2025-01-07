import os
import sys
import json
import numpy as np
import pyaudio
from collections import deque
from vosk import Model, KaldiRecognizer, SpkModel

PARENT = os.path.dirname(os.path.dirname(__file__))

MODEL_PATH = f"{PARENT}/audio/input/models/vosk-model-small-en"
SPK_MODEL_PATH = f"{PARENT}/audio/input/models/vosk-model-speaker-recognition"
SAMPLE_RATE = 16000
CHANNELS = 1
FRAMES_PER_BUFFER = 8000
XVECTOR_BUFFER_MAXLEN = 50
OUTPUT_FILE = "vector_combine.txt"


def check_model_paths(model_path, spk_model_path):
    """
    Check if the required model directories exist.
    """
    if not os.path.exists(model_path):
        print(f"Speech recognition model not found at {model_path}.")
        sys.exit(1)

    if not os.path.exists(spk_model_path):
        print(f"Speaker recognition model not found at {spk_model_path}.")
        sys.exit(1)


def initialize_audio_stream(rate, channels, frames_per_buffer):
    """
    Initialize the audio stream using PyAudio.
    """
    pyaudio_instance = pyaudio.PyAudio()
    stream = pyaudio_instance.open(
        rate=rate,
        channels=channels,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=frames_per_buffer
    )
    return stream


def process_audio_data(recognizer, stream, xvector_buffer):
    """
    Process audio data from the stream and update the x-vector buffer.

    :param recognizer: The KaldiRecognizer object.
    :param stream: The PyAudio stream object.
    :param xvector_buffer: A deque for storing speaker x-vectors.
    :return: The calculated speaker signature if the buffer is full; otherwise, None.
    """
    data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
    if recognizer.AcceptWaveform(data) and len(data) > 1:
        result = json.loads(recognizer.Result())
        print("Text:", result.get("text", ""))

        if "spk" in result:
            xvector_buffer.append(result["spk"])

        # Display how many samples have been recorded out of XVECTOR_BUFFER_MAXLEN
        print(f"Recorded {len(xvector_buffer)} out of {XVECTOR_BUFFER_MAXLEN} samples.")

        if len(xvector_buffer) == xvector_buffer.maxlen:
            return np.mean(np.array(xvector_buffer), axis=0)

    return None


def save_speaker_signature(signature, output_file):
    """
    Save the speaker signature to a file.

    :param signature: The speaker signature vector.
    :param output_file: The path to the output file.
    """
    with open(output_file, "w") as file:
        file.write(json.dumps(signature.tolist()))
    print(f"Speaker signature saved to {output_file}.")


def main():
    check_model_paths(MODEL_PATH, SPK_MODEL_PATH)

    print("Loading models...")
    speech_model = Model(MODEL_PATH)
    spk_model = SpkModel(SPK_MODEL_PATH)
    recognizer = KaldiRecognizer(speech_model, SAMPLE_RATE)
    recognizer.SetSpkModel(spk_model)

    print("Initializing audio stream...")
    stream = initialize_audio_stream(SAMPLE_RATE, CHANNELS, FRAMES_PER_BUFFER)

    xvector_buffer = deque(maxlen=XVECTOR_BUFFER_MAXLEN)

    print("Listening... Speak into the microphone.")
    try:
        while True:
            speaker_signature = process_audio_data(recognizer, stream, xvector_buffer)
            if speaker_signature is not None:
                save_speaker_signature(speaker_signature, OUTPUT_FILE)
                break
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
    finally:
        stream.stop_stream()
        stream.close()


if __name__ == "__main__":
    main()
