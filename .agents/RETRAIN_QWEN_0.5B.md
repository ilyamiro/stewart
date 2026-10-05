# Plan & Blueprint: Retraining Qwen2.5-0.5B on Expanded Tool Suite & Persona Dataset

This document details the complete, step-by-step engineering plan to retrain the **Qwen2.5-0.5B** model on Stewart's upgraded dataset (25 tools, rich candidate schemas, Russian/English commands, MCP Studieplus, MCP Gmail, and chitchat rejection), bringing 0.5B to full parity with the newly trained 1.5B model while preserving backward compatibility.

---

## 1. Architectural Strategy & Design

### Dual Model Hierarchy
Stewart maintains two parallel model tiers that can be switched instantly via `config/config.yaml`:
1. **Qwen2.5-1.5B** (Higher reasoning capacity, multi-argument slot filling, complex conversational nuance).
2. **Qwen2.5-0.5B** (Ultra-low latency ~20-30ms, minimal VRAM consumption ~400MB, ideal for lightweight background execution).

Both models share the **exact same system prompt format**, **tool signature schemas**, and **interchangeable LoRA structure**:
* **Adapter 1 (`tool_caller`)**: Identifies tool intent, extracts arguments into JSON `<tool_call>`, or outputs direct text for chitchat/negative turns.
* **Adapter 2 (`persona`)**: Produces 1-2 sentence refined British butler voice responses addressing the user as Sir or Illia (сэр / Илья), conditioned on tool results for Kokoro TTS.

---

## 2. Dataset Blueprint

The retraining uses the enhanced datasets generated during the 1.5B upgrade:

| Dataset | File Path | Samples | Description |
| :--- | :--- | :--- | :--- |
| **Tool Train** | `data/dataset/train_1.5b.jsonl` | **1,021** | 25 tools (Core Linux, Dynamic Tools, MCP Studieplus, MCP Gmail, IB study tools), bilingual EN/RU, candidate prompt formatting, negative chitchat. |
| **Tool Val** | `data/dataset/val_1.5b.jsonl` | **114** | Unseen validation queries for tool classification & argument extraction accuracy. |
| **Persona Train** | `data/dataset/persona_train_1.5b.jsonl` | **13,365** | Bilingual British butler voice turns with action confirmations and polite conversational replies. |
| **Persona Val** | `data/dataset/persona_val_1.5b.jsonl` | **1,485** | Validation turns (sliced to 120 samples per eval step for fast training iterations). |

### 25 Tools Included in Retraining:
* **Core Desktop / System**: `media_control`, `volume`, `brightness`, `timer`, `screenshot`, `lock_session`, `battery_health`, `tell_time`, `say_weather`, `hotkey`, `subprocess`, `play_song`, `find_video`, `web_search`, `read_clipboard`.
* **Dynamic File Tools**: `change_file_name` (handling file renames and moves).
* **MCP Studieplus School Suite**: `studieplus_get_schedule`, `studieplus_get_assignments`, `studieplus_get_conversations`, `studieplus_check_session`.
* **MCP Study & IB Suite**: `study_get_ib_resources`, `study_prepare_test`, `study_get_past_topics`.
* **MCP Gmail Suite**: `gmail_check_status`, `gmail_search_emails`, `gmail_send_email`.
* **Negative / Chitchat**: Rejection of general questions and greetings without triggering hallucinated tool calls.

---

## 3. Hardware & Hyperparameters (NVIDIA RTX 3050 Laptop GPU)

Because `Qwen2.5-0.5B` contains only **490 million parameters** (~3x smaller than 1.5B):
* **Base Model Memory (4-bit NF4)**: ~380 MiB VRAM.
* **Peak Training VRAM**: ~1.8–2.2 GiB (well below the 4.0 GiB GPU limit).
* **Throughput**: ~15–20 samples/second.
* **Expected Training Time**: **~3.5 to 5 minutes** per LoRA adapter.

### Recommended Training Parameters:
```yaml
base_model: "Qwen/Qwen2.5-0.5B-Instruct"
quantization: "4-bit BitsAndBytes NF4 (double quant)"
compute_dtype: "torch.float16"
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
lora_target_modules: ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
batch_size: 2
grad_accumulation: 4  # Effective batch size = 8
learning_rate: 3.0e-4
lr_scheduler: "cosine"
warmup_ratio: 0.05
max_seq_length: 256 tokens
optimizer: "paged_adamw_8bit"
eval_steps: 60
total_steps: 300 steps (~2.3 epochs)
```

---

## 4. Step-by-Step Execution Plan

### Step 0: Backup Legacy 0.5B Models
Ensure existing 0.5B models remain safe and runnable:
```bash
mkdir -p data/models/legacy_0.5b
cp -r data/models/qwen2.5-0.5b-stewart-lora data/models/legacy_0.5b/
cp -r data/models/qwen2.5-0.5b-persona-lora data/models/legacy_0.5b/
cp data/models/gguf/qwen2.5-0.5b-tool-caller-q8_0.gguf data/models/legacy_0.5b/
cp data/models/gguf/qwen2.5-0.5b-persona-q8_0.gguf data/models/legacy_0.5b/
```

---

### Step 1: Pre-Training System Check (GPU Reset if Required)
If the NVIDIA driver is in a defensive lock (`cuInit 999`), reload the kernel module or reboot the machine:
```bash
sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm
# Verify clean CUDA initialization:
nix-shell shell.nix --run ".venv_qwen/bin/python -c 'import torch; print(\"CUDA Status:\", torch.cuda.is_available(), torch.cuda.get_device_name(0))'"
```

---

### Step 2: Fine-Tune 0.5B Tool Calling LoRA
Execute training on the 25-tool dataset:
```bash
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/train_qwen_0.5b_tool.py \
    --model_name_or_path Qwen/Qwen2.5-0.5B-Instruct \
    --train_file data/dataset/train_1.5b.jsonl \
    --val_file data/dataset/val_1.5b.jsonl \
    --output_dir data/models/qwen2.5-0.5b-stewart-lora \
    --epochs 3 \
    --batch_size 2 \
    --grad_accum 4 \
    --lr 3e-4 \
    --max_length 256"
```
* **Target Metric**: Validation Loss $< 0.15$ within 250–300 steps (~4 mins).
* **Artifacts Saved**: `adapter_model.safetensors`, `adapter_config.json`, `tokenizer.json`.

---

### Step 3: Fine-Tune 0.5B Voice Persona LoRA
Train the British butler persona adapter:
```bash
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/train_qwen_0.5b_persona.py \
    --model_name_or_path Qwen/Qwen2.5-0.5B-Instruct \
    --train_file data/dataset/persona_train_1.5b.jsonl \
    --val_file data/dataset/persona_val_1.5b.jsonl \
    --output_dir data/models/qwen2.5-0.5b-persona-lora \
    --epochs 1 \
    --batch_size 2 \
    --grad_accum 4 \
    --lr 2.5e-4 \
    --max_length 180"
```
* **Target Metric**: Validation Loss $< 0.10$ within 300 steps (~4 mins).
* **Artifacts Saved**: `adapter_model.safetensors`, `adapter_config.json`.

---

### Step 4: Merge LoRA Adapters & Export to GGUF
For ultra-fast C++ inference via `llama-cpp-python` (<25ms TTFT, ~400MB VRAM):
1. **Merge LoRA weights into standalone models**:
   ```bash
   nix-shell shell.nix --run ".venv_qwen/bin/python scripts/merge_qwen_lora.py \
       --base_model Qwen/Qwen2.5-0.5B-Instruct \
       --lora_path data/models/qwen2.5-0.5b-stewart-lora \
       --output_dir data/models/qwen2.5-0.5b-stewart"

   nix-shell shell.nix --run ".venv_qwen/bin/python scripts/merge_qwen_lora.py \
       --base_model Qwen/Qwen2.5-0.5B-Instruct \
       --lora_path data/models/qwen2.5-0.5b-persona-lora \
       --output_dir data/models/qwen2.5-0.5b-persona"
   ```

2. **Convert to GGUF format**:
   ```bash
   nix-shell shell.nix --run ".venv_qwen/bin/python scripts/convert_hf_to_gguf.py \
       data/models/qwen2.5-0.5b-stewart \
       --outfile data/models/gguf/qwen2.5-0.5b-tool-caller-q8_0.gguf \
       --outtype q8_0"

   nix-shell shell.nix --run ".venv_qwen/bin/python scripts/convert_hf_to_gguf.py \
       data/models/qwen2.5-0.5b-persona \
       --outfile data/models/gguf/qwen2.5-0.5b-persona-q8_0.gguf \
       --outtype q8_0"
   ```

---

## 5. Seamless Runtime Switching in Stewart

Stewart is designed to switch between models effortlessly without code changes:

### In `config/config.yaml`:
To run the lightweight **0.5B** model:
```yaml
router:
  mode: hybrid
  qwen:
    model_size: "0.5b"
    model_path: data/models/gguf/qwen2.5-0.5b-tool-caller-q8_0.gguf
    max_new_tokens: 128

persona:
  enabled: true
  model_size: "0.5b"
  model_path: data/models/gguf/qwen2.5-0.5b-persona-q8_0.gguf
  max_new_tokens: 64
```

To run the upgraded **1.5B** model:
```yaml
router:
  mode: hybrid
  qwen:
    model_size: "1.5b"
    model_path: data/models/qwen2.5-1.5b-stewart-lora
    max_new_tokens: 128

persona:
  enabled: true
  model_size: "1.5b"
  model_path: data/models/qwen2.5-1.5b-persona-lora
  max_new_tokens: 64
```

Or via shell environment variable:
```bash
export QWEN_MODEL_SIZE="0.5b"   # or "1.5b"
python main.py
```

---

## 6. Expected Performance Comparison After Retraining

| Capability | Legacy 0.5B (Original) | Retrained 0.5B (v2) | Qwen2.5-1.5B |
| :--- | :--- | :--- | :--- |
| **Available Tools** | 15 tools | **25 tools** | **25 tools** |
| **MCP Support (Studieplus, Gmail)** | None (0% accuracy) | **Full Support (>90%)** | **Full Support (>95%)** |
| **Russian Variations** | Basic | **Native slot filling** | **Native slot filling** |
| **Chitchat Rejection** | Partial (frequent hallucination) | **High (>85%)** | **Superior (>95%)** |
| **Inference Latency (GGUF)** | ~25 ms | **~25 ms** | ~45 ms |
| **Runtime VRAM Footprint** | ~350 MiB | **~380 MiB** | ~1.25 GiB |
| **TTS Persona Voice** | Generic | **British Butler (Kokoro-tailored)** | **British Butler (Kokoro-tailored)** |
