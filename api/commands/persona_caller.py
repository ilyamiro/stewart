import os
import re
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Generator

if os.path.exists("/run/opengl-driver/lib"):
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "/run/opengl-driver/lib")

log = logging.getLogger("API: persona")

try:
    import llama_cpp
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    llama_cpp = None
    LLAMA_CPP_AVAILABLE = False

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    torch = None
    AutoTokenizer = None
    AutoModelForCausalLM = None
    TextIteratorStreamer = None
    TRANSFORMERS_AVAILABLE = False


SYSTEM_PROMPT_EN = (
    "You are Stewart, an intelligent, refined AI butler running on Linux. "
    "You speak concisely (1-2 sentences) in a polite, respectful tone, addressing the user as Sir or Illia. "
    "You confirm actions smoothly and provide witty, helpful answers. "
    "CRITICAL FOR VOICE TTS: Speak strictly in English. Do not mix other languages or alphabets. "
    "Do not use markdown, code blocks, emojis, or numbered lists."
)

SYSTEM_PROMPT_RU = (
    "Вы — Стюарт, умный и вежливый голосовой дворецкий для Linux. "
    "Вы говорите лаконично (1-2 предложения), уважительно, называя пользователя сэр или Илья. "
    "Вы изящно подтверждаете действия и даете полезные ответы. "
    "КРИТИЧЕСКИ ВАЖНО ДЛЯ ГОЛОСОВОГО СИНТЕЗА: Ответ должен быть СТРОГО на русском языке, только русскими буквами (кириллицей). "
    "Категорически запрещено использовать английские слова или латинские буквы! Любые бренды, сервисы, имена, сайты и термины транслитерируйте по-русски (например: Google -> Гугл, YouTube -> Ютуб, daily.dev -> Дейли дэв, Gmail -> Джимейл, Wi-Fi -> Вай-Фай). "
    "Не используйте цифры и списки с точками (1., 2.), пишите числа словами и говорите связным разговорным текстом."
)


class QwenPersonaCaller:
    """
    Stewart Butler Voice Persona model.
    Generates intelligent, refined, context-aware 1-2 sentence spoken responses for Kokoro TTS.
    Supports bilingual English and Russian, addressing user as Sir / Illia (сэр / Илья).
    Features high-performance GGUF runtime via llama-cpp-python (<10ms TTFT) with token streaming,
    and fallback to PyTorch FP16 / torch.compile.
    """

    def __init__(self,
                 model_path: Optional[Union[str, Path]] = None,
                 model_size: Optional[str] = None,
                 base_model_id: Optional[str] = None,
                 device: Optional[str] = None,
                 max_new_tokens: int = 64,
                 temperature: float = 0.6,
                 n_ctx: int = 512,
                 backend: Optional[str] = None,
                 shared_caller: Optional[Any] = None):
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
                f"data/models/gguf/qwen2.5-{self.model_size}-persona-q8_0.gguf",
                f"data/models/gguf/qwen2.5-{self.model_size}-persona-f16.gguf",
                f"data/models/gguf/qwen2.5-{self.model_size}-persona.gguf",
            ]:
                found = resolve_file(suffix)
                if found:
                    self.gguf_path = found
                    break

        if not self.hf_path:
            self.hf_path = (
                resolve_file(f"data/models/qwen2.5-{self.model_size}-persona-lora")
                or resolve_file(f"data/models/qwen2.5-{self.model_size}-persona")
                or (Path(__file__).resolve().parent.parent.parent / f"data/models/qwen2.5-{self.model_size}-persona")
            )

        self.model_path = self.gguf_path if (self.gguf_path and LLAMA_CPP_AVAILABLE) else self.hf_path
        self.base_model_id = base_model_id

        env_dev = os.getenv("QWEN_DEVICE")
        self.device = device or env_dev or ("cuda" if (torch and torch.cuda.is_available()) else "cpu")
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.n_ctx = n_ctx
        self.shared_caller = shared_caller

        env_backend = os.getenv("PERSONA_BACKEND", "").lower()
        self.backend = backend or env_backend or ("gguf" if (self.gguf_path and LLAMA_CPP_AVAILABLE) else "pytorch")

        # Persistent runtime instances
        self.llm: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.model: Optional[Any] = None
        self._is_loaded = False

    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> bool:
        # 1. GGUF + llama-cpp-python Acceleration (~10-15ms)
        if self.backend in ("gguf", "auto") and self.gguf_path and self.gguf_path.exists() and LLAMA_CPP_AVAILABLE:
            try:
                n_gpu = -1 if self.device == "cuda" else 0
                log.info(f"Loading persistent GGUF Persona model from {self.gguf_path} (n_gpu_layers={n_gpu})...")
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
                        log.warning(f"CUDA initialization failed for GGUF persona ({cuda_err}), falling back to CPU...")
                        self.llm = llama_cpp.Llama(
                            model_path=str(self.gguf_path),
                            n_gpu_layers=0,
                            n_ctx=self.n_ctx,
                            n_threads=4,
                            verbose=False
                        )
                    else:
                        raise cuda_err

                # Warm-up pass
                _ = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": "You are Stewart."},
                        {"role": "user", "content": "hello"}
                    ],
                    max_tokens=4,
                    temperature=0.0
                )
                self.backend = "gguf"
                self._is_loaded = True
                log.info(f"GGUF Persona model loaded and warmed up successfully ({self.gguf_path.name}).")
                return True
            except Exception as e:
                log.warning(f"Failed to load GGUF persona model via llama-cpp: {e}. Falling back to PyTorch.", exc_info=True)
                self.llm = None

        # 2. PyTorch Fallback
        if not TRANSFORMERS_AVAILABLE:
            log.warning("Neither llama-cpp nor PyTorch/Transformers are available; cannot load Persona model.")
            return False

        if not self.hf_path or not self.hf_path.exists():
            log.warning(f"Persona model directory '{self.hf_path}' does not exist.")
            return False

        try:
            # Check if we can share weights with an existing PyTorch QwenToolCaller
            if self.shared_caller and getattr(self.shared_caller, "_is_loaded", False) and getattr(self.shared_caller, "backend", "") == "pytorch":
                log.info("Reusing existing base model from shared PyTorch Qwen caller for Persona LoRA...")
                self.tokenizer = self.shared_caller.tokenizer
                base_peft_model = self.shared_caller.model
                from peft import PeftModel
                if isinstance(base_peft_model, PeftModel):
                    base_peft_model.load_adapter(str(self.hf_path), adapter_name="persona")
                    self.model = base_peft_model
                else:
                    self.model = PeftModel.from_pretrained(base_peft_model, str(self.hf_path), adapter_name="persona")
                self.backend = "pytorch"
                self._is_loaded = True
                return True

            log.info(f"Loading PyTorch Qwen Persona model from {self.hf_path} on {self.device}...")
            is_lora = (self.hf_path / "adapter_config.json").exists()
            base_model_id = self.base_model_id
            if is_lora and not base_model_id:
                try:
                    with open(self.hf_path / "adapter_config.json", "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        base_model_id = cfg.get("base_model_name_or_path")
                except Exception:
                    pass
            if not base_model_id:
                base_model_id = f"Qwen/Qwen2.5-{self.model_size}-Instruct" if is_lora else str(self.hf_path)
            tok_source = base_model_id

            self.tokenizer = AutoTokenizer.from_pretrained(tok_source, trust_remote_code=True)
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
                tok_source,
                torch_dtype=torch_dtype,
                quantization_config=bnb_config,
                device_map=self.device if self.device == "cuda" else None,
                trust_remote_code=True
            )

            if is_lora:
                from peft import PeftModel
                self.model = PeftModel.from_pretrained(base_model, str(self.hf_path), adapter_name="persona")
            else:
                self.model = base_model

            if self.device != "cuda":
                self.model.to(self.device)

            self.model.eval()

            # Optional torch.compile acceleration fallback
            if os.getenv("PERSONA_TORCH_COMPILE", "0").lower() in ("1", "true", "yes"):
                try:
                    log.info("Compiling PyTorch Persona model graph with mode='reduce-overhead'...")
                    self.model = torch.compile(self.model, mode="reduce-overhead")
                except Exception as ce:
                    log.warning(f"torch.compile failed on Persona model: {ce}")

            self.backend = "pytorch"
            self._is_loaded = True
            log.info("Local PyTorch Qwen Persona model loaded successfully.")
            return True

        except Exception as e:
            log.error(f"Failed to load Persona model from {self.hf_path}: {e}", exc_info=True)
            self._is_loaded = False
            return False

    def _build_messages(self,
                        user_query: str,
                        tool_name: Optional[str] = None,
                        tool_result: Optional[Any] = None,
                        lang: str = "en") -> List[Dict[str, str]]:
        is_ru = (lang == "ru") or any(ord(c) > 127 for c in user_query)
        sys_prompt = SYSTEM_PROMPT_RU if is_ru else SYSTEM_PROMPT_EN

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_query}
        ]

        if tool_name and tool_result is not None:
            content = tool_result if isinstance(tool_result, str) else json.dumps(tool_result, ensure_ascii=False)
            messages.append({
                "role": "tool",
                "name": tool_name,
                "content": content
            })

        return messages

    def stream_response(self,
                        user_query: str,
                        tool_name: Optional[str] = None,
                        tool_result: Optional[Any] = None,
                        lang: str = "en") -> Generator[str, None, None]:
        """
        Streams generated Persona response tokens in real-time.
        Yields individual text delta tokens as they are produced.
        """
        # 1. Attempt GPU Worker first (Dynamic LoRA on RTX 3050 GPU)
        try:
            from .gpu_client import GPUClient
            gpu_client = GPUClient.get_instance()
            if gpu_client is not None and gpu_client.is_ready:
                messages = self._build_messages(user_query, tool_name, tool_result, lang)
                for token in gpu_client.stream_persona(messages, max_tokens=self.max_new_tokens, temperature=self.temperature):
                    yield token
                return
        except Exception as ge:
            log.debug(f"GPU Worker stream_persona failed or not available ({ge}); falling back to local runner.")

        if not self._is_loaded:
            if not self.load_model():
                return

        messages = self._build_messages(user_query, tool_name, tool_result, lang)

        # 1. GGUF Streaming via llama-cpp-python (<10ms TTFT)
        if self.backend == "gguf" and self.llm is not None:
            try:
                stream = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=self.max_new_tokens,
                    temperature=self.temperature if self.temperature > 0 else 0.0,
                    top_p=0.9 if self.temperature > 0 else 1.0,
                    stream=True
                )
                for chunk in stream:
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                return
            except Exception as e:
                log.warning(f"Error in GGUF persona token streaming: {e}", exc_info=True)
                return

        # 2. PyTorch Streaming Fallback
        if self.backend == "pytorch" and self.model is not None and self.tokenizer is not None:
            try:
                from peft import PeftModel
                if isinstance(self.model, PeftModel) and "persona" in self.model.peft_config:
                    self.model.set_adapter("persona")
            except Exception:
                pass

            try:
                full_prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.device)

                streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
                gen_kwargs = dict(
                    **inputs,
                    streamer=streamer,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=(self.temperature > 0),
                    temperature=self.temperature if self.temperature > 0 else None,
                    top_p=0.9 if self.temperature > 0 else None,
                    pad_token_id=self.tokenizer.eos_token_id,
                    use_cache=True
                )

                def _generate():
                    with torch.inference_mode():
                        self.model.generate(**gen_kwargs)

                thread = threading.Thread(target=_generate, daemon=True)
                thread.start()

                for token in streamer:
                    yield token

                thread.join()
                return
            except Exception as e:
                log.warning(f"Error in PyTorch persona token streaming: {e}", exc_info=True)
                return

    def generate_response(self,
                          user_query: str,
                          tool_name: Optional[str] = None,
                          tool_result: Optional[Any] = None,
                          lang: str = "en") -> Optional[str]:
        """
        Generates an elegant, natural, context-aware butler response.
        Returns a concise 1-2 sentence string tailored for Kokoro TTS.
        """
        tokens = []
        for token in self.stream_response(user_query, tool_name=tool_name, tool_result=tool_result, lang=lang):
            tokens.append(token)

        if not tokens:
            return None

        response = "".join(tokens).strip()

        # Clean up response for Kokoro TTS
        response = response.strip('"\'`')
        response = re.sub(r"<tool_call>.*?</tool_call>", "", response, flags=re.DOTALL).strip()
        response = re.sub(r"<tool_response>.*?</tool_response>", "", response, flags=re.DOTALL).strip()

        log.info(f"Persona generated response: '{response}' (query='{user_query}', tool={tool_name})")
        return response if response else None
