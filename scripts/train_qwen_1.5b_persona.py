#!/usr/bin/env python3
"""
High-Performance Fine-Tuning Script for Qwen2.5-1.5B-Instruct on Stewart Butler Voice Persona.
Uses 4-bit QLoRA (NF4 double quant) with Paged 8-bit AdamW and Gradient Checkpointing.
Tuned specifically for RTX 3050 Laptop GPU to utilize 3.2-3.3 GB VRAM with fast convergence.
Saves LoRA adapter to `data/models/qwen2.5-1.5b-persona-lora`.
"""

import os
import sys

# Ensure NixOS CUDA driver compatibility
if os.path.exists("/run/opengl-driver/lib"):
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List

import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    BitsAndBytesConfig
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("TrainQwen1.5B-Persona")


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen2.5-1.5B on Stewart Voice Persona")
    parser.add_argument("--model_name_or_path", type=str, default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--train_file", type=str, default="data/dataset/persona_train_1.5b.jsonl")
    parser.add_argument("--val_file", type=str, default="data/dataset/persona_val_1.5b.jsonl")
    parser.add_argument("--output_dir", type=str, default="data/models/qwen2.5-1.5b-persona-lora")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--max_steps", type=int, default=300,
                        help="Limit training steps for fast, high-quality convergence")
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max_length", type=int, default=192)
    return parser.parse_args()


def main():
    args = parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info(f"Using device: {device}")
    if device == "cuda":
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        log.info(f"GPU: {torch.cuda.get_device_name(0)}, Total VRAM: {vram_gb:.2f} GB")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    log.info(f"Loading tokenizer from {args.model_name_or_path}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    log.info("Configuring 4-bit QLoRA quantization (BitsAndBytes NF4 double quant)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16
    )

    log.info(f"Loading base model '{args.model_name_or_path}'...")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path,
        quantization_config=bnb_config,
        torch_dtype=torch.float16,
        device_map="auto" if device == "cuda" else None,
        trust_remote_code=True
    )

    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})

    log.info("Attaching LoRA adapters to attention and MLP projection layers...")
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    log.info(f"Loading datasets: {args.train_file}, {args.val_file}...")
    dataset = load_dataset("json", data_files={"train": args.train_file, "validation": args.val_file})

    def preprocess_function(examples):
        input_ids_list = []
        labels_list = []

        for messages in examples["messages"]:
            full_prompt = tokenizer.apply_chat_template(messages, tokenize=False)
            tokenized_full = tokenizer(full_prompt, max_length=args.max_length, truncation=True)
            input_ids = tokenized_full["input_ids"]

            labels = list(input_ids)
            assistant_header = "<|im_start|>assistant\n"
            header_ids = tokenizer.encode(assistant_header, add_special_tokens=False)

            assistant_start_idx = -1
            for i in range(len(input_ids) - len(header_ids) + 1):
                if input_ids[i:i+len(header_ids)] == header_ids:
                    assistant_start_idx = i + len(header_ids)
                    break

            if assistant_start_idx != -1:
                for i in range(assistant_start_idx):
                    labels[i] = -100

            input_ids_list.append(input_ids)
            labels_list.append(labels)

        return {"input_ids": input_ids_list, "labels": labels_list}

    tokenized_datasets = dataset.map(
        preprocess_function,
        batched=True,
        remove_columns=dataset["train"].column_names,
        desc="Tokenizing and masking persona conversations"
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
        label_pad_token_id=-100
    )

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=20,
        max_steps=args.max_steps,
        fp16=(device == "cuda"),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        dataloader_pin_memory=False,
        optim="paged_adamw_8bit" if device == "cuda" else "adamw_torch",
        logging_steps=20,
        eval_strategy="steps",
        eval_steps=60,
        save_strategy="steps",
        save_steps=60,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["validation"].select(range(min(120, len(tokenized_datasets["validation"])))),
        data_collator=data_collator,
    )

    log.info("Starting Qwen2.5-1.5B Persona LoRA fine-tuning...")
    trainer.train()

    log.info(f"Saving fine-tuned Persona LoRA adapter to {args.output_dir}...")
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    log.info("Qwen2.5-1.5B Persona LoRA fine-tuning complete!")


if __name__ == "__main__":
    main()
