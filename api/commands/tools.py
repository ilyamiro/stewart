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
        from .actions import BaseAction

        if isinstance(func, BaseAction):
            self.name = func.name or name
            self.func = func
            self.description = description or func.description
            self.parameters_schema = parameters_schema or func.to_ollama_tool()["function"]["parameters"]
            self.default_params = default_params or {}
            self.requires_context = requires_context or func.requires_context
            self.sample_phrases = sample_phrases if sample_phrases is not None else list(func.sample_phrases)
            self.plugin_name = plugin_name if plugin_name != "core" else func.plugin_name
        else:
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
        from .tree import Command
        if not isinstance(command, Command):
            cmd_args = dict(kwargs)
            if isinstance(command, str):
                cmd_args["command"] = command
            command = Command(
                keywords=[self.name],
                action=self.name,
                parameters={**self.default_params, **cmd_args}
            )
        try:
            return self.func(command=command, context=context, history=history or [], **kwargs)
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
    def __init__(self, api=None, mcp_manager=None):
        self.api = api
        self.mcp_manager = mcp_manager
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

    @staticmethod
    def format_tool_schemas(tool_schemas: List[Dict[str, Any]]) -> str:
        """Formats tool schemas into concise text representation for LLM prompts."""
        tool_lines = []
        for tool in tool_schemas:
            fn = tool.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_strs = []
            for pname, pinfo in params.items():
                ptype = pinfo.get("type", "any")
                if "enum" in pinfo:
                    ptype = "|".join(f'"{e}"' for e in pinfo["enum"])
                param_strs.append(f"{pname}: {ptype}")
            params_repr = ", ".join(param_strs)
            tool_lines.append(f"- {name}({params_repr}) - {desc}")
        return "\n".join(tool_lines)

    def get_formatted_tool_schemas(self) -> str:
        return self.format_tool_schemas(self.get_all_tool_schemas())

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

        from .actions import BaseAction

        for name, func in actions.items():
            if name.startswith("_"):
                continue  # skip internal functions
            meta = action_metadata.get(name, {})

            if isinstance(func, BaseAction):
                # Inherit BaseAction's typed schema and metadata
                tool_schema = func.to_ollama_tool()["function"]["parameters"]
                samples = list(func.sample_phrases)
                for s in meta.get("samples", []):
                    if s not in samples:
                        samples.append(s)

                tool = ActionTool(
                    name=func.name or name,
                    func=func,
                    description=func.description,
                    parameters_schema=tool_schema,
                    default_params=meta.get("parameters", {}),
                    requires_context=meta.get("continues", False) or func.requires_context,
                    sample_phrases=samples,
                    plugin_name=func.plugin_name
                )
                self.register(tool)
                continue

            doc = (inspect.getdoc(func) or "").strip().split("\n")[0]
            if not doc:
                doc = f"Executes system action '{name}'"

            # Auto-infer parameter schema for legacy function actions
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
        self.register_core_categorical_tools()
        self.sync_from_mcp()

    def register_core_categorical_tools(self):
        """
        Registers first-class categorical MCP-style tools:
        file, web, app, brightness, volume, music, hotkey, timer, system.
        """
        import os
        import shutil
        import urllib.parse
        from api.services.desktop import get_desktop_service

        # 1. file tool
        def file_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            action = args.get("action", "open")
            path = args.get("path") or args.get("target") or context
            new_name = args.get("new_name") or args.get("dst")
            desktop = get_desktop_service(api=self.api)
            if action == "open" and path:
                ok = desktop.open_file(path)
                return {"status": "success" if ok else "error", "opened_file": path}
            elif action == "rename" and path and new_name:
                try:
                    p = os.path.expanduser(os.path.expandvars(path))
                    n = os.path.expanduser(os.path.expandvars(new_name))
                    if not os.path.isabs(n) and os.path.dirname(p):
                        n = os.path.join(os.path.dirname(p), n)
                    os.rename(p, n)
                    return {"status": "success", "renamed": f"{path} -> {new_name}"}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
            elif action == "delete" and path:
                try:
                    os.remove(os.path.expanduser(os.path.expandvars(path)))
                    return {"status": "success", "deleted": path}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
            return {"status": "error", "error": f"Invalid file action '{action}' or missing path"}

        file_action.__name__ = "file"
        file_action.is_query = True
        self.register(ActionTool(
            name="file",
            func=file_action,
            description="Open, rename, or delete files and directories on the local Linux filesystem.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open", "rename", "delete"], "description": "File action"},
                    "path": {"type": "string", "description": "Target file or folder path (e.g. ~/Downloads, report.pdf)"},
                    "new_name": {"type": "string", "description": "New filename when renaming"}
                },
                "required": ["action", "path"]
            },
            plugin_name="core"
        ))

        # 2. web tool
        def web_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            action = args.get("action", "open")
            url = args.get("url")
            query = args.get("query") or (context if action == "search" else None)
            desktop = get_desktop_service(api=self.api)
            if action == "open" and url:
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"
                ok = desktop.open_url(url)
                return {"status": "success" if ok else "error", "opened_url": url}
            elif action == "search" and query:
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                ok = desktop.open_url(search_url)
                return {"status": "success" if ok else "error", "searched": query}
            elif url:
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"
                ok = desktop.open_url(url)
                return {"status": "success" if ok else "error", "opened_url": url}
            return {"status": "error", "error": "Neither URL nor query specified"}

        web_action.__name__ = "web"
        web_action.is_query = True
        self.register(ActionTool(
            name="web",
            func=web_action,
            description="Open web URLs or perform internet search queries in the default browser.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open", "search"], "description": "Web action"},
                    "url": {"type": "string", "description": "Website URL to open (e.g. https://wikipedia.org, https://youtube.com)"},
                    "query": {"type": "string", "description": "Search query terms"}
                },
                "required": ["action"]
            },
            plugin_name="core"
        ))

        # 3. app tool
        def app_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            action = args.get("action", "launch")
            name = (args.get("name") or args.get("app") or context).strip()
            desktop = get_desktop_service(api=self.api)
            if action == "close":
                ok = desktop.close_active_window()
                return {"status": "success" if ok else "error", "message": "Closed active window"}
            elif action == "switch" and name:
                ok = desktop.focus_window(name)
                return {"status": "success" if ok else "error", "switched_to": name}
            elif action == "launch" and name:
                name_lower = name.lower()
                if name_lower in ("youtube", "yt"):
                    ok = desktop.open_url("https://youtube.com")
                    return {"status": "success" if ok else "error", "launched": "youtube"}
                elif name_lower in ("terminal", "term", "console"):
                    for term in ["kitty", "alacritty", "foot", "wezterm", "gnome-terminal"]:
                        if shutil.which(term):
                            ok = desktop.launch_app(term)
                            return {"status": "success" if ok else "error", "launched": term}
                    desktop.launch_app("xterm")
                    return {"status": "success", "launched": "xterm"}
                elif name_lower in ("files", "file manager", "nautilus", "explorer"):
                    for fm in ["nautilus", "thunar", "dolphin", "pcmanfm"]:
                        if shutil.which(fm):
                            desktop.launch_app(fm)
                            return {"status": "success", "launched": fm}
                    desktop.launch_app(["xdg-open", "."])
                    return {"status": "success", "launched": "files"}
                elif name_lower in ("browser", "chrome", "google chrome"):
                    for b in ["google-chrome", "brave", "firefox", "chromium"]:
                        if shutil.which(b):
                            desktop.launch_app(b)
                            return {"status": "success", "launched": b}
                    desktop.open_url("https://google.com")
                    return {"status": "success", "launched": "browser"}
                else:
                    ok = desktop.launch_app(name)
                    return {"status": "success" if ok else "error", "launched": name}
            return {"status": "error", "error": "Missing application name or action"}

        app_action.__name__ = "app"
        app_action.is_query = True
        self.register(ActionTool(
            name="app",
            func=app_action,
            description="Launch, close, or switch desktop applications (terminal, browser, files, code, etc.).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["launch", "close", "switch"], "description": "Application action"},
                    "name": {"type": "string", "description": "Application name or binary (e.g. kitty, terminal, files, telegram, code, youtube)"}
                },
                "required": ["action"]
            },
            plugin_name="core"
        ))

        # 4. brightness tool
        def brightness_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            cmd = args.get("command") or args.get("action", "set")
            val = args.get("value") or context
            desktop = get_desktop_service(api=self.api)
            ok = desktop.set_brightness(command=cmd, value=val)
            return {"status": "success" if ok else "error", "brightness": val, "command": cmd}

        brightness_action.__name__ = "brightness"
        brightness_action.is_query = True
        self.register(ActionTool(
            name="brightness",
            func=brightness_action,
            description="Adjust or set display screen brightness via brightnessctl.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": ["set", "up", "down"], "description": "Brightness operation"},
                    "value": {"type": "string", "description": "Brightness percentage (e.g. 100%, 50%, 20%)"}
                },
                "required": ["command"]
            },
            plugin_name="core"
        ))

        # 5. volume tool
        def volume_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            cmd = args.get("command") or args.get("action", "set")
            val = args.get("value") or context
            desktop = get_desktop_service(api=self.api)
            ok = desktop.set_volume(command=cmd, value=val)
            return {"status": "success" if ok else "error", "volume": val, "command": cmd}

        volume_action.__name__ = "volume"
        volume_action.is_query = True
        self.register(ActionTool(
            name="volume",
            func=volume_action,
            description="Adjust or set master system volume level via PipeWire/PulseAudio.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": ["set", "up", "down", "mute", "unmute"], "description": "Volume operation"},
                    "value": {"type": "string", "description": "Volume percentage or step (e.g. 80%, 50%, 15%)"}
                },
                "required": ["command"]
            },
            plugin_name="core"
        ))

        # 6. music tool
        def music_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            action = args.get("action", "play-pause")
            track = args.get("track") or args.get("query")
            desktop = get_desktop_service(api=self.api)
            if action == "play" and track:
                from plugins.core.actions.media import play_song
                cmd_mock = type("Cmd", (), {"parameters": {}})()
                play_song(command=cmd_mock, context=track)
                return {"status": "success", "playing": track}
            elif action in ("pause", "resume", "play-pause", "next", "previous", "stop"):
                player_act = "play-pause" if action in ("pause", "resume") else action
                desktop.media_control(player_act)
                return {"status": "success", "music_action": action}
            return {"status": "error", "error": f"Unknown music action '{action}'"}

        music_action.__name__ = "music"
        music_action.is_query = True
        self.register(ActionTool(
            name="music",
            func=music_action,
            description="Control music and media playback (pause, resume, play, next, previous, stop).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["pause", "resume", "play", "next", "previous", "stop"], "description": "Playback action"},
                    "track": {"type": "string", "description": "Song title or artist query when playing"}
                },
                "required": ["action"]
            },
            plugin_name="core"
        ))

        # 7. hotkey tool
        def hotkey_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            keys = args.get("keys") or args.get("hotkey") or []
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split("+")]
            desktop = get_desktop_service(api=self.api)
            ok = desktop.send_hotkey(keys)
            return {"status": "success" if ok else "error", "pressed_keys": keys}

        hotkey_action.__name__ = "hotkey"
        hotkey_action.is_query = True
        self.register(ActionTool(
            name="hotkey",
            func=hotkey_action,
            description="Send keyboard shortcut or hotkey combination to focused window.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["press"], "description": "Keypress action"},
                    "keys": {"type": "array", "items": {"type": "string"}, "description": "List of keys (e.g. ['ctrl', 'f'], ['ctrl', 'w'])"}
                },
                "required": ["action", "keys"]
            },
            plugin_name="core"
        ))

        # 8. timer tool
        def timer_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            action = args.get("action", "set")
            duration = args.get("duration") or context
            from plugins.core.actions.core import timer
            cmd_mock = type("Cmd", (), {"parameters": {"action": action}})()
            timer(command=cmd_mock, context=duration)
            return {"status": "success", "timer_action": action, "duration": duration}

        timer_action.__name__ = "timer"
        timer_action.is_query = True
        self.register(ActionTool(
            name="timer",
            func=timer_action,
            description="Set, cancel or inspect countdown timers.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["set", "cancel", "status"], "description": "Timer action"},
                    "duration": {"type": "string", "description": "Timer duration (e.g. 5 minutes, 30 seconds)"}
                },
                "required": ["action"]
            },
            plugin_name="core"
        ))

        # 9. system tool
        def system_action(command=None, context: str = "", history=None, **kwargs):
            args = dict(kwargs)
            if command and hasattr(command, "parameters"):
                args.update(command.parameters)
            action = args.get("action", "lock")
            target = args.get("target") or context
            desktop = get_desktop_service(api=self.api)
            if action == "lock":
                desktop.lock_session()
                return {"status": "success", "locked": True}
            elif action == "screenshot":
                desktop.screenshot(mode=target or "full")
                return {"status": "success", "screenshot": True}
            elif action == "workspace" and target:
                desktop.switch_workspace(str(target))
                return {"status": "success", "workspace": target}
            elif action == "battery":
                from plugins.core.actions.core import battery
                cmd_mock = type("Cmd", (), {"parameters": {}})()
                battery(command=cmd_mock, context="")
                return {"status": "success", "checked": "battery"}
            elif action == "time":
                from plugins.core.actions.core import tell_time
                cmd_mock = type("Cmd", (), {"parameters": {}})()
                tell_time(command=cmd_mock, context="")
                return {"status": "success", "checked": "time"}
            elif action == "weather":
                from plugins.core.actions.core import say_weather
                cmd_mock = type("Cmd", (), {"parameters": {}})()
                say_weather(command=cmd_mock, context=target)
                return {"status": "success", "checked": "weather"}
            return {"status": "error", "error": f"Unknown system action '{action}'"}

        system_action.__name__ = "system"
        system_action.is_query = True
        self.register(ActionTool(
            name="system",
            func=system_action,
            description="System level operations: lock screen, check battery, tell time, weather, screenshot, or switch workspace.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["lock", "battery", "time", "weather", "screenshot", "workspace"], "description": "System action"},
                    "target": {"type": "string", "description": "Target argument (e.g. workspace number '2')"}
                },
                "required": ["action"]
            },
            plugin_name="core"
        ))

        log.info("Registered 9 core categorical MCP-style tools into ToolRegistry.")

    def sync_from_mcp(self, mcp_manager=None):
        """
        Discovers tools from MCP servers (e.g. studieplus, gmail) and registers them as ActionTool instances.
        """
        if mcp_manager is not None:
            self.mcp_manager = mcp_manager
        elif self.mcp_manager is None:
            try:
                from .mcp_client import MCPManager
                cfg = getattr(self.api, "config", {}) if self.api else {}
                self.mcp_manager = MCPManager(config=cfg)
            except Exception as e:
                log.warning(f"Could not initialize MCPManager: {e}")
                return

        try:
            mcp_tools = self.mcp_manager.discover_tools()
            for t in mcp_tools:
                name = t.get("name")
                if not name:
                    continue
                desc = t.get("description", f"MCP Tool {name}")
                schema = t.get("inputSchema") or {"type": "object", "properties": {}}

                def make_mcp_caller(tool_name):
                    def mcp_action(command=None, context: str = "", history: Optional[List] = None, **kwargs):
                        args = dict(kwargs)
                        if command and hasattr(command, "parameters") and isinstance(command.parameters, dict):
                            args.update(command.parameters)
                        args.pop("command", None)
                        args.pop("context", None)
                        args.pop("history", None)
                        return self.mcp_manager.call_tool(tool_name, args)
                    mcp_action.is_query = True
                    mcp_action.__name__ = tool_name
                    mcp_action.__doc__ = desc
                    return mcp_action

                caller = make_mcp_caller(name)
                server_name = getattr(self.mcp_manager, "_tool_to_server", {}).get(name, "mcp")

                tool = ActionTool(
                    name=name,
                    func=caller,
                    description=desc,
                    parameters_schema=schema,
                    default_params={},
                    requires_context=False,
                    sample_phrases=[],
                    plugin_name=f"mcp:{server_name}"
                )
                tool.is_query = True
                self.register(tool)

                # Register in api.__actions__ if available
                if self.api and hasattr(self.api, "__actions__") and isinstance(self.api.__actions__, dict):
                    self.api.__actions__[name] = caller

            log.info(f"Synchronized {len(mcp_tools)} MCP tools into ToolRegistry (Total tools: {len(self._tools)}).")
        except Exception as e:
            log.warning(f"Error syncing MCP tools: {e}", exc_info=True)

        # Sync dynamic tools as well
        self.sync_dynamic_tools()

    def sync_dynamic_tools(self):
        """
        Loads all persistent dynamically registered tools created on the fly.
        """
        try:
            from .dynamic_tools import get_dynamic_tool_manager
            dtm = get_dynamic_tool_manager()
            tools = dtm.list_tools()
            for dt in tools:
                def make_dynamic_caller(dynamic_tool):
                    def dynamic_action(command=None, context: str = "", history: Optional[List] = None, **kwargs):
                        args = dict(kwargs)
                        if command and hasattr(command, "parameters") and isinstance(command.parameters, dict):
                            args.update(command.parameters)
                        if context and "context" not in args:
                            args["context"] = context
                        return dynamic_tool.execute(**args)
                    dynamic_action.__name__ = dynamic_tool.name
                    dynamic_action.__doc__ = dynamic_tool.description
                    dynamic_action.is_query = True
                    return dynamic_action

                caller = make_dynamic_caller(dt)
                tool = ActionTool(
                    name=dt.name,
                    func=caller,
                    description=dt.description,
                    parameters_schema=dt.parameters_schema,
                    default_params={},
                    requires_context=False,
                    sample_phrases=dt.sample_phrases,
                    plugin_name="dynamic"
                )
                tool.is_query = True
                self.register(tool)
                if self.api and hasattr(self.api, "__actions__") and isinstance(self.api.__actions__, dict):
                    self.api.__actions__[dt.name] = caller

            # Register built-in dynamic tool creator tool
            def create_tool_action(command=None, context: str = "", history: Optional[List] = None, **kwargs):
                args = dict(kwargs)
                if isinstance(command, str) and "command" not in args:
                    args["command"] = command
                elif command and hasattr(command, "parameters") and isinstance(command.parameters, dict):
                    args.update(command.parameters)
                name = args.get("name")
                desc = args.get("description") or args.get("desc") or f"Custom tool {name}"
                cmd_template = args.get("command") or args.get("cmd") or args.get("command_template")
                samples = args.get("sample_phrases") or args.get("samples") or []
                if isinstance(samples, str):
                    samples = [s.strip() for s in samples.split(",") if s.strip()]
                params = args.get("parameters_schema") or args.get("params") or {}
                if isinstance(params, str):
                    import json
                    try:
                        params = json.loads(params)
                    except Exception:
                        params = {}
                if not name or not cmd_template:
                    return {"status": "error", "error": "Both 'name' and 'command' are required"}
                dt = dtm.register(name=name, description=desc, command_template=cmd_template, parameters_schema=params, sample_phrases=samples)
                self.sync_dynamic_tools()
                return {"status": "success", "tool_name": name, "message": f"Tool '{name}' created and saved successfully."}
            create_tool_action.__name__ = "create_tool"
            create_tool_action.is_query = True
            creator_tool = ActionTool(
                name="create_tool",
                func=create_tool_action,
                description="Dynamically creates and permanently registers a new custom tool or command. Executes shell commands or scripts on demand.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Identifier for the new tool (e.g. check_cpu_temp, get_weather)"},
                        "description": {"type": "string", "description": "Explanation of what the tool does"},
                        "command": {"type": "string", "description": "Shell command template to execute, with optional {context} placeholder"},
                        "sample_phrases": {"type": "array", "items": {"type": "string"}, "description": "Sample voice phrases"}
                    },
                    "required": ["name", "command"]
                },
                default_params={},
                requires_context=False,
                sample_phrases=["create a tool", "new tool", "register tool", "создай команду", "создай инструмент"],
                plugin_name="dynamic"
            )
            creator_tool.is_query = True
            self.register(creator_tool)
            if self.api and hasattr(self.api, "__actions__") and isinstance(self.api.__actions__, dict):
                self.api.__actions__["create_tool"] = create_tool_action

            log.info(f"Synchronized {len(tools)} dynamic tools into ToolRegistry (Total tools: {len(self._tools)}).")
        except Exception as e:
            log.warning(f"Error syncing dynamic tools: {e}")



    def execute(self, tool_name: str, parameters: Optional[Dict[str, Any]] = None, context: str = "", history: Optional[List] = None) -> Any:
        tool = self.get(tool_name)
        if not tool:
            log.warning(f"Tool '{tool_name}' not found in registry")
            return None
        return tool.invoke(context=context, history=history, **(parameters or {}))
