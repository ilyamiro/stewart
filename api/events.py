import time
from enum import Enum
from datetime import datetime


class Event:
    def __init__(self, event_type: str, details: dict = None):
        if not details:
            details = {}

        self.type = event_type
        self.details = details
        self.timestamp = time.time()

    def gpt(self):
        event_type_str = f"Type: {self.type}"
        timestamp_str = f"Timestamp: {datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
        details_str = "Details:\n"
        for key, value in self.details.items():
            details_str += f"  {key}: {value}\n"

        return f"""{event_type_str}
{timestamp_str}
{details_str}"""


class EventLogger:
    def __init__(self):
        self.history = []

    def record(self, event: Event):
        self.history.append(event)

    def length(self, limit):
        difference = len(self.history) > limit
        if difference:
            self.history = self.history[len(self.history) - limit:]

    def clear(self):
        self.history = []

