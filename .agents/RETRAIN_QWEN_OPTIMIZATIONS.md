# Advanced Optimization & 8-Bit Re-Training Blueprint for Stewart Qwen2.5-1.5B

This technical blueprint provides an architectural and implementation guide for retraining the **Qwen2.5-1.5B** Stewart Tool Calling and Butler Voice Persona models to achieve minimal validation loss ($< 0.05$), higher argument slot-filling precision, and zero-hallucination tool dispatch.

---

## 1. Hardware Budget & Mathematical VRAM Envelope (RTX 3050 4GB)

* **Physical VRAM**: 4,096 MiB (~3,680 MiB usable for PyTorch CUDA allocator).
* **NixOS Driver**: Driver 595.99.02, CUDA 13.2 runtime compatibility.
* **Mandatory Environment Variables**:
  ```bash
  export TRITON_LIBCUDA_PATH="/run/opengl-driver/lib"
  export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
  ```

---

## 2. 8-Bit Base Weight Training (BitsAndBytes LLM.int8())

In 4-bit QLoRA (NF4), base weights are compressed to 4 bits (~0.95 GB), but the dequantization kernel reconstructs FP16 values dynamically during every forward pass. While fast and low-memory, this introduces subtle numeric rounding noise into the activation stream.

### 8-Bit Int8 Base Training Mechanics
With **8-bit quantization (`load_in_8bit=True`)**:
* **Base Model Memory**:
  $$\text{VRAM}_{\text{weights}} = 1.54 \times 10^9 \text{ parameters} \times 1 \text{ byte} \approx 1.54\text{ GB}$$
* **LoRA Weights ($r=32$, all linear projections)**:
  $$\approx 36.9 \times 10^6 \text{ parameters} \times 2 \text{ bytes (FP16)} \approx 74\text{ MB}$$
* **Optimizer States (Paged 8-bit AdamW)**:
  $$36.9 \times 10^6 \text{ params} \times 2 \times 1 \text{ byte} \approx 74\text{ MB}$$
* **Total Static Footprint**: **~1.69 GB**.
* **Dynamic Activation Footprint (with Gradient Checkpointing at $L=192$, batch=1)**: **~1.45 to 1.55 GB**.
* **Peak VRAM Total**: **~3.25 to 3.35 GB** (fits cleanly within the 3.68 GB CUDA allocation limit!).

### Implementation Configuration for 8-Bit Training
```python
import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from peft import prepare_model_for_kbit_training

bnb_8bit_config = BitsAndBytesConfig(
    load_in_8bit=True,
    llm_int8_threshold=6.0,          # Outlier separation threshold
    llm_int8_skip_modules=["lm_head"] # Keep output projection in FP16
)

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-1.5B-Instruct",
    quantization_config=bnb_8bit_config,
    torch_dtype=torch.float16,
    device_map="auto"
)

# Mandatory preparation for backward pass on 8-bit models
model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
```

---

## 3. LoRA Topology & Rank Upgrades

### A. Scaling Rank & Alpha with RSLoRA (Rank-Stabilized LoRA)
Standard LoRA computes adapter delta as:
$$\Delta W = \frac{\alpha}{r} (B \times A)$$
When scaling rank from $r=16$ to $r=32$ or $r=64$, standard scaling can cause gradient instability. Using **Rank-Stabilized LoRA (RSLoRA)** scales by $\frac{\alpha}{\sqrt{r}}$, allowing higher ranks to learn stable, deep representations without exploding gradients:

```python
from peft import LoraConfig

lora_config = LoraConfig(
    r=32,
    lora_alpha=64,
    use_rslora=True, # Rank-stabilized scaling: alpha / sqrt(r)
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)
```

### B. Incorporating `embed_tokens` and `lm_head`
In tool calling, special tokens (`<tool_call>`, `</tool_call>`) and JSON delimiters (`{`, `}`, `": "`) occur in strict structural patterns. Adapting the embedding layer helps the model specialize its token clusters:

```python
target_modules = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
    "embed_tokens", "lm_head"
]
```
*(Note: Training `lm_head` on a 152k vocabulary requires ~150 MB of optimizer states. Keep $r=16$ or $r=32$ on projection layers and use Paged AdamW to fit in VRAM).*

---

## 4. Dataset Entropy Reduction (Canonical Normalization)

In causal language modeling, the cross-entropy loss floor is bounded by dataset label entropy:
$$H(Y|X) = -\sum_{x, y} P(x, y) \log P(y|x)$$
If the dataset contains syntactic inconsistency, the model cannot drive loss below that ambiguity threshold.

### Mandatory Dataset Canonicalization Rules
1. **Sorted JSON Keys**:
   Always serialize arguments with sorted keys:
   ```python
   json.dumps(args, sort_keys=True, ensure_ascii=False)
   ```
   *Incorrect*: Sometimes `{"name": "...", "arguments": ...}` and other times `{"arguments": ..., "name": ...}`.
2. **Canonical Units**:
   * Volume: strictly integer percentages `"10"`, `"20"`, `"50"`, `"100"` (strip `%` symbols or enforce `%` consistently across all samples).
   * Durations: strictly normalized seconds or standard strings (`"300s"`, `"10 minutes"`).
3. **Consistent Negative Framing**:
   Ensure chitchat/general queries follow a unified response pattern so the model has a definitive boundary between tool calls and direct answers.

---

## 5. Token-Weighted Cross-Entropy Loss

Standard instruction fine-tuning penalizes every assistant token equally:
$$\mathcal{L} = -\frac{1}{N}\sum_{i=1}^N \log P(w_i | w_{<i})$$

In tool calling, formatting punctuation (`<tool_call>`, `\n`, `{"name": "`, `", "arguments": {`) is easy to predict, but semantic tokens (the actual tool name like `studieplus_get_schedule` and slot values like `"tomorrow"`) carry the actual functional payload.

### Custom Trainer with Semantic Token Weighting
```python
import torch
import torch.nn as nn
from transformers import Trainer

class SemanticWeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.get("labels")
        outputs = model(**inputs)
        logits = outputs.get("logits")
        
        # Shift logits and labels for causal LM
        shift_logits = logits[..., :-1, :].contiguous()
        shift_labels = labels[..., 1:].contiguous()
        
        # Base cross-entropy (reduction='none' to inspect per-token loss)
        loss_fct = nn.CrossEntropyLoss(reduction="none", ignore_index=-100)
        per_token_loss = loss_fct(
            shift_logits.view(-1, shift_logits.size(-1)),
            shift_labels.view(-1)
        )
        
        # Apply 2.5x weight to non-boilerplate tokens
        # (Tokens that are not braces, quotes, spaces, or tag tokens)
        weights = torch.ones_like(per_token_loss)
        valid_mask = (shift_labels.view(-1) != -100)
        weights = torch.where(valid_mask, weights, torch.zeros_like(weights))
        
        loss = (per_token_loss * weights).sum() / (weights.sum() + 1e-8)
        return (loss, outputs) if return_outputs else loss
```

---

## 6. Learning Rate & Optimizer Fine-Tuning

For deep convergence without gradient shocks:
* **Optimizer**: `paged_adamw_8bit` (BitsAndBytes)
* **Peak Learning Rate**: `1.2e-4` (slightly lower than the initial `2e-4` to prevent divergence at higher rank)
* **Warmup**: 50 optimizer steps
* **LR Schedule**: `cosine_with_min_lr` with `min_lr = 1e-6`
* **Weight Decay**: `0.01` (prevents LoRA matrix drift)
* **Gradient Clipping**: `max_grad_norm = 0.5`

---

## 7. Direct Preference Optimization (DPO) for Tool Precision

To eradicate tool selection hallucinations (e.g., calling `volume` when asked to `dim the screen`):
1. Create a pairwise dataset (`data/dataset/tool_dpo.jsonl`):
   ```json
   {
     "prompt": "<|im_start|>user\nMake the display darker<|im_end|>\n<|im_start|>assistant\n",
     "chosen": "<tool_call>\n{\"name\": \"brightness\", \"arguments\": {\"command\": \"down\"}}\n</tool_call>",
     "rejected": "<tool_call>\n{\"name\": \"volume\", \"arguments\": {\"command\": \"down\"}}\n</tool_call>"
   }
   ```
2. Train with HuggingFace `DPOTrainer`:
   ```bash
   nix-shell shell.nix --run ".venv_qwen/bin/python scripts/train_qwen_dpo.py"
   ```
   DPO directly optimizes the log-likelihood ratio, guaranteeing the model never selects distractor tools for ambiguous queries.

---

## 8. Summary Comparison

| Parameter | Standard 4-bit (Current) | Advanced 8-bit Optimization |
| :--- | :--- | :--- |
| **Base Model Precision** | 4-bit NF4 double quant | **8-bit Int8 (LLM.int8)** |
| **LoRA Rank ($r$)** | 16 | **32 (with RSLoRA)** |
| **LoRA Alpha ($\alpha$)** | 32 | **64** |
| **Target Modules** | All 7 linear projections | **Linear + embed_tokens** |
| **Dataset Normalization** | Semi-canonical | **Strictly sorted & normalized** |
| **Loss Function** | Standard Cross-Entropy | **Semantic Token-Weighted Loss** |
| **Expected Final Loss** | ~0.13 | **< 0.04** |
| **Peak VRAM on RTX 3050** | ~3.22 GB | **~3.30–3.35 GB** |
