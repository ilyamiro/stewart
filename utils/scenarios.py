import re
from typing import List, Callable, Union, Optional


class Trigger:
    def __init__(self, keywords: List[str], callback: Optional[Callable] = None):
        self.keywords = keywords
        self.callback = blank if callback is None else callback

    def blank(self, request):
        pass

    def match(self, request: str) -> bool:
        request_lower = request.lower()
        pattern = r'\b({0})\b'.format('|'.join(re.escape(kw) for kw in self.keywords))
        matches = re.findall(pattern, request_lower)

        if len(matches) == len(self.keywords):
            keyword_indices = [request_lower.index(match) for match in matches]
            return all(keyword_indices[i] < keyword_indices[i + 1] for i in range(len(keyword_indices) - 1))

        return False


class Timeline:
    def __init__(self, timeline_structure: List[Union[List, 'Timeline']]):
        self.timeline_structure = timeline_structure
        self.current_group_index = 0
        self.current_trigger_index = 0

    def get_current_triggers(self):
        return self.timeline_structure[self.current_group_index]

    def advance(self):
        self.current_group_index += 1
        self.current_trigger_index = 0

    def reset(self):
        self.current_group_index = 0
        self.current_trigger_index = 0


class Scenario:
    def __init__(self, name: str, timeline: Timeline, max_gap: int = 3):
        self.name = name
        self.timeline = timeline
        self.max_gap = max_gap
        self.active = False
        self.request_since_last_trigger = 0

    def check_scenario(self, request: str, request_history: List[str]) -> bool:
        if not self.active:
            start_triggers = self.timeline.get_current_triggers()
            for trigger in start_triggers:
                if isinstance(trigger, Trigger) and trigger.match(request):
                    self.active = True
                    self.request_since_last_trigger = 0
                    if trigger.callback:
                        trigger.callback(request)
                    self.timeline.advance()
                    return True
            return False

        current_triggers = self.timeline.get_current_triggers()
        self.request_since_last_trigger += 1

        if self.request_since_last_trigger > self.max_gap:
            self.active = False
            self.timeline.reset()
            return False

        for trigger in current_triggers:
            if isinstance(trigger, Trigger) and trigger.match(request):
                self.request_since_last_trigger = 0
                if trigger.callback:
                    trigger.callback(request)
                self.timeline.advance()
                return True

            elif isinstance(trigger, Timeline):
                sub_scenario = Scenario(trigger, self.max_gap)
                if sub_scenario.check_scenario(request, request_history):
                    return True

        return True

