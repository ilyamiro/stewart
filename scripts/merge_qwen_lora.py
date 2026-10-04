#!/usr/bin/env python3
"""
Merge fine-tuned LoRA weights into standalone Qwen2.5-0.5B model.
"""

import os
import sys
from pathlib import Path

# Ensure Triton driver on NixOS
if os.path.exists("/run/opengl-driver/lib"):
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LORA_PATH = PROJECT_ROOT / "data/models/qwen2.5-0.5b-stewart-lora/checkpoint-700"
OUTPUT_PATH = PROJECT_ROOT / "data/models/qwen2.5-0.5b-stewart"
BASE_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

print(f"Loading base model {BASE_MODEL_ID}...")
tokenizer = AutoTokenizer.from_pretrained(str(LORA_PATH), trust_remote_code=True)
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_ID,
    torch_dtype=torch.float16,
    device_map="cpu",
    trust_remote_code=True
)

print(f"Loading LoRA adapter from {LORA_PATH}...")
peft_model = PeftModel.from_pretrained(base_model, str(LORA_PATH))

print("Merging LoRA weights with base model...")
merged_model = peft_model.merge_and_unload()

print(f"Saving standalone merged model to {OUTPUT_PATH}...")
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
merged_model.save_pretrained(str(OUTPUT_PATH))
tokenizer.save_pretrained(str(OUTPUT_PATH))

print("Merge complete! Standalone model is ready.")
