"""
Session Memory & Situational Context Tracker for Stewart.
Maintains a lightweight, sliding-window persistent context of recent user/assistant turns
and real-time Hyprland window/desktop telemetry for zero-overhead situational awareness.
"""
import time
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger("API: session_memory")


class SessionMemory:
    """
    Tracks recent conversational turns and active desktop context.
    Ensures Qwen can resolve situational follow-ups (e.g. 'open youtube' -> 'open search')
    without exceeding tight token/latency budgets (<80 tokens of history).
    """
    _instance: Optional["SessionMemory"] = None

    def __init__(self, ttl_seconds: float = 90.0, max_turns: int = 2):
        self.ttl_seconds = ttl_seconds
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = []
        self.last_interaction_time: float = 0.0
        self.active_context_hint: str = ""

    @classmethod
    def get_instance(cls) -> "SessionMemory":
        if cls._instance is None:
            cls._instance = SessionMemory()
        return cls._instance

    def clear(self):
        """Clears the conversational context."""
        self.history.clear()
        self.active_context_hint = ""
        self.last_interaction_time = 0.0

    def check_expiration(self):
        """Resets history if inactivity exceeds TTL."""
        if self.last_interaction_time > 0:
            if time.time() - self.last_interaction_time > self.ttl_seconds:
                log.debug("Session memory expired due to inactivity. Clearing context.")
                self.clear()

    def get_active_window_hint(self, desktop_service=None) -> str:
        """Inspects Hyprland active window to get real-time context hint."""
        if desktop_service is None:
            from api.services.desktop import get_desktop_service
            desktop_service = get_desktop_service()

        win_info = desktop_service.get_active_window() if desktop_service else {}
        if win_info:
            cls_name = win_info.get("class", "").strip()
            title = win_info.get("title", "").strip()
            if cls_name or title:
                # Keep hint short and informative
                short_title = title[:30] if title else cls_name
                return f"{cls_name} ({short_title})" if cls_name and cls_name.lower() not in short_title.lower() else short_title
        return self.active_context_hint

    def get_rolling_messages(self, current_user_request: str, desktop_service=None) -> List[Dict[str, str]]:
        """
        Builds the conversation messages array for Qwen chat template.
        Includes at most 1-2 prior turns, plus the current user request.
        """
        self.check_expiration()
        messages: List[Dict[str, str]] = []

        # Include prior turns if within TTL
        for turn in self.history[- (self.max_turns * 2):]:
            messages.append(turn)

        messages.append({"role": "user", "content": current_user_request})
        return messages

    def record_turn(self, user_request: str, assistant_tool_call: str):
        """
        Saves a completed turn (user query and model tool call / response).
        """
        self.check_expiration()
        self.history.append({"role": "user", "content": user_request.strip()})
        self.history.append({"role": "assistant", "content": assistant_tool_call.strip()})

        # Cap history to max_turns * 2 entries
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-(self.max_turns * 2):]

        self.last_interaction_time = time.time()

        # Update context hint if tool call was web/app/file
        import re
        match = re.search(r'"(?:url|name|path)":\s*"([^"]+)"', assistant_tool_call)
        if match:
            self.active_context_hint = match.group(1)
