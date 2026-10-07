import os
import re
import shutil
import logging
import tempfile
import subprocess
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import numpy as np

logger = logging.getLogger("telegram_tts")

STEWART_CACHE = Path.home() / ".cache" / "stewart" / "models"
LIFE_CACHE = Path.home() / ".cache" / "life" / "models"

RU_MODEL_URL = "https://models.silero.ai/models/tts/ru/v5_ru.pt"
EN_MODEL_URL = "https://models.silero.ai/models/tts/en/v3_en.pt"

RU_AVAILABLE_SPEAKERS = ["aidar", "baya", "kseniya", "eugene", "xenia"]
EN_DEFAULT_SPEAKER = "en_73"
RU_DEFAULT_SPEAKER = "eugene"

COMMON_WORDS_RU = {
    'google': 'гугл',
    'youtube': 'ютуб',
    'gmail': 'джимейл',
    'email': 'мейл',
    'github': 'гитхаб',
    'linux': 'линукс',
    'python': 'пайтон',
    'telethon': 'телетон',
    'telegram': 'телеграм',
    'studieplus': 'студие плюс',
    'studie+': 'студие плюс',
    'studie': 'студие',
    'stewart': 'стюарт',
    'antigravity': 'антигравити',
    'silero': 'силеро',
    'whisper': 'виcпер',
    'chatgpt': 'чат джи пи ти',
    'gemini': 'джеминай',
    'wifi': 'вай-фай',
    'wi-fi': 'вай-фай',
    'bluetooth': 'блютуз',
    'ok': 'окей',
    'stop': 'стоп',
    'maths': 'математика',
    'math': 'математика',
    'physics': 'физика',
    'chemistry': 'химия',
    'economics': 'экономика',
    'history': 'история',
    'english': 'инглиш',
    'danish': 'датский',
    'hl': 'эйч эл',
    'sl': 'эс эл',
    'aa': 'эй эй',
    'ai': 'эй ай',
    'ib': 'ай би',
    'mcp': 'эм си пи',
    'cli': 'си эл ай',
    'api': 'апи',
    'url': 'урл',
    'id': 'ай ди',
    'pdf': 'пэ дэ эф',
}

LATIN_TO_CYRILLIC_MULTI = [
    ('shch', 'щ'), ('yo', 'ё'), ('zh', 'ж'), ('ch', 'ч'), ('sh', 'ш'),
    ('yu', 'ю'), ('ya', 'я'), ('th', 'с'), ('ph', 'ф'), ('ck', 'к'),
    ('kh', 'х'), ('ts', 'ц'), ('ee', 'и'), ('oo', 'у'), ('qu', 'кв'),
]

LATIN_TO_CYRILLIC_SINGLE = {
    'a': 'а', 'b': 'б', 'c': 'к', 'd': 'д', 'e': 'е',
    'f': 'ф', 'g': 'г', 'h': 'х', 'i': 'и', 'j': 'дж',
    'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
    'p': 'п', 'q': 'к', 'r': 'р', 's': 'с', 't': 'т',
    'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс', 'y': 'и', 'z': 'з'
}

CYRILLIC_TO_LATIN_MULTI = [
    ('щ', 'shch'), ('ё', 'yo'), ('ж', 'zh'), ('ч', 'ch'), ('ш', 'sh'),
    ('ю', 'yu'), ('я', 'ya'), ('х', 'kh'), ('ц', 'ts'),
]

CYRILLIC_TO_LATIN_SINGLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ф': 'f', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e'
}

ONES_RU = {0: 'ноль', 1: 'один', 2: 'два', 3: 'три', 4: 'четыре', 5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'}
TEENS_RU = {10: 'десять', 11: 'одиннадцать', 12: 'двенадцать', 13: 'тринадцать', 14: 'четырнадцать', 15: 'пятнадцать', 16: 'шестнадцать', 17: 'семнадцать', 18: 'восемнадцать', 19: 'девятнадцать'}
TENS_RU = {20: 'двадцать', 30: 'тридцать', 40: 'сорок', 50: 'пятьдесят', 60: 'шестьдесят', 70: 'семьдесят', 80: 'восемьдесят', 90: 'девяносто'}
HUNDREDS_RU = {100: 'сто', 200: 'двести', 300: 'триста', 400: 'четыреста', 500: 'пятьсот', 600: 'шестьсот', 700: 'семьсот', 800: 'восемьсот', 900: 'девятьсот'}

ONES_EN = {0: 'zero', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine'}
TEENS_EN = {10: 'ten', 11: 'eleven', 12: 'twelve', 13: 'thirteen', 14: 'fourteen', 15: 'fifteen', 16: 'sixteen', 17: 'seventeen', 18: 'eighteen', 19: 'nineteen'}
TENS_EN = {20: 'twenty', 30: 'thirty', 40: 'forty', 50: 'fifty', 60: 'sixty', 70: 'seventy', 80: 'eighty', 90: 'ninety'}


def num_to_ru(n: int) -> str:
    """Expand integer to Russian spoken words up to 999,999."""
    if n < 0:
        return f"минус {num_to_ru(abs(n))}"
    if n in ONES_RU:
        return ONES_RU[n]
    if n in TEENS_RU:
        return TEENS_RU[n]
    if n in TENS_RU:
        return TENS_RU[n]
    if n in HUNDREDS_RU:
        return HUNDREDS_RU[n]
    if 21 <= n <= 99:
        return f"{TENS_RU[(n // 10) * 10]} {ONES_RU[n % 10]}"
    if 101 <= n <= 999:
        rem = n % 100
        h_str = HUNDREDS_RU[(n // 100) * 100]
        return h_str if rem == 0 else f"{h_str} {num_to_ru(rem)}"
    if 1000 <= n <= 999999:
        thousands = n // 1000
        rem = n % 1000
        if thousands % 10 == 1 and thousands % 100 != 11:
            t_word = "тысяча"
            t_num = num_to_ru(thousands)
            if t_num.endswith("один"):
                t_num = t_num[:-4] + "одна"
        elif thousands % 10 in (2, 3, 4) and thousands % 100 not in (12, 13, 14):
            t_word = "тысячи"
            t_num = num_to_ru(thousands)
            if t_num.endswith("два"):
                t_num = t_num[:-3] + "две"
        else:
            t_word = "тысяч"
            t_num = num_to_ru(thousands)
        res = f"{t_num} {t_word}"
        if rem > 0:
            res += f" {num_to_ru(rem)}"
        return res
    return str(n)


def num_to_en(n: int) -> str:
    """Expand integer to English spoken words up to 999,999."""
    if n < 0:
        return f"minus {num_to_en(abs(n))}"
    if n in ONES_EN:
        return ONES_EN[n]
    if n in TEENS_EN:
        return TEENS_EN[n]
    if n in TENS_EN:
        return TENS_EN[n]
    if 21 <= n <= 99:
        return f"{TENS_EN[(n // 10) * 10]}-{ONES_EN[n % 10]}"
    if 100 <= n <= 999:
        rem = n % 100
        h_str = f"{ONES_EN[n // 100]} hundred"
        return h_str if rem == 0 else f"{h_str} {num_to_en(rem)}"
    if 1000 <= n <= 999999:
        thousands = n // 1000
        rem = n % 1000
        t_str = f"{num_to_en(thousands)} thousand"
        return t_str if rem == 0 else f"{t_str} {num_to_en(rem)}"
    return str(n)


def strip_emojis(text: str) -> str:
    """Remove emoji and pictographic symbols."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002300-\U000023FF"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text)


def strip_markdown_and_links(text: str) -> str:
    """Clean markdown formatting, code blocks, URLs, bullet points, and emojis for TTS."""
    if not text:
        return ""
    text = strip_emojis(text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'[*_~]{1,3}([^*_~]+)[*_~]{1,3}', r'\1', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*>\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[\r\n]+', '. ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def clean_for_silero_ru(text: str) -> str:
    """
    Clean and adapt text for Silero Russian TTS (v5_ru.pt).
    Strictly ensures EVERY SINGLE LETTER is converted to Cyrillic!
    English names, technical words, and abbreviations are translated or transliterated.
    Numbers are expanded to Russian words.
    """
    if not text or not isinstance(text, str):
        return ""

    try:
        from api.commands.agy_caller import clean_for_russian_tts
        return clean_for_russian_tts(text)
    except Exception:
        pass

    text = strip_markdown_and_links(text)
    text = text.lower()
    text = re.sub(r'([a-zA-Zа-яА-ЯёЁ]+)(\d+)', r'\1 \2', text)
    text = re.sub(r'(\d+)([a-zA-Zа-яА-ЯёЁ]+)', r'\1 \2', text)
    text = text.replace('/', ' ')

    def time_range_repl(m):
        h1, m1, h2, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        t1 = f"{num_to_ru(h1)} {num_to_ru(m1)}" if m1 else f"{num_to_ru(h1)}"
        t2 = f"{num_to_ru(h2)} {num_to_ru(m2)}" if m2 else f"{num_to_ru(h2)}"
        return f"с {t1} до {t2}"
    text = re.sub(r'\b(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\b', time_range_repl, text)

    def time_repl(m):
        h, mn = int(m.group(1)), int(m.group(2))
        return f"{num_to_ru(h)} {num_to_ru(mn)}" if mn else f"{num_to_ru(h)} ноль ноль"
    text = re.sub(r'\b(\d{1,2}):(\d{2})\b', time_repl, text)

    text = re.sub(r'\b(\d{1,6})\b', lambda m: num_to_ru(int(m.group(1))), text)

    for w, r in COMMON_WORDS_RU.items():
        text = re.sub(r'\b' + re.escape(w) + r'\b', r, text)

    for eng, ru in LATIN_TO_CYRILLIC_MULTI:
        text = text.replace(eng, ru)

    chars = []
    for c in text:
        chars.append(LATIN_TO_CYRILLIC_SINGLE.get(c, c))
    text = "".join(chars)

    text = text.replace('—', '–').replace('"', '').replace("'", "")
    allowed = set('_~|!+,-.:;?абвгдежзийклмнопрстуфхцчшщъыьэюяё–… ')
    text = ''.join(c for c in text if c in allowed)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def clean_for_silero_en(text: str) -> str:
    """
    Clean and adapt text for Silero English TTS (v3_en.pt).
    Ensures all Cyrillic characters are transliterated to Latin.
    Numbers are expanded to English words.
    """
    if not text or not isinstance(text, str):
        return ""

    text = strip_markdown_and_links(text)
    text = text.lower()

    def time_repl(m):
        h, mn = int(m.group(1)), int(m.group(2))
        return f"{num_to_en(h)} {num_to_en(mn)}"
    text = re.sub(r'\b(\d{1,2}):(\d{2})\b', time_repl, text)

    text = re.sub(r'\b(\d{1,6})\b', lambda m: num_to_en(int(m.group(1))), text)

    for ru, eng in CYRILLIC_TO_LATIN_MULTI:
        text = text.replace(ru, eng)

    chars = []
    for c in text:
        chars.append(CYRILLIC_TO_LATIN_SINGLE.get(c, c))
    text = "".join(chars)

    text = text.replace('—', '-').replace('"', '').replace("'", "")
    allowed = set("abcdefghijklmnopqrstuvwxyz .,!?-:;'0123456789")
    text = ''.join(c for c in text if c in allowed)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def detect_language(text: str) -> str:
    """
    Detect whether text is predominantly Russian or English.
    Returns 'ru' or 'en'.
    """
    cyrillic_count = len(re.findall(r'[а-яА-ЯёЁ]', text))
    latin_count = len(re.findall(r'[a-zA-Z]', text))
    if cyrillic_count > 0 and cyrillic_count >= latin_count:
        return "ru"
    return "en"





class SileroVoiceSynthesizer:
    """
    Silero Text-to-Speech Engine supporting both Russian (v5_ru) and English (v3_en) models.
    Produces high quality speech, encodes to Telegram-native Opus voice notes,
    and handles strict language sanitization / transliteration.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SileroVoiceSynthesizer, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.sample_rate = 24000
        self._models = {}
        self._load_lock = threading.Lock()
        self._initialized = True

    def _resolve_model_path(self, lang: str) -> Path:
        """Find model in cache or download it."""
        filename = "v5_ru.pt" if lang == "ru" else "v3_en.pt"
        url = RU_MODEL_URL if lang == "ru" else EN_MODEL_URL

        candidates = [
            STEWART_CACHE / filename,
            LIFE_CACHE / filename,
            Path("/home/ilyamiro/.cache/stewart/models") / filename,
            Path.home() / ".cache" / "stewart" / "models" / filename,
        ]
        for c in candidates:
            if c.exists() and c.stat().st_size > 1024 * 1024:
                return c

        target = LIFE_CACHE / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading Silero {lang} model from {url} to {target}...")
        import torch
        torch.hub.download_url_to_file(url, str(target))
        return target

    def get_model(self, lang: str):
        """Loads and returns the Silero model for 'ru' or 'en'."""
        with self._load_lock:
            if lang in self._models:
                return self._models[lang]

            import torch
            model_path = self._resolve_model_path(lang)
            logger.info(f"Loading Silero {lang.upper()} TTS model from {model_path}...")
            importer = torch.package.PackageImporter(str(model_path))
            model = importer.load_pickle("tts_models", "model")
            device = torch.device("cpu")
            model.to(device)
            self._models[lang] = model
            logger.info(f"Silero {lang.upper()} TTS loaded successfully.")
            return model

    def synthesize(
        self,
        text: str,
        lang: str = "auto",
        speaker: Optional[str] = None,
        output_format: str = "ogg"
    ) -> Tuple[str, str]:
        """
        Synthesizes text into an audio file.
        Returns: (file_path, detected_or_used_lang)
        If output_format is 'ogg', converts via ffmpeg to Telegram-native Opus voice note.
        """
        if lang == "auto":
            lang = detect_language(text)

        if lang == "ru":
            clean_text = clean_for_silero_ru(text)
            if not speaker or speaker not in RU_AVAILABLE_SPEAKERS:
                speaker = RU_DEFAULT_SPEAKER
        else:
            clean_text = clean_for_silero_en(text)
            if not speaker:
                speaker = EN_DEFAULT_SPEAKER

        if not clean_text:
            raise ValueError(f"No synthesizable text remains after cleaning for language '{lang}'.")

        logger.info(f"Synthesizing [{lang}/{speaker}]: '{clean_text[:60]}...'")
        model = self.get_model(lang)

        audio_tensor = model.apply_tts(
            text=clean_text,
            speaker=speaker,
            sample_rate=self.sample_rate
        )
        audio_np = audio_tensor.cpu().numpy()

        tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_wav_path = tmp_wav.name
        tmp_wav.close()

        import soundfile as sf
        sf.write(tmp_wav_path, audio_np, self.sample_rate)

        if output_format.lower() in ("ogg", "opus"):
            tmp_ogg = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
            tmp_ogg_path = tmp_ogg.name
            tmp_ogg.close()

            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", tmp_wav_path,
                        "-c:a", "libopus",
                        "-b:a", "32k",
                        "-vbr", "on",
                        "-compression_level", "10",
                        tmp_ogg_path
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                try:
                    os.unlink(tmp_wav_path)
                except Exception:
                    pass
                return tmp_ogg_path, lang
            except Exception as e:
                logger.warning(f"ffmpeg conversion to ogg failed ({e}), using wav.")
                return tmp_wav_path, lang

        return tmp_wav_path, lang


_synthesizer: Optional[SileroVoiceSynthesizer] = None

def get_synthesizer() -> SileroVoiceSynthesizer:
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = SileroVoiceSynthesizer()
    return _synthesizer
