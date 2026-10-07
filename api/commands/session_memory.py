import time
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger("API: session_memory")


class SessionMemory:
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
        self.history.clear()
        self.active_context_hint = ""
        self.last_interaction_time = 0.0

    def check_expiration(self):
        if self.last_interaction_time > 0:
            if time.time() - self.last_interaction_time > self.ttl_seconds:
                self.clear()

    def get_active_window_hint(self, desktop_service=None) -> str:
        if desktop_service is None:
            from api.services.desktop import get_desktop_service
            desktop_service = get_desktop_service()

        win_info = desktop_service.get_active_window() if desktop_service else {}
        if win_info:
            cls_name = win_info.get("class", "").strip()
            title = win_info.get("title", "").strip()
            if cls_name or title:
                short_title = title[:30] if title else cls_name
                return f"{cls_name} ({short_title})" if cls_name and cls_name.lower() not in short_title.lower() else short_title
        return self.active_context_hint

    def get_rolling_messages(self, current_user_request: str, desktop_service=None) -> List[Dict[str, str]]:
        self.check_expiration()
        messages: List[Dict[str, str]] = []

        for turn in self.history[- (self.max_turns * 2):]:
            messages.append(turn)

        messages.append({"role": "user", "content": current_user_request})

        window_hint = self.get_active_window_hint(desktop_service)
        if window_hint:
            context_prefix = f"[Active Window: {window_hint}]\n"
            messages[-1]["content"] = context_prefix + current_user_request

        return messages

    def record_turn(self, user_request: str, assistant_response: str):
        self.check_expiration()
        clean_user = user_request.strip()
        clean_resp = assistant_response.strip()

        if clean_user and clean_resp:
            self.history.append({"role": "user", "content": clean_user})
            self.history.append({"role": "assistant", "content": clean_resp})
            self.last_interaction_time = time.time()

            if len(self.history) > (self.max_turns * 2):
                self.history = self.history[- (self.max_turns * 2):]
