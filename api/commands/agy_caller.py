import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

log = logging.getLogger("API: agy")


class AgyResponse(str):
    def __new__(cls, text: str, needs_confirmation: bool = False, confirmation_prompt: str = "", raw_output: str = ""):
        obj = super().__new__(cls, text)
        obj.needs_confirmation = needs_confirmation
        obj.confirmation_prompt = confirmation_prompt
        obj.raw_output = raw_output or text
        return obj


def format_tool_activity(tool_name: str, params: dict, state: str) -> tuple[str, str]:
    p = params or {}
    called_mcp_tool = None
    server_name = None
    action_desc = None

    if tool_name in ("call_mcp_tool", "mcp_call_tool", "call_tool"):
        called_mcp_tool = (
            p.get("ToolName")
            or p.get("tool_name")
            or p.get("tool")
            or p.get("name")
            or p.get("target_tool")
        )
        server_name = p.get("ServerName") or p.get("server_name") or p.get("server")
        raw_args = p.get("Arguments") or p.get("arguments") or p.get("args") or p.get("parameters") or {}
        action_desc = p.get("toolAction") or p.get("tool_action")

        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    p = parsed
            except Exception:
                p = {}
        elif isinstance(raw_args, dict):
            p = raw_args

        if called_mcp_tool:
            tool_name = str(called_mcp_tool).strip('"\'')
        else:
            act_text = str(action_desc).strip('"\'') if action_desc else (
                f"Calling MCP ({str(server_name).strip('\"\'')})" if server_name else "Calling MCP tool"
            )
            return ("⚙️", act_text)

    if tool_name.startswith("mcp_") and tool_name not in ("mcp_call_tool",):
        parts = tool_name.split("_", 2)
        if len(parts) == 3:
            tool_name = parts[2]

    act = ""
    emoji = "⚙️"

    if tool_name == "studieplus_get_schedule":
        d = p.get("date", "today")
        act = f"Checking schedule ({d})"
        emoji = "📅"
    elif tool_name == "studieplus_get_assignments":
        subj = p.get("subject")
        act = f"Checking {subj + ' ' if subj else ''}assignments"
        emoji = "📝"
    elif tool_name == "studieplus_get_conversations":
        act = "Checking school messages"
        emoji = "💬"
    elif tool_name == "studieplus_check_session":
        act = "Verifying school session"
        emoji = "🔑"
    elif tool_name == "study_get_ib_resources":
        subj = p.get("subject", "IB")
        act = f"Searching {subj} past papers"
        emoji = "📚"
    elif tool_name == "study_prepare_test":
        subj = p.get("subject", "exam")
        act = f"Preparing {subj} revision & topics"
        emoji = "🎯"
    elif tool_name == "study_get_past_topics":
        subj = p.get("subject", "syllabus")
        act = f"Reviewing {subj} topics"
        emoji = "📖"
    elif tool_name == "gmail_search_emails":
        q = p.get("query")
        act = f"Searching emails{f' ({q})' if q else ''}"
        emoji = "✉️"
    elif tool_name == "gmail_get_email":
        act = "Reading email"
        emoji = "📨"
    elif tool_name == "gmail_send_email":
        to = p.get("to", "recipient")
        act = f"Sending email to {to}"
        emoji = "📤"
    elif tool_name == "gmail_check_status":
        act = "Checking Gmail inbox"
        emoji = "📬"
    elif tool_name == "telegram_get_unread":
        act = "Checking unread Telegram messages"
        emoji = "💬"
    elif tool_name == "telegram_get_dialogs":
        act = "Checking Telegram chats"
        emoji = "💬"
    elif tool_name == "telegram_get_messages":
        act = "Reading conversation history"
        emoji = "💬"
    elif tool_name == "telegram_send_message":
        act = "Sending Telegram message"
        emoji = "✉️"
    elif tool_name in ("telegram_send_voice_message", "tts_synthesize"):
        act = "Synthesizing voice response"
        emoji = "🎙️"
    elif tool_name == "calendar_list_events":
        act = "Checking Google Calendar"
        emoji = "📆"
    elif tool_name in ("calendar_create_event", "calendar_quick_add"):
        s = p.get("summary") or p.get("text")
        act = f"Scheduling event{f' ({s})' if s else ''}"
        emoji = "🗓️"
    elif tool_name in ("gdrive_search_files", "gdrive_list_files"):
        q = p.get("name_contains") or p.get("query")
        act = f"Searching Google Drive{f' ({q})' if q else ''}"
        emoji = "📁"
    elif tool_name == "gdrive_download_file":
        act = "Downloading Drive file"
        emoji = "⬇️"
    elif tool_name == "gdrive_upload_file":
        act = "Uploading file to Google Drive"
        emoji = "⬆️"
    elif tool_name == "github_list_repos":
        act = "Checking GitHub repositories"
        emoji = "🐙"
    elif tool_name == "github_list_issues":
        repo = p.get("repo")
        act = f"Checking GitHub issues{f' in {repo}' if repo else ''}"
        emoji = "🐙"
    elif tool_name == "weather_get_forecast":
        act = "Checking weather forecast"
        emoji = "🌤️"
    elif tool_name == "vision_analyze_image":
        act = "Analyzing image content"
        emoji = "🖼️"
    elif tool_name == "vision_extract_text":
        act = "Extracting text via OCR"
        emoji = "🔍"
    elif tool_name == "youtube_search":
        q = p.get("query")
        act = f"Searching YouTube{f' ({q})' if q else ''}"
        emoji = "📺"
    elif tool_name == "youtube_get_transcript":
        act = "Fetching YouTube transcript"
        emoji = "📺"
    elif tool_name in ("system_control", "system_ipc"):
        act_name = p.get("command") or f"{p.get('action', 'desktop')} {p.get('target', '')}".strip()
        act = f"Desktop IPC: {act_name}"
        emoji = "🖥️"
    elif tool_name == "run_command":
        cmd = p.get("CommandLine", "")
        cmd_short = cmd[:35] + ("..." if len(cmd) > 35 else "")
        act = f"Running command{f' (`{cmd_short}`)' if cmd_short else ''}"
        emoji = "⚡"
    else:
        clean = (
            tool_name.replace("studieplus_", "")
            .replace("telegram_", "")
            .replace("study_", "")
            .replace("gmail_", "")
            .replace("github_", "")
            .replace("gdrive_", "")
            .replace("calendar_", "")
            .replace("youtube_", "")
            .replace("_", " ")
            .capitalize()
        )
        act = action_desc or clean
        emoji = "⚙️"

    return (emoji, act)


class AgyCaller:
    def __init__(self,
                 command: str = "agy",
                 model: str = "gemini-3.8-flash-low",
                 effort: str = "low",
                 timeout: float = 60.0,
                 dangerously_skip_permissions: bool = True,
                 skill_name: Optional[str] = "stewart-voice",
                 cwd: Optional[str] = None):
        self.command = command
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.dangerously_skip_permissions = dangerously_skip_permissions
        self.skill_name = skill_name
        self.cwd = cwd or str(Path(__file__).resolve().parent.parent.parent)

    def is_available(self) -> bool:
        try:
            res = subprocess.run([self.command, "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False

    def clean_text_for_tts(self, text: str) -> str:
        if not text:
            return ""

        cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        if not cleaned.strip():
            inner_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\n?(.*?)```", text, flags=re.DOTALL)
            extracted = []
            for b in inner_blocks:
                b_stripped = b.strip()
                if not b_stripped.startswith("<tool_call>") and not b_stripped.startswith("{"):
                    extracted.append(b_stripped)
            cleaned = " ".join(extracted) if extracted else text

        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", cleaned)
        cleaned = re.sub(r"^[\s*\-•]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\d+\.\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"
            "\U0001FA70-\U0001FAFF"
            "]+",
            flags=re.UNICODE
        )
        cleaned = emoji_pattern.sub("", cleaned)
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        return " ".join(lines).strip()

    def execute_request(self,
                        request: str,
                        confirmed: bool = False,
                        tools: Optional[Any] = None) -> Optional[AgyResponse]:
        clean_req = request.strip()
        if not clean_req:
            return None

        tools_block = ""
        if tools:
            if isinstance(tools, str):
                formatted_tools = tools.strip()
            else:
                from .tools import ToolRegistry
                formatted_tools = ToolRegistry.format_tool_schemas(tools).strip()
            if formatted_tools:
                tools_block = f"\n\nAvailable tools:\n{formatted_tools}"

        if confirmed:
            prompt_payload = f"The user has confirmed proceeding with this action via voice. Execute and complete: {clean_req}"
        else:
            prompt_payload = clean_req

        if self.skill_name:
            full_prompt = f"/{self.skill_name} {prompt_payload}{tools_block}"
        else:
            full_prompt = (
                f"You are Stewart. Respond in plain speech text only (1-2 sentences), "
                f"no markdown, no emojis, no artifacts. Execute any needed tools and respond directly: {prompt_payload}{tools_block}"
            )

        cmd = [
            self.command,
            "--model", self.model,
            "--effort", self.effort,
            "--output-format", "stream-json",
            "-p", full_prompt
        ]
        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        log.info(f"Dispatching request to agy (model={self.model}): '{clean_req}'")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
                bufsize=1
            )

            raw_collected = []
            final_response = ""
            active_tool_displayed = False

            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue

                try:
                    ev = json.loads(line_str)
                except Exception:
                    continue

                event_type = ev.get("event")

                if event_type == "step_update":
                    su = ev.get("step_update", {})
                    stype = su.get("step_type")
                    sstate = su.get("state")

                    if stype == "tool":
                        tname = su.get("tool_name", "") or su.get("name", "")
                        tinfo = su.get("tool_info", {})
                        tparams = {}
                        if isinstance(tinfo, dict):
                            tparams = tinfo.get("parameters") or tinfo.get("args") or tinfo.get("arguments") or {}
                        if not tparams:
                            tparams = su.get("parameters") or su.get("args") or {}
                        if isinstance(tparams, str):
                            try:
                                tparams = json.loads(tparams)
                            except Exception:
                                tparams = {}

                        emoji, act_desc = format_tool_activity(tname, tparams, sstate)
                        if sstate == "ACTIVE":
                            sys.stdout.write(f"\r\033[K⏳ {emoji} {act_desc}...")
                            sys.stdout.flush()
                            active_tool_displayed = True
                        elif sstate == "DONE":
                            sys.stdout.write(f"\r\033[K✓ {emoji} {act_desc}\n")
                            sys.stdout.flush()
                            active_tool_displayed = False

                    elif stype == "agent_response":
                        delta = su.get("text_delta")
                        if delta:
                            raw_collected.append(delta)

                elif event_type == "result":
                    res = ev.get("result", {})
                    final_response = res.get("response", "")

            proc.wait(timeout=self.timeout)

            if active_tool_displayed:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()

            if not final_response and raw_collected:
                final_response = "".join(raw_collected).strip()

            if not final_response:
                return None

            conf_match = re.search(r"CONFIRMATION_REQUIRED:\s*(.*)", final_response, re.IGNORECASE | re.DOTALL)
            if conf_match and not confirmed:
                conf_prompt = conf_match.group(1).strip()
                cleaned_conf = self.clean_text_for_tts(conf_prompt)
                return AgyResponse(cleaned_conf, needs_confirmation=True, confirmation_prompt=cleaned_conf, raw_output=final_response)

            cleaned_speech = self.clean_text_for_tts(final_response)
            if cleaned_speech:
                print(f'Stewart: "{cleaned_speech}"')
            return AgyResponse(cleaned_speech, needs_confirmation=False, raw_output=final_response)
        except subprocess.TimeoutExpired:
            log.warning(f"agy request timed out after {self.timeout}s for '{clean_req}'")
            return None
        except Exception as e:
            log.error(f"Error executing agy: {e}", exc_info=True)
            return None
