import json
import logging
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger("API: ollama")

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None


class OllamaToolCaller:
    """
    Client for local Ollama / OpenAI-compatible models that dispatches user queries
    into tool calls with JSON schemas.
    """
    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "llama3.2:1b", timeout: float = 3.0):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._is_available: Optional[bool] = None

    def check_availability(self) -> bool:
        """Quickly ping Ollama /api/tags to see if the server is active."""
        try:
            req = urllib.request.Request(f"{self.endpoint}/api/tags", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    self._is_available = True
                    return True
        except Exception:
            pass
        self._is_available = False
        return False

    def call_tool(self, request: str, tool_schemas: List[Dict[str, Any]]) -> Optional[Tuple[str, Dict[str, Any], str]]:
        """
        Sends the user request and available tool schemas to Ollama.
        Returns (tool_name, arguments, context) if a tool was chosen, else None.
        """
        if self._is_available is False:
            return None

        url = f"{self.endpoint}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Stewart's tool execution dispatcher. You have access to system tools. "
                        "When the user speaks a command, choose and call the single best tool with appropriate arguments. "
                        "Do not explain yourself, call the tool directly."
                    )
                },
                {"role": "user", "content": request}
            ],
            "tools": tool_schemas,
            "stream": False
        }

        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            msg = data.get("message", {})
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                call = tool_calls[0]
                fn = call.get("function", {})
                tool_name = fn.get("name")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"context": args}
                context = args.get("context", "")
                return tool_name, args, context

        except (urllib.error.URLError, TimeoutError) as e:
            log.debug(f"Ollama server not reachable or timed out: {e}")
            self._is_available = False
        except Exception as e:
            log.warning(f"Error communicating with Ollama: {e}")

        return None
