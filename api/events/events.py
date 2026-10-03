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

