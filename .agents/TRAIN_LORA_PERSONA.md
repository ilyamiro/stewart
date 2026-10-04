# Persona LoRA Fine-Tuning Guide for Stewart (Qwen2.5)

This document is a technical blueprint for training a natural, context-aware **voice persona model** for Stewart on this NixOS host using **Qwen2.5 (1.5B or 0.5B)**.

---

## 1. Host Architecture & NixOS Environment

This system runs NixOS with strict isolation and an immutable filesystem (`/nix/store`). Any agent working on training must adhere to these host rules:

### A. Hardware Specifications
* **GPU**: NVIDIA GeForce RTX 3050 Laptop GPU
* **Total VRAM**: 4,096 MiB (~3,680 MiB usable for PyTorch CUDA)
* **Driver**: NVIDIA Linux driver version `595.99.02`, CUDA `13.2` runtime compatible

### B. NixOS-Specific Quirk & Workarounds
1. **No `/sbin/ldconfig`**:
   * Standard Linux wheels (like Triton / FlashAttention) try to call `/sbin/ldconfig -p` to find `libcuda.so.1`. NixOS does not have `/sbin/ldconfig`.
   * **Mandatory Fix**: You must set:
     ```bash
     export TRITON_LIBCUDA_PATH="/run/opengl-driver/lib"
     ```
     Or in Python before importing `torch`:
     ```python
     import os
     if os.path.exists("/run/opengl-driver/lib"):
         os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")
     ```
2. **CUDA Memory Allocation (Preventing OOM on 4GB VRAM)**:
   * To prevent memory fragmentation:
     ```bash
     export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
     ```
3. **The Nix Development Shell (`shell.nix`)**:
   * Always run commands through `nix-shell shell.nix --run "..."`.
   * [`shell.nix`](file:///home/ilyamiro/Projects/stewart/shell.nix) provides:
     - `pkgs.python311` (Python 3.11.16)
     - `pkgs.uv` (0.12.5)
     - Host GPU driver bindings (`/run/opengl-driver/lib`)
     - Shared libraries (`stdenv.cc.cc.lib`, `zlib`, `glib`, `openssl`, `libGL`, `mpv`, `portaudio`)
4. **Dedicated Python Virtual Environment (`.venv_qwen`)**:
   * Located at `/home/ilyamiro/Projects/stewart/.venv_qwen`.
   * PyTorch `2.14.1+cu130` with full CUDA 12 support, `transformers 5.18.0`, `peft 0.21.2`, `accelerate 1.15.0`, `bitsandbytes 0.50.2`, `datasets 5.0.1` are already installed and tested.

---

## 2. Choosing Model Architecture: 0.5B Multi-LoRA vs 1.5B Dedicated

You have two architectural options for the Persona model:

### Option A: Qwen2.5-0.5B Multi-LoRA (Same Base Model, Adapter Swapping)
* **How it works**:
  The base model `Qwen/Qwen2.5-0.5B-Instruct` stays loaded in GPU VRAM once (~1 GB).
  - Adapter 1: `stewart-tool-caller` (fine-tuned on tool calling)
  - Adapter 2: `stewart-persona` (fine-tuned on butler conversational responses)
* **VRAM**: Only ~1.2 GB total for both adapters.
* **Latency**: Extremely fast (~20–30ms per response).
* **Adapter Swap Time**: Calling `model.set_adapter("persona")` in PEFT takes **< 1 millisecond**.
* **Dataset Requirement**: Needs a very well-structured synthetic dataset (~4,000–6,000 dialogues) with explicit context injection (user name, time, tool results, mood).

### Option B: Qwen2.5-1.5B Dedicated Persona Model
* **How it works**:
  A separate 1.5B model (`Qwen/Qwen2.5-1.5B-Instruct`) fine-tuned specifically for rich conversational responses.
* **VRAM**:
  - In 4-bit QLoRA: ~900 MB
  - In fp16: ~3.0 GB (fits on RTX 3050 if Whisper STT runs on CPU or small model)
* **Latency**: ~50–80ms per response.
* **Benefit**: More natural wit, complex phrasing, and deeper general world knowledge.

---

## 3. Stewart Persona Guidelines & Specifications

Stewart is designed with the persona of a refined, highly competent **modern British Butler / Digital Concierge** (inspired by J.A.R.V.I.S.).

1. **User Identity** (from `config/langs/en.yaml` and `ru.yaml`):
   - User Name: `Illia`
   - Formal Address: `Sir` (or `сэр` in Russian)
2. **Conciseness for Voice TTS (Crucial)**:
   - Voice assistant responses must **never** be wordy paragraphs.
   - Optimal length: **1 to 2 crisp, elegant sentences** (5 to 25 words).
   - Long responses sound unnatural when spoken by Kokoro TTS.
3. **Contextual Awareness**:
   Responses should acknowledge the real-time context:
   * **Action Confirmation**: *"Volume adjusted to forty percent, sir."* / *"Громкость установлена на сорок процентов, сэр."*
   * **Time of Day Awareness**: *"Good morning, sir. Systems are online."*
   * **Weather Responses**: *"It is currently 15 degrees and overcast in Berlin, sir. Rain is unlikely."*
   * **Media Playback**: *"Resuming your playback, sir."*
   * **Polite Chitchat / Jokes**: Short, dry, witty humor.

---

## 4. Dataset Generation Pipeline for Persona

To train the persona, generate a dataset (`data/dataset/persona_train.jsonl` and `persona_val.jsonl`) with conversations following this schema:

### Example Training Turn (Tool Result $\rightarrow$ Persona Answer)
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are Stewart, an intelligent, refined AI butler running on Linux. You speak concisely (1-2 sentences) in a polite, respectful tone, addressing the user as Sir or Illia. You confirm actions smoothly and provide witty, helpful answers."
    },
    {
      "role": "user",
      "content": "Can you make it a bit quieter? I have a meeting."
    },
    {
      "role": "tool",
      "name": "volume",
      "content": "{\"status\": \"success\", \"current_volume\": 35}"
    },
    {
      "role": "assistant",
      "content": "Lowered the volume to thirty-five percent, sir. Best of luck with your meeting."
    }
  ]
}
```

### Russian Equivalent Example
```json
{
  "messages": [
    {
      "role": "system",
      "content": "Вы — Стюарт, умный и вежливый голосовой ассистент для Linux. Вы говорите лаконично (1-2 предложения), уважительно, называя пользователя сэр или Илья."
    },
    {
      "role": "user",
      "content": "Стюарт, сделай экран поярче, ничего не видно."
    },
    {
      "role": "tool",
      "name": "brightness",
      "content": "{\"status\": \"success\", \"brightness\": 80}"
    },
    {
      "role": "assistant",
      "content": "Яркость увеличена до восьмидесяти процентов, сэр."
    }
  ]
}
```

---

## 5. Hyperparameters for 4GB VRAM Training (Tested & Verified)

When training on this machine's RTX 3050 Laptop GPU, use these exact parameters to prevent CUDA Out-Of-Memory (OOM):

| Parameter | Recommended Value | Reason |
| :--- | :--- | :--- |
| `model_name_or_path` | `Qwen/Qwen2.5-1.5B-Instruct` or `Qwen/Qwen2.5-0.5B-Instruct` | Base model |
| `qlora` | `True` (4-bit NF4) | Reduces base weights to ~350MB (0.5B) or ~900MB (1.5B) |
| `per_device_train_batch_size` | `1` | Essential for Qwen's large 152k vocab logits tensor |
| `gradient_accumulation_steps` | `8` | Effective batch size of 8 |
| `gradient_checkpointing` | `True` (`use_reentrant: False`) | Frees activation memory during backward pass |
| `optim` | `"paged_adamw_8bit"` | Paged memory optimizer prevents spike OOMs |
| `max_length` | `384` | Ample for short voice dialogue turns |
| `learning_rate` | `2e-4` with cosine schedule | Stable convergence |
| `warmup_steps` | `50` | Avoids gradient shocks in early steps |
| `fp16` | `True` | Hardware acceleration on RTX Tensor Cores |

---

## 6. Training Execution Command

Create a script `scripts/train_qwen_persona.py` (modelled after `scripts/train_qwen_lora.py`) and launch inside `shell.nix`:

```bash
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/train_qwen_persona.py \
  --model_name_or_path Qwen/Qwen2.5-1.5B-Instruct \
  --train_file data/dataset/persona_train.jsonl \
  --val_file data/dataset/persona_val.jsonl \
  --output_dir data/models/qwen2.5-1.5b-persona-lora \
  --merged_dir data/models/qwen2.5-1.5b-persona \
  --epochs 3 \
  --batch_size 1 \
  --grad_accum 8 \
  --lr 2e-4 \
  --max_length 384"
```

---

## 7. Connecting Persona to Stewart's Voice Pipeline

1. **Execution Point**:
   In [`api/commands/router.py`](file:///home/ilyamiro/Projects/stewart/api/commands/router.py), after a tool executes via [`ActionTool.invoke()`](file:///home/ilyamiro/Projects/stewart/api/commands/tools.py#L51):
2. **Dynamic Spoken Text**:
   Instead of choosing a random string from `cmd.responses` in [`config/langs/en.yaml`](file:///home/ilyamiro/Projects/stewart/config/langs/en.yaml), pass `(user_query, tool_name, tool_output)` to the Persona model.
3. **Audio Output**:
   The generated string is passed directly to Kokoro TTS:
   ```python
   spoken_text = persona_caller.generate_response(query, action_result)
   api.speaker.say(spoken_text)
   ```
