import re
import inspect

from typing import List, Callable, Union, Optional, Dict


class Trigger:
    """
    Trigger class, reacts to keywords and executes a callback inside of a timeline.
    Can and should be used together with commands.
    """
    def __init__(self,
                 keywords: List[str],
                 callback: Optional[Callable] = None,
                 synonyms: Dict[str, List[str]] = None,
                 equivalents: List[List[str]] = None):
        self.keywords = keywords
        self.synonyms = synonyms if synonyms is not None else {}
        self.equivalents = equivalents if equivalents is not None else []
        self.callback = self.blank if callback is None else callback
        self.keyword_combinations = self._generate_keyword_combinations()

    def blank(self, request):
        pass

    def _generate_keyword_combinations(self) -> List[List[str]]:
        """
        Generates all possible keyword combinations a trigger could react to
        """
        def generate_combinations(current_keywords: List[str], keyword_index: int) -> List[List[str]]:
            if keyword_index >= len(current_keywords):
                return [current_keywords.copy()]

            combinations = []
            current_word = current_keywords[keyword_index]
            words_to_try = [current_word]

            if current_word in self.synonyms:
                words_to_try.extend(self.synonyms[current_word])

            for word in words_to_try:
                current_keywords[keyword_index] = word
                combinations.extend(generate_combinations(current_keywords, keyword_index + 1))

            current_keywords[keyword_index] = current_word
            return combinations

        base_combinations = generate_combinations(self.keywords.copy(), 0)
        all_combinations = base_combinations.copy()
        for equivalent in self.equivalents:
            all_combinations.extend(generate_combinations(equivalent.copy(), 0))

        return all_combinations

    def match(self, request: str) -> bool:
        """
        Checks whether the trigger keywords match the user request
        """
        request_lower = request.lower()

        for keyword_set in self.keyword_combinations:
            if self._match_keywords(request_lower, keyword_set):
                return True

        return False

    @staticmethod
    def _match_keywords(request_lower: str, keywords: List[str]) -> bool:
        """
        Checks matches of all the possible keyword combinations with a request
        """
        pattern = r'\b({0})\b'.format('|'.join(re.escape(kw) for kw in keywords))
        matches = re.findall(pattern, request_lower)
        if len(matches) == len(keywords):
            keyword_indices = [request_lower.index(match) for match in matches]
            return all(keyword_indices[i] < keyword_indices[i + 1] for i in range(len(keyword_indices) - 1))
        return False


class Timeline:
    def __init__(self, timeline_structure: List[Union[List, 'Timeline']]):
        self.timeline_structure = timeline_structure
        self.current_group_index = 0
        self.current_trigger_index = 0

    def is_complete(self) -> bool:
        """
        Check if we've reached the end of the timeline
        """
        return self.current_group_index >= len(self.timeline_structure)

    def get_current_triggers(self):
        """
        Get current triggers or return empty list if timeline is complete
        """
        if self.is_complete():
            return []
        return self.timeline_structure[self.current_group_index]

    def advance(self):
        """
        Advance the timeline, but don't exceed its length
        """
        self.current_group_index += 1
        self.current_trigger_index = 0

    def reset(self):
        """
        Reset timeline to initial state
        """
        self.current_group_index = 0
        self.current_trigger_index = 0


class Scenario:
    def __init__(self, name: str, timeline: Timeline, max_gap: int = 3):
        self.name = name
        self.timeline = timeline if timeline is not None else Timeline([])
        self.max_gap = max_gap
        self.active = False
        self.request_since_last_trigger = 0

    @staticmethod
    def _call_callback(callback, request):
        """
        Checks what arguments does the active trigger callback accept
        """
        sig = inspect.signature(callback)
        params = sig.parameters

        accepts_positional = False
        accepts_kwargs = False
        no_params = len(params) == 0

        for p in params.values():
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                accepts_positional = True
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                accepts_kwargs = True

        if accepts_positional:
            callback(request)
        elif accepts_kwargs:
            callback(request=request)
        elif no_params:
            callback()
        else:
            callback(request)

    def check_scenario(self, request: str, request_history) -> bool:
        """
        Checks whether the user request activates the scenario
        """
        request_history = [event.details.get("request") for event in request_history]
        if not self.active:
            start_triggers = self.timeline.get_current_triggers()
            for trigger in start_triggers:
                if isinstance(trigger, Trigger) and trigger.match(request):
                    self.active = True
                    self.request_since_last_trigger = 0
                    if trigger.callback:
                        self._call_callback(trigger.callback, request)
                    self.timeline.advance()
                    return True
            return False

        if self.timeline.is_complete():
            self.active = False
            self.timeline.reset()
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
                    self._call_callback(trigger.callback, request)
                self.timeline.advance()
                return True
            elif isinstance(trigger, Timeline):
                sub_scenario = Scenario("sub", trigger, self.max_gap)
                if sub_scenario.check_scenario(request, request_history):
                    return True
        return True
