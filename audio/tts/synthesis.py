import logging
import os
import re
import subprocess
import sys
import threading
from importlib import import_module
from pathlib import Path
from typing import Optional

import numpy as np

KPipeline = None

# Set once torch has been imported/warmed on the main thread (by the STT loader) or when voice input
# is not used. Kokoro's heavy torch/transformers import waits for it: running them concurrently with the
# first TorchScript/BLAS use crashes the process (SIGFPE/SIGSEGV in libopenblas sgemm).
TORCH_READY = threading.Event()

from data.constants import PROJECT_DIR, TTS_CACHE_DIR, USER_DATA_DIR
from utils import called_from

log = logging.getLogger("tts")

# Mapping Stewart language codes to Kokoro language codes
# Kokoro supports:
#   'a': American English, 'b': British English,
#   'e': Spanish, 'f': French, 'h': Hindi,
#   'i': Italian, 'j': Japanese, 'p': Portuguese, 'z': Chinese
LANGUAGE_CODES = {
    "en": "a",
    "en_us": "a",
    "en_gb": "b",
    "es": "e",
    "fr": "f",
    "hi": "h",
    "it": "i",
    "ja": "j",
    "pt": "p",
    "zh": "z",
}


def play_audio(path: str) -> None:
    """Plays audio file across Linux, macOS, and Windows."""
    if not os.path.exists(path):
        return

    if sys.platform == "linux":
        for player in ["paplay", "pw-play", "aplay", "mpv"]:
            try:
                cmd = ["mpv", "--no-video", "--really-quiet", path] if player == "mpv" else [player, path]
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
    elif sys.platform == "darwin":
        try:
            subprocess.run(
                ["afplay", path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    elif sys.platform == "win32":
        try:
            import playsound
            playsound.playsound(path)
        except Exception:
            pass


class TTS:
    """
    Kokoro-82M Text-to-Speech engine integration for Stewart.
    Lightweight, fast CPU neural speech synthesis.
    """

    def __init__(self, config: dict, lang: str):
        self.lang = lang
        self.config = config
        tts_cfg = config.get("audio", {}).get("tts", {})
        self.enabled = tts_cfg.get("enable", True)

        lang_cfg = tts_cfg.get(lang, {})
        sex = lang_cfg.get("sex", "m")
        self.default_voice = (
            lang_cfg.get("voice")
            or lang_cfg.get(sex)
            or ("af_heart" if sex == "f" else "am_adam")
        )
        self.lang_code = lang_cfg.get("lang_code") or LANGUAGE_CODES.get(lang.lower(), "a")
        self.speed = float(tts_cfg.get("speed", 1.0))

        self._pipeline_lock = threading.Lock()
        self._pipeline: Optional[object] = None
        self._init_thread = None

        if self.enabled:
            # Pre-warm Kokoro pipeline in background thread so application startup is instantaneous
            self._init_thread = threading.Thread(target=self._init_pipeline, daemon=True, name="Kokoro-Init")
            self._init_thread.start()

    @property
    def active(self) -> bool:
        return self.enabled

    @property
    def pipeline(self):
        return self.get_pipeline()

    def get_pipeline(self):
        if self._pipeline is None:
            if self._init_thread and self._init_thread.is_alive():
                self._init_thread.join()
            elif self._pipeline is None and self.enabled:
                self._init_pipeline()
        return self._pipeline

    def _init_pipeline(self) -> None:
        TORCH_READY.wait(timeout=60)
        with self._pipeline_lock:
            if self._pipeline is not None:
                return
            try:
                from kokoro import KPipeline
            except (ImportError, Exception):
                log.warning("Kokoro is not installed. To enable TTS, run: pip install kokoro soundfile")
                return

            try:
                log.info(f"Initializing Kokoro TTS pipeline with lang_code='{self.lang_code}'...")
                self._pipeline = KPipeline(lang_code=self.lang_code, repo_id="hexgrad/Kokoro-82M")
                log.info("Kokoro TTS pipeline successfully initialized")
            except Exception as e:
                log.warning(f"Could not initialize Kokoro TTS pipeline: {e}")
                self._pipeline = None

    def synthesize(self, text: str, path: str, voice: Optional[str] = None, speed: float = 1.0) -> str:
        """Synthesize text to audio file using Kokoro-82M."""
        pipeline = self.get_pipeline()
        if not pipeline:
            raise RuntimeError("Kokoro pipeline is not initialized.")

        voice = voice or self.default_voice
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        generator = pipeline(text, voice=voice, speed=speed)
        audio_chunks = []
        for _, _, audio in generator:
            if hasattr(audio, "numpy"):
                audio = audio.numpy()
            elif hasattr(audio, "cpu"):
                audio = audio.cpu().numpy()
            if isinstance(audio, np.ndarray):
                audio_chunks.append(audio)

        if not audio_chunks:
            raise RuntimeError(f"Kokoro produced no audio output for: '{text}'")

        full_audio = np.concatenate(audio_chunks, axis=0) if len(audio_chunks) > 1 else audio_chunks[0]

        # Save to wav file
        saved = False
        try:
            import soundfile as sf
            sf.write(path, full_audio, 24000)
            saved = True
        except ImportError:
            pass

        if not saved:
            import wave
            int_audio = (np.clip(full_audio, -1.0, 1.0) * 32767).astype(np.int16)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(int_audio.tobytes())

        log.debug(f"Kokoro synthesized {len(full_audio) / 24000:.2f}s of audio to {path}")
        return path

    def say(
        self,
        text: str,
        no_audio: bool = False,
        prosody: int = 100,
        speaker: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        """Synthesize and optionally play back text."""
        pipeline = self.get_pipeline()
        if not self.enabled or not pipeline:
            log.debug(f"TTS inactive, skipping speech: {text}")
            return

        if path is None:
            os.makedirs(TTS_CACHE_DIR, exist_ok=True)
            path = str(TTS_CACHE_DIR / "audio.wav")

        text = self.parse_config_answers(text)
        voice = speaker or self.default_voice
        speed = (prosody / 100.0) if prosody else self.speed

        try:
            self.synthesize(text, path, voice=voice, speed=speed)
            if not no_audio:
                play_audio(path)
        except Exception as e:
            log.error(f"Error during Kokoro speech synthesis: {e}")

        called_from()
        log.debug(text)

    def parse_config_answers(self, string: str, module=None) -> str:
        """Parse dynamic answer templates with brackets, e.g. [get_part_of_day]."""
        if not module:
            try:
                module = import_module(f"utils.lang.{self.lang}")
            except ImportError:
                return string

        pattern = re.compile(r"\[(.*?)]")
        matches = pattern.findall(string)

        for match in matches:
            if hasattr(module, match):
                func = getattr(module, match)
                if callable(func):
                    string = string.replace(f"[{match}]", str(func()))

        return string
