# Stewart Neural Tool Calling with Qwen2.5-0.5B

Stewart integrates a local fine-tuned **Qwen2.5-0.5B-Instruct** model using **QLoRA (4-bit quantization)** to perform high-speed, intelligent function calling and argument extraction across natural voice and text requests in both **English and Russian**.

---

## 1. Architecture & Routing Hierarchy

Stewart's [`CommandRouter`](file:///home/ilyamiro/Projects/stewart/api/commands/router.py) supports a multi-tier recognition pipeline:

```
User Query (Voice / Text)
        │
        ▼
┌──────────────────────────────────────────────┐
│  Tier 1: Algorithmic Tree Matcher (<0.1ms)   │ (Exact / synonym matching)
└──────────────────────┬───────────────────────┘
                       │ (if no exact algorithmic match)
                       ▼
┌──────────────────────────────────────────────┐
│  Tier 2: Fine-Tuned Qwen2.5-0.5B / SpaCy     │ (Zero-shot in-context tool calling)
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  Tool Execution via ToolRegistry & Action    │
└──────────────────────────────────────────────┘
```

* **Tier 1 (Algorithmic)**: Evaluates canonical phrases in <0.1ms without invoking any neural network.
* **Tier 2 (Neural Tool Dispatcher)**: If the user speaks colloquial, complex, elliptical, or bilingual phrases (e.g., *"Stewart, turn down the volume a bit"*, *"Сделай экран поярче на 20 процентов"*, *"Close this browser tab"*), the fine-tuned Qwen2.5-0.5B reads the registered tool schemas, extracts typed JSON arguments, and triggers the corresponding action.

---

## 2. Configuration (`config/config.yaml`)

```yaml
router:
  mode: hybrid # Options: 'hybrid' (algorithmic first, model fallback), 'qwen', 'model', 'algorithmic'
  confidence_threshold: 0.55
  model:
    provider: qwen # Options: 'qwen' (local fine-tuned Qwen2.5), 'spacy' (ultra-fast classifier), 'ollama'
  qwen:
    model_path: data/models/qwen2.5-0.5b-stewart # Path to merged model or checkpoint
    max_new_tokens: 128
```

---

## 3. Training & Dataset Pipeline

### A. Synthetic Dataset Generation
Generates thousands of balanced, realistic examples across all core tools in Russian and English with diverse prefixes, fillers, and negative samples:
```bash
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/generate_qwen_dataset.py"
```
* Generates `data/dataset/train.jsonl` (5,929 examples) and `data/dataset/val.jsonl` (659 holdout test examples).

### B. QLoRA Fine-Tuning
Fine-tunes `Qwen/Qwen2.5-0.5B-Instruct` on GPU with 4-bit NF4 quantization, gradient checkpointing, and paged 8-bit AdamW:
```bash
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/train_qwen_lora.py"
```
* **VRAM footprint**: ~2.1 GB (fits comfortably in 4GB VRAM).
* **Speed**: ~3.8 seconds per step.
* **Loss**: Drops to <0.0001 within 100 steps.
* **Checkpoints**: Saved automatically every 100 steps to `data/models/qwen2.5-0.5b-stewart-lora/checkpoint-<step>/`.
* **Automatic Merge**: Merges LoRA adapter into standalone weights at `data/models/qwen2.5-0.5b-stewart`.

---

## 4. Testing & Verification

Run the interactive test bench on any query:
```bash
# Test a single query
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/test_qwen_tool.py 'Please pause the music right now'"

# Test Russian command
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/test_qwen_tool.py 'Сделай звук погромче на 10 процентов'"

# Run full automated test suite across 20+ scenarios
nix-shell shell.nix --run ".venv_qwen/bin/python scripts/test_qwen_tool.py"
```

---

## 5. Adding New Tools (Zero-Shot Support)

Because Qwen was fine-tuned on **in-context tool schemas** rather than hardcoded classification labels, **new tools do not require retraining**:
1. Define a standard Python action function in Stewart or any plugin.
2. Provide a descriptive docstring and typed parameter signature.
3. Stewart's [`ToolRegistry`](file:///home/ilyamiro/Projects/stewart/api/commands/tools.py#L71) automatically generates its JSON schema and injects it into the prompt.
4. Qwen will immediately recognize and dispatch the new tool based on user intent.
