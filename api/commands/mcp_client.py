import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger("API: mcp")

DEFAULT_MCP_SERVERS = {
    "studieplus": {
        "command": "/home/ilyamiro/Projects/life/bin/studieplus-mcp",
        "args": []
    },
    "gmail": {
        "command": "/home/ilyamiro/Projects/life/bin/gmail-mcp",
        "args": []
    }
}

KNOWN_MCP_TOOLS = {
    "studieplus": [
        {
            "name": "studieplus_get_schedule",
            "description": "Fetch Studie+ timetable / lessons for a specific day or week. Returns date, time, subject, teacher, room, class group, and lesson homework notes.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Target date: 'today', 'tomorrow', or 'YYYY-MM-DD' (e.g. '2026-10-06')",
                        "default": "today"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["day", "week"],
                        "default": "day",
                        "description": "Whether to return the specific day schedule or the full week"
                    }
                }
            }
        },
        {
            "name": "studieplus_get_assignments",
            "description": "Query Studie+ assignments database. Supports filtering by due date, date range, days ahead, subject, and status (open, graded, submitted, all).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "graded", "submitted", "all"],
                        "default": "open",
                        "description": "Filter by assignment status: 'open', 'graded', 'submitted', or 'all'"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Exact due date: 'today', 'tomorrow', or 'YYYY-MM-DD'"
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Find assignments due within next N days"
                    },
                    "from_date": {"type": "string", "description": "Filter assignments due on or after date"},
                    "to_date": {"type": "string", "description": "Filter assignments due on or before date"},
                    "subject": {"type": "string", "description": "Filter by subject (e.g. 'Maths', 'TOK')"},
                    "with_details": {"type": "boolean", "default": False, "description": "Fetch full descriptions and files"}
                }
            }
        },
        {
            "name": "studieplus_get_conversations",
            "description": "Fetch conversations and announcements from Studie+ where the student participates.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10, "description": "Number of recent conversations to retrieve"},
                    "with_content": {"type": "boolean", "default": True, "description": "Fetch full message body and replies"},
                    "view_all": {"type": "boolean", "default": False, "description": "Retrieve all conversations instead of just last 14 days"}
                }
            }
        },
        {
            "name": "studieplus_check_session",
            "description": "Check if the Studie+ Firefox profile has an active authenticated session.",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "study_get_ib_resources",
            "description": "Search, download, and open IB past papers and markschemes (e.g. Maths AA HL, Physics HL, Economics, History) from official IB mirrors with automatic PDF launch.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject name or slug", "default": "math aa"},
                    "level": {"type": "string", "enum": ["HL", "SL", "both"], "default": "HL"},
                    "paper_num": {"type": "integer", "description": "Paper number (1, 2, or 3)"},
                    "year": {"type": "string", "description": "Exam year (e.g. '2025', '2024')"},
                    "session": {"type": "string", "description": "Exam session: 'May' or 'November'"},
                    "component": {"type": "string", "enum": ["paper", "markscheme", "all"], "default": "paper"},
                    "query": {"type": "string", "description": "Free text query within paper titles"},
                    "download": {"type": "boolean", "default": True},
                    "open_after_download": {"type": "boolean", "default": True}
                }
            }
        },
        {
            "name": "study_prepare_test",
            "description": "Prepare for an upcoming IB test (e.g. Maths AA HL). Reads past class history and homework to extract covered syllabus topics, downloading and opening practice papers.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "default": "Maths AA HL"},
                    "test_date": {"type": "string", "description": "Target test date (e.g. '2026-10-27')", "default": "2026-10-27"},
                    "from_date": {"type": "string", "default": "2026-08-10"},
                    "auto_download_papers": {"type": "boolean", "default": True},
                    "open_after_download": {"type": "boolean", "default": True}
                }
            }
        },
        {
            "name": "study_get_past_topics",
            "description": "Retrieve all topics, lessons, and homework covered so far this year for a given subject from the schedule cache.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "default": "Maths AA HL"},
                    "from_date": {"type": "string", "default": "2026-08-10"},
                    "to_date": {"type": "string", "description": "End date for analysis"}
                }
            }
        }
    ],
    "gmail": [
        {
            "name": "gmail_check_status",
            "description": "Check authentication status and total inbox message count for ilyamiro.work@gmail.com.",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "gmail_search_emails",
            "description": "Search emails in Gmail inbox. Supports filtering by query keywords, sender, subject, unread status, and limit.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or text within email bodies/subjects"},
                    "sender": {"type": "string", "description": "Filter by sender email or name"},
                    "subject": {"type": "string", "description": "Filter by subject keyword"},
                    "unread_only": {"type": "boolean", "default": False, "description": "If true, only return unread emails"},
                    "limit": {"type": "integer", "default": 10, "description": "Maximum number of emails to return"}
                }
            }
        },
        {
            "name": "gmail_get_email",
            "description": "Retrieve full body text, headers, and attachment details for a specific email by its ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "email_id": {"type": "string", "description": "The unique email message ID from search results"}
                },
                "required": ["email_id"]
            }
        },
        {
            "name": "gmail_send_email",
            "description": "Send an email from ilyamiro.work@gmail.com.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body content"},
                    "cc": {"type": "string", "description": "Optional CC recipient"}
                },
                "required": ["to", "subject", "body"]
            }
        }
    ]
}



class MCPServerProcess:
    """
    Manages a single MCP server running over JSON-RPC 2.0 via stdio.
    """
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
            # Initialize connection
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

                # Read response line with timeout
                # For stdio JSON-RPC, the server writes one JSON object per line on stdout
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
                        # Skip banner / log messages printed to stdout if any
                        continue
            except Exception as e:
                log.error(f"Error communicating with MCP server '{self.name}': {e}")
                return None

    def list_tools(self, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """Queries 'tools/list' from server."""
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
        """Executes 'tools/call' on server."""
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
    """
    Central coordinator for external MCP servers in Stewart.
    Discovers, connects to, and dispatches tool calls to MCP servers.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._servers: Dict[str, MCPServerProcess] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._tool_cache: Dict[str, Dict[str, Any]] = {}
        self._initialized = False

    def initialize(self):
        """Initializes configured MCP servers."""
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

    def discover_tools(self) -> List[Dict[str, Any]]:
        """
        Discovers all tools across all configured MCP servers.
        Preloads known tool schemas and attempts dynamic discovery.
        Returns list of MCP tool schema objects.
        """
        self.initialize()
        
        # 1. Preload known tools for zero-latency startup
        for s_name, tools in KNOWN_MCP_TOOLS.items():
            if s_name in self._servers or not self._servers:
                for tool in tools:
                    t_name = tool.get("name")
                    if t_name:
                        self._tool_to_server[t_name] = s_name
                        self._tool_cache[t_name] = tool

        # 2. Query running / configured servers for any dynamic updates
        for s_name, s_proc in self._servers.items():
            try:
                live_tools = s_proc.list_tools(timeout=3.0)
                for tool in live_tools:
                    t_name = tool.get("name")
                    if t_name:
                        self._tool_to_server[t_name] = s_name
                        self._tool_cache[t_name] = tool
            except Exception as e:
                log.debug(f"Dynamic tool discovery skipped for '{s_name}' (using cached schema): {e}")

        return list(self._tool_cache.values())


    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """
        Calls an MCP tool by name with arguments.
        """
        s_name = self._tool_to_server.get(tool_name)
        if not s_name:
            # Check if any server owns this tool
            self.discover_tools()
            s_name = self._tool_to_server.get(tool_name)

        if not s_name or s_name not in self._servers:
            log.warning(f"No MCP server found for tool '{tool_name}'")
            return {"error": f"Tool '{tool_name}' is not registered with any MCP server"}

        server = self._servers[s_name]
        return server.call_tool(tool_name, arguments)

    def close(self):
        for s in self._servers.values():
            s.close()
