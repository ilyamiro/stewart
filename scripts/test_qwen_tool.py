#!/usr/bin/env python3
"""
CLI Testing Tool for fine-tuned Stewart Qwen2.5-0.5B Tool Calling.
Tests user queries and displays raw model output, parsed tool name, arguments, and latency.
"""

import sys
import time
import json
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Add api/commands to sys.path to avoid triggering api.app mpv dependency
sys.path.insert(0, str(PROJECT_ROOT / "api" / "commands"))
from qwen_caller import QwenToolCaller


def main():
    tools_file = PROJECT_ROOT / "data/dataset/stewart_tools.json"
    if not tools_file.exists():
        print(f"Error: Tools schema not found at {tools_file}")
        sys.exit(1)

    with open(tools_file, "r", encoding="utf-8") as f:
        tools = json.load(f)

    # Check for merged model or checkpoint
    merged_path = PROJECT_ROOT / "data/models/qwen2.5-0.5b-stewart"
    lora_path = PROJECT_ROOT / "data/models/qwen2.5-0.5b-stewart-lora"
    
    # Also check if any checkpoint exists
    checkpoints = sorted(lora_path.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1])) if lora_path.exists() else []

    target_path = None
    if merged_path.exists():
        target_path = merged_path
        print(f"Using standalone merged model: {target_path}")
    elif checkpoints:
        target_path = checkpoints[-1]
        print(f"Using latest training checkpoint: {target_path}")
    elif lora_path.exists():
        target_path = lora_path
        print(f"Using LoRA model: {target_path}")
    else:
        print(f"No trained model found yet at {merged_path} or {lora_path}")
        sys.exit(1)

    print(f"Loading QwenToolCaller with {len(tools)} registered tools...")
    caller = QwenToolCaller(model_path=str(target_path))
    loaded = caller.load_model()
    if not loaded:
        print("Failed to load model.")
        sys.exit(1)

    test_queries = [
        "Please pause the music right now",
        "Make it louder please",
        "Set volume to 40%",
        "What time is it?",
        "How is the weather outside?",
        "Set a timer for 15 minutes",
        "Close this browser tab",
        "Open file manager",
        "Take a screenshot",
        "Lock my computer screen",
        "Поставь музыку на паузу пожалуйста",
        "Сделай погромче звук",
        "Сколько сейчас времени?",
        "Какая сегодня погода в Москве?",
        "Поставь таймер на 10 минут",
        "Закрой эту вкладку",
        "Открой терминал",
        "Заблокируй экран",
        "What is the capital of France?" # Chitchat / negative sample
    ]

    print("\n" + "=" * 70)
    print("RUNNING AUTOMATED TEST BENCH ON USER COMMANDS")
    print("=" * 70)

    for query in test_queries:
        t0 = time.perf_counter()
        result = caller.call_tool(query, tools)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"\nUser Query: \"{query}\"")
        if result:
            tool_name, args, ctx = result
            print(f"  -> Dispatched Tool: [{tool_name}] (Latency: {elapsed_ms:.1f}ms)")
            print(f"  -> Extracted Arguments: {json.dumps(args, ensure_ascii=False)}")
        else:
            print(f"  -> No Tool Dispatched (Normal Conversation / Unrecognized) ({elapsed_ms:.1f}ms)")

    print("\n" + "=" * 70)
    print("Test bench complete. You can also run interactive queries:")
    print("  python scripts/test_qwen_tool.py \"your command here\"")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        tools_file = PROJECT_ROOT / "data/dataset/stewart_tools.json"
        with open(tools_file, "r", encoding="utf-8") as f:
            tools = json.load(f)
        merged_path = PROJECT_ROOT / "data/models/qwen2.5-0.5b-stewart"
        lora_path = PROJECT_ROOT / "data/models/qwen2.5-0.5b-stewart-lora"
        checkpoints = sorted(lora_path.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1])) if lora_path.exists() else []
        target = merged_path if merged_path.exists() else (checkpoints[-1] if checkpoints else lora_path)
        
        caller = QwenToolCaller(model_path=str(target))
        caller.load_model()
        res = caller.call_tool(query, tools)
        if res:
            name, args, ctx = res
            print(f"Tool: {name}\nArgs: {json.dumps(args, ensure_ascii=False, indent=2)}")
        else:
            print("No tool call triggered.")
    else:
        main()
