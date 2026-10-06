import os
import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

log = logging.getLogger("API: dynamic_tools")

BASE_DYNAMIC_TOOLS_FILE = Path(__file__).resolve().parent.parent.parent / "data/dynamic_tools.json"
USER_DYNAMIC_TOOLS_FILE = Path(os.environ.get("STEWART_CONFIG_DIR") or (Path.home() / ".config/stewart")) / "dynamic_tools.json"
DEFAULT_DYNAMIC_TOOLS_FILE = USER_DYNAMIC_TOOLS_FILE


class DynamicTool:
    """
    Represents a dynamically synthesized tool created on the fly.
    Executes a shell command template or Python logic with sanitized argument substitution.
    """
    def __init__(self,
                 name: str,
                 description: str,
                 command_template: str,
                 parameters_schema: Optional[Dict[str, Any]] = None,
                 sample_phrases: Optional[List[str]] = None,
                 created_at: Optional[str] = None):
        self.name = name
        self.description = description
        self.command_template = command_template
        self.parameters_schema = parameters_schema or {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Command context or arguments"}
            }
        }
        self.sample_phrases = sample_phrases or []
        self.created_at = created_at

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Executes the command template with supplied arguments.
        """
        # Interpolate variables safely into template
        cmd_str = self.command_template
        for k, v in kwargs.items():
            placeholder = "{" + k + "}"
            if placeholder in cmd_str:
                cmd_str = cmd_str.replace(placeholder, str(v))

        log.info(f"Executing dynamic tool '{self.name}': {cmd_str}")
        try:
            res = subprocess.run(
                cmd_str,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15.0
            )
            out = res.stdout.strip()
            err = res.stderr.strip()
            success = res.returncode == 0
            return {
                "success": success,
                "returncode": res.returncode,
                "stdout": out,
                "stderr": err,
                "message": out if success else (err or f"Exited with code {res.returncode}")
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out after 15 seconds"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "command_template": self.command_template,
            "parameters_schema": self.parameters_schema,
            "sample_phrases": self.sample_phrases,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DynamicTool":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            command_template=data.get("command_template", ""),
            parameters_schema=data.get("parameters_schema"),
            sample_phrases=data.get("sample_phrases", []),
            created_at=data.get("created_at")
        )


class DynamicToolManager:
    """
    Manages persistent dynamic tools that are synthesized on the fly by AGY mode or users.
    """
    def __init__(self, storage_file: Optional[Path] = None):
        self.storage_file = storage_file or DEFAULT_DYNAMIC_TOOLS_FILE
        self._tools: Dict[str, DynamicTool] = {}
        self.load()

    def load(self):
        """Loads registered dynamic tools from disk, merging base defaults and user tools."""
        files_to_load = []
        if BASE_DYNAMIC_TOOLS_FILE.exists() and BASE_DYNAMIC_TOOLS_FILE != self.storage_file:
            files_to_load.append(BASE_DYNAMIC_TOOLS_FILE)
        if self.storage_file.exists():
            files_to_load.append(self.storage_file)

        for sfile in files_to_load:
            try:
                with open(sfile, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    tools_list = data.get("tools", []) if isinstance(data, dict) else data
                    for item in tools_list:
                        if isinstance(item, dict) and "name" in item:
                            tool = DynamicTool.from_dict(item)
                            self._tools[tool.name] = tool
                log.info(f"Loaded dynamic tools from {sfile} (total registered: {len(self._tools)})")
            except Exception as e:
                log.warning(f"Error loading dynamic tools from {sfile}: {e}")

    def save(self):
        """Persists registered dynamic tools to disk."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"tools": [tool.to_dict() for tool in self._tools.values()]}
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.info(f"Saved {len(self._tools)} dynamic tools to {self.storage_file}")
        except Exception as e:
            log.error(f"Error saving dynamic tools to {self.storage_file}: {e}")

    def register(self,
                 name: str,
                 description: str,
                 command_template: str,
                 parameters_schema: Optional[Dict[str, Any]] = None,
                 sample_phrases: Optional[List[str]] = None) -> DynamicTool:
        """Registers a new dynamic tool and persists it."""
        import datetime
        tool = DynamicTool(
            name=name,
            description=description,
            command_template=command_template,
            parameters_schema=parameters_schema,
            sample_phrases=sample_phrases or [],
            created_at=datetime.datetime.now().isoformat()
        )
        self._tools[name] = tool
        self.save()
        log.info(f"Dynamically registered tool '{name}' ({description})")
        return tool

    def get(self, name: str) -> Optional[DynamicTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[DynamicTool]:
        return list(self._tools.values())


# Global singleton instance
_dynamic_tool_manager: Optional[DynamicToolManager] = None


def get_dynamic_tool_manager() -> DynamicToolManager:
    global _dynamic_tool_manager
    if _dynamic_tool_manager is None:
        _dynamic_tool_manager = DynamicToolManager()
    return _dynamic_tool_manager


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stewart Dynamic Tool Manager CLI")
    subparsers = parser.add_subparsers(dest="subcommand")

    reg_p = subparsers.add_parser("register", help="Register a new dynamic tool")
    reg_p.add_argument("--name", required=True, help="Tool identifier (e.g. rename_file)")
    reg_p.add_argument("--desc", required=True, help="Tool description")
    reg_p.add_argument("--cmd", required=True, help="Shell command template with {args}")
    reg_p.add_argument("--params", help="JSON string of parameter schema", default="{}")
    reg_p.add_argument("--samples", help="Comma-separated sample activation phrases", default="")

    list_p = subparsers.add_parser("list", help="List registered dynamic tools")

    args = parser.parse_args()
    mgr = get_dynamic_tool_manager()

    if args.subcommand == "register":
        try:
            params_dict = json.loads(args.params) if args.params else {}
        except Exception:
            params_dict = {}
        samples_list = [s.strip() for s in args.samples.split(",") if s.strip()]
        tool = mgr.register(
            name=args.name,
            description=args.desc,
            command_template=args.cmd,
            parameters_schema=params_dict,
            sample_phrases=samples_list
        )
        print(f"Tool '{tool.name}' successfully registered and saved.")
    elif args.subcommand == "list":
        tools = mgr.list_tools()
        print(f"Registered Dynamic Tools ({len(tools)}):")
        for t in tools:
            print(f"- {t.name}: {t.description} -> `{t.command_template}`")
    else:
        parser.print_help()

