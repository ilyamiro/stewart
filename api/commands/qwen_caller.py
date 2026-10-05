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
                 model_size: Optional[str] = None,
                 device: Optional[str] = None,
                 max_new_tokens: int = 128,
                 n_ctx: int = 4096,
                 backend: Optional[str] = None):
        search_roots = [
            Path.cwd(),
            Path.home() / "Projects/stewart",
            Path.home() / ".cache/stewart",
            Path.home() / ".local/share/stewart",
            Path(__file__).resolve().parent.parent.parent,
        ]

        def resolve_file(rel_path: Union[str, Path]) -> Optional[Path]:
            p = Path(rel_path).expanduser()
            if p.is_absolute() and p.exists():
                return p
            for root in search_roots:
                cand = root / rel_path
                if cand.exists():
                    return cand
            return None

        env_size = os.getenv("QWEN_MODEL_SIZE", "").lower()
        self.model_size = (model_size or env_size or "0.5b").lower()

        self.custom_path: Optional[Path] = None
        self.gguf_path: Optional[Path] = None
        self.hf_path: Optional[Path] = None

        if model_path:
            resolved = resolve_file(model_path)
            if resolved:
                self.custom_path = resolved
                if resolved.is_file() and resolved.suffix == ".gguf":
                    self.gguf_path = resolved
                elif resolved.is_dir():
                    found_gguf = list(resolved.glob("*.gguf"))
                    if found_gguf:
                        self.gguf_path = found_gguf[0]
                    else:
                        self.hf_path = resolved

        if not self.gguf_path:
            for suffix in [
                f"data/models/gguf/qwen2.5-{self.model_size}-tool-caller-q8_0.gguf",
                f"data/models/gguf/qwen2.5-{self.model_size}-stewart-q8_0.gguf",
                f"data/models/gguf/qwen2.5-{self.model_size}-tool-caller-f16.gguf",
                f"data/models/gguf/qwen2.5-{self.model_size}-stewart-f16.gguf",
                f"data/models/gguf/qwen2.5-{self.model_size}-tool-caller.gguf",
            ]:
                found = resolve_file(suffix)
                if found:
                    self.gguf_path = found
                    break

        if not self.hf_path:
            self.hf_path = (
                resolve_file(f"data/models/qwen2.5-{self.model_size}-stewart")
                or resolve_file(f"data/models/qwen2.5-{self.model_size}-stewart-lora")
                or (Path(__file__).resolve().parent.parent.parent / f"data/models/qwen2.5-{self.model_size}-stewart")
            )

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
        self._grammar: Optional[Any] = None
        self._is_loaded = False

    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> bool:
        # 1. Attempt GGUF + llama-cpp-python (fastest, ~30ms latency)
        if self.backend in ("gguf", "auto") and self.gguf_path and self.gguf_path.exists() and LLAMA_CPP_AVAILABLE:
            try:
                n_gpu = -1 if self.device == "cuda" else 0
                log.info(f"Loading persistent GGUF tool caller from {self.gguf_path} (n_gpu_layers={n_gpu})...")
                try:
                    self.llm = llama_cpp.Llama(
                        model_path=str(self.gguf_path),
                        n_gpu_layers=n_gpu,
                        n_ctx=self.n_ctx,
                        n_threads=4,
                        verbose=False
                    )
                except Exception as cuda_err:
                    if n_gpu != 0:
                        log.warning(f"CUDA initialization failed for GGUF tool caller ({cuda_err}), falling back to CPU...")
                        self.llm = llama_cpp.Llama(
                            model_path=str(self.gguf_path),
                            n_gpu_layers=0,
                            n_ctx=self.n_ctx,
                            n_threads=4,
                            verbose=False
                        )
                    else:
                        raise cuda_err

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
            base_model_id = None
            if is_lora:
                try:
                    with open(self.hf_path / "adapter_config.json", "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        base_model_id = cfg.get("base_model_name_or_path")
                except Exception:
                    pass
            if not base_model_id:
                base_model_id = f"Qwen/Qwen2.5-{self.model_size}-Instruct" if is_lora else str(self.hf_path)

            self.tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
            bnb_config = None
            if self.device == "cuda" and self.model_size == "1.5b":
                try:
                    from transformers import BitsAndBytesConfig
                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_compute_dtype=torch.float16
                    )
                except Exception:
                    bnb_config = None

            torch_dtype = torch.float16 if self.device == "cuda" else torch.float32
            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                torch_dtype=torch_dtype,
                quantization_config=bnb_config,
                device_map=self.device if self.device == "cuda" else None,
                trust_remote_code=True
            )

            if is_lora:
                from peft import PeftModel
                self.model = PeftModel.from_pretrained(base_model, str(self.hf_path), adapter_name="tool_caller")
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
        tool_lines = []
        for t in tool_schemas:
            fn = t.get("function", t)
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_strs = []
            for pname, pinfo in params.items():
                ptype = pinfo.get("type", "any")
                if "enum" in pinfo:
                    ptype = "|".join(f'"{e}"' for e in pinfo["enum"])
                param_strs.append(f"{pname}: {ptype}")
            params_repr = ", ".join(param_strs)
            tool_lines.append(f"- {name}({params_repr}) - {desc}")
        tools_block = "\n".join(tool_lines)
        return (
            "You are Stewart, an intelligent Linux AI voice assistant.\n"
            "Available tools:\n"
            f"{tools_block}\n"
            "Call single tool using: <tool_call>{\"name\": \"...\", \"arguments\": {...}}</tool_call>.\n"
            "If no tool applies, answer directly."
        )

    def _get_tool_grammar(self) -> Optional[Any]:
        if self._grammar is not None:
            return self._grammar
        if not LLAMA_CPP_AVAILABLE:
            return None
        try:
            grammar_text = r"""
root ::= (tool-call | text-response)
tool-call ::= "<tool_call>\n" json-object "\n</tool_call>"
text-response ::= [^<]+
json-object ::= "{" ws (member ("," ws member)*)? ws "}"
member ::= string ws ":" ws value
value ::= json-object | array | string | number | "true" | "false" | "null"
array ::= "[" ws (value ("," ws value)*)? ws "]"
string ::= "\"" [^"\\]* "\""
number ::= "-"? [0-9]+ ("." [0-9]+)?
ws ::= [ \t\n\r]*
"""
            self._grammar = llama_cpp.LlamaGrammar.from_string(grammar_text)
            return self._grammar
        except Exception as e:
            log.warning(f"Failed to compile GBNF tool grammar: {e}")
            return None

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

        # GGUF Execution (~10-40ms) with GBNF Constrained Decoding
        if self.backend == "gguf" and self.llm is not None:
            try:
                grammar = self._get_tool_grammar()
                kwargs = {
                    "messages": messages,
                    "max_tokens": self.max_new_tokens,
                    "temperature": 0.0
                }
                if grammar is not None:
                    kwargs["grammar"] = grammar

                res = self.llm.create_chat_completion(**kwargs)
                response_text = res["choices"][0]["message"].get("content", "").strip()
            except Exception as e:
                log.warning(f"Error during GGUF tool call completion: {e}", exc_info=True)
                return None

        # PyTorch Execution Fallback
        elif self.backend == "pytorch" and self.model is not None and self.tokenizer is not None:
            try:
                from peft import PeftModel
                if isinstance(self.model, PeftModel):
                    if "tool_caller" in self.model.peft_config:
                        self.model.set_adapter("tool_caller")
                    elif "default" in self.model.peft_config:
                        self.model.set_adapter("default")
            except Exception:
                pass

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
