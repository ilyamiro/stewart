import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from data.constants import PROJECT_DIR, USER_CACHE_DIR

log = logging.getLogger("tts.silero")

COMMON_WORDS_RU = {
    'google': 'гугл',
    'youtube': 'ютуб',
    'gmail': 'джимейл',
    'email': 'мейл',
    'github': 'гитхаб',
    'linux': 'линукс',
    'daily.dev': 'дейли дэв',
    'daily': 'дейли',
    'dev': 'дэв',
    'taken': 'сделан',
    'wifi': 'вай-фай',
    'wi-fi': 'вай-фай',
    'bluetooth': 'блютуз',
    'stewart': 'стюарт',
    'telegram': 'телеграм',
    'ok': 'окей',
    'stop': 'стоп',
}

TRANSLIT_PAIRS = [
    ('shch', 'щ'), ('yo', 'ё'), ('zh', 'ж'), ('ch', 'ч'), ('sh', 'ш'),
    ('yu', 'ю'), ('ya', 'я'), ('th', 'с'), ('ph', 'ф'), ('ck', 'к'),
    ('ee', 'и'), ('oo', 'у'),
    ('a', 'а'), ('b', 'б'), ('c', 'к'), ('d', 'д'), ('e', 'е'),
    ('f', 'ф'), ('g', 'г'), ('h', 'х'), ('i', 'и'), ('j', 'дж'),
    ('k', 'к'), ('l', 'л'), ('m', 'м'), ('n', 'н'), ('o', 'о'),
    ('p', 'п'), ('q', 'к'), ('r', 'р'), ('s', 'с'), ('t', 'т'),
    ('u', 'у'), ('v', 'в'), ('w', 'в'), ('x', 'кс'), ('y', 'и'), ('z', 'з')
]

ONES_RU = {0: 'ноль', 1: 'один', 2: 'два', 3: 'три', 4: 'четыре', 5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'}
TEENS_RU = {10: 'десять', 11: 'одиннадцать', 12: 'двенадцать', 13: 'тринадцать', 14: 'четырнадцать', 15: 'пятнадцать', 16: 'шестнадцать', 17: 'семнадцать', 18: 'восемнадцать', 19: 'девятнадцать'}
TENS_RU = {20: 'двадцать', 30: 'тридцать', 40: 'сорок', 50: 'пятьдесят', 60: 'шестьдесят', 70: 'семьдесят', 80: 'восемьдесят', 90: 'девяносто'}
HUNDREDS_RU = {100: 'сто', 200: 'двести', 300: 'триста', 400: 'четыреста', 500: 'пятьсот', 600: 'шестьсот', 700: 'семьсот', 800: 'восемьсот', 900: 'девятьсот'}

def num_to_ru(n: int) -> str:
    if n in ONES_RU: return ONES_RU[n]
    if n in TEENS_RU: return TEENS_RU[n]
    if n in TENS_RU: return TENS_RU[n]
    if n in HUNDREDS_RU: return HUNDREDS_RU[n]
    if 21 <= n <= 99:
        return f'{TENS_RU[(n // 10) * 10]} {ONES_RU[n % 10]}'
    if 101 <= n <= 999:
        rem = n % 100
        h_str = HUNDREDS_RU[(n // 100) * 100]
        if rem == 0: return h_str
        return f'{h_str} {num_to_ru(rem)}'
    return str(n)

def clean_for_silero(text: str) -> str:
    try:
        from api.commands.agy_caller import clean_for_russian_tts
        return clean_for_russian_tts(text)
    except Exception:
        if not text or not isinstance(text, str):
            return ""
        text = text.lower()
        for w, r in COMMON_WORDS_RU.items():
            text = re.sub(r'\b' + re.escape(w) + r'\b', r, text)
        for eng, ru in TRANSLIT_PAIRS:
            text = text.replace(eng, ru)
        text = re.sub(r'\b(\d{1,6})\b', lambda m: num_to_ru(int(m.group(1))), text)
        text = text.replace('—', '–').replace('"', '').replace("'", "")
        allowed = set('_~|!+,-.:;?абвгдежзийклмнопрстуфхцчшщъыьэюяё–… ')
        text = ''.join(c for c in text if c in allowed)
        return re.sub(r'\s+', ' ', text).strip()

SILERO_V5_RU_URL = "https://models.silero.ai/models/tts/ru/v5_ru.pt"
AVAILABLE_SPEAKERS = ["aidar", "baya", "kseniya", "xenia", "eugene"]
DEFAULT_SPEAKERS = {
    "m": "aidar",
    "f": "baya",
}


class SileroTTS:
    """
    Silero Russian Text-to-Speech engine integration for Stewart.
    High-performance neural speech synthesis on CPU using PyTorch / Torch Package (with ONNX support if present).
    """

    def __init__(self, config: dict, lang: str = "ru"):
        self.lang = lang
        self.config = config
        tts_cfg = config.get("audio", {}).get("tts", {})
        self.enabled = tts_cfg.get("enable", True)

        ru_cfg = tts_cfg.get("ru", {})
        lang_cfg = tts_cfg.get(lang, {}) if lang == "ru" else ru_cfg
        sex = lang_cfg.get("sex", ru_cfg.get("sex", "m"))
        voice = (
            lang_cfg.get("voice")
            or ru_cfg.get("voice")
            or lang_cfg.get(sex)
            or ru_cfg.get(sex)
        )
        if voice in AVAILABLE_SPEAKERS:
            self.default_voice = voice
        else:
            self.default_voice = DEFAULT_SPEAKERS.get(sex, "eugene")

        self.sample_rate = int(ru_cfg.get("sample_rate", lang_cfg.get("sample_rate", 24000)))
        self.speed = float(tts_cfg.get("speed", 1.0))

        self.onnx_model_path = ru_cfg.get("onnx_model_path", lang_cfg.get("onnx_model_path"))
        self._model = None
        self._model_lock = threading.Lock()
        self._init_thread = None

        if self.enabled:
            self._init_thread = threading.Thread(
                target=self._init_pipeline, daemon=True, name="Silero-Init"
            )
            self._init_thread.start()

    @property
    def active(self) -> bool:
        return self.enabled

    @property
    def model(self):
        return self.get_model()

    def get_model(self):
        if self._model is None:
            if self._init_thread and self._init_thread.is_alive():
                self._init_thread.join()
            elif self._model is None and self.enabled:
                self._init_pipeline()
        return self._model

    def _resolve_model_path(self) -> Path:
        """Locates or downloads the Silero v5 Russian model."""
        candidates = [
            Path(PROJECT_DIR) / "audio/tts/models/v5_ru.pt",
            USER_CACHE_DIR / "models/v5_ru.pt",
            Path.home() / ".cache/stewart/models/v5_ru.pt",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.stat().st_size > 1024 * 1024:
                return candidate

        target = USER_CACHE_DIR / "models/v5_ru.pt"
        target.parent.mkdir(parents=True, exist_ok=True)
        log.info(f"Downloading Silero TTS v5 Russian model from {SILERO_V5_RU_URL}...")
        try:
            import torch
            torch.hub.download_url_to_file(SILERO_V5_RU_URL, str(target))
            log.info(f"Downloaded Silero v5 model to {target}")
            return target
        except Exception as e:
            log.error(f"Failed to download Silero model: {e}")
            raise

    def _init_pipeline(self) -> None:
        from audio.tts.synthesis import TORCH_READY
        TORCH_READY.wait(timeout=60)

        with self._model_lock:
            if self._model is not None:
                return

            if self.onnx_model_path and os.path.exists(self.onnx_model_path):
                try:
                    import onnxruntime as ort
                    log.info(f"Initializing Silero TTS via ONNX Runtime: {self.onnx_model_path}")
                    session = ort.InferenceSession(self.onnx_model_path)
                    self._model = ("onnx", session)
                    log.info("Silero ONNX TTS model loaded successfully")
                    return
                except Exception as e:
                    log.warning(f"Could not load Silero ONNX model ({e}), falling back to PyTorch")

            try:
                import torch
                model_path = self._resolve_model_path()
                log.info(f"Loading Silero TTS model from {model_path}...")
                importer = torch.package.PackageImporter(str(model_path))
                model = importer.load_pickle("tts_models", "model")
                device = torch.device("cpu")
                model.to(device)
                self._model = ("torch", model)
                log.info("Silero TTS v5 Russian model loaded successfully")
            except Exception as e:
                log.error(f"Could not initialize Silero TTS pipeline: {e}")
                self._model = None

    def synthesize(
        self,
        text: str,
        path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> str:
        """Synthesizes text to a WAV audio file using Silero TTS."""
        loaded = self.get_model()
        if not loaded:
            raise RuntimeError("Silero TTS model is not initialized.")

        backend, model = loaded
        speaker = voice or self.default_voice
        if speaker not in AVAILABLE_SPEAKERS:
            speaker = self.default_voice
            if speaker not in AVAILABLE_SPEAKERS:
                speaker = "eugene"

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        clean_text = clean_for_silero(text)
        if not clean_text or not any(c in 'абвгдежзийклмнопрстуфхцчшщъыьэюяё' for c in clean_text):
            log.debug(f"Silero: text '{text}' has no synthesizable Russian Cyrillic characters after cleaning, skipping.")
            return path

        if backend == "torch":
            try:
                audio_tensor = model.apply_tts(
                    text=clean_text,
                    speaker=speaker,
                    sample_rate=self.sample_rate,
                )
                audio_np = audio_tensor.cpu().numpy()
            except Exception as e:
                raise RuntimeError(f"Silero TTS synthesis error: {e}") from e
        elif backend == "onnx":
            raise NotImplementedError("ONNX session inference without pre-processing not configured.")

        saved = False
        try:
            import soundfile as sf
            sf.write(path, audio_np, self.sample_rate)
            saved = True
        except ImportError:
            pass

        if not saved:
            import wave
            int_audio = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(int_audio.tobytes())

        log.debug(f"Silero synthesized {len(audio_np) / self.sample_rate:.2f}s audio to {path}")
        return path
