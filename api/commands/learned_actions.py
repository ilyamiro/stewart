import os
import json
import logging
import datetime
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

log = logging.getLogger("API: learned_actions")

BASE_LEARNED_ACTIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data/learned_actions.json"
USER_LEARNED_ACTIONS_FILE = Path(os.environ.get("STEWART_CONFIG_DIR") or (Path.home() / ".config/stewart")) / "learned_actions.json"
DEFAULT_LEARNED_ACTIONS_FILE = USER_LEARNED_ACTIONS_FILE


class LearnedAction:
    """
    Represents an algorithmic action synthesized by Antigravity (AGY).
    Binds trigger keywords directly to native Stewart actions or command templates.
    """
    def __init__(self,
                 name: str,
                 keywords: List[str],
                 description: str = "",
                 synonyms: Optional[Dict[str, List[str]]] = None,
                 equivalents: Optional[List[List[str]]] = None,
                 action_type: str = "command_template",
                 target_action: Optional[str] = None,
                 command_template: Optional[str] = None,
                 parameters: Optional[Dict[str, Any]] = None,
                 continues: bool = True,
                 responses: Optional[List[str]] = None,
                 tts: bool = True,
                 requires_thinking: bool = False,
                 created_at: Optional[str] = None):
        self.name = name
        self.keywords = [k.lower().strip() for k in keywords]
        self.description = description or f"Synthesized action '{name}'"
        self.synonyms = {k.lower().strip(): [s.lower().strip() for s in v] for k, v in (synonyms or {}).items()}
        self.equivalents = equivalents or []
        self.action_type = action_type
        self.target_action = target_action
        self.command_template = command_template
        self.parameters = parameters or {}
        self.continues = continues
        self.responses = responses or []
        self.tts = tts
        self.requires_thinking = requires_thinking
        self.created_at = created_at or datetime.datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "keywords": self.keywords,
            "description": self.description,
            "synonyms": self.synonyms,
            "equivalents": self.equivalents,
            "action_type": self.action_type,
            "target_action": self.target_action,
            "command_template": self.command_template,
            "parameters": self.parameters,
            "continues": self.continues,
            "responses": self.responses,
            "tts": self.tts,
            "requires_thinking": self.requires_thinking,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearnedAction":
        return cls(
            name=data["name"],
            keywords=data.get("keywords", [data["name"]]),
            description=data.get("description", ""),
            synonyms=data.get("synonyms"),
            equivalents=data.get("equivalents"),
            action_type=data.get("action_type", "command_template"),
            target_action=data.get("target_action"),
            command_template=data.get("command_template"),
            parameters=data.get("parameters"),
            continues=data.get("continues", True),
            responses=data.get("responses"),
            tts=data.get("tts", True),
            requires_thinking=data.get("requires_thinking", False),
            created_at=data.get("created_at"),
        )


class LearnedActionManager:
    """
    Manages persistent synthesized actions created by Antigravity.
    Instantly compiles learned actions into live Stewart CommandTree instances.
    """
    def __init__(self, manager=None, api=None, storage_file: Optional[Path] = None):
        self.manager = manager
        self.api = api
        self.storage_file = storage_file or DEFAULT_LEARNED_ACTIONS_FILE
        self._actions: Dict[str, LearnedAction] = {}
        self.load()

    def load(self):
        """Loads learned actions from disk, merging base defaults and user storage."""
        files_to_load = []
        if BASE_LEARNED_ACTIONS_FILE.exists() and BASE_LEARNED_ACTIONS_FILE != self.storage_file:
            files_to_load.append(BASE_LEARNED_ACTIONS_FILE)
        if self.storage_file.exists():
            files_to_load.append(self.storage_file)

        for sfile in files_to_load:
            try:
                with open(sfile, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = data.get("actions", []) if isinstance(data, dict) else data
                    for item in items:
                        if isinstance(item, dict) and "name" in item:
                            act = LearnedAction.from_dict(item)
                            self._actions[act.name] = act
                log.info(f"Loaded learned actions from {sfile} (total: {len(self._actions)})")
            except Exception as e:
                log.warning(f"Error loading learned actions from {sfile}: {e}")

    def save(self):
        """Persists learned actions to disk."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"actions": [act.to_dict() for act in self._actions.values()]}
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.info(f"Saved {len(self._actions)} learned actions to {self.storage_file}")
        except Exception as e:
            log.error(f"Error saving learned actions to {self.storage_file}: {e}")

    def create_action_callable(self, action: LearnedAction) -> Callable:
        """Constructs an executable callable for the given LearnedAction."""
        if action.action_type == "existing_action" and action.target_action:
            def existing_runner(command=None, context: str = "", history: Optional[List] = None, **kwargs):
                args = dict(action.parameters)
                if command and hasattr(command, "parameters") and isinstance(command.parameters, dict):
                    args.update(command.parameters)
                args.update(kwargs)

                for k, v in list(args.items()):
                    if isinstance(v, str) and "{context}" in v:
                        args[k] = v.replace("{context}", context.strip())

                target_fn = None
                if self.api:
                    if hasattr(self.api, "find_action"):
                        target_fn = self.api.find_action(action.target_action)
                    elif hasattr(self.api, "__actions__") and action.target_action in self.api.__actions__:
                        target_fn = self.api.__actions__[action.target_action]

                if not target_fn and hasattr(self.api, "tool_registry"):
                    tool = self.api.tool_registry.get(action.target_action)
                    if tool:
                        target_fn = tool.invoke

                if target_fn:
                    return target_fn(command=command, context=context, history=history, **args)

                log.error(f"Target action '{action.target_action}' could not be resolved for learned action '{action.name}'")
                return {"status": "error", "error": f"Target action '{action.target_action}' not found"}

            existing_runner.__name__ = action.name
            existing_runner.__doc__ = action.description
            return existing_runner

        def template_runner(command=None, context: str = "", history: Optional[List] = None, **kwargs):
            cmd_str = action.command_template or ""
            clean_ctx = context.strip()
            escaped_ctx = clean_ctx.replace("'", "'\\''")
            cmd_str = cmd_str.replace("{context}", escaped_ctx)

            all_params = dict(action.parameters)
            if command and hasattr(command, "parameters") and isinstance(command.parameters, dict):
                all_params.update(command.parameters)
            all_params.update(kwargs)

            for k, v in all_params.items():
                cmd_str = cmd_str.replace("{" + k + "}", str(v))

            log.info(f"Executing synthesized action '{action.name}': {cmd_str}")
            try:
                res = subprocess.run(
                    cmd_str,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15.0
                )
                success = res.returncode == 0
                return {
                    "status": "success" if success else "error",
                    "stdout": res.stdout.strip(),
                    "stderr": res.stderr.strip(),
                    "returncode": res.returncode
                }
            except Exception as e:
                log.error(f"Error executing learned action template '{action.name}': {e}")
                return {"status": "error", "error": str(e)}

        template_runner.__name__ = action.name
        template_runner.__doc__ = action.description
        return template_runner

    def compile_command(self, action: LearnedAction):
        """Compiles a LearnedAction into a Stewart Command instance with its executable attached."""
        from .tree import Command
        cmd = Command(
            keywords=action.keywords,
            action=action.name,
            synonyms=action.synonyms,
            responses=action.responses,
            parameters=action.parameters,
            continues=action.continues,
            equivalents=action.equivalents,
            tts=action.tts
        )
        runner = self.create_action_callable(action)
        cmd._action_callable = runner

        if self.api and hasattr(self.api, "__actions__") and isinstance(self.api.__actions__, dict):
            self.api.__actions__[action.name] = runner

        if self.api and hasattr(self.api, "tool_registry"):
            from .tools import ActionTool
            tool = ActionTool(
                name=action.name,
                func=runner,
                description=action.description,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "context": {"type": "string", "description": "Command context or arguments"}
                    }
                },
                default_params=action.parameters,
                requires_context=action.continues,
                sample_phrases=[" ".join(action.keywords)],
                plugin_name="learned"
            )
            self.api.tool_registry.register(tool)

        return cmd

    def register_action(self,
                        name: str,
                        keywords: List[str],
                        description: str = "",
                        synonyms: Optional[Dict[str, List[str]]] = None,
                        equivalents: Optional[List[List[str]]] = None,
                        action_type: str = "command_template",
                        target_action: Optional[str] = None,
                        command_template: Optional[str] = None,
                        parameters: Optional[Dict[str, Any]] = None,
                        continues: bool = True,
                        responses: Optional[List[str]] = None,
                        tts: bool = True,
                        requires_thinking: bool = False) -> LearnedAction:
        """
        Registers a new learned action, persists it to disk, and live-binds it into Stewart's
        Manager command tree so it is immediately recognized algorithmically.
        """
        action = LearnedAction(
            name=name,
            keywords=keywords,
            description=description,
            synonyms=synonyms,
            equivalents=equivalents,
            action_type=action_type,
            target_action=target_action,
            command_template=command_template,
            parameters=parameters,
            continues=continues,
            responses=responses,
            tts=tts,
            requires_thinking=requires_thinking
        )
        self._actions[name] = action
        self.save()

        if not requires_thinking and self.manager:
            cmd = self.compile_command(action)
            self.manager.add(cmd)
            log.info(f"Live-bound learned action '{name}' into Stewart algorithmic CommandTree.")

        return action

    def bind_all(self, manager=None, api=None):
        """Binds all non-thinking learned actions into the CommandTree and API."""
        if manager:
            self.manager = manager
        if api:
            self.api = api

        if not self.manager:
            return

        count = 0
        for act in self._actions.values():
            if not act.requires_thinking:
                cmd = self.compile_command(act)
                self.manager.add(cmd)
                count += 1
        log.info(f"Bound {count} learned action(s) into Stewart CommandTree.")

    def list_actions(self) -> List[LearnedAction]:
        return list(self._actions.values())

    def get(self, name: str) -> Optional[LearnedAction]:
        return self._actions.get(name)


_learned_action_manager: Optional[LearnedActionManager] = None


def get_learned_action_manager(manager=None, api=None) -> LearnedActionManager:
    global _learned_action_manager
    if _learned_action_manager is None:
        _learned_action_manager = LearnedActionManager(manager=manager, api=api)
    elif manager or api:
        if manager:
            _learned_action_manager.manager = manager
        if api:
            _learned_action_manager.api = api
    return _learned_action_manager


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stewart Learned Action CLI")
    subparsers = parser.add_subparsers(dest="subcommand")

    reg = subparsers.add_parser("register", help="Register a new learned algorithmic action")
    reg.add_argument("--name", required=True, help="Unique action name (e.g. find_image)")
    reg.add_argument("--keywords", required=True, help="Space-separated trigger keywords (e.g. 'find image')")
    reg.add_argument("--desc", default="", help="Description")
    reg.add_argument("--type", choices=["command_template", "existing_action"], default="command_template")
    reg.add_argument("--target", help="Target action when type=existing_action (e.g. browser)")
    reg.add_argument("--cmd", help="Command template when type=command_template (e.g. 'echo {context}')")
    reg.add_argument("--synonyms", default="{}", help="JSON dictionary of keyword synonyms")
    reg.add_argument("--params", default="{}", help="JSON dictionary of parameters")
    reg.add_argument("--continues", action="store_true", default=True, help="Captures trailing context")
    reg.add_argument("--responses", default="", help="Comma-separated responses")

    list_p = subparsers.add_parser("list", help="List registered learned actions")

    args = parser.parse_args()
    mgr = get_learned_action_manager()

    if args.subcommand == "register":
        kw_list = [k.strip() for k in args.keywords.split() if k.strip()]
        try:
            syn_dict = json.loads(args.synonyms) if args.synonyms else {}
        except Exception:
            syn_dict = {}
        try:
            params_dict = json.loads(args.params) if args.params else {}
        except Exception:
            params_dict = {}
        resp_list = [r.strip() for r in args.responses.split(",") if r.strip()]

        action = mgr.register_action(
            name=args.name,
            keywords=kw_list,
            description=args.desc,
            synonyms=syn_dict,
            action_type=args.type,
            target_action=args.target,
            command_template=args.cmd,
            parameters=params_dict,
            continues=args.continues,
            responses=resp_list
        )
        print(f"Action '{action.name}' successfully registered and persisted.")
    elif args.subcommand == "list":
        acts = mgr.list_actions()
        print(f"Learned Actions ({len(acts)}):")
        for a in acts:
            print(f"- {a.name} (keywords: {a.keywords}): type={a.action_type} target={a.target_action or a.command_template}")
    else:
        parser.print_help()
