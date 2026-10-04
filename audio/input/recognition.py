import os
import sys
import json
import threading
import ast
import logging
import time
import shutil
import re
import functools
import contextlib
from pathlib import Path

import numpy as np

@contextlib.contextmanager
def silence_c_stderr():
    """Silences C-level stderr (file descriptor 2) to eliminate noisy ALSA/Jack/PortAudio logs."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        sys.stderr.flush()
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            yield
        finally:
            sys.stderr.flush()
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
    except Exception:
        yield

try:
    with silence_c_stderr():
        import pyaudio
except (ImportError, Exception):
    pyaudio = None

torch = None

try:
    from vosk import KaldiRecognizer, Model, SpkModel, SetLogLevel
    if SetLogLevel:
        SetLogLevel(-1)
except (ImportError, Exception):
    KaldiRecognizer = Model = SpkModel = SetLogLevel = None

WhisperModel = None
openai_whisper = None

from data.constants import PROJECT_DIR, CONFIG_FILE, USER_DATA_DIR
from utils import load_yaml
from audio.input.corrector import WhisperVoiceCorrector
from audio.input.voice_isolator import isolate_voice

# Logging setup
log = logging.getLogger("stt")

# Configuration and model paths
SPK_MODEL_PATH = f"{PROJECT_DIR}/audio/input/models/vosk-model-speaker-recognition"
MODEL_BASE_PATH = f"{PROJECT_DIR}/audio/input/models"

WHISPER_STRENGTH_PRESETS = {
    "low": {"model": "tiny", "beam_size": 1},
    "fast": {"model": "tiny", "beam_size": 1},
    "medium": {"model": "base", "beam_size": 2},
    "balanced": {"model": "base", "beam_size": 2},
    "high": {"model": "small", "beam_size": 5},
    "precise": {"model": "small", "beam_size": 5},
    "very_high": {"model": "medium", "beam_size": 5},
    "ultra": {"model": "large-v3", "beam_size": 5},
    "maximum": {"model": "large-v3", "beam_size": 5},
}

_config = None


def _get_config():
    global _config
    if _config is not None:
        return _config
    try:
        from api import app
        _config = app.config
        return _config
    except Exception:
        _config = load_yaml(CONFIG_FILE) or {}
        return _config


@functools.lru_cache(maxsize=16)
def _load_speaker_signature(lang: str):
    candidate_paths = [
        USER_DATA_DIR / f"vectors/{lang}.txt",
        Path(PROJECT_DIR) / f"audio/input/vectors/{lang}.txt"
    ]
    for path in candidate_paths:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return ast.literal_eval(f.read().replace("\n", ""))
            except Exception as e:
                log.warning(f"Error loading speaker vector from {path}: {e}")
    return None


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
    def __init__(self, lang: str, size: str = None, backend: str = None):
        self.config = _get_config()
        stt_cfg = self.config.get("audio", {}).get("stt", {})
        raw_backend = backend or stt_cfg.get("backend") or stt_cfg.get("engine") or "vosk"
        if raw_backend.lower() in ("whisper", "faster-whisper", "whisper.cpp", "whisper-cpp"):
            self.backend = "whisper"
        else:
            self.backend = "vosk"

        missing = []
        if pyaudio is None:
            missing.append("pyaudio")

        if self.backend == "vosk":
            if Model is None:
                missing.append("vosk")
        elif self.backend == "whisper":
            whisper_avail = False
            try:
                from faster_whisper import WhisperModel
                whisper_avail = True
            except (ImportError, Exception):
                pass
            try:
                import whisper as openai_whisper
                whisper_avail = True
            except (ImportError, Exception):
                pass
            if not whisper_avail and shutil.which("whisper-cli") is None:
                missing.append("faster-whisper (or openai-whisper / whisper-cpp)")

        if missing:
            raise RuntimeError(f"Missing STT dependencies for backend '{self.backend}': {', '.join(missing)}")

        self.lang = lang
        strength = str(stt_cfg.get("strength", "high")).lower()
        preset = WHISPER_STRENGTH_PRESETS.get(strength, WHISPER_STRENGTH_PRESETS["high"])

        if self.backend == "vosk":
            vosk_model = size or stt_cfg.get("vosk_model") or stt_cfg.get("model")
            if not vosk_model or vosk_model in ("tiny", "base", "medium", "large"):
                vosk_model = "small"
            self.size = vosk_model
            self.beam_size = 1
        else:
            whisper_model = size or stt_cfg.get("whisper_model") or stt_cfg.get("model") or preset["model"]
            self.size = whisper_model
            self.beam_size = int(stt_cfg.get("beam_size", preset["beam_size"]))

        self.vad_threshold = float(stt_cfg.get("vad_threshold", 0.5))
        self.pause_threshold = float(stt_cfg.get("pause_threshold", 0.8))
        self.min_speech_duration = float(stt_cfg.get("min_speech_duration", 0.25))

        # -------- Audio Stream Initialization --------
        with silence_c_stderr():
            self.pyaudio_instance = pyaudio.PyAudio()
            self.stream = self._initialize_audio_stream()

        # -------- VAD Model Background Loading --------
        # NOTE: must load on the main thread. Loading the TorchScript model in a background thread
        # while other threads import torch/transformers (Kokoro) crashed with SIGFPE on first inference.
        self._vad_model = None
        self._vad_thread = None
        self._load_vad_model()

        # -------- Backend Specific Initialization --------
        if self.backend == "vosk":
            self.model_path = f"{MODEL_BASE_PATH}/vosk-model-{self.size}-{self.lang}"
            self.model = self._load_model()
            if stt_cfg.get("speaker-recognition"):
                self.spk_model = self._load_speaker_model()
            else:
                self.spk_model = None
            self.recognizer = self.create_new_recognizer()
            log.info(f"Initialized Vosk STT engine (model: {self.size}, lang: {self.lang})")
        else:
            self.recognizer = None
            self.spk_model = None
            self.model = None
            self._whisper_model = None
            self._whisper_lock = threading.Lock()
            self._whisper_thread = threading.Thread(target=self._init_whisper_background, daemon=True, name="Whisper-Init")
            self._whisper_thread.start()
            self.speech_buffer = b""
            self.pre_buffer = []
            self.silence_count = 0
            self.is_speaking = False
            self.corrector = WhisperVoiceCorrector(lang=self.lang)
            self.hotwords_str = None
            configured_triggers = self.config.get("settings", {}).get("trigger", {}).get("triggers", ["stewart"])
            if self.lang == "ru":
                self.initial_prompt = f"{', '.join(configured_triggers)}, Стюарт, закрой вкладку, открой страницу, поставь на паузу, включи музыку, сделай громче, выключи свет, поставь таймер, найди видео."
            else:
                self.initial_prompt = f"{', '.join(configured_triggers)}, Stewart, open tab, close tab, pause video, play music, volume up, volume down, next video, set timer, turn off lights, find video."
            log.info(f"Initialized Whisper STT engine (model: {self.size}, strength: {strength}, beam_size: {self.beam_size}, lang: {self.lang})")

    def _initialize_audio_stream(self):
        """
        Set up PyAudio stream for audio input.

        Uses a mono, 16kHz, 16-bit format.
        """
        device_index = self.config.get("audio", {}).get("stt", {}).get("device_index")
        with silence_c_stderr():
            open_kwargs = {
                "rate": 16000,
                "channels": 1,
                "format": pyaudio.paInt16,
                "input": True,
                "frames_per_buffer": 2048,
            }
            if device_index is not None:
                open_kwargs["input_device_index"] = int(device_index)
            stream = self.pyaudio_instance.open(**open_kwargs)
        log.debug("PyAudio stream instance successfully opened for input")
        return stream

    def _load_model(self):
        """
        Load Vosk model for speech recognition.
        """
        if not os.path.exists(self.model_path):
            alt_path = Path(PROJECT_DIR) / f"audio/input/models/vosk-model-{self.size}-{self.lang}"
            if alt_path.exists():
                self.model_path = str(alt_path)
            else:
                cwd_path = Path.cwd() / f"audio/input/models/vosk-model-{self.size}-{self.lang}"
                if cwd_path.exists():
                    self.model_path = str(cwd_path)
                else:
                    fallback = Path(PROJECT_DIR) / f"audio/input/models/vosk-model-small-{self.lang}"
                    if fallback.exists():
                        self.model_path = str(fallback)
        model = Model(str(self.model_path))
        log.debug(f"Vosk model loaded from {self.model_path}")
        return model

    def _load_whisper_model(self):
        """
        Load Whisper model using faster-whisper, openai-whisper, or whisper-cli.
        """
        stt_cfg = self.config.get("audio", {}).get("stt", {})
        model_name = self.size
        # Use English-specific model for faster/better English transcription if applicable
        if self.lang == "en" and model_name in ("tiny", "base", "small", "medium"):
            model_name = f"{model_name}.en"

        device = stt_cfg.get("device", "auto")
        if device == "auto":
            try:
                import torch
                device = "cuda" if (torch.cuda.is_available() and torch.cuda.device_count() > 0) else "cpu"
            except Exception:
                device = "cpu"

        compute_type = stt_cfg.get("compute_type", "default")
        if compute_type in ("default", "auto", None):
            compute_type = "int8" if device == "cpu" else "float16"

        try:
            from faster_whisper import WhisperModel
            log.info(f"Loading faster-whisper model '{model_name}' on {device} ({compute_type})...")
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            log.info("faster-whisper model loaded successfully")
            return ("faster-whisper", model)
        except (ImportError, Exception):
            pass

        try:
            import whisper as openai_whisper
            log.info(f"Loading openai-whisper model '{model_name}' on {device}...")
            model = openai_whisper.load_model(model_name, device=device)
            log.info("openai-whisper model loaded successfully")
            return ("openai-whisper", model)
        except (ImportError, Exception):
            pass

        if shutil.which("whisper-cli") is not None:
            log.info("Using whisper-cli (whisper.cpp) for STT")
            return ("whisper-cli", shutil.which("whisper-cli"))
        else:
            raise RuntimeError("No Whisper implementation available")

    def _init_whisper_background(self):
        with self._whisper_lock:
            if self._whisper_model is None:
                self._whisper_model = self._load_whisper_model()

    def wait_ready(self, timeout: int = 120):
        if self.backend == "whisper":
            if hasattr(self, "_whisper_thread") and self._whisper_thread and self._whisper_thread.is_alive():
                self._whisper_thread.join(timeout=timeout)
            return self._whisper_model is not None
        return True

    @property
    def whisper_model(self):
        if self._whisper_model is None:
            if hasattr(self, "_whisper_thread") and self._whisper_thread and self._whisper_thread.is_alive():
                self._whisper_thread.join()
            elif self._whisper_model is None:
                self._init_whisper_background()
        return self._whisper_model

    @staticmethod
    def _load_speaker_model():
        """
        Load speaker recognition model.
        """
        spk_path = SPK_MODEL_PATH
        if not os.path.exists(spk_path):
            alt = Path(PROJECT_DIR) / "audio/input/models/vosk-model-speaker-recognition"
            if alt.exists():
                spk_path = str(alt)
            else:
                cwd_path = Path.cwd() / "audio/input/models/vosk-model-speaker-recognition"
                if cwd_path.exists():
                    spk_path = str(cwd_path)
        spk_model = SpkModel(str(spk_path))
        log.debug("Speaker model loaded")
        return spk_model

    def _init_vad_background(self):
        try:
            self._load_vad_model()
        except Exception as e:
            log.warning(f"Background VAD init warning: {e}")

    def _load_vad_model(self):
        """
        Load voice activity detection (VAD) model.
        """
        if self._vad_model is not None:
            return self._vad_model
        global torch
        if torch is None:
            import torch
        try:
            torch.set_num_threads(1)
        except Exception:
            pass
        vad_path = f"{MODEL_BASE_PATH}/silero_vad.jit"
        if not os.path.exists(vad_path):
            alt = Path(PROJECT_DIR) / "audio/input/models/silero_vad.jit"
            if alt.exists():
                vad_path = str(alt)
            else:
                cwd_path = Path.cwd() / "audio/input/models/silero_vad.jit"
                if cwd_path.exists():
                    vad_path = str(cwd_path)
        self._vad_model = torch.jit.load(str(vad_path), map_location="cpu")
        # Warm-up forward pass: initializes BLAS/JIT state once, on this thread, so concurrent
        # torch users (Kokoro init thread) don't race with the first real inference.
        try:
            with torch.no_grad():
                self._vad_model(torch.zeros(512), 16000)
            self._vad_model.reset_states()
        except Exception:
            pass
        log.debug("VAD model loaded")
        try:
            from audio.tts.synthesis import TORCH_READY
            TORCH_READY.set()
        except Exception:
            pass
        return self._vad_model

    @property
    def vad_model(self):
        if self._vad_model is None:
            if hasattr(self, "_vad_thread") and self._vad_thread and self._vad_thread.is_alive():
                self._vad_thread.join()
            if self._vad_model is None:
                self._load_vad_model()
        return self._vad_model

    def set_command_vocabulary(self, manager=None, words=None, triggers=None):
        """
        Dynamically updates the command vocabulary, hotwords, and initial prompt for Whisper.
        Also configures the WhisperVoiceCorrector with active command tree vocabulary.
        """
        vocab_words = set(words or [])
        phrases = []
        if manager is not None:
            if hasattr(manager, "get_all_vocabulary"):
                vocab = manager.get_all_vocabulary()
                vocab_words.update(vocab.get("words", []))
                phrases.extend(vocab.get("phrases", []))
            elif hasattr(manager, "_all_known_words"):
                vocab_words.update(manager._all_known_words)

        all_triggers = list(triggers or self.config.get("settings", {}).get("trigger", {}).get("triggers", ["stewart"]))
        for standard in ("стюарт", "стюард", "stewart", "steward"):
            if standard not in all_triggers:
                all_triggers.append(standard)

        self.corrector.set_vocabulary(vocab_words, triggers=all_triggers, phrases=phrases)

        # Build hotwords string for faster-whisper decoder biasing
        hotword_set = set(all_triggers)
        hotword_set.update(vocab_words)
        clean_hotwords = [w for w in hotword_set if w and len(w) >= 2]
        self.hotwords_str = " ".join(sorted(clean_hotwords))

        # Build dynamic initial prompt with triggers and sample commands
        sample_phrases = phrases[:12] if phrases else []
        if sample_phrases:
            phrase_str = ", ".join(sample_phrases)
            self.initial_prompt = f"{', '.join(all_triggers)}. {phrase_str}."
        elif self.lang == "ru":
            self.initial_prompt = f"{', '.join(all_triggers)}, закрой вкладку, открой страницу, пауза, включи музыку, сделай громче, выключи свет, поставь таймер, найди видео."
        else:
            self.initial_prompt = f"{', '.join(all_triggers)}, open tab, close tab, pause video, play music, volume up, volume down, next video, set timer, turn off lights, find video."

        log.info(f"Updated Whisper vocabulary: {len(vocab_words)} words, {len(all_triggers)} triggers, prompt length {len(self.initial_prompt)}")

    def transcribe_whisper(self, pcm_bytes: bytes) -> str:
        """
        Transcribe raw 16kHz 16-bit mono PCM bytes using Whisper.
        Applies audio conditioning, prompt & hotwords biasing, and acoustic voice correction.
        """
        if not pcm_bytes:
            return ""

        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Voice isolation: bandpass filter (80Hz-7.5kHz), Silero VAD speech masking,
        # non-speech gap attenuation, and peak/RMS AGC normalization
        audio_float32 = isolate_voice(audio_float32, vad_model=self.vad_model, sr=16000)

        model_entry = self.whisper_model
        if not model_entry:
            log.warning("Whisper model is not available or failed to load")
            return ""
        engine_type, engine = model_entry
        text = ""
        words_with_prob = []

        try:
            if engine_type == "faster-whisper":
                transcribe_kwargs = {
                    "language": self.lang,
                    "initial_prompt": getattr(self, "initial_prompt", None),
                    "beam_size": self.beam_size,
                    "temperature": 0.0,
                    "vad_filter": False,
                    "condition_on_previous_text": False,
                    "word_timestamps": True,
                }
                if getattr(self, "hotwords_str", None):
                    transcribe_kwargs["hotwords"] = self.hotwords_str

                segments, info = engine.transcribe(audio_float32, **transcribe_kwargs)
                raw_parts = []
                for seg in segments:
                    raw_parts.append(seg.text)
                    if hasattr(seg, "words") and seg.words:
                        for w in seg.words:
                            clean_w = re.sub(r"[^\w]", "", w.word).strip().lower()
                            if clean_w:
                                words_with_prob.append((clean_w, getattr(w, "probability", 1.0)))
                text = " ".join(raw_parts).strip()

            elif engine_type == "openai-whisper":
                result = engine.transcribe(
                    audio_float32,
                    language=self.lang,
                    fp16=(self.config.get("audio", {}).get("stt", {}).get("device") == "cuda"),
                    beam_size=self.beam_size,
                    temperature=0.0,
                    initial_prompt=getattr(self, "initial_prompt", None),
                    condition_on_previous_text=False,
                )
                text = result.get("text", "").strip()

            elif engine_type == "whisper-cli":
                import tempfile
                import subprocess
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    wav_path = f.name
                try:
                    import soundfile as sf
                    sf.write(wav_path, audio_float32, 16000)
                    cmd = [engine, "-l", self.lang, "-nt", "-f", wav_path]
                    prompt = getattr(self, "initial_prompt", None)
                    if prompt:
                        cmd.extend(["-p", prompt])
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                    text = res.stdout.strip()
                finally:
                    if os.path.exists(wav_path):
                        os.remove(wav_path)
        except Exception as e:
            log.error(f"Whisper transcription error: {e}")
            return ""

        cleaned = re.sub(r"[^\w\s]", "", text).lower().strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            return ""

        # Post-transcription acoustic, phonetic & vocabulary alignment
        corrected = self.corrector.correct(cleaned, words_with_prob)
        if corrected != cleaned:
            log.info(f"Whisper transcript aligned: '{cleaned}' -> '{corrected}'")
        else:
            log.info(f"Text recognized (Whisper): '{corrected}'")
        return corrected

    def listen(self, data):
        """
        Listen for speech input.
        - For Vosk: feeds chunks into Kaldi recognizer and yields on accepted waveform.
        - For Whisper: detects speech activity, accumulates speech buffer, and transcribes upon silence.
        """
        if self.backend == "vosk":
            result = self.process(data)
            if result:
                yield result
        elif self.backend == "whisper":
            has_voice = self.vad(data)
            chunk_samples = len(data) // 2
            chunk_duration = (chunk_samples / 16000.0) if chunk_samples > 0 else 0.064
            silence_chunks_needed = max(4, int(self.pause_threshold / chunk_duration))

            if has_voice:
                if not self.is_speaking:
                    self.is_speaking = True
                    self.silence_count = 0
                    self.speech_buffer = b"".join(self.pre_buffer) + data
                    self.pre_buffer = []
                else:
                    self.speech_buffer += data
                    self.silence_count = 0
            else:
                if self.is_speaking:
                    self.speech_buffer += data
                    self.silence_count += 1
                    if self.silence_count >= silence_chunks_needed:
                        self.is_speaking = False
                        self.silence_count = 0
                        min_bytes = int(self.min_speech_duration * 16000 * 2)
                        if len(self.speech_buffer) >= min_bytes:
                            pcm = self.speech_buffer
                            self.speech_buffer = b""
                            text = self.transcribe_whisper(pcm)
                            if text:
                                yield text
                        self.speech_buffer = b""
                else:
                    self.pre_buffer.append(data)
                    max_pre_chunks = max(6, int(0.35 / chunk_duration))
                    if len(self.pre_buffer) > max_pre_chunks:
                        self.pre_buffer.pop(0)

    def flush(self):
        """
        Drains all pending audio frames from the hardware microphone stream
        and resets speech buffers, silence counters, and VAD model state.
        Ensures recognition starts with clean, current audio.
        """
        if hasattr(self, "stream") and self.stream:
            try:
                available = self.stream.get_read_available()
                if available > 0:
                    self.stream.read(available, exception_on_overflow=False)
            except Exception as e:
                log.debug(f"Audio stream flush warning: {e}")

        self.speech_buffer = b""
        if hasattr(self, "pre_buffer") and isinstance(self.pre_buffer, list):
            self.pre_buffer.clear()
        self.silence_count = 0
        self.is_speaking = False

        if hasattr(self, "_vad_model") and self._vad_model is not None:
            try:
                self._vad_model.reset_states()
            except Exception:
                pass
        log.debug("STT audio stream and internal buffers flushed.")


    def process(self, data):
        """
        Process audio data.
        """
        if self.backend == "vosk":
            if self.recognizer and self.recognizer.AcceptWaveform(data):
                answer = json.loads(self.recognizer.Result())
                if self.config["audio"]["stt"]["speaker-recognition"]:
                    spk_sig = _load_speaker_signature(self.lang)
                    if "spk" in answer and spk_sig:
                        distance = cosine_dist(spk_sig, answer["spk"])
                        if distance < 0.55 and answer.get("text"):
                            log.info(f"Text recognized: {answer['text']}, speaker distance: {distance}")
                            return answer["text"]
                        else:
                            log.info(f"Speaker distance ({distance}) exceeds threshold. Ignoring result.")
                    elif answer.get("text"):
                        return answer["text"]
                else:
                    if answer.get("text"):
                        log.info(f"Text recognized: {answer['text']}")
                        return answer["text"]
        elif self.backend == "whisper":
            return self.transcribe_whisper(data)

    def check_speaker(self, data):
        if self.backend == "vosk" and self.config["audio"]["stt"]["speaker-recognition"]:
            spk_sig = _load_speaker_signature(self.lang)
            if self.recognizer and self.recognizer.AcceptWaveform(data):
                answer = json.loads(self.recognizer.Result())
                if "spk" in answer and spk_sig:
                    distance = cosine_dist(spk_sig, answer["spk"])
                    log.info(f"Speaker recognized with distance: {distance}")
                    return distance < 0.40
                return True
            return False
        return True

    # -------- Voice Activity Detection --------
    def vad(self, data):
        """
        Detect voice activity using VAD model.
        Silero VAD requires 512 samples at 16000Hz.
        Handles arbitrary input lengths by checking 512-sample windows.
        """
        if not data or len(data) < 512:
            return False
        audio_int16 = np.frombuffer(data, np.int16)
        audio_float32 = int2float(audio_int16)
        if len(audio_float32) < 512:
            return False

        if self.vad_model is None:
            return False

        window_size = 512
        threshold = getattr(self, "vad_threshold", 0.5)
        for i in range(0, len(audio_float32) - window_size + 1, window_size):
            chunk = audio_float32[i : i + window_size]
            with torch.no_grad():
                confidence = self.vad_model(torch.from_numpy(chunk), 16000).item()
            if confidence > threshold:
                return True
        return False

    def create_new_recognizer(self):
        """
        Initialize a new Vosk recognizer.
        """
        if self.backend == "vosk" and self.model:
            recognizer = KaldiRecognizer(self.model, 16000)
            if self.config["audio"]["stt"]["speaker-recognition"]:
                recognizer.SetSpkModel(self.spk_model)
            log.info("New vosk recognizer instance created")
            return recognizer
        return None

    @staticmethod
    def set_grammar(path, recognizer):
        """
        Set grammar for recognizer from file.
        """
        if recognizer is not None and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                recognizer.SetGrammar(file.readline())
        return recognizer

