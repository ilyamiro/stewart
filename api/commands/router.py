import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from .tree import Command, Manager
from .tools import ToolRegistry, ActionTool
from .classifier import SpacyActionClassifier
from .ollama import OllamaToolCaller
from .qwen_caller import QwenToolCaller
from .persona_caller import QwenPersonaCaller

log = logging.getLogger("API: router")


class CommandRouter:
    """
    Unified Command & Tool Router.
    Dispatches user input between algorithmic tree matching, fine-grained command intent
    classification via SpaCy, and local Ollama/Qwen tool calling with dynamic Persona voice responses.
    """
    def __init__(self, manager: Manager, tool_registry: Optional[ToolRegistry] = None, config: Optional[Dict[str, Any]] = None):
        self.manager = manager
        self.tool_registry = tool_registry or ToolRegistry()
        self.config = config or {}

        # Read router config
        router_cfg = self.config.get("router", {})
        self.mode = router_cfg.get("mode", "hybrid").lower()
        self.confidence_threshold = float(router_cfg.get("confidence_threshold", 0.45))

        # Model settings
        model_cfg = router_cfg.get("model", {})
        self.provider = model_cfg.get("provider", "spacy").lower()
        default_model_dir = Path(__file__).resolve().parent.parent.parent / "data/models/action_classifier"
        model_path_str = model_cfg.get("model_path", str(default_model_dir))
        self.model_path = Path(model_path_str)
        self.auto_train = model_cfg.get("auto_train", True)
        self.fallback_to_algorithmic = model_cfg.get("fallback_to_algorithmic", True)

        # Ollama settings
        ollama_cfg = router_cfg.get("ollama", {})
        self.ollama_caller = OllamaToolCaller(
            endpoint=ollama_cfg.get("endpoint", "http://localhost:11434"),
            model=ollama_cfg.get("model", "llama3.2:1b"),
            timeout=float(ollama_cfg.get("timeout", 3.0))
        )

        # Qwen Local Tool Caller settings
        qwen_cfg = router_cfg.get("qwen", {})
        default_qwen_dir = Path(__file__).resolve().parent.parent.parent / "data/models/qwen2.5-0.5b-stewart"
        qwen_path_str = qwen_cfg.get("model_path", str(default_qwen_dir))
        self.qwen_caller = QwenToolCaller(model_path=qwen_path_str)

        # Persona Voice Model settings
        persona_cfg = self.config.get("persona", {}) or router_cfg.get("persona", {})
        self.persona_enabled = persona_cfg.get("enabled", True)
        default_persona_dir = Path(__file__).resolve().parent.parent.parent / "data/models/qwen2.5-0.5b-persona-lora"
        persona_path_str = persona_cfg.get("model_path", str(default_persona_dir))
        self.persona_caller = QwenPersonaCaller(
            model_path=persona_path_str,
            max_new_tokens=int(persona_cfg.get("max_new_tokens", 64)),
            temperature=float(persona_cfg.get("temperature", 0.6)),
            shared_caller=self.qwen_caller
        )

        # SpaCy Classifier
        lang = self.config.get("lang", {}).get("prefix", "en") if isinstance(self.config.get("lang"), dict) else "en"
        self.classifier = SpacyActionClassifier(model_path=str(self.model_path), lang=lang)

        self._route_cache: Dict[str, List] = {}
        self._cmd_id_to_command: Dict[str, Command] = {}
        self._action_to_command: Dict[str, Command] = {}

    def initialize(self):
        """
        Initializes tools, maps command intents, and loads or trains the SpaCy model.
        """
        # Map specific command intents (action + keywords) and action fallbacks
        for cmd in self.manager.commands:
            kw_str = "-".join(str(w) for w in cmd.keywords)
            cmd_id = f"{cmd.action}::{kw_str}" if kw_str else cmd.action
            if cmd_id not in self._cmd_id_to_command:
                self._cmd_id_to_command[cmd_id] = cmd
            if cmd.action not in self._action_to_command:
                self._action_to_command[cmd.action] = cmd

        if self.mode in ("model", "hybrid") and self.provider == "spacy":
            loaded = self.classifier.load_model(self.model_path)
            if not loaded and self.auto_train:
                log.info("SpaCy action classifier not found on disk; auto-training now...")
                all_cmds = []
                if "commands" in self.config and isinstance(self.config["commands"], dict):
                    all_cmds.extend(self.config["commands"].get("default", []))
                    all_cmds.extend(self.config["commands"].get("repeat", []))
                if all_cmds:
                    success = self.classifier.train(all_cmds, save_path=self.model_path)
                    if success:
                        log.info("Auto-training completed and model ready.")
                    else:
                        log.warning("Auto-training did not succeed.")

        log.info(f"CommandRouter initialized with mode='{self.mode}', provider='{self.provider}'")

    def _find_or_create_command(self, cmd_id: str, action: str, parameters: Dict[str, Any], context: str) -> Command:
        """Locates the exact Command matching cmd_id, or falls back to action template."""
        # 1. Exact command intent match
        target_cmd = self._cmd_id_to_command.get(cmd_id)
        if target_cmd:
            cmd = target_cmd.copy(target_cmd.keywords)
            merged_params = dict(target_cmd.parameters)
            merged_params.update(parameters)
            cmd.parameters = merged_params
            return cmd

        # 2. Action fallback template
        template = self._action_to_command.get(action)
        if template:
            cmd = template.copy(template.keywords)
            cmd.action = action
            merged_params = dict(template.parameters)
            merged_params.update(parameters)
            cmd.parameters = merged_params
            return cmd

        # 3. Create dynamically from registered tool
        tool = self.tool_registry.get(action)
        merged_params = dict(tool.default_params) if tool else {}
        merged_params.update(parameters)
        return Command(
            keywords=[action],
            action=action,
            parameters=merged_params,
            responses=[],
            synonyms={},
            tts=False
        )

    def route(self, request: str) -> List[List[Any]]:
        """
        Main routing function for user requests.
        Returns a list of [Command, context_str] identical to Manager.find format.
        """
        if not request or not request.strip():
            return []

        clean_request = request.strip()
        cached = self._route_cache.get(clean_request)
        if cached is not None:
            return [[c[0], c[1]] for c in cached]

        results = []

        if self.mode == "algorithmic":
            results = self.manager.find_algorithmic(clean_request)

        elif self.mode == "ollama":
            schemas = self.tool_registry.get_all_tool_schemas()
            call = self.ollama_caller.call_tool(clean_request, schemas)
            if call:
                action, args, ctx = call
                cmd = self._find_or_create_command(action, action, args, ctx)
                results = [[cmd, ctx]]
            elif self.fallback_to_algorithmic:
                results = self.manager.find_algorithmic(clean_request)

        elif self.mode in ("qwen", "local_llm"):
            schemas = self.tool_registry.get_all_tool_schemas()
            call = self.qwen_caller.call_tool(clean_request, schemas)
            if call:
                action, args, ctx = call
                cmd = self._find_or_create_command(action, action, args, ctx)
                results = [[cmd, ctx]]
            elif self.fallback_to_algorithmic:
                results = self.manager.find_algorithmic(clean_request)

        elif self.mode == "model":
            # Direct model selection first
            results = self._route_via_model(clean_request)
            if not results and self.fallback_to_algorithmic:
                results = self.manager.find_algorithmic(clean_request)

        else:
            # "hybrid" mode (Default):
            # 1. Fast algorithmic tree check (<0.1ms)
            algo_results = self.manager.find_algorithmic(clean_request)
            if algo_results:
                results = algo_results
            else:
                # 2. Fall back to smart model tool selection (SpaCy or Qwen)
                results = self._route_via_model(clean_request)

        if len(self._route_cache) < 1000:
            self._route_cache[clean_request] = [[c[0], c[1]] for c in results]

        return results

    def _route_via_model(self, request: str) -> List[List[Any]]:
        """Invokes Qwen, Ollama, or SpaCy model depending on configured provider."""
        if self.provider in ("qwen", "local_llm"):
            schemas = self.tool_registry.get_all_tool_schemas()
            call = self.qwen_caller.call_tool(request, schemas)
            if call:
                action, args, ctx = call
                cmd = self._find_or_create_command(action, action, args, ctx)
                log.info(f"Qwen routed request '{request}' -> tool '{action}' (args={args})")
                return [[cmd, ctx]]
            return []

        if self.provider == "ollama":
            schemas = self.tool_registry.get_all_tool_schemas()
            call = self.ollama_caller.call_tool(request, schemas)
            if call:
                action, args, ctx = call
                cmd = self._find_or_create_command(action, action, args, ctx)
                log.info(f"Ollama routed request '{request}' -> tool '{action}' (args={args})")
                return [[cmd, ctx]]
            return []

        # SpaCy provider
        if not self.classifier.is_loaded():
            self.classifier.load_model(self.model_path)

        if self.classifier.is_loaded():
            pred = self.classifier.predict(request, threshold=self.confidence_threshold)
            if pred:
                cmd_id, action, conf, params, ctx = pred
                cmd = self._find_or_create_command(cmd_id, action, params, ctx)
                log.info(f"SpaCy classifier routed request '{request}' -> intent '{cmd_id}' (action={action}, conf={conf:.3f}, params={params}, ctx='{ctx}')")
                return [[cmd, ctx]]

        # Secondary fallback to Qwen if SpaCy was uncertain and Qwen model exists
        if self.qwen_caller.model_path.exists():
            schemas = self.tool_registry.get_all_tool_schemas()
            call = self.qwen_caller.call_tool(request, schemas)
            if call:
                action, args, ctx = call
                cmd = self._find_or_create_command(action, action, args, ctx)
                log.info(f"Qwen fallback routed request '{request}' -> tool '{action}' (args={args})")
                return [[cmd, ctx]]

        return []

    def generate_persona_response(self,
                                  user_query: str,
                                  tool_name: Optional[str] = None,
                                  tool_result: Optional[Any] = None,
                                  lang: str = "en") -> Optional[str]:
        """Generates dynamic Butler persona voice response for Kokoro TTS."""
        if not self.persona_enabled or not self.persona_caller:
            return None
        return self.persona_caller.generate_response(
            user_query=user_query,
            tool_name=tool_name,
            tool_result=tool_result,
            lang=lang
        )

    def stream_persona_response(self,
                                user_query: str,
                                tool_name: Optional[str] = None,
                                tool_result: Optional[Any] = None,
                                lang: str = "en"):
        """Streams dynamic Butler persona voice response tokens for Kokoro TTS."""
        if not self.persona_enabled or not self.persona_caller:
            return iter([])
        return self.persona_caller.stream_response(
            user_query=user_query,
            tool_name=tool_name,
            tool_result=tool_result,
            lang=lang
        )

