import os
import sys
import json
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator

log = logging.getLogger("API: gpu_client")

class GPUClient:
    _instance: Optional["GPUClient"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.req_lock = threading.Lock()
        self.is_ready = False
        self._start_worker()

    @classmethod
    def get_instance(cls) -> Optional["GPUClient"]:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            if not cls._instance.is_ready:
                return None
            return cls._instance

    def _start_worker(self):
        search_dirs = [
            Path.cwd(),
            Path.home() / "Projects/stewart",
            Path.home() / ".local/share/stewart",
            Path(__file__).resolve().parent.parent.parent
        ]
        venv_python = None
        worker_script = None
        base_dir = None
        for d in search_dirs:
            cand_py = d / ".venv_qwen/bin/python"
            cand_worker = d / "api/commands/gpu_worker.py"
            if cand_py.exists() and cand_worker.exists():
                venv_python = cand_py
                worker_script = cand_worker
                base_dir = d
                break

        if not venv_python or not worker_script:
            log.warning("GPU Worker python or script not found; GPU offload worker unavailable.")
            return

        try:
            log.info(f"Starting persistent GPU Worker using {venv_python} on RTX 3050 GPU...")
            env = os.environ.copy()
            import glob
            nvidia_libs = glob.glob(str(base_dir / ".venv_qwen/lib/python*/site-packages/nvidia/*/lib"))
            ld_parts = [
                "/run/current-system/sw/share/nix-ld/lib",
                "/run/opengl-driver/lib",
                "/run/opengl-driver-32/lib"
            ] + nvidia_libs
            nix_ld = env.get("NIX_LD_LIBRARY_PATH", "")
            if nix_ld:
                ld_parts.insert(0, nix_ld)
            existing_ld = env.get("LD_LIBRARY_PATH", "")
            if existing_ld:
                ld_parts.append(existing_ld)
            env["LD_LIBRARY_PATH"] = ":".join(ld_parts)
            env["CUDA_HOME"] = "/run/opengl-driver"
            env["TRITON_LIBCUDA_PATH"] = "/run/opengl-driver/lib"
            
            self.proc = subprocess.Popen(
                [str(venv_python), str(worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )

            # Wait for ready signal
            ready_line = self.proc.stdout.readline()
            if ready_line:
                data = json.loads(ready_line.strip())
                if data.get("status") == "ready":
                    self.is_ready = True
                    log.info("GPU Worker initialized successfully on RTX 3050 GPU (1 base 1.5B model + interchangeable LoRAs).")
                    return
            
            err = self.proc.stderr.read() if self.proc.stderr else ""
            log.warning(f"GPU Worker failed to signal ready: {err}")
        except Exception as e:
            log.warning(f"Failed to start GPU Worker: {e}", exc_info=True)
            self.is_ready = False

    def call_tool(self, messages: List[Dict[str, Any]], max_tokens: int = 128) -> Optional[str]:
        if not self.is_ready or not self.proc:
            return None
        with self.req_lock:
            try:
                req = {"action": "call_tool", "messages": messages, "max_tokens": max_tokens}
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()

                resp_line = self.proc.stdout.readline()
                if not resp_line:
                    return None
                data = json.loads(resp_line.strip())
                if data.get("status") == "ok":
                    return data.get("content", "")
            except Exception as e:
                log.warning(f"Error communicating with GPU Worker for call_tool: {e}")
        return None

    def generate_persona(self, messages: List[Dict[str, Any]], max_tokens: int = 64, temperature: float = 0.6) -> Optional[str]:
        if not self.is_ready or not self.proc:
            return None
        with self.req_lock:
            try:
                req = {"action": "generate_persona", "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()

                resp_line = self.proc.stdout.readline()
                if not resp_line:
                    return None
                data = json.loads(resp_line.strip())
                if data.get("status") == "ok":
                    return data.get("content", "")
            except Exception as e:
                log.warning(f"Error communicating with GPU Worker for generate_persona: {e}")
        return None

    def stream_persona(self, messages: List[Dict[str, Any]], max_tokens: int = 64, temperature: float = 0.6) -> Generator[str, None, None]:
        if not self.is_ready or not self.proc:
            return
        with self.req_lock:
            try:
                req = {"action": "stream_persona", "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()

                while True:
                    line = self.proc.stdout.readline()
                    if not line:
                        break
                    data = json.loads(line.strip())
                    if data.get("status") == "token":
                        yield data.get("token", "")
                    elif data.get("status") == "done":
                        break
                    elif data.get("status") == "error":
                        break
            except Exception as e:
                log.warning(f"Error communicating with GPU Worker for stream_persona: {e}")
