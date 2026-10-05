"""
Stewart Core Action Framework.
Provides typed command pattern, execution contexts, structured results,
and native tool schema generation for LLM (Ollama/OpenAI) and MCP tool calling.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, Union, get_type_hints, get_origin, get_args
import inspect
import logging

log = logging.getLogger("API: actions")

# Check if Pydantic is available in the current environment
try:
    import pydantic
    _HAS_PYDANTIC = True
except ImportError:
    _HAS_PYDANTIC = False


class _FieldInfo:
    def __init__(self, default=..., default_factory=None, description=""):
        self.default = default
        self.default_factory = default_factory
        self.description = description


def Field(default=..., default_factory=None, description=""):
    """Helper to attach documentation and defaults to schema parameters."""
    return _FieldInfo(default=default, default_factory=default_factory, description=description)


class ActionParameters:
    """
    Typed parameter schema for Stewart Actions.
    Generates standard JSON Schema compatible with Ollama, OpenAI, and MCP tool calling.
    Falls back cleanly to built-in introspection when Pydantic is not installed.
    """
    def __init__(self, **kwargs):
        annotations = getattr(self.__class__, "__annotations__", {})
        cls = self.__class__

        for name, expected_type in annotations.items():
            field_def = getattr(cls, name, None)
            default_val = None
            if isinstance(field_def, _FieldInfo):
                if field_def.default_factory is not None:
                    default_val = field_def.default_factory()
                else:
                    default_val = field_def.default
            elif field_def is not None:
                default_val = field_def

            if name in kwargs:
                val = kwargs[name]
                # Light type casting for common primitive types
                val = self._cast_value(val, expected_type)
                setattr(self, name, val)
            elif default_val is not Ellipsis and default_val is not None:
                setattr(self, name, default_val)
            else:
                setattr(self, name, None)

        # Allow extra parameters passed dynamically
        for k, v in kwargs.items():
            if not hasattr(self, k):
                setattr(self, k, v)

    @classmethod
    def _cast_value(cls, val: Any, expected_type: Any) -> Any:
        if val is None:
            return None
        origin = get_origin(expected_type) or expected_type
        try:
            if origin is bool and isinstance(val, str):
                return val.lower() in ("true", "1", "yes", "on")
            if origin is int and not isinstance(val, int):
                return int(float(val))
            if origin is float and not isinstance(val, float):
                return float(val)
            if origin is list and isinstance(val, str):
                return [val]
            if origin is str and not isinstance(val, str):
                return str(val)
        except Exception:
            return val
        return val

    @classmethod
    def model_json_schema(cls) -> Dict[str, Any]:
        """Generates standard JSON Schema for tool calling."""
        annotations = getattr(cls, "__annotations__", {})
        properties = {}
        required = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }

        for name, typ in annotations.items():
            field_def = getattr(cls, name, None)
            desc = ""
            default = None
            is_required = True

            if isinstance(field_def, _FieldInfo):
                desc = field_def.description
                if field_def.default is not Ellipsis:
                    default = field_def.default
                    is_required = False
            elif field_def is not None:
                default = field_def
                is_required = False

            origin = get_origin(typ)
            args = get_args(typ)

            # Handle Optional[...] / Union[T, None]
            if origin is Union:
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    typ = non_none[0]
                    origin = get_origin(typ)
                    is_required = False

            json_type = type_map.get(origin or typ, "string")
            prop_def: Dict[str, Any] = {"type": json_type}

            if json_type == "array":
                item_type = args[0] if args else str
                prop_def["items"] = {"type": type_map.get(item_type, "string")}

            if desc:
                prop_def["description"] = desc
            if default is not None and default is not Ellipsis:
                prop_def["default"] = default

            properties[name] = prop_def
            if is_required and default is None:
                required.append(name)

        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": True
        }
        if required:
            schema["required"] = required
        return schema

    def model_dump(self) -> Dict[str, Any]:
        return {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_")
        }


@dataclass
class ActionResult:
    """Standardized result returned by any Stewart Action execution."""
    success: bool = True
    data: Optional[Any] = None
    spoken_feedback: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "spoken_feedback": self.spoken_feedback,
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class ExecutionContext:
    """Runtime execution environment passed into Action.execute()."""
    api: Any = None
    desktop: Any = None
    command: Any = None
    context: str = ""
    history: List[Any] = field(default_factory=list)
    logger: Optional[logging.Logger] = None

    def say(self, text: str):
        """Speaks text using Stewart TTS or API."""
        if self.api and hasattr(self.api, "say"):
            self.api.say(text)

    def translate(self, domain: str, key: str, **kwargs) -> str:
        """Translates localized message keys."""
        if self.api and hasattr(self.api, "localeService"):
            return self.api.localeService.translate(domain, key, **kwargs)
        return key


class BaseAction(ABC):
    """
    Abstract Base Class for Stewart Actions / Tools.
    Encapsulates schema, execution logic, tool descriptions, and backward-compatible callable interface.
    """
    name: str = ""
    description: str = ""
    parameters_schema: Type[ActionParameters] = ActionParameters
    category: str = "core"
    sample_phrases: List[str] = []
    requires_context: bool = False
    plugin_name: str = "core"

    def __init__(self, api=None, desktop=None):
        self.api = api
        self.desktop = desktop
        if not self.description:
            doc = (inspect.getdoc(self.__class__) or inspect.getdoc(self.execute) or f"Execute action '{self.name}'")
            self.description = doc.strip().split("\n")[0]

    @abstractmethod
    def execute(self, params: Any, ctx: ExecutionContext) -> ActionResult:
        """Executes the action with validated parameters and execution context."""
        pass

    def to_ollama_tool(self) -> Dict[str, Any]:
        """Returns standard OpenAI / Ollama / MCP function calling schema."""
        if hasattr(self.parameters_schema, "model_json_schema"):
            schema = self.parameters_schema.model_json_schema()
        else:
            schema = {"type": "object", "properties": {}, "additionalProperties": True}

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        }

    def __call__(self, command=None, context: str = "", history: Optional[List] = None, **kwargs) -> Any:
        """
        Callable interface allowing BaseAction instances to be dispatched directly
        by App.do(), ActionTool.invoke(), or action executor threads.
        """
        # Resolve DesktopService
        desktop = self.desktop
        if desktop is None:
            if self.api and hasattr(self.api, "desktop"):
                desktop = self.api.desktop
            else:
                from api.services.desktop import get_desktop_service
                desktop = get_desktop_service(api=self.api)

        # Merge parameters
        param_dict: Dict[str, Any] = {}
        if command and hasattr(command, "parameters") and isinstance(command.parameters, dict):
            param_dict.update(command.parameters)
        param_dict.update(kwargs)

        # Pass context if parameter schema specifies context or requires_context is set
        if context and "context" not in param_dict:
            schema_props = getattr(self.parameters_schema, "__annotations__", {})
            if "context" in schema_props or self.requires_context:
                param_dict["context"] = context

        # Instantiate parameter object
        try:
            params = self.parameters_schema(**param_dict)
        except Exception as e:
            log.warning(f"Parameter validation failed for action '{self.name}': {e}. Using raw parameters.")
            params = param_dict

        ctx = ExecutionContext(
            api=self.api,
            desktop=desktop,
            command=command,
            context=context,
            history=history or [],
            logger=log
        )

        try:
            result = self.execute(params, ctx)
            if not isinstance(result, ActionResult):
                # Normalize legacy return types
                result = ActionResult(success=True, data=result)

            # Trigger spoken feedback if produced by action
            if result.spoken_feedback:
                ctx.say(result.spoken_feedback)

            return result
        except Exception as e:
            log.error(f"Error executing action '{self.name}': {e}", exc_info=True)
            return ActionResult(success=False, error=str(e))

    def __repr__(self):
        return f"<{self.__class__.__name__} name='{self.name}'>"
