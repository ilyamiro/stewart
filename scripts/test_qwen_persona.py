#!/usr/bin/env python3
"""
Test script for Stewart Voice Persona Model (Qwen2.5-0.5B).
Verifies that generated responses follow the British butler persona (Sir / Illia),
are concise 1-2 spoken sentences suitable for Kokoro TTS, and handle both EN and RU.
"""

import os
import sys
import time
from pathlib import Path

# Setup NixOS environment
if os.path.exists("/run/opengl-driver/lib"):
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.commands.persona_caller import QwenPersonaCaller

TEST_CASES = [
    # English Tool Responses
    {
        "lang": "en",
        "query": "Can you lower the volume? I have a meeting.",
        "tool": "volume",
        "result": {"status": "success", "current_volume": 35, "action": "down"}
    },
    {
        "lang": "en",
        "query": "How is the weather outside in Berlin today?",
        "tool": "say_weather",
        "result": {"city": "Berlin", "temperature": 18, "condition": "Partly Cloudy", "rain_chance": "10%"}
    },
    {
        "lang": "en",
        "query": "Set a timer for 10 minutes for my pasta.",
        "tool": "timer",
        "result": {"status": "started", "duration": "10 minutes", "label": "pasta"}
    },
    {
        "lang": "en",
        "query": "Stewart, skip this track.",
        "tool": "media_control",
        "result": {"status": "success", "action": "next_track"}
    },
    {
        "lang": "en",
        "query": "How is my laptop battery doing?",
        "tool": "battery_health",
        "result": {"percent": 88, "charging": True}
    },
    # Russian Tool Responses
    {
        "lang": "ru",
        "query": "Стюарт, сделай экран поярче, ничего не видно.",
        "tool": "brightness",
        "result": {"status": "success", "brightness": 80}
    },
    {
        "lang": "ru",
        "query": "Какая сейчас погода в Москве?",
        "tool": "say_weather",
        "result": {"city": "Москва", "temperature": 4, "condition": "пасмурно"}
    },
    {
        "lang": "ru",
        "query": "Поставь музыку на паузу.",
        "tool": "media_control",
        "result": {"status": "success", "playback": "paused"}
    },
    # Conversational Dialogue (No Tool)
    {
        "lang": "en",
        "query": "Good morning Stewart.",
        "tool": None,
        "result": None
    },
    {
        "lang": "ru",
        "query": "С добрым утром, Стюарт. Как твои дела?",
        "tool": None,
        "result": None
    }
]


def main():
    print("=" * 60)
    print("Stewart Voice Persona Model Evaluation")
    print("=" * 60)

    caller = QwenPersonaCaller()
    print(f"Loading persona model from: {caller.model_path} on {caller.device}...")
    t0 = time.time()
    if not caller.load_model():
        print(f"ERROR: Could not load persona model from {caller.model_path}")
        sys.exit(1)
    load_time = time.time() - t0
    print(f"Model loaded successfully in {load_time:.2f}s!\n")

    print(f"{'User Request':<45} | {'Latency':<8} | {'Generated Spoken Persona Answer'}")
    print("-" * 100)

    for case in TEST_CASES:
        t_start = time.time()
        ans = caller.generate_response(
            user_query=case["query"],
            tool_name=case["tool"],
            tool_result=case["result"],
            lang=case["lang"]
        )
        latency = (time.time() - t_start) * 1000
        print(f"{case['query']:<45} | {latency:6.1f}ms | {ans}")

    print("\nEvaluation complete!")


if __name__ == "__main__":
    main()
