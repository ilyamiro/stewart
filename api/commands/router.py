import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from .tree import Command, Manager
from .tools import ToolRegistry, ActionTool
from .classifier import SpacyActionClassifier
from .ollama import OllamaToolCaller
from .qwen_caller import QwenToolCaller
from .persona_caller import QwenPersonaCaller
from .agy_caller import AgyCaller

log = logging.getLogger("API: router")


class CommandRouter:
    """
    Unified Command & Tool Router.
    Dispatches user input between algorithmic tree matching, fine-grained command intent
    classification via SpaCy, local Ollama/Qwen tool calling with dynamic Persona voice responses,
    and Antigravity (agy -p) CLI execution.
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
        model_size = qwen_cfg.get("model_size") or router_cfg.get("model_size") or "1.5b"
        qwen_path_str = qwen_cfg.get("model_path")
        self.qwen_caller = QwenToolCaller(model_path=qwen_path_str, model_size=model_size)

        # Persona Voice Model settings
        persona_cfg = router_cfg.get("persona", {}) or self.config.get("persona", {})
        self.persona_enabled = persona_cfg.get("enabled", True)
        self.persona_provider = persona_cfg.get("provider", "agy" if self.mode == "agy" else "qwen").lower()
        persona_model_size = persona_cfg.get("model_size") or model_size
        persona_path_str = persona_cfg.get("model_path")
        if self.persona_provider == "agy":
            self.persona_caller = None
        else:
            self.persona_caller = QwenPersonaCaller(
                model_path=persona_path_str,
                model_size=persona_model_size,
                max_new_tokens=int(persona_cfg.get("max_new_tokens", 64)),
                temperature=float(persona_cfg.get("temperature", 0.6)),
                shared_caller=self.qwen_caller
            )

        # Agy CLI Caller settings
        agy_cfg = router_cfg.get("agy", {}) or self.config.get("agy", {})
        self.agy_caller = AgyCaller(
            command=agy_cfg.get("command", "agy"),
            model=agy_cfg.get("model", "gemini-3.8-flash-low"),
            effort=agy_cfg.get("effort", "low"),
            timeout=float(agy_cfg.get("timeout", 30.0)),
            dangerously_skip_permissions=bool(agy_cfg.get("dangerously_skip_permissions", True)),
            skill_name=agy_cfg.get("skill_name", "stewart-voice")
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

        # Sync MCP tools into tool registry
        if hasattr(self.tool_registry, "sync_from_mcp"):
            self.tool_registry.sync_from_mcp()
        if hasattr(self.tool_registry, "sync_dynamic_tools"):
            self.tool_registry.sync_dynamic_tools()

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
        cmd = Command(
            keywords=[action],
            action=action,
            parameters=merged_params,
            responses=[],
            synonyms={},
            tts=False
        )
        if tool:
            cmd._action_callable = tool.func
            if getattr(tool, "is_query", False):
                cmd.is_query = True
        return cmd


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

        elif self.mode == "agy":
            ans = self.agy_caller.execute_request(clean_request)
            if ans:
                if hasattr(self.tool_registry, "sync_dynamic_tools"):
                    self.tool_registry.sync_dynamic_tools()
                is_conf = getattr(ans, "needs_confirmation", False)
                cmd = Command(
                    keywords=["confirmation" if is_conf else "speak"],
                    action="confirmation" if is_conf else "speak",
                    parameters={
                        "text": str(ans),
                        "prompt": getattr(ans, "confirmation_prompt", str(ans)),
                        "original_request": clean_request,
                        "needs_confirmation": is_conf
                    },
                    responses=[str(ans)],
                    synonyms={},
                    tts=True
                )
                cmd.needs_confirmation = is_conf
                results = [[cmd, clean_request]]
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
                # If command has no parameters/context (e.g. "stop", "time", "lock"), algorithmic handles it immediately
                has_context = any(bool(c[1] and c[1].strip()) for c in algo_results)
                if not has_context:
                    results = algo_results
                else:
                    # If command has natural language arguments/context, prefer model tool caller (Qwen) if available
                    model_res = self._route_via_model(clean_request)
                    results = model_res if model_res else algo_results
            else:
                # 2. Fall back to smart model tool selection (SpaCy, Qwen, or Agy)
                results = self._route_via_model(clean_request)

        if len(self._route_cache) < 1000:
            self._route_cache[clean_request] = [[c[0], c[1]] for c in results]

        return results

    def _route_via_model(self, request: str) -> List[List[Any]]:
        """Invokes Agy, Qwen, Ollama, or SpaCy model depending on configured provider."""
        if self.provider == "agy":
            ans = self.agy_caller.execute_request(request)
            if ans:
                if hasattr(self.tool_registry, "sync_dynamic_tools"):
                    self.tool_registry.sync_dynamic_tools()
                is_conf = getattr(ans, "needs_confirmation", False)
                cmd = Command(
                    keywords=["confirmation" if is_conf else "speak"],
                    action="confirmation" if is_conf else "speak",
                    parameters={
                        "text": str(ans),
                        "prompt": getattr(ans, "confirmation_prompt", str(ans)),
                        "original_request": request,
                        "needs_confirmation": is_conf
                    },
                    responses=[str(ans)],
                    synonyms={},
                    tts=True
                )
                cmd.needs_confirmation = is_conf
                log.info(f"Agy routed and answered request '{request}' (needs_confirmation={is_conf})")
                return [[cmd, request]]
            return []


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
        if self.qwen_caller.model_path and self.qwen_caller.model_path.exists():
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
        if not self.persona_enabled:
            return None
        if self.persona_provider == "agy" and hasattr(self, "agy_caller"):
            import json
            tool_info = f"Tool executed: '{tool_name}' with result: {json.dumps(tool_result, ensure_ascii=False) if tool_result else 'None'}. " if tool_name else ""
            prompt = (
                f"You are Stewart, a polite British AI butler. The user said: '{user_query}'. {tool_info}"
                f"Respond directly in 1-2 spoken sentences to the user in {lang}. "
                f"No markdown, no emojis, no code blocks."
            )
            res = self.agy_caller.execute_request(prompt)
            return str(res) if res else None
        if not self.persona_caller:
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
        if not self.persona_enabled:
            return iter([])
        if self.persona_provider == "agy" and hasattr(self, "agy_caller"):
            full_text = self.generate_persona_response(user_query, tool_name, tool_result, lang)
            if full_text:
                return iter([full_text])
            return iter([])
        if not self.persona_caller:
            return iter([])
        return self.persona_caller.stream_response(
            user_query=user_query,
            tool_name=tool_name,
            tool_result=tool_result,
            lang=lang
        )

