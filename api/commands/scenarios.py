import re
import inspect
from typing import List, Callable, Union, Optional, Dict, Any, Set


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
        self.keywords = [k.lower().strip() for k in keywords]
        self.synonyms = {k.lower().strip(): [s.lower().strip() for s in v] for k, v in (synonyms or {}).items()}
        self.equivalents = [[k.lower().strip() for k in eq] for eq in (equivalents or [])]
        self.callback = self.blank if callback is None else callback

        # Build requirement clusters for fast set-based matching without regex combinatorial explosion
        self._patterns: List[List[frozenset]] = []
        primary_pattern = [
            frozenset([kw] + self.synonyms.get(kw, []))
            for kw in self.keywords
        ]
        self._patterns.append(primary_pattern)

        for eq in self.equivalents:
            eq_pattern = [
                frozenset([kw] + self.synonyms.get(kw, []))
                for kw in eq
            ]
            self._patterns.append(eq_pattern)

        self._cached_keyword_combinations = None

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

    @property
    def keyword_combinations(self) -> List[List[str]]:
        if self._cached_keyword_combinations is None:
            self._cached_keyword_combinations = self._generate_keyword_combinations()
        return self._cached_keyword_combinations

    def match(self, request: str) -> bool:
        """
        Checks whether the trigger keywords match the user request.
        Handles duplicate words, punctuation, and flexible word order reliably.
        """
        tokens = [t.lower() for t in re.findall(r"[^\s,!?;:()[\]{}\"'`~*.]+", request)]
        if not tokens:
            return False

        for pattern in self._patterns:
            k_len = len(pattern)
            pos_lists = []
            possible = True
            for cluster in pattern:
                matches = [i for i, t in enumerate(tokens) if t in cluster]
                if not matches:
                    possible = False
                    break
                pos_lists.append(matches)

            if not possible:
                continue

            if k_len == 1:
                return True
            elif k_len == 2:
                for p0 in pos_lists[0]:
                    for p1 in pos_lists[1]:
                        if p0 != p1:
                            return True
            else:
                def can_match(cluster_idx: int, used_indices: Set[int]) -> bool:
                    if cluster_idx == k_len:
                        return True
                    for p in pos_lists[cluster_idx]:
                        if p not in used_indices:
                            used_indices.add(p)
                            if can_match(cluster_idx + 1, used_indices):
                                return True
                            used_indices.remove(p)
                    return False

                if can_match(0, set()):
                    return True

        return False

    @staticmethod
    def _match_keywords(request_lower: str, keywords: List[str]) -> bool:
        """
        Checks matches of all the possible keyword combinations with a request
        """
        tokens = [t.lower() for t in re.findall(r"[^\s,!?;:()[\]{}\"'`~*.]+", request_lower)]
        req_set = set(keywords)
        matched = set()
        for t in tokens:
            if t in req_set:
                matched.add(t)
        return len(matched) == len(req_set)


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
        Checks whether the user request activates the scenario or advances it.
        """
        if self.timeline.is_complete():
            self.active = False
            self.timeline.reset()
            return False

        current_triggers = self.timeline.get_current_triggers()

        # Check if any trigger in the current step matches
        matched_trigger = None
        for trigger in current_triggers:
            if isinstance(trigger, Trigger) and trigger.match(request):
                matched_trigger = trigger
                break
            elif isinstance(trigger, Timeline):
                sub_scenario = Scenario("sub", trigger, self.max_gap)
                if sub_scenario.check_scenario(request, request_history):
                    matched_trigger = trigger
                    break

        if matched_trigger is not None:
            self.active = True
            self.request_since_last_trigger = 0
            if isinstance(matched_trigger, Trigger) and matched_trigger.callback:
                self._call_callback(matched_trigger.callback, request)
            self.timeline.advance()

            # If the timeline has reached completion after this step:
            if self.timeline.is_complete():
                self.active = False
                self.timeline.reset()
            return True

        # If it did not match:
        if not self.active:
            return False

        # If already active, count this as an intervening gap request:
        self.request_since_last_trigger += 1
        if self.request_since_last_trigger > self.max_gap:
            self.active = False
            self.timeline.reset()
            return False

        return True

