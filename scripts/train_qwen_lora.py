#!/usr/bin/env python3
"""
Fine-tuning script for Qwen2.5-0.5B-Instruct on Stewart Tool Calling using LoRA / QLoRA.
Trains locally with PyTorch + CUDA, saves LoRA adapter and creates a standalone merged model.
"""

import os
import sys

# Ensure Triton locates host CUDA driver on NixOS
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
    prepare_model_for_kbit_training,
    PeftModel
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("TrainQwen")


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen2.5-0.5B on Stewart Tool Calling")
    parser.add_argument("--model_name_or_path", type=str, default="Qwen/Qwen2.5-0.5B-Instruct",
                        help="HuggingFace model ID or local path")
    parser.add_argument("--train_file", type=str, default="data/dataset/train.jsonl")
    parser.add_argument("--val_file", type=str, default="data/dataset/val.jsonl")
    parser.add_argument("--output_dir", type=str, default="data/models/qwen2.5-0.5b-stewart-lora")
    parser.add_argument("--merged_dir", type=str, default="data/models/qwen2.5-0.5b-stewart")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max_length", type=int, default=384)
    parser.add_argument("--qlora", action="store_true", default=True,
                        help="Use 4-bit QLoRA (recommended for 4GB VRAM)")
    parser.add_argument("--no_qlora", action="store_false", dest="qlora",
                        help="Use standard 16-bit LoRA")
    parser.add_argument("--skip_merge", action="store_true", default=False,
                        help="Skip merging LoRA weights into standalone model")
    return parser.parse_args()


def main():
    args = parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info(f"Using device: {device} (CUDA available: {torch.cuda.is_available()})")
    if device == "cuda":
        log.info(f"GPU: {torch.cuda.get_device_name(0)}, Total VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")

    log.info(f"Loading tokenizer from {args.model_name_or_path}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Setup quantization config if using QLoRA
    bnb_config = None
    if args.qlora and device == "cuda":
        log.info("Configuring 4-bit QLoRA quantization (BitsAndBytes NF4)...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16
        )

    log.info(f"Loading base model '{args.model_name_or_path}'...")
    torch_dtype = torch.float16 if device == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path,
        quantization_config=bnb_config,
        torch_dtype=torch_dtype,
        device_map="auto" if device == "cuda" else None,
        trust_remote_code=True
    )

    if args.qlora and device == "cuda":
        model = prepare_model_for_kbit_training(model)

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

    # Preprocess dataset: format messages and mask prompt loss
    log.info(f"Loading datasets: {args.train_file}, {args.val_file}...")
    dataset = load_dataset("json", data_files={"train": args.train_file, "validation": args.val_file})

    def preprocess_function(examples):
        input_ids_list = []
        labels_list = []

        for messages in examples["messages"]:
            # Format using official chat template
            full_prompt = tokenizer.apply_chat_template(messages, tokenize=False)
            tokenized_full = tokenizer(full_prompt, max_length=args.max_length, truncation=True)
            input_ids = tokenized_full["input_ids"]

            # Compute label mask: only compute loss on assistant turn!
            labels = list(input_ids)
            # Find the start of assistant token
            assistant_header = "<|im_start|>assistant\n"
            header_ids = tokenizer.encode(assistant_header, add_special_tokens=False)

            # Find where assistant header begins in input_ids
            assistant_start_idx = -1
            for i in range(len(input_ids) - len(header_ids) + 1):
                if input_ids[i:i+len(header_ids)] == header_ids:
                    assistant_start_idx = i + len(header_ids)
                    break

            if assistant_start_idx != -1:
                # Mask out everything before assistant generation
                for i in range(assistant_start_idx):
                    labels[i] = -100
            else:
                # Fallback: if not found, don't mask
                pass

            input_ids_list.append(input_ids)
            labels_list.append(labels)

        return {"input_ids": input_ids_list, "labels": labels_list}

    tokenized_datasets = dataset.map(
        preprocess_function,
        batched=True,
        remove_columns=dataset["train"].column_names,
        desc="Tokenizing and masking chat conversations"
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
        warmup_steps=50,
        num_train_epochs=args.epochs,
        fp16=(device == "cuda"),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        dataloader_pin_memory=False,
        optim="paged_adamw_8bit" if device == "cuda" else "adamw_torch",
        logging_steps=25,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["validation"],
        data_collator=data_collator,
    )

    log.info("Starting LoRA fine-tuning...")
    trainer.train()

    log.info(f"Saving fine-tuned LoRA adapter to {args.output_dir}...")
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    log.info("LoRA fine-tuning complete!")

    # Merge LoRA adapter into base model for fast standalone deployment
    if not args.skip_merge:
        log.info(f"Merging LoRA weights with base model into {args.merged_dir}...")
        del model
        del trainer
        torch.cuda.empty_cache()

        base_model = AutoModelForCausalLM.from_pretrained(
            args.model_name_or_path,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="cpu",
            trust_remote_code=True
        )
        peft_model = PeftModel.from_pretrained(base_model, args.output_dir)
        merged_model = peft_model.merge_and_unload()

        merged_path = Path(args.merged_dir)
        merged_path.mkdir(parents=True, exist_ok=True)
        merged_model.save_pretrained(str(merged_path))
        tokenizer.save_pretrained(str(merged_path))
        log.info(f"Standalone merged Qwen2.5 Stewart model saved to {args.merged_dir}!")


if __name__ == "__main__":
    main()
