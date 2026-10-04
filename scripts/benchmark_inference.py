#!/usr/bin/env python3
"""
Benchmark Inference Script for Stewart Qwen2.5-0.5B Models.
Measures Time-To-First-Token (TTFT), Total Latency, Generation Throughput (tokens/sec),
First-Chunk Spoken Dispatch Latency to Kokoro TTS, and Output Validity across EN and RU.
"""

import os
import sys
import time
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Setup Environment
if os.path.exists("/run/opengl-driver/lib"):
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.commands.qwen_caller import QwenToolCaller
from api.commands.persona_caller import QwenPersonaCaller


def test_tool_caller_benchmarks() -> List[Dict[str, Any]]:
    print("\n" + "=" * 75)
    print(" 1. BENCHMARKING QWEN2.5-0.5B TOOL CALLER (GGUF CUDA vs Target < 200ms)")
    print("=" * 75)

    caller = QwenToolCaller()
    t0 = time.perf_counter()
    loaded = caller.load_model()
    load_time_ms = (time.perf_counter() - t0) * 1000
    print(f"[*] Tool Caller Model Loaded: {loaded} in {load_time_ms:.1f}ms (Backend: {caller.backend})")

    # Load Stewart tool schemas
    tools_file = PROJECT_ROOT / "data/dataset/stewart_tools.json"
    if tools_file.exists():
        with open(tools_file, "r", encoding="utf-8") as f:
            schemas = json.load(f)
    else:
        schemas = [
            {"function": {"name": "volume", "description": "Adjust system volume", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "context": {"type": "string"}}}}},
            {"function": {"name": "media_control", "description": "Control playback", "parameters": {"type": "object", "properties": {"control": {"type": "string"}}}}},
            {"function": {"name": "say_weather", "description": "Weather forecast", "parameters": {"type": "object", "properties": {"context": {"type": "string"}}}}}
        ]

    test_queries = [
        ("Set volume to 40%", "volume", "en"),
        ("Please pause the music right now", "media_control", "en"),
        ("Set a timer for 15 minutes", "timer", "en"),
        ("How is the weather outside in Berlin today?", "say_weather", "en"),
        ("Поставь таймер на 10 минут", "timer", "ru"),
        ("Сделай погромче звук", "volume", "ru"),
        ("Какая сегодня погода в Москве?", "say_weather", "ru")
    ]

    results = []
    # Warmup pass
    _ = caller.call_tool("hello", schemas)

    for query, expected_tool, lang in test_queries:
        t_start = time.perf_counter()
        call = caller.call_tool(query, schemas)
        lat_ms = (time.perf_counter() - t_start) * 1000

        tool_name = call[0] if call else None
        valid = (tool_name == expected_tool) if expected_tool else True

        results.append({
            "query": query,
            "lang": lang,
            "expected": expected_tool,
            "actual": tool_name,
            "latency_ms": lat_ms,
            "valid": valid
        })

        status = "PASSED" if valid else "MISMATCH"
        print(f"  [{lang.upper()}] \"{query}\" -> Tool: {tool_name} | Latency: {lat_ms:5.1f}ms | [{status}]")

    return results


def test_persona_streaming_benchmarks() -> List[Dict[str, Any]]:
    print("\n" + "=" * 75)
    print(" 2. BENCHMARKING QWEN2.5-0.5B BUTLER PERSONA & STREAMING TO KOKORO TTS")
    print("=" * 75)

    persona = QwenPersonaCaller()
    t0 = time.perf_counter()
    loaded = persona.load_model()
    load_time_ms = (time.perf_counter() - t0) * 1000
    print(f"[*] Persona Model Loaded: {loaded} in {load_time_ms:.1f}ms (Backend: {persona.backend})")

    delimiters = re.compile(r"([.,!?;—\n]+)")

    test_cases = [
        {
            "lang": "en",
            "query": "Lower the volume to 30 percent, please.",
            "tool": "volume",
            "result": {"status": "success", "level": 30}
        },
        {
            "lang": "en",
            "query": "What is the forecast for tomorrow?",
            "tool": "say_weather",
            "result": {"forecast": "Clear skies and 20 degrees"}
        },
        {
            "lang": "en",
            "query": "Good morning Stewart, how are you today?",
            "tool": None,
            "result": None
        },
        {
            "lang": "ru",
            "query": "Стюарт, сделай громкость тридцать процентов.",
            "tool": "volume",
            "result": {"status": "success", "level": 30}
        },
        {
            "lang": "ru",
            "query": "Какая погода ожидается завтра?",
            "tool": "say_weather",
            "result": {"forecast": "Ясно, двадцать градусов"}
        },
        {
            "lang": "ru",
            "query": "Доброе утро, Стюарт, как твои дела?",
            "tool": None,
            "result": None
        }
    ]

    results = []
    # Warmup
    _ = persona.generate_response("warmup", lang="en")

    for tc in test_cases:
        query = tc["query"]
        lang = tc["lang"]
        tool = tc["tool"]
        res = tc["result"]

        t_start = time.perf_counter()
        stream = persona.stream_response(query, tool_name=tool, tool_result=res, lang=lang)

        ttft_ms = None
        first_clause_ms = None
        first_clause_text = None
        buffer = ""
        tokens = []

        for token in stream:
            now = time.perf_counter()
            if ttft_ms is None:
                ttft_ms = (now - t_start) * 1000
            tokens.append(token)
            buffer += token

            if first_clause_ms is None:
                parts = delimiters.split(buffer)
                if len(parts) > 1:
                    first_clause_ms = (now - t_start) * 1000
                    first_clause_text = (parts[0] + parts[1]).strip()

        total_ms = (time.perf_counter() - t_start) * 1000
        full_text = "".join(tokens).strip()
        num_tokens = len(tokens)
        tok_per_sec = (num_tokens / (total_ms / 1000.0)) if total_ms > 0 else 0.0

        # Persona validation check: English should use Sir / Illia, Russian should use сэр / Илья
        is_butler_tone = False
        text_lower = full_text.lower()
        if lang == "en":
            is_butler_tone = ("sir" in text_lower or "illia" in text_lower or "pleasure" in text_lower or "certainly" in text_lower)
        else:
            is_butler_tone = ("сэр" in text_lower or "илья" in text_lower or "готов" in text_lower or "слуша" in text_lower)

        results.append({
            "query": query,
            "lang": lang,
            "ttft_ms": ttft_ms or 0.0,
            "first_clause_ms": first_clause_ms or total_ms,
            "first_clause_text": first_clause_text or full_text,
            "total_ms": total_ms,
            "num_tokens": num_tokens,
            "tok_per_sec": tok_per_sec,
            "full_text": full_text,
            "butler_persona": is_butler_tone
        })

        print(f"\n[{lang.upper()}] Query: \"{query}\"")
        print(f"  -> TTFT: {ttft_ms or 0.0:5.1f} ms | First Clause to Kokoro: {first_clause_ms or total_ms:5.1f} ms | Total: {total_ms:5.1f} ms ({tok_per_sec:.0f} tok/s)")
        print(f"  -> First Spoken Clause: \"{first_clause_text or full_text}\"")
        print(f"  -> Full Response: \"{full_text}\"")
        print(f"  -> Butler Persona Marker: {'Verified' if is_butler_tone else 'Polite neutral'}")

    return results


def main():
    print("\n===========================================================================")
    print(" STEWART LLM INFERENCE ACCELERATION BENCHMARK (NVIDIA RTX 3050 - NixOS)")
    print(" Target: TTFT < 200ms | Real-Time Voice Perceptual Response")
    print("===========================================================================")

    tool_results = test_tool_caller_benchmarks()
    persona_results = test_persona_streaming_benchmarks()

    print("\n" + "=" * 75)
    print(" SUMMARY BENCHMARK REPORT")
    print("=" * 75)

    avg_tool_lat = sum(r["latency_ms"] for r in tool_results) / len(tool_results) if tool_results else 0
    avg_ttft = sum(r["ttft_ms"] for r in persona_results) / len(persona_results) if persona_results else 0
    avg_first_chunk = sum(r["first_clause_ms"] for r in persona_results) / len(persona_results) if persona_results else 0
    avg_total_persona = sum(r["total_ms"] for r in persona_results) / len(persona_results) if persona_results else 0
    avg_tok_s = sum(r["tok_per_sec"] for r in persona_results) / len(persona_results) if persona_results else 0

    print(f"\n| Metric                               | Result          | Target       | Status   |")
    print(f"|--------------------------------------|-----------------|--------------|----------|")
    print(f"| Tool Caller Average Latency          | {avg_tool_lat:6.1f} ms       | < 100 ms     | {'PASS' if avg_tool_lat < 100 else 'WARN'}     |")
    print(f"| Persona Time-To-First-Token (TTFT)   | {avg_ttft:6.1f} ms       | < 200 ms     | {'PASS' if avg_ttft < 200 else 'FAIL'}     |")
    print(f"| First-Clause Dispatch to Kokoro TTS  | {avg_first_chunk:6.1f} ms       | < 100 ms     | {'PASS' if avg_first_chunk < 100 else 'WARN'}     |")
    print(f"| Persona Generation Speed             | {avg_tok_s:6.0f} tok/s    | > 50 tok/s   | {'PASS' if avg_tok_s > 50 else 'WARN'}     |")
    print(f"| Persona Total Latency                | {avg_total_persona:6.1f} ms       | < 300 ms     | {'PASS' if avg_total_persona < 300 else 'WARN'}     |")

    print("\nAll acceleration tests completed successfully.")


if __name__ == "__main__":
    main()
