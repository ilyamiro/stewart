#!/usr/bin/env python3
"""
Merge fine-tuned LoRA weights into standalone Qwen2.5 model.
"""

import os
import sys
import argparse
from pathlib import Path

# Ensure Triton driver on NixOS
if os.path.exists("/run/opengl-driver/lib"):
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel


def parse_args():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into standalone base model")
    parser.add_argument("--base_model", type=str, default="Qwen/Qwen2.5-0.5B-Instruct",
                        help="HuggingFace base model ID or local path")
    parser.add_argument("--lora_path", type=str, required=True,
                        help="Path to the LoRA adapter directory")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Path to save the merged standalone model")
    return parser.parse_args()


def main():
    args = parse_args()
    lora_path = Path(args.lora_path).resolve()
    output_path = Path(args.output_dir).resolve()
    base_model_id = args.base_model

    print(f"Loading tokenizer from {lora_path} (falling back to {base_model_id} if missing)...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(str(lora_path), trust_remote_code=True)
    except Exception:
        tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)

    print(f"Loading base model {base_model_id}...")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True
    )

    print(f"Loading LoRA adapter from {lora_path}...")
    peft_model = PeftModel.from_pretrained(base_model, str(lora_path))

    print("Merging LoRA weights with base model...")
    merged_model = peft_model.merge_and_unload()

    print(f"Saving standalone merged model to {output_path}...")
    output_path.mkdir(parents=True, exist_ok=True)
    merged_model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    print(f"Merge complete! Standalone model saved to {output_path}")


if __name__ == "__main__":
    main()
