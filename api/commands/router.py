import json
import logging
import random
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from .tree import Command, Manager
from .tools import ToolRegistry, ActionTool
from .ollama import OllamaToolCaller
from .agy_caller import AgyCaller

log = logging.getLogger("API: router")


class CommandRouter:
    def __init__(self, manager: Manager, tool_registry: Optional[ToolRegistry] = None, config: Optional[Dict[str, Any]] = None):
        self.manager = manager
        self.tool_registry = tool_registry or ToolRegistry()
        self.config = config or {}

        router_cfg = self.config.get("router", {})
        self.mode = router_cfg.get("mode", "hybrid").lower()

        model_cfg = router_cfg.get("model", {})
        self.provider = model_cfg.get("provider", "agy").lower()
        self.fallback_to_algorithmic = model_cfg.get("fallback_to_algorithmic", True)

        ollama_cfg = router_cfg.get("ollama", {})
        self.ollama_caller = OllamaToolCaller(
            endpoint=ollama_cfg.get("endpoint", "http://localhost:11434"),
            model=ollama_cfg.get("model", "llama3.2:1b"),
            timeout=float(ollama_cfg.get("timeout", 3.0))
        )

        persona_cfg = router_cfg.get("persona", {}) or self.config.get("persona", {})
        self.persona_enabled = persona_cfg.get("enabled", True)
        self.persona_provider = "agy"
        self.persona_caller = None

        agy_cfg = router_cfg.get("agy", {}) or self.config.get("agy", {})
        self.agy_caller = AgyCaller(
            command=agy_cfg.get("command", "agy"),
            model=agy_cfg.get("model", "gemini-3.8-flash-low"),
            effort=agy_cfg.get("effort", "low"),
            timeout=float(agy_cfg.get("timeout", 30.0)),
            dangerously_skip_permissions=bool(agy_cfg.get("dangerously_skip_permissions", True)),
            skill_name=agy_cfg.get("skill_name", "stewart-voice")
        )

        self._route_cache: Dict[str, List] = {}
        self._cmd_id_to_command: Dict[str, Command] = {}
        self._action_to_command: Dict[str, Command] = {}

    def initialize(self):
        for cmd in self.manager.commands:
            kw_str = "-".join(str(w) for w in cmd.keywords)
            cmd_id = f"{cmd.action}::{kw_str}" if kw_str else cmd.action
            if cmd_id not in self._cmd_id_to_command:
                self._cmd_id_to_command[cmd_id] = cmd
            if cmd.action not in self._action_to_command:
                self._action_to_command[cmd.action] = cmd

        if hasattr(self.tool_registry, "sync_from_mcp"):
            self.tool_registry.sync_from_mcp()
        if hasattr(self.tool_registry, "sync_dynamic_tools"):
            self.tool_registry.sync_dynamic_tools()

        try:
            from .learned_actions import get_learned_action_manager
            self.learned_action_manager = get_learned_action_manager(manager=self.manager, api=getattr(self.manager, "api", None))
            self.learned_action_manager.bind_all(manager=self.manager)
        except Exception as le:
            log.warning(f"Error binding learned actions: {le}")

    def _find_or_create_command(self, cmd_id: str, action: str, params: Dict[str, Any], ctx: str) -> Command:
        existing = self._cmd_id_to_command.get(cmd_id) or self._action_to_command.get(action)
        if existing:
            merged_params = dict(existing.parameters)
            merged_params.update(params)
            merged_params["original_context"] = ctx
            return Command(
                keywords=existing.keywords,
                action=existing.action,
                parameters=merged_params,
                responses=existing.responses,
                synonyms=existing.synonyms,
                equivalents=existing.equivalents,
                tts=existing.tts,
                continues=existing.continues
            )

        tool = self.tool_registry.get(action)
        responses = []
        is_query = False
        if tool:
            is_query = getattr(tool, "is_query", False)

        cmd = Command(
            keywords=[action],
            action=action,
            parameters=params,
            responses=responses,
            synonyms={},
            tts=is_query
        )
        cmd.is_query = is_query
        return cmd

    def route(self, request: str, history: Optional[List] = None) -> List[List[Any]]:
        clean_request = request.strip()
        if not clean_request:
            return []

        if clean_request in self._route_cache:
            return [[c[0], c[1]] for c in self._route_cache[clean_request]]

        results = []

        if self.mode == "agy":
            schemas = self.tool_registry.get_all_tool_schemas()
            ans = self.agy_caller.execute_request(clean_request, tools=schemas)
            if ans:
                if hasattr(self.tool_registry, "sync_dynamic_tools"):
                    self.tool_registry.sync_dynamic_tools()

                raw_payload = getattr(ans, "raw_output", str(ans))
                matches = list(re.finditer(r"<tool_call>\s*(.*?)(?:</tool_call>|$)", raw_payload, re.DOTALL))
                if matches:
                    tool_cmds = []
                    for m in matches:
                        try:
                            call_data = json.loads(m.group(1).strip())
                            items = call_data if isinstance(call_data, list) else [call_data]
                            for it in items:
                                if isinstance(it, dict) and "name" in it:
                                    action = it.get("name")
                                    args = it.get("arguments") or it.get("parameters") or {}
                                    cmd = self._find_or_create_command(action, action, args, clean_request)
                                    tool_cmds.append([cmd, clean_request])
                        except Exception as je:
                            log.debug(f"Failed parsing tool call from AGY output: {je}")
                    if tool_cmds:
                        return tool_cmds

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

        else:
            if self._requires_reasoning_or_waiting(clean_request):
                results = self._route_via_model(clean_request)
            else:
                algo_results = self.manager.find_algorithmic(clean_request)
                if algo_results:
                    results = algo_results
                else:
                    results = self._route_via_model(clean_request)

        if len(self._route_cache) < 1000:
            self._route_cache[clean_request] = [[c[0], c[1]] for c in results]

        return results

    def _requires_reasoning_or_waiting(self, request: str) -> bool:
        lowered = f" {request.lower().strip()} "
        temporal_markers = [
            " then ", " and then ", " after that ", " afterwards ", " wait for ", " until ",
            " затем ", " потом ", " после этого ", " подожди ", " а потом ", " и затем "
        ]
        if any(m in lowered for m in temporal_markers):
            return True

        coref_markers = [
            " it ", " that ", " them ", " its ", " this ",
            " его ", " ее ", " их ", " это ", " этот ", " эту "
        ]
        has_conjunction = any(c in lowered for c in [" and ", " then ", " also ", " и ", " а также "])
        has_coreference = any(cr in lowered for cr in coref_markers)
        if has_conjunction and has_coreference:
            return True

        return False

    def _route_via_model(self, request: str) -> List[List[Any]]:
        if self.provider == "agy":
            schemas = self.tool_registry.get_all_tool_schemas()
            ans = self.agy_caller.execute_request(request, tools=schemas)
            if ans:
                if hasattr(self.tool_registry, "sync_dynamic_tools"):
                    self.tool_registry.sync_dynamic_tools()
                if hasattr(self, "learned_action_manager") and self.learned_action_manager:
                    self.learned_action_manager.load()
                    self.learned_action_manager.bind_all(self.manager)

                match = re.search(r"<tool_call>\s*(.*?)(?:</tool_call>|$)", str(ans), re.DOTALL)
                if match:
                    try:
                        call_data = json.loads(match.group(1).strip())
                        action = call_data.get("name")
                        args = call_data.get("arguments") or call_data.get("parameters") or {}
                        ctx = request
                        cmd = self._find_or_create_command(action, action, args, ctx)
                        return [[cmd, ctx]]
                    except Exception as je:
                        log.debug(f"Failed parsing tool call: {je}")

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
                return [[cmd, request]]
            return []

        if self.provider == "ollama":
            schemas = self.tool_registry.get_all_tool_schemas()
            call = self.ollama_caller.call_tool(request, schemas)
            if call:
                action, args, ctx = call
                cmd = self._find_or_create_command(action, action, args, ctx)
                return [[cmd, ctx]]

        return []

    def generate_persona_response(self,
                                  user_query: str,
                                  tool_name: Optional[str] = None,
                                  tool_result: Optional[Any] = None,
                                  lang: str = "en") -> Optional[str]:
        if not self.persona_enabled:
            return None

        is_query = bool(tool_name and (tool_name.startswith(("studieplus_", "study_", "gmail_")) or (isinstance(tool_result, dict) and any(k in tool_result for k in ("stdout", "message", "emails", "schedule", "assignments")))))
        if tool_name and not is_query:
            if lang.lower().startswith("ru"):
                return random.choice(["Сделано, сэр.", "Выполнено, сэр.", "Слушаюсь, сэр.", "Готово, сэр."])
            else:
                return random.choice(["Done, Sir.", "At once, Sir.", "Right away, Sir.", "Completed, Sir."])

        tool_info = f"Tool executed: '{tool_name}' with result: {json.dumps(tool_result, ensure_ascii=False) if tool_result else 'None'}. " if tool_name else ""
        if lang.lower().startswith("ru"):
            prompt = (
                f"You are Stewart, a polite British AI butler. The user said: '{user_query}'. {tool_info}"
                f"Respond directly in 1-2 spoken sentences to the user STRICTLY in Russian using ONLY Cyrillic letters. "
                f"Do NOT use numbered lists or bullet points. Speak in smooth, connected conversational sentences. "
                f"No markdown, no emojis, no code blocks."
            )
        else:
            prompt = (
                f"You are Stewart, a polite British AI butler. The user said: '{user_query}'. {tool_info}"
                f"Respond directly in 1-2 spoken sentences to the user STRICTLY in English. "
                f"No markdown, no emojis, no code blocks, no numbered lists or bullet points."
            )
        res = self.agy_caller.execute_request(prompt)
        return str(res) if res else None

    def stream_persona_response(self,
                                user_query: str,
                                tool_name: Optional[str] = None,
                                tool_result: Optional[Any] = None,
                                lang: str = "en"):
        if not self.persona_enabled:
            return iter([])
        full_text = self.generate_persona_response(user_query, tool_name, tool_result, lang)
        if full_text:
            return iter([full_text])
        return iter([])
