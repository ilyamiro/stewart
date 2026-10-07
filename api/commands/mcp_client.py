import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

log = logging.getLogger("API: mcp")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_MCP_SERVERS = {
    "life": {
        "command": str(PROJECT_ROOT / "bin/life-mcp"),
        "args": []
    },
    "studieplus": {
        "command": str(PROJECT_ROOT / "bin/studieplus-mcp"),
        "args": []
    },
    "gmail": {
        "command": str(PROJECT_ROOT / "bin/gmail-mcp"),
        "args": []
    },
    "telegram": {
        "command": str(PROJECT_ROOT / "bin/telegram-mcp"),
        "args": []
    },
    "calendar": {
        "command": str(PROJECT_ROOT / "bin/calendar-mcp"),
        "args": []
    },
    "drive": {
        "command": str(PROJECT_ROOT / "bin/drive-mcp"),
        "args": []
    },
    "github": {
        "command": str(PROJECT_ROOT / "bin/github-mcp"),
        "args": []
    },
    "maps": {
        "command": str(PROJECT_ROOT / "bin/maps-mcp"),
        "args": []
    },
    "youtube": {
        "command": str(PROJECT_ROOT / "bin/youtube-mcp"),
        "args": []
    },
    "memory": {
        "command": str(PROJECT_ROOT / "bin/memory-mcp"),
        "args": []
    },
    "streaming": {
        "command": str(PROJECT_ROOT / "bin/streaming-mcp"),
        "args": []
    }
}


def _load_known_mcp_tools() -> Dict[str, List[Dict[str, Any]]]:
    json_path = PROJECT_ROOT / "data/known_mcp_tools.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Failed to read {json_path}: {e}")
    return {}


KNOWN_MCP_TOOLS = _load_known_mcp_tools()


class MCPServerProcess:
    def __init__(self, name: str, command: str, args: Optional[List[str]] = None, cwd: Optional[str] = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.cwd = cwd or str(Path(command).resolve().parent.parent) if os.path.exists(command) else None
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._req_id = 0

    def _ensure_process(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True

        if not os.path.exists(self.command):
            log.warning(f"MCP server '{self.name}' command not found: {self.command}")
            return False

        try:
            full_cmd = [self.command] + self.args
            log.info(f"Starting MCP server '{self.name}': {full_cmd}")
            self._proc = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=self.cwd
            )
            init_req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {}
            }
            res = self._send_raw(init_req, timeout=10.0)
            if res is not None:
                log.info(f"MCP server '{self.name}' initialized successfully.")
                return True
            else:
                log.warning(f"MCP server '{self.name}' failed to respond to initialize.")
                self.close()
                return False
        except Exception as e:
            log.error(f"Error launching MCP server '{self.name}': {e}", exc_info=True)
            self._proc = None
            return False

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send_raw(self, request: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                return None
            try:
                req_line = json.dumps(request) + "\n"
                self._proc.stdin.write(req_line)
                self._proc.stdin.flush()

                while True:
                    line = self._proc.stdout.readline()
                    if not line:
                        log.warning(f"MCP server '{self.name}' closed stdout stream unexpectedly.")
                        return None
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        resp = json.loads(line)
                        if isinstance(resp, dict) and (resp.get("id") == request.get("id") or "result" in resp or "error" in resp):
                            return resp
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                log.error(f"Error communicating with MCP server '{self.name}': {e}")
                return None

    def list_tools(self, timeout: float = 10.0) -> List[Dict[str, Any]]:
        if not self._ensure_process():
            return []
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }
        resp = self._send_raw(req, timeout=timeout)
        if resp and "result" in resp:
            return resp["result"].get("tools", [])
        return []

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        if not self._ensure_process():
            return {"error": f"MCP server '{self.name}' is not running"}

        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {}
            }
        }
        resp = self._send_raw(req, timeout=timeout)
        if not resp:
            return {"error": f"No response from MCP server '{self.name}' for tool '{tool_name}'"}

        if "error" in resp:
            log.warning(f"MCP tool '{tool_name}' returned error: {resp['error']}")
            return {"error": resp["error"]}

        result = resp.get("result", {})
        content = result.get("content", [])
        if isinstance(content, list) and content:
            text_blocks = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
            if text_blocks:
                full_text = "\n".join(text_blocks)
                try:
                    return json.loads(full_text)
                except Exception:
                    return full_text
        return result

    def close(self):
        with self._lock:
            if self._proc:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.close()
                    if self._proc.stdout:
                        self._proc.stdout.close()
                    if self._proc.stderr:
                        self._proc.stderr.close()
                    self._proc.terminate()
                    self._proc.wait(timeout=2.0)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None


class MCPManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._servers: Dict[str, MCPServerProcess] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._tool_cache: Dict[str, Dict[str, Any]] = {}
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return

        mcp_cfg = self.config.get("mcp", {})
        enabled = mcp_cfg.get("enabled", True)
        if not enabled:
            log.info("MCP integration is disabled in config.")
            return

        servers_cfg = mcp_cfg.get("servers", {}) or DEFAULT_MCP_SERVERS
        for s_name, s_info in servers_cfg.items():
            cmd = s_info.get("command")
            args = s_info.get("args", [])
            cwd = s_info.get("cwd")
            if cmd:
                self._servers[s_name] = MCPServerProcess(s_name, cmd, args, cwd)

        log.info(f"MCPManager configured with {len(self._servers)} server(s): {list(self._servers.keys())}")
        self._initialized = True

    def _async_refresh_tools(self):
        for s_name, s_proc in self._servers.items():
            try:
                live_tools = s_proc.list_tools(timeout=5.0)
                for tool in live_tools:
                    t_name = tool.get("name")
                    if t_name:
                        self._tool_to_server[t_name] = s_name
                        self._tool_cache[t_name] = tool
            except Exception as e:
                log.debug(f"Dynamic tool discovery skipped for '{s_name}': {e}")

    def discover_tools(self, background_sync: bool = True) -> List[Dict[str, Any]]:
        self.initialize()

        for s_name, tools in KNOWN_MCP_TOOLS.items():
            if s_name in self._servers or not self._servers:
                for tool in tools:
                    t_name = tool.get("name")
                    if t_name:
                        self._tool_to_server[t_name] = s_name
                        self._tool_cache[t_name] = tool

        if background_sync and not getattr(self, "_refresh_started", False):
            self._refresh_started = True
            threading.Thread(target=self._async_refresh_tools, daemon=True, name="MCP-ToolRefresh").start()
        elif not background_sync:
            self._async_refresh_tools()

        return list(self._tool_cache.values())

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        s_name = self._tool_to_server.get(tool_name)
        if not s_name:
            self.discover_tools(background_sync=False)
            s_name = self._tool_to_server.get(tool_name)

        if not s_name or s_name not in self._servers:
            log.warning(f"No MCP server found for tool '{tool_name}'")
            return {"error": f"Tool '{tool_name}' is not registered with any MCP server"}

        server = self._servers[s_name]
        return server.call_tool(tool_name, arguments)

    def close(self):
        for s in self._servers.values():
            s.close()
