import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

log = logging.getLogger("API: agy")


class AgyResponse(str):
    """
    Result string from AgyCaller with metadata indicating if user confirmation is required.
    Acts as a standard string for full backward compatibility.
    """
    def __new__(cls, text: str, needs_confirmation: bool = False, confirmation_prompt: str = "", raw_output: str = ""):
        obj = super().__new__(cls, text)
        obj.needs_confirmation = needs_confirmation
        obj.confirmation_prompt = confirmation_prompt
        obj.raw_output = raw_output or text
        return obj


class AgyCaller:
    """
    Antigravity CLI Caller for Stewart.
    Dispatches user requests through `agy -p` (print mode) powered by Gemini 3.8 Flash Low
    with light thinking effort, running tools and generating spoken plain text answers
    in a single turn. Supports dynamic tool synthesis and voice confirmation detection.
    """
    def __init__(self,
                 command: str = "agy",
                 model: str = "gemini-3.8-flash-low",
                 effort: str = "low",
                 timeout: float = 60.0,
                 dangerously_skip_permissions: bool = False,
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
        """Checks if the agy executable is accessible in PATH."""
        try:
            res = subprocess.run([self.command, "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False

    def clean_text_for_tts(self, text: str) -> str:
        """
        Strips markdown asterisks, backticks, hashes, bullets, and emojis
        so that Kokoro TTS can produce smooth, immediate audio without pronunciation glitches.
        """
        if not text:
            return ""

        # Remove code blocks and inline backticks
        cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        if not cleaned.strip():
            # If removing code blocks left nothing, extract text from within code block (excluding tool_call)
            inner_blocks = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\n?(.*?)```", text, flags=re.DOTALL)
            extracted = []
            for b in inner_blocks:
                b_stripped = b.strip()
                if not b_stripped.startswith("<tool_call>") and not b_stripped.startswith("{"):
                    extracted.append(b_stripped)
            if extracted:
                cleaned = " ".join(extracted)
            else:
                cleaned = text

        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

        # Remove markdown headers (# Header)
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)

        # Remove bold / italic markers (**text**, *text*, __text__, _text_)
        cleaned = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", cleaned)

        # Remove bullet points and list numbers at line starts
        cleaned = re.sub(r"^[\s*\-•]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\d+\.\s+", "", cleaned, flags=re.MULTILINE)

        # Remove markdown links [text](url) -> text
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

        # Remove common unicode emoji ranges
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA70-\U0001FAFF"
            "]+",
            flags=re.UNICODE
        )
        cleaned = emoji_pattern.sub("", cleaned)

        # Collapse whitespace
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        return " ".join(lines).strip()

    def execute_request(self,
                        request: str,
                        confirmed: bool = False,
                        tools: Optional[Any] = None) -> Optional[AgyResponse]:
        """
        Executes agy -p for the user request and returns the clean spoken text response.
        If confirmation is required by safety protocol, returns AgyResponse with needs_confirmation=True.
        Accepts optional tool schemas (list of dicts or pre-formatted string) to provide AGY with full tool knowledge.
        """
        clean_req = request.strip()
        if not clean_req:
            return None

        # Build tools block
        tools_block = ""
        if tools:
            if isinstance(tools, str):
                formatted_tools = tools.strip()
            else:
                from .tools import ToolRegistry
                formatted_tools = ToolRegistry.format_tool_schemas(tools).strip()
            if formatted_tools:
                tools_block = f"\n\nAvailable tools:\n{formatted_tools}"

        # Build prompt: prepend skill slash command if available or reinforce concise plain text
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
            "-p", full_prompt,
            "--model", self.model,
            "--effort", self.effort,
        ]
        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        log.info(f"Dispatching request to agy (model={self.model}, effort={self.effort}): '{clean_req}' (confirmed={confirmed}, tools_count={len(tools) if isinstance(tools, list) else (1 if tools else 0)})")
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
                timeout=self.timeout
            )
            if res.returncode != 0:
                log.warning(f"agy process exited with code {res.returncode}. Stderr: {res.stderr.strip()}")
                # If slash command wasn't found or errored, try without slash command
                if self.skill_name and "slash command" in res.stderr.lower():
                    fallback_prompt = (
                        f"Respond in plain text only without markdown or emojis: {prompt_payload}"
                    )
                    cmd[2] = fallback_prompt
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.cwd, timeout=self.timeout)

            raw_out = res.stdout.strip()
            if not raw_out:
                log.warning(f"agy returned empty output for request '{clean_req}'")
                return None

            # Check if confirmation is required
            conf_match = re.search(r"CONFIRMATION_REQUIRED:\s*(.*)", raw_out, re.IGNORECASE | re.DOTALL)
            if conf_match and not confirmed:
                conf_prompt = conf_match.group(1).strip()
                cleaned_conf = self.clean_text_for_tts(conf_prompt)
                log.info(f"agy requested voice confirmation: '{cleaned_conf}'")
                return AgyResponse(cleaned_conf, needs_confirmation=True, confirmation_prompt=cleaned_conf, raw_output=raw_out)

            cleaned_speech = self.clean_text_for_tts(raw_out)
            log.info(f"agy response generated ({len(cleaned_speech)} chars): '{cleaned_speech}'")
            return AgyResponse(cleaned_speech, needs_confirmation=False, raw_output=raw_out)
        except subprocess.TimeoutExpired:
            log.warning(f"agy request timed out after {self.timeout}s for '{clean_req}'")
            return None
        except Exception as e:
            log.error(f"Error executing agy: {e}", exc_info=True)
            return None

