import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

if os.path.exists("/run/opengl-driver/lib"):
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")

log = logging.getLogger("API: qwen")

try:
    import llama_cpp
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    llama_cpp = None
    LLAMA_CPP_AVAILABLE = False

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    torch = None
    AutoTokenizer = None
    AutoModelForCausalLM = None
    TRANSFORMERS_AVAILABLE = False


class QwenToolCaller:
    """
    Local neural tool caller powered by fine-tuned Qwen2.5-0.5B.
    Performs fast, accurate tool selection, argument extraction, and slot-filling.
    Supports high-speed GGUF inference via llama-cpp-python with full CUDA offload (30-50ms),
    with seamless fallback to PyTorch FP16 / torch.compile.
    """
    def __init__(self,
                 model_path: Optional[str] = None,
                 device: Optional[str] = None,
                 max_new_tokens: int = 128,
                 n_ctx: int = 4096,
                 backend: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent.parent
        gguf_candidates = [
            base_dir / "data/models/gguf/qwen2.5-0.5b-tool-caller-q8_0.gguf",
            base_dir / "data/models/gguf/qwen2.5-0.5b-stewart-q8_0.gguf",
            base_dir / "data/models/gguf/qwen2.5-0.5b-tool-caller-f16.gguf",
            base_dir / "data/models/gguf/qwen2.5-0.5b-stewart-f16.gguf",
            base_dir / "data/models/gguf/qwen2.5-0.5b-tool-caller.gguf"
        ]
        default_hf_dir = base_dir / "data/models/qwen2.5-0.5b-stewart"
        lora_hf_dir = base_dir / "data/models/qwen2.5-0.5b-stewart-lora"

        self.custom_path = Path(model_path) if model_path else None
        self.gguf_path: Optional[Path] = None
        self.hf_path: Optional[Path] = None

        if self.custom_path:
            if self.custom_path.is_file() and self.custom_path.suffix == ".gguf":
                self.gguf_path = self.custom_path
            elif self.custom_path.is_dir():
                # Check if dir contains gguf or is HF
                found_gguf = list(self.custom_path.glob("*.gguf"))
                if found_gguf:
                    self.gguf_path = found_gguf[0]
                else:
                    self.hf_path = self.custom_path
        
        if not self.gguf_path:
            for cand in gguf_candidates:
                if cand.exists():
                    self.gguf_path = cand
                    break

        if not self.hf_path:
            self.hf_path = default_hf_dir if default_hf_dir.exists() else lora_hf_dir

        self.model_path = self.gguf_path if (self.gguf_path and LLAMA_CPP_AVAILABLE) else self.hf_path

        env_dev = os.getenv("QWEN_DEVICE")
        self.device = device or env_dev or ("cuda" if (torch and torch.cuda.is_available()) else "cpu")
        self.max_new_tokens = max_new_tokens
        self.n_ctx = n_ctx
        
        env_backend = os.getenv("QWEN_BACKEND", "").lower()
        self.backend = backend or env_backend or ("gguf" if (self.gguf_path and LLAMA_CPP_AVAILABLE) else "pytorch")

        # Persistent runtime instances
        self.llm: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.model: Optional[Any] = None
        self._is_loaded = False

    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> bool:
        # 1. Attempt GGUF + llama-cpp-python (fastest, ~30ms latency)
        if self.backend in ("gguf", "auto") and self.gguf_path and self.gguf_path.exists() and LLAMA_CPP_AVAILABLE:
            try:
                n_gpu = -1 if self.device == "cuda" else 0
                log.info(f"Loading persistent GGUF tool caller from {self.gguf_path} (n_gpu_layers={n_gpu})...")
                self.llm = llama_cpp.Llama(
                    model_path=str(self.gguf_path),
                    n_gpu_layers=n_gpu,
                    n_ctx=self.n_ctx,
                    n_threads=4,
                    verbose=False
                )
                # Warm-up pass to compile/initialize GPU kernels
                _ = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": "You are Stewart."},
                        {"role": "user", "content": "ping"}
                    ],
                    max_tokens=2,
                    temperature=0.0
                )
                self.backend = "gguf"
                self._is_loaded = True
                log.info(f"GGUF Tool Caller loaded and warmed up successfully ({self.gguf_path.name}).")
                return True
            except Exception as e:
                log.warning(f"Failed to load GGUF model via llama-cpp-python: {e}. Falling back to PyTorch.", exc_info=True)
                self.llm = None

        # 2. PyTorch HuggingFace Fallback
        if not TRANSFORMERS_AVAILABLE:
            log.warning("Neither llama-cpp nor PyTorch/Transformers are available; cannot load Qwen tool caller.")
            return False

        if not self.hf_path or not self.hf_path.exists():
            log.warning(f"Qwen model directory '{self.hf_path}' does not exist.")
            return False

        try:
            log.info(f"Loading local PyTorch Qwen2.5 model from {self.hf_path} on {self.device}...")
            is_lora = (self.hf_path / "adapter_config.json").exists()
            base_model_id = "Qwen/Qwen2.5-0.5B-Instruct" if is_lora else str(self.hf_path)

            self.tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
            torch_dtype = torch.float16 if self.device == "cuda" else torch.float32

            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                torch_dtype=torch_dtype,
                device_map=self.device if self.device == "cuda" else None,
                trust_remote_code=True
            )

            if is_lora:
                from peft import PeftModel
                self.model = PeftModel.from_pretrained(base_model, str(self.hf_path))
            else:
                self.model = base_model

            if self.device != "cuda":
                self.model.to(self.device)

            self.model.eval()

            # Optional torch.compile acceleration fallback
            if os.getenv("QWEN_TORCH_COMPILE", "0").lower() in ("1", "true", "yes"):
                try:
                    log.info("Compiling PyTorch Qwen model graph with mode='reduce-overhead'...")
                    self.model = torch.compile(self.model, mode="reduce-overhead")
                    dummy_in = self.tokenizer("warmup", return_tensors="pt").to(self.device)
                    with torch.inference_mode():
                        _ = self.model.generate(**dummy_in, max_new_tokens=4, use_cache=True)
                    log.info("PyTorch model compiled and warmed up successfully.")
                except Exception as ce:
                    log.warning(f"torch.compile failed: {ce}. Continuing with eager PyTorch.", exc_info=True)

            self.backend = "pytorch"
            self._is_loaded = True
            log.info("Local PyTorch Qwen2.5 tool caller loaded successfully.")
            return True
        except Exception as e:
            log.error(f"Failed to load PyTorch Qwen model from {self.hf_path}: {e}", exc_info=True)
            self._is_loaded = False
            return False

    def _format_system_prompt(self, tool_schemas: List[Dict[str, Any]]) -> str:
        tool_descs = []
        for t in tool_schemas:
            fn = t.get("function", t)
            schema_json = json.dumps(fn, indent=2, ensure_ascii=False)
            name = fn.get("name", "unknown")
            tool_descs.append(f"## {name}\n\n```json\n{schema_json}\n```")

        tools_block = "\n\n".join(tool_descs)
        return (
            "You are Stewart, an intelligent AI voice assistant running on Linux. "
            "You have access to the following tools to execute user commands:\n\n"
            f"# Tools\n\n{tools_block}\n\n"
            "When the user's request corresponds to an available tool, call the single best tool using:\n"
            "<tool_call>\n"
            "{\"name\": \"tool_name\", \"arguments\": {\"param\": \"value\"}}\n"
            "</tool_call>\n\n"
            "If the user is asking a general question, greeting, or chatting and no tool applies, answer directly without tool calls."
        )

    def call_tool(self, request: str, tool_schemas: List[Dict[str, Any]]) -> Optional[Tuple[str, Dict[str, Any], str]]:
        """
        Sends the user request and available tool schemas to Qwen.
        Returns (tool_name, arguments, context) if a tool was chosen, else None.
        """
        if not self._is_loaded:
            if not self.load_model():
                return None

        system_prompt = self._format_system_prompt(tool_schemas)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request}
        ]

        response_text = ""

        # GGUF Execution (~10-40ms)
        if self.backend == "gguf" and self.llm is not None:
            try:
                res = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=self.max_new_tokens,
                    temperature=0.0
                )
                response_text = res["choices"][0]["message"].get("content", "").strip()
            except Exception as e:
                log.warning(f"Error during GGUF tool call completion: {e}", exc_info=True)
                return None

        # PyTorch Execution Fallback
        elif self.backend == "pytorch" and self.model is not None and self.tokenizer is not None:
            try:
                full_prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.device)

                with torch.inference_mode():
                    output_ids = self.model.generate(
                        **inputs,
                        max_new_tokens=self.max_new_tokens,
                        do_sample=False,
                        temperature=None,
                        top_p=None,
                        use_cache=True,
                        pad_token_id=self.tokenizer.eos_token_id
                    )

                gen_ids = output_ids[0][inputs.input_ids.shape[1]:]
                response_text = self.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
            except Exception as e:
                log.warning(f"Error executing PyTorch Qwen tool calling: {e}", exc_info=True)
                return None

        if not response_text:
            return None

        # Parse tool call from response
        match = re.search(r"<tool_call>\s*(.*?)(?:</tool_call>|$)", response_text, re.DOTALL)
        if match:
            try:
                raw_call = match.group(1).strip()
                call_data = json.loads(raw_call)
                tool_name = call_data.get("name")
                args = call_data.get("arguments") or call_data.get("parameters") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"context": args}
                context = args.get("context", "")
                log.info(f"Qwen detected tool call '{tool_name}' with args {args} for request '{request}'")
                return tool_name, args, context
            except Exception as je:
                log.warning(f"Failed to parse tool call JSON '{match.group(1)}': {je}")

        return None
