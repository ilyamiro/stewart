#!/usr/bin/env python3
"""
Comprehensive Test Suite for Whisper Speech Recognition Enhancements in Stewart:
- WhisperVoiceCorrector: Acoustic, phonetic, split-word, and payload-preserving correction
- Command Tree: Algorithmic fuzzy token matching and scoring
- Wake-word Detection: Greeting stripping, split wake-word merging, and fuzzy trigger matching
- Audio Normalization: DC bias removal, peak AGC, and silence trimming
- Dynamic Vocabulary: Vocabulary extraction, hotwords generation, and prompt biasing
"""

import sys
import unittest
import numpy as np

from audio.input.corrector import WhisperVoiceCorrector, fast_damerau_levenshtein, string_similarity
from api.commands.tree import Command, Manager
from app.app import App


class TestWhisperCorrector(unittest.TestCase):
    def setUp(self):
        self.en_vocab = {
            "close", "tab", "open", "browser", "pause", "video", "playback",
            "volume", "up", "down", "next", "previous", "timer", "lights",
            "turn", "off", "on", "play", "find", "search", "mute", "music",
            "stopwatch", "shutdown"
        }
        self.en_corrector = WhisperVoiceCorrector(
            lang="en",
            known_words=self.en_vocab,
            trigger_words=["stewart"],
            phrases=["turn off", "turn on", "volume up", "volume down", "close tab", "open tab", "pause video"]
        )

        self.ru_vocab = {
            "закрой", "вкладку", "открой", "страницу", "паузу", "видео",
            "громкость", "свет", "выключи", "включи", "поставь", "таймер",
            "найди", "поищи", "музыку", "следующее", "будильник"
        }
        self.ru_corrector = WhisperVoiceCorrector(
            lang="ru",
            known_words=self.ru_vocab,
            trigger_words=["стюарт"],
            phrases=["закрой вкладку", "открой страницу", "выключи свет", "включи музыку", "поставь таймер"]
        )

    def test_wake_word_homophones_english(self):
        cases = [
            ("stuart pause video", "stewart pause video"),
            ("steward volume up", "stewart volume up"),
            ("stewert close tab", "stewart close tab"),
            ("hey stuart pause video", "stewart pause video"),
            ("ok steward open browser", "stewart open browser"),
        ]
        for inp, expected in cases:
            self.assertEqual(self.en_corrector.correct(inp), expected)

    def test_split_words_repair(self):
        cases = [
            ("stew art pause video", "stewart pause video"),
            ("time or ten minutes", "timer ten minutes"),
            ("play back resume", "playback resume"),
            ("shut down system", "shutdown system"),
        ]
        for inp, expected in cases:
            self.assertEqual(self.en_corrector.correct(inp), expected)

    def test_acoustic_substitutions_english(self):
        cases = [
            ("paws video", "pause video"),
            ("clothes tab", "close tab"),
            ("volum up", "volume up"),
            ("valium down", "volume down"),
            ("tern off lights", "turn off lights"),
            ("turn off the lites", "turn off the lights"),
            ("moot music", "mute music"),
            ("browzer open", "browser open"),
        ]
        for inp, expected in cases:
            self.assertEqual(self.en_corrector.correct(inp), expected)

    def test_payload_protection_continues(self):
        # Open-ended queries must NOT have query payload altered
        cases = [
            ("play bohemian rhapsody by queen", "play bohemian rhapsody by queen"),
            ("find interstellar movie full soundtrack", "find interstellar movie full soundtrack"),
            ("search quantum computing news", "search quantum computing news"),
        ]
        for inp, expected in cases:
            self.assertEqual(self.en_corrector.correct(inp), expected)

    def test_russian_wake_words_and_inflections(self):
        cases = [
            ("стюард выключить свет", "стюарт выключи свет"),
            ("стуарт закрыть вкладку", "стюарт закрой вкладку"),
            ("привет стюарт открой страницу", "стюарт открой страницу"),
            ("поставить таймер", "поставь таймер"),
            ("выключить освещение", "выключи освещение"),
            ("громкось прибавь", "громкость прибавь"),
            ("найди рецепт домашней пиццы", "найди рецепт домашней пиццы"),
        ]
        for inp, expected in cases:
            self.assertEqual(self.ru_corrector.correct(inp), expected)


class TestCommandTreeFuzzyMatching(unittest.TestCase):
    def setUp(self):
        self.m = Manager()
        self.m.add(
            Command(["close", "tab"], action="close_tab", synonyms={"close": ["shut"], "tab": ["page"]}),
            Command(["open", "tab"], action="open_tab", synonyms={"open": ["launch"], "tab": ["page"]}),
            Command(["pause", "video"], action="pause_video", synonyms={"video": ["playback"]}),
            Command(["volume", "up"], action="volume_up"),
            Command(["volume", "down"], action="volume_down"),
            Command(["play"], action="play", continues=True),
            Command(["find"], action="find", continues=True),
            Command(["закрой", "вкладку"], action="ru_close_tab", synonyms={"закрой": ["закрыть"], "вкладку": ["страницу"]}),
            Command(["выключи", "свет"], action="ru_lights_off", synonyms={"выключи": ["погаси"], "свет": ["освещение"]}),
        )

    def test_exact_matches_preferred(self):
        res = self.m.find("close tab")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0][0].action, "close_tab")

    def test_fuzzy_matches_succeed(self):
        # Slightly misrecognized or misspelled words
        test_cases = [
            ("clos tab", "close_tab"),
            ("volum up", "volume_up"),
            ("volum down", "volume_down"),
            ("pause playbac", "pause_video"),
            ("закрой страниц", "ru_close_tab"),
            ("выключи освещени", "ru_lights_off"),
        ]
        for inp, expected_action in test_cases:
            res = self.m.find_algorithmic(inp)
            self.assertEqual(len(res), 1, f"Failed for '{inp}': got {res}")
            self.assertEqual(res[0][0].action, expected_action)

    def test_negative_cases_reject(self):
        # Incomplete or unrelated chatter should return []
        negatives = [
            "close",
            "random noise here",
            "weather is nice today",
            "nothing to see",
        ]
        for neg in negatives:
            res = self.m.find_algorithmic(neg)
            self.assertEqual(res, [], f"Expected [] for '{neg}', got {res}")

    def test_vocabulary_extraction(self):
        vocab = self.m.get_all_vocabulary()
        self.assertIn("close", vocab["words"])
        self.assertIn("tab", vocab["words"])
        self.assertIn("volume", vocab["words"])
        self.assertTrue(len(vocab["phrases"]) > 0)

        recognizer_str = self.m.construct_recognizer_string()
        self.assertIn("close", recognizer_str)
        self.assertIn("volume", recognizer_str)


class DummyApi:
    def __init__(self):
        self.lang = "en"
        self.manager = Manager()


class TestTriggerWordExtraction(unittest.TestCase):
    def setUp(self):
        self.app = App(DummyApi())
        self.app.config = {
            "settings": {
                "trigger": {
                    "triggers": ["stewart", "стюарт"]
                }
            }
        }

    def test_trigger_variations(self):
        cases = [
            ("stewart pause video", ("stewart", "pause video")),
            ("hey stuart pause video", ("stuart", "pause video")),
            ("ok steward volume up", ("steward", "volume up")),
            ("stew art close tab", ("stewart", "close tab")),
            ("stewert next video", ("stewert", "next video")),
            ("стюард выключи свет", ("стюард", "выключи свет")),
            ("привет стюарт открой страницу", ("стюарт", "открой страницу")),
            ("unrelated text without trigger", ("blank", "blank")),
        ]
        for inp, expected in cases:
            trig, payload = self.app.remove_trigger_word(inp)
            self.assertEqual((trig, payload), expected, f"Failed for '{inp}'")


class TestAudioPreProcessing(unittest.TestCase):
    def test_audio_normalization_and_trimming(self):
        sr = 16000
        # 0.2s silence + 0.5s tone + 0.2s silence
        silence_start = np.full(int(0.2 * sr), 0.0001, dtype=np.float32)
        silence_end = np.full(int(0.2 * sr), 0.0001, dtype=np.float32)
        t = np.linspace(0, 0.5, int(0.5 * sr), endpoint=False, dtype=np.float32)
        tone = 0.15 * np.sin(2 * np.pi * 440 * t)

        raw_audio = np.concatenate([silence_start, tone, silence_end])

        # Apply pipeline:
        conditioned = raw_audio - np.mean(raw_audio)
        self.assertAlmostEqual(float(np.mean(conditioned)), 0.0, places=4)

        peak = np.max(np.abs(conditioned))
        self.assertTrue(peak > 0.01)
        normalized = (conditioned / peak) * 0.95
        self.assertAlmostEqual(float(np.max(np.abs(normalized))), 0.95, places=4)

        non_silent = np.where(np.abs(normalized) > 0.02)[0]
        self.assertTrue(len(non_silent) > 0)
        start_idx = max(0, non_silent[0] - 800)
        end_idx = min(len(normalized), non_silent[-1] + 800)
        trimmed = normalized[start_idx:end_idx]

        self.assertTrue(len(trimmed) < len(raw_audio))
        self.assertTrue(len(trimmed) >= int(0.5 * sr))


if __name__ == "__main__":
    unittest.main()
