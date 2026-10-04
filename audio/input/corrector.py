"""
Acoustic & Phonetic Voice Command Corrector for Whisper STT.

Provides high-speed contextual correction, phonetic alignment, split-word repairing,
and confidence-weighted vocabulary matching for voice commands in Stewart.
Supports English and Russian.
"""

import re
import logging
from typing import List, Tuple, Set, Dict, Optional, Any

log = logging.getLogger("stt:corrector")


def fast_damerau_levenshtein(s1: str, s2: str, max_dist: int = 3) -> int:
    """
    Computes Damerau-Levenshtein distance (insertions, deletions, substitutions, transpositions)
    with early-exit pruning if distance exceeds max_dist.
    """
    if s1 == s2:
        return 0
    l1, l2 = len(s1), len(s2)
    if abs(l1 - l2) > max_dist:
        return max_dist + 1

    d: Dict[Tuple[int, int], int] = {}
    for i in range(-1, l1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, l2 + 1):
        d[(-1, j)] = j + 1

    for i in range(l1):
        min_in_row = max_dist + 1
        for j in range(l2):
            cost = 0 if s1[i] == s2[j] else 1
            val = min(
                d[(i - 1, j)] + 1,          # deletion
                d[(i, j - 1)] + 1,          # insertion
                d[(i - 1, j - 1)] + cost,   # substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                val = min(val, d[(i - 2, j - 2)] + 1)  # transposition
            d[(i, j)] = val
            if val < min_in_row:
                min_in_row = val
        if min_in_row > max_dist:
            return max_dist + 1

    return d[(l1 - 1, l2 - 1)]


def string_similarity(s1: str, s2: str) -> float:
    """Returns normalized similarity between 0.0 and 1.0."""
    if s1 == s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    dist = fast_damerau_levenshtein(s1, s2, max_dist=max_len)
    return max(0.0, 1.0 - (dist / max_len))


# Pre-defined phonetic / acoustic substitutions for common Whisper errors
ENGLISH_ACOUSTIC_MAP = {
    # Wake word variants
    "stuart": "stewart",
    "steward": "stewart",
    "stewert": "stewart",
    "stewerd": "stewart",
    "stuert": "stewart",
    # Actions & keywords
    "paws": "pause",
    "paus": "pause",
    "pawsed": "pause",
    "clothes": "close",
    "clos": "close",
    "cloze": "close",
    "moot": "mute",
    "mut": "mute",
    "mutee": "mute",
    "valium": "volume",
    "volum": "volume",
    "vollume": "volume",
    "lites": "lights",
    "lite": "light",
    "tern": "turn",
    "musick": "music",
    "muzik": "music",
    "browzer": "browser",
    "brower": "browser",
    "taimer": "timer",
    "tymer": "timer",
    "nex": "next",
    "fall": "full",
    "skreen": "screen",
    "screan": "screen",
    "shutt": "shut",
}

RUSSIAN_ACOUSTIC_MAP = {
    # Wake words
    "стюард": "стюарт",
    "стуарт": "стюарт",
    "стюарт": "стюарт",
    # Verb infinitives & imperfective forms to imperative command forms
    "выключить": "выключи",
    "выключать": "выключи",
    "выключай": "выключи",
    "отключить": "отключи",
    "погасить": "погаси",
    "включить": "включи",
    "включать": "включи",
    "включай": "включи",
    "запустить": "запусти",
    "закрыть": "закрой",
    "закрывать": "закрой",
    "закрывай": "закрой",
    "открыть": "открой",
    "открывать": "открой",
    "открывай": "открой",
    "поставить": "поставь",
    "поставляй": "поставь",
    "ставить": "поставь",
    "сделать": "сделай",
    "найти": "найди",
    "поискать": "поищи",
    "гуглить": "гугли",
    "переключить": "переключи",
    "переключай": "переключи",
    "остановить": "останови",
    "останавливай": "останови",
    "удалить": "удали",
    "создать": "создай",
    "увеличить": "увеличь",
    "убавить": "убавь",
    "убавляй": "убавь",
    "прибавить": "прибавь",
    "прибавляй": "прибавь",
    "уменьшить": "уменьши",
    # Noun inflections
    "вкладка": "вкладку",
    "вкладки": "вкладку",
    "страница": "страницу",
    "страницы": "страницу",
    "пауза": "паузу",
    "пагода": "погода",
    "погоду": "погода",
    "громкось": "громкость",
    "будильника": "будильник",
    "таймера": "таймер",
}

# Known common split words in Whisper
SPLIT_WORDS = {
    ("stew", "art"): "stewart",
    ("stew", "ward"): "stewart",
    ("time", "or"): "timer",
    ("play", "back"): "playback",
    ("shut", "down"): "shutdown",
    ("you", "tube"): "youtube",
    ("turn", "off"): "turn off",
    ("turn", "on"): "turn on",
    ("volume", "up"): "volume up",
    ("volume", "down"): "volume down",
    ("close", "tab"): "close tab",
    ("open", "tab"): "open tab",
    ("pause", "video"): "pause video",
}

# Verbs that typically start open-ended payloads
CONTINUES_VERBS = {
    "play", "find", "search", "google", "ask", "tell", "say", "echo",
    "включи", "найди", "поищи", "гугли", "скажи", "воспроизведи"
}

COMMON_CONNECTORS = {
    "and", "then", "the", "a", "an", "please", "to", "for", "with",
    "и", "затем", "потом", "пожалуйста", "на", "в", "для"
}


class WhisperVoiceCorrector:
    """
    Contextual Voice Command Post-Processor for Whisper transcripts.
    Uses dynamic command vocabulary, phonetic maps, split-word repairing,
    and Levenshtein matching to align noisy speech-to-text output with commands.
    """

    def __init__(
        self,
        lang: str = "en",
        known_words: Optional[Set[str]] = None,
        trigger_words: Optional[List[str]] = None,
        phrases: Optional[List[str]] = None,
    ):
        self.lang = lang.lower() if lang else "en"
        self.known_words: Set[str] = set(w.lower() for w in (known_words or []))
        self.trigger_words: List[str] = [t.lower() for t in (trigger_words or ["stewart", "стюарт"])]
        self.phrases: List[str] = [p.lower() for p in (phrases or [])]

        # Fast lookup map for known words by length
        self._words_by_len: Dict[int, List[str]] = {}
        self._rebuild_length_index()

        # Acoustic maps
        self.acoustic_map = dict(ENGLISH_ACOUSTIC_MAP if self.lang == "en" else RUSSIAN_ACOUSTIC_MAP)

    def set_vocabulary(self, words: Set[str], triggers: Optional[List[str]] = None, phrases: Optional[List[str]] = None):
        """Updates known vocabulary words, triggers, and command phrases."""
        self.known_words = set(w.lower().strip() for w in words if w.strip())
        if triggers:
            self.trigger_words = [t.lower().strip() for t in triggers if t.strip()]
        if phrases:
            self.phrases = [p.lower().strip() for p in phrases if p.strip()]
        self._rebuild_length_index()

    def _rebuild_length_index(self):
        self._words_by_len = {}
        for w in self.known_words:
            l = len(w)
            self._words_by_len.setdefault(l, []).append(w)

    def repair_split_words(self, tokens: List[str]) -> List[str]:
        """
        Merges adjacent tokens that were erroneously split by Whisper.
        e.g. ['stew', 'art'] -> ['stewart'], ['time', 'or'] -> ['timer'].
        """
        if len(tokens) < 2:
            return tokens

        result = []
        i = 0
        while i < len(tokens):
            if i < len(tokens) - 1:
                pair = (tokens[i].lower(), tokens[i + 1].lower())
                combined = tokens[i].lower() + tokens[i + 1].lower()

                # Check explicit split words table
                if pair in SPLIT_WORDS:
                    replacement = SPLIT_WORDS[pair]
                    # If replacement has space (phrase), extend result
                    for sub in replacement.split():
                        result.append(sub)
                    i += 2
                    continue

                # Check if concatenated pair matches any known word or trigger
                if combined in self.known_words or combined in self.trigger_words:
                    result.append(combined)
                    i += 2
                    continue

            result.append(tokens[i])
            i += 1

        return result

    def match_closest_known_word(self, word: str, min_similarity: float = 0.80) -> Optional[Tuple[str, float]]:
        """
        Finds the closest known command word within acceptable edit distance.
        Returns (best_word, similarity) or None.
        """
        w_clean = word.lower()
        w_len = len(w_clean)
        if w_len < 3:
            return None

        # Early exit if exact match
        if w_clean in self.known_words:
            return (w_clean, 1.0)

        # Acoustic map match
        if w_clean in self.acoustic_map:
            target = self.acoustic_map[w_clean]
            if target in self.known_words or target in self.trigger_words:
                return (target, 0.95)

        max_dist = 1 if w_len <= 5 else 2

        best_word = None
        best_sim = 0.0

        # Search candidates in length window [w_len - max_dist, w_len + max_dist]
        for l in range(max(1, w_len - max_dist), w_len + max_dist + 1):
            candidates = self._words_by_len.get(l, [])
            for cand in candidates:
                dist = fast_damerau_levenshtein(w_clean, cand, max_dist=max_dist)
                if dist <= max_dist:
                    sim = 1.0 - (dist / max(w_len, l))
                    if sim >= min_similarity and sim > best_sim:
                        best_sim = sim
                        best_word = cand

        if best_word:
            return (best_word, best_sim)
        return None

    def correct_trigger(self, text: str) -> str:
        """
        Detects and normalizes wake words at the beginning of the text.
        Handles prefixes like 'hey stuart', 'ok steward', 'stew art', 'стюард'.
        """
        if not text:
            return text

        tokens = text.strip().split()
        if not tokens:
            return text

        tokens = self.repair_split_words(tokens)

        # Remove leading conversational greetings: hey, ok, hi, привет, хей
        greetings = {"hey", "hi", "ok", "okay", "привет", "хей", "эй", "слушай"}
        start_idx = 0
        if tokens and tokens[0].lower() in greetings:
            start_idx = 1

        if start_idx >= len(tokens):
            return " ".join(tokens)

        first_word = tokens[start_idx].lower()

        # Check direct triggers
        target_trigger = self.trigger_words[0] if self.trigger_words else ("stewart" if self.lang == "en" else "стюарт")

        # Acoustic check
        if first_word in self.acoustic_map:
            mapped = self.acoustic_map[first_word]
            if mapped in self.trigger_words or mapped in ("stewart", "стюарт"):
                tokens[start_idx] = mapped
                return " ".join(tokens[start_idx:])

        # Fuzzy check on wake word
        for trig in self.trigger_words:
            sim = string_similarity(first_word, trig)
            if sim >= 0.75:
                tokens[start_idx] = trig
                return " ".join(tokens[start_idx:])

        # If greeting was stripped and no trigger found, return original from start
        return " ".join(tokens)

    def correct(
        self,
        text: str,
        word_probabilities: Optional[List[Tuple[str, float]]] = None
    ) -> str:
        """
        Corrects a transcribed voice command string.
        - Merges split words
        - Normalizes wake words
        - Applies acoustic & phonetic substitutions
        - Aligns near-miss command words to active command tree vocabulary
        - Protects open-ended command payloads (continues=True)
        """
        if not text or not text.strip():
            return ""

        # Normalize punctuation and extra spaces
        clean_text = re.sub(r"[^\w\s]", " ", text).strip()
        tokens = clean_text.split()
        if not tokens:
            return ""

        # Step 1: Repair split words
        tokens = self.repair_split_words(tokens)

        # Step 2: Normalize trigger if present
        corrected_trigger_str = self.correct_trigger(" ".join(tokens))
        tokens = corrected_trigger_str.split()

        corrected_tokens = []
        in_payload = False

        prob_dict = {}
        if word_probabilities:
            for w, p in word_probabilities:
                prob_dict[w.lower()] = p

        for i, token in enumerate(tokens):
            t_clean = token.lower()

            # Once in payload for continues command, don't modify words
            if in_payload:
                corrected_tokens.append(token)
                continue

            # Check if this word starts an open-ended payload
            if t_clean in CONTINUES_VERBS:
                corrected_tokens.append(t_clean)
                in_payload = True
                continue

            # Check acoustic map
            if t_clean in self.acoustic_map:
                mapped = self.acoustic_map[t_clean]
                corrected_tokens.append(mapped)
                if mapped in CONTINUES_VERBS:
                    in_payload = True
                continue

            # If word is already a known command keyword or trigger or connector, keep it
            if t_clean in self.known_words or t_clean in self.trigger_words or t_clean in COMMON_CONNECTORS:
                corrected_tokens.append(t_clean)
                continue

            # Check confidence probability if available
            prob = prob_dict.get(t_clean, 1.0)
            threshold = 0.72 if prob < 0.85 else 0.80

            # Match against known command vocabulary
            match = self.match_closest_known_word(t_clean, min_similarity=threshold)
            if match:
                best_word, sim = match
                corrected_tokens.append(best_word)
                if best_word in CONTINUES_VERBS:
                    in_payload = True
            else:
                corrected_tokens.append(t_clean)

        result = " ".join(corrected_tokens).strip()
        result = re.sub(r"\s+", " ", result)
        return result
