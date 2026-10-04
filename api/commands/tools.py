import inspect
import logging
from typing import Dict, Any, List, Optional, Callable

log = logging.getLogger("API: tools")


class ActionTool:
    """
    Represents an action from Stewart plugins or core modules exposed as a callable tool.
    Compatible with MCP / Ollama / OpenAI tool definitions.
    """
    def __init__(self,
                 name: str,
                 func: Callable,
                 description: str = "",
                 parameters_schema: Optional[Dict[str, Any]] = None,
                 default_params: Optional[Dict[str, Any]] = None,
                 requires_context: bool = False,
                 sample_phrases: Optional[List[str]] = None,
                 plugin_name: str = "core"):
        self.name = name
        self.func = func
        self.description = description or (inspect.getdoc(func) or f"Execute action '{name}'").strip().split("\n")[0]
        self.parameters_schema = parameters_schema or {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Additional text or argument context for the action"
                }
            },
            "additionalProperties": True
        }
        self.default_params = default_params or {}
        self.requires_context = requires_context
        self.sample_phrases = sample_phrases or []
        self.plugin_name = plugin_name

    def to_ollama_tool(self) -> Dict[str, Any]:
        """Returns standard OpenAI / Ollama function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema
            }
        }

    def invoke(self, command=None, context: str = "", history: Optional[List] = None, **kwargs) -> Any:
        """Invokes the action function with the standard Stewart signature."""
        if command is None:
            # Create a lightweight stub Command for direct tool invocations
            from .tree import Command
            command = Command(
                keywords=[self.name],
                action=self.name,
                parameters={**self.default_params, **kwargs}
            )
        try:
            return self.func(command=command, context=context, history=history or [])
        except Exception as e:
            log.error(f"Error invoking tool '{self.name}': {e}", exc_info=True)
            return None

    def __repr__(self):
        return f"<ActionTool name={self.name} plugin={self.plugin_name}>"


class ToolRegistry:
    """
    Maintains all registered tools across plugins and built-in actions.
    Provides discovery, schema export, and tool execution.
    """
    def __init__(self, api=None):
        self.api = api
        self._tools: Dict[str, ActionTool] = {}
        self._tool_by_sample: Dict[str, str] = {}

    def register(self, tool: ActionTool):
        self._tools[tool.name] = tool
        for phrase in tool.sample_phrases:
            self._tool_by_sample[phrase.lower().strip()] = tool.name
        log.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[ActionTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[ActionTool]:
        return list(self._tools.values())

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        return [tool.to_ollama_tool() for tool in self._tools.values()]

    def sync_from_app(self, api):
        """
        Inspects api.__actions__ and configured commands to discover and enrich all available tools.
        """
        self.api = api
        actions = getattr(api, "__actions__", {})
        config_commands = []
        if hasattr(api, "config") and isinstance(api.config, dict):
            cmds_section = api.config.get("commands", {})
            if isinstance(cmds_section, dict):
                config_commands = cmds_section.get("default", []) + cmds_section.get("repeat", [])

        # Map action -> samples, parameters, and continues flag
        action_metadata: Dict[str, Dict[str, Any]] = {}
        for cmd_entry in config_commands:
            action_name = cmd_entry.get("action")
            if not action_name:
                continue
            meta = action_metadata.setdefault(action_name, {
                "samples": [],
                "parameters": {},
                "continues": False,
                "synonyms": {}
            })
            cmd_kw = cmd_entry.get("command") or []
            if isinstance(cmd_kw, list):
                meta["samples"].append(" ".join(str(w) for w in cmd_kw))
            for eq in cmd_entry.get("equivalents") or []:
                if isinstance(eq, list):
                    meta["samples"].append(" ".join(str(w) for w in eq))
            if cmd_entry.get("parameters"):
                meta["parameters"].update(cmd_entry.get("parameters"))
            if cmd_entry.get("continues"):
                meta["continues"] = True

        for name, func in actions.items():
            if name.startswith("_"):
                continue  # skip internal functions
            meta = action_metadata.get(name, {})
            doc = (inspect.getdoc(func) or "").strip().split("\n")[0]
            if not doc:
                doc = f"Executes system action '{name}'"

            # Auto-infer parameter schema
            props = {}
            if meta.get("parameters"):
                for k, v in meta["parameters"].items():
                    props[k] = {"type": "string" if isinstance(v, str) else type(v).__name__, "default": v}
            props["context"] = {"type": "string", "description": "Context or arguments for this action"}

            schema = {
                "type": "object",
                "properties": props,
                "additionalProperties": True
            }

            tool = ActionTool(
                name=name,
                func=func,
                description=doc,
                parameters_schema=schema,
                default_params=meta.get("parameters", {}),
                requires_context=meta.get("continues", False),
                sample_phrases=meta.get("samples", []),
                plugin_name=getattr(func, "__module__", "unknown")
            )
            self.register(tool)

        log.info(f"Synchronized {len(self._tools)} tools into ToolRegistry from actions.")

    def execute(self, tool_name: str, parameters: Optional[Dict[str, Any]] = None, context: str = "", history: Optional[List] = None) -> Any:
        tool = self.get(tool_name)
        if not tool:
            log.warning(f"Tool '{tool_name}' not found in registry")
            return None
        return tool.invoke(context=context, history=history, **(parameters or {}))
