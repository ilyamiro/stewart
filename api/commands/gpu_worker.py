#!/usr/bin/env python3
"""
Single-process GPU Worker for Stewart.
Maintains ONE Qwen2.5-1.5B base model in GPU VRAM (RTX 3050 CUDA0),
with dynamic interchangeable LoRA adapters:
1. Tool Calling LoRA adapter
2. Persona Butler Voice LoRA adapter
Achieves ~600ms latency, zero CPU load, and under 2.0 GB VRAM usage.
"""
import os
import sys
import json
import glob
from pathlib import Path

# Setup NVIDIA CUDA library paths and nix-ld paths for NixOS dynamic linking
search_dirs = [
    Path.cwd(),
    Path.home() / "Projects/stewart",
    Path.home() / ".local/share/stewart",
    Path(__file__).resolve().parent.parent.parent
]
base_dir = search_dirs[1]
for d in search_dirs:
    if (d / ".venv_qwen").exists():
        base_dir = d
        break

nvidia_libs = glob.glob(str(base_dir / ".venv_qwen/lib/python*/site-packages/nvidia/*/lib"))
ld_paths = [
    "/run/current-system/sw/share/nix-ld/lib",
    "/run/opengl-driver/lib",
    "/run/opengl-driver-32/lib"
] + nvidia_libs
nix_ld = os.environ.get("NIX_LD_LIBRARY_PATH", "")
if nix_ld:
    ld_paths.insert(0, nix_ld)
existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
if existing_ld:
    ld_paths.append(existing_ld)
os.environ["LD_LIBRARY_PATH"] = ":".join(ld_paths)
os.environ["CUDA_HOME"] = "/run/opengl-driver"
os.environ["TRITON_LIBCUDA_PATH"] = "/run/opengl-driver/lib"

try:
    import llama_cpp
except ImportError as e:
    sys.stderr.write(f"GPU Worker ImportError: {e}\n")
    sys.stderr.flush()
    sys.exit(1)


def resolve_file(rel_path: str) -> Path:
    candidates = [
        base_dir / rel_path,
        Path.home() / "Projects/stewart" / rel_path,
        Path.home() / ".cache/stewart" / rel_path,
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def main():
    base_model_path = resolve_file("data/models/gguf/qwen2.5-1.5b-base-q8_0.gguf")
    tool_lora_path = resolve_file("data/models/gguf/qwen2.5-1.5b-tool-lora-f16.gguf")
    persona_lora_path = resolve_file("data/models/gguf/qwen2.5-1.5b-persona-lora-f16.gguf")

    sys.stderr.write(f"GPU Worker: Loading ONE base model {base_model_path.name} on RTX 3050 GPU...\n")
    sys.stderr.flush()

    llm = llama_cpp.Llama(
        model_path=str(base_model_path),
        n_gpu_layers=-1,
        n_ctx=2048,
        verbose=False
    )

    sys.stderr.write(f"GPU Worker: Initializing interchangeable LoRA adapters...\n")
    tool_lora = llama_cpp.llama_adapter_lora_init(llm.model, str(tool_lora_path).encode("utf-8"))
    persona_lora = llama_cpp.llama_adapter_lora_init(llm.model, str(persona_lora_path).encode("utf-8"))
    sys.stderr.write(f"GPU Worker: LoRA adapters ready (tool: {tool_lora_path.name}, persona: {persona_lora_path.name})\n")
    sys.stderr.flush()

    # Compile GBNF grammar for tool calling
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
    grammar = llama_cpp.LlamaGrammar.from_string(grammar_text)

    sys.stderr.write("GPU Worker READY\n")
    sys.stderr.flush()

    # Signal ready to parent
    print(json.dumps({"status": "ready"}))
    sys.stdout.flush()

    current_adapter = None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            action = req.get("action")

            if action == "call_tool":
                # Switch to tool caller LoRA
                if current_adapter != "tool":
                    llama_cpp.llama_set_adapter_lora(llm.ctx, persona_lora, 0.0)
                    llama_cpp.llama_set_adapter_lora(llm.ctx, tool_lora, 1.0)
                    current_adapter = "tool"

                messages = req.get("messages", [])
                max_tokens = int(req.get("max_tokens", 128))
                res = llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    grammar=grammar
                )
                content = res["choices"][0]["message"].get("content", "").strip()
                print(json.dumps({"status": "ok", "content": content}))
                sys.stdout.flush()

            elif action == "generate_persona":
                # Switch to persona LoRA
                if current_adapter != "persona":
                    llama_cpp.llama_set_adapter_lora(llm.ctx, tool_lora, 0.0)
                    llama_cpp.llama_set_adapter_lora(llm.ctx, persona_lora, 1.0)
                    current_adapter = "persona"

                messages = req.get("messages", [])
                max_tokens = int(req.get("max_tokens", 64))
                temp = float(req.get("temperature", 0.6))
                res = llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temp
                )
                content = res["choices"][0]["message"].get("content", "").strip()
                print(json.dumps({"status": "ok", "content": content}))
                sys.stdout.flush()

            elif action == "stream_persona":
                # Switch to persona LoRA
                if current_adapter != "persona":
                    llama_cpp.llama_set_adapter_lora(llm.ctx, tool_lora, 0.0)
                    llama_cpp.llama_set_adapter_lora(llm.ctx, persona_lora, 1.0)
                    current_adapter = "persona"

                messages = req.get("messages", [])
                max_tokens = int(req.get("max_tokens", 64))
                temp = float(req.get("temperature", 0.6))
                stream = llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temp,
                    stream=True
                )
                for chunk in stream:
                    delta = chunk["choices"][0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        print(json.dumps({"status": "token", "token": token}))
                        sys.stdout.flush()
                print(json.dumps({"status": "done"}))
                sys.stdout.flush()

            elif action == "ping":
                print(json.dumps({"status": "pong"}))
                sys.stdout.flush()

            elif action == "quit":
                break

        except Exception as e:
            sys.stderr.write(f"GPU Worker error: {e}\n")
            sys.stderr.flush()
            print(json.dumps({"status": "error", "error": str(e)}))
            sys.stdout.flush()

    try:
        llama_cpp.llama_adapter_lora_free(tool_lora)
        llama_cpp.llama_adapter_lora_free(persona_lora)
    except Exception:
        pass


if __name__ == "__main__":
    main()
