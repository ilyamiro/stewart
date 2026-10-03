import re
import datetime
from typing import List, Dict, Optional, Any, Set, Tuple

CONNECTORS = {
    "and", "then", "also", "after", "that", "please", "now", "so", "to",
    "и", "потом", "затем", "также", "пожалуйста", "сейчас", "давай", "чтобы"
}

_PUNCT_TABLE = str.maketrans(
    ",.!?;:()[]{}\"'`~*¿¡",
    "                   "
)


class Command:
    def __init__(self, keywords: List[str], action: str, synonyms: Dict[str, List[str]] = None, responses: List = None,
                 parameters: Dict = None, continues: bool = False, equivalents: List = None, tts: bool = False):
        if synonyms is None:
            synonyms = {}
        if parameters is None:
            parameters = {}
        if responses is None:
            responses = []
        if equivalents is None:
            equivalents = []

        self.keywords = [k.lower().strip() for k in keywords]
        self.synonyms = {k.lower().strip(): [s.lower().strip() for s in v] for k, v in synonyms.items()}
        self.responses = responses
        self.action = action
        self.parameters = parameters
        self.continues = continues
        self.equivalents = equivalents
        self.tts = tts
        self._action_callable = None

        # Precompute set of all words and fast synonym-to-keyword lookup
        self._all_words_set = set(self.keywords)
        self._synonym_to_key_map = {}
        for kw, syns in self.synonyms.items():
            for syn in syns:
                self._all_words_set.add(syn)
                self._synonym_to_key_map[syn] = kw

        # Precompute requirement clusters for fast matching
        self._req_groups = [
            frozenset([kw] + self.synonyms.get(kw, []))
            for kw in self.keywords
        ]
        self._all_req_words = frozenset().union(*self._req_groups) if self._req_groups else frozenset()

    def copy(self, keywords):
        return Command(keywords, self.action, self.synonyms, self.responses, self.parameters, self.continues,
                       tts=self.tts)


class Token:
    __slots__ = ('text', 'clean', 'start_char', 'end_char', 'index')

    def __init__(self, text: str, clean: str, start_char: int, end_char: int, index: int):
        self.text = text
        self.clean = clean
        self.start_char = start_char
        self.end_char = end_char
        self.index = index


class CandidateMatch:
    __slots__ = ('command', 'start', 'end', 'matched_indices', 'in_order', 'k_len', 'span', 'score')

    def __init__(self, command: Command, start: int, end: int, matched_indices: Tuple[int, ...], in_order: bool, k_len: int):
        self.command = command
        self.start = start
        self.end = end
        self.matched_indices = matched_indices
        self.in_order = in_order
        self.k_len = k_len
        self.span = end - start + 1
        # Specificity score: keyword count dominates (1000 per keyword),
        # penalize span (-10 per word), bonus for canonical order (+50)
        self.score = (k_len * 1000) - (self.span * 10) + (50 if in_order else 0)


class Manager:
    def __init__(self):
        self.Command = Command
        self.commands: List[Command] = []
        self._first_keywords = {}
        self._commands_by_first_kw = {}
        self._all_first_words = set()
        self._all_known_words: Set[str] = set()
        self._word_to_cmd_indices: Dict[str, List[int]] = {}
        self._query_cache: Dict[str, List] = {}

    def _rebuild_index(self):
        self._first_keywords = {}
        self._commands_by_first_kw = {}
        self._all_first_words = set()
        self._all_known_words = set()
        self._word_to_cmd_indices = {}
        self._query_cache.clear()

        for idx, command in enumerate(self.commands):
            first_kw = command.keywords[0]
            self._first_keywords[first_kw] = command
            self._all_first_words.add(first_kw)
            self._commands_by_first_kw.setdefault(first_kw, []).append(command)

            for synonym in command.synonyms.get(first_kw, []):
                self._first_keywords[synonym] = command
                self._all_first_words.add(synonym)
                self._commands_by_first_kw.setdefault(synonym, []).append(command)

            for word in command._all_req_words:
                self._all_known_words.add(word)
                self._word_to_cmd_indices.setdefault(word, []).append(idx)

    def add(self, *commands: Command):
        """
        Add one or more Command instances to the manager.
        """
        changed = False
        for command in commands:
            if isinstance(command, Command):
                for cmd in self.commands[:]:
                    if cmd.keywords == command.keywords:
                        self.commands.remove(cmd)
                self.commands.append(command)
                for equivalent in command.equivalents:
                    self.commands.append(command.copy(equivalent))
                changed = True
            else:
                raise TypeError(f"Expected Command instance, got {type(command).__name__}")
        if changed:
            self._rebuild_index()

    def construct_recognizer_string(self):
        words = []
        for command in self.commands:
            words.extend(command.keywords)
            for synonyms in command.synonyms.values():
                words.extend(synonyms)
        return " ".join(set(words))

    @staticmethod
    def _tokenize(request: str) -> List[Token]:
        tokens = []
        # Find all words ignoring surrounding punctuation
        for m in re.finditer(r"[^\s,!?;:()[\]{}\"'`~*.]+", request):
            text = m.group(0)
            clean = text.lower()
            tokens.append(Token(text, clean, m.start(), m.end(), len(tokens)))
        return tokens

    def find(self, request: str):
        cached = self._query_cache.get(request)
        if cached is not None:
            return [[c[0], c[1]] for c in cached]

        if not request or not request.strip():
            return []

        tokens = self._tokenize(request)
        if not tokens:
            return []

        query_words = set(t.clean for t in tokens)
        if query_words.isdisjoint(self._all_known_words):
            if len(self._query_cache) < 1000:
                self._query_cache[request] = []
            return []

        # Find candidate commands whose requirement groups are all present in query_words
        candidate_cmd_indices = set()
        for w in query_words:
            if w in self._word_to_cmd_indices:
                candidate_cmd_indices.update(self._word_to_cmd_indices[w])

        candidates: List[CandidateMatch] = []
        max_gap = 4

        for cmd_idx in candidate_cmd_indices:
            cmd = self.commands[cmd_idx]
            req_groups = cmd._req_groups
            k_len = len(req_groups)

            # Check if all requirement groups have at least one matching token
            pos_lists = []
            possible = True
            for group in req_groups:
                positions = [t.index for t in tokens if t.clean in group]
                if not positions:
                    possible = False
                    break
                pos_lists.append(positions)

            if not possible:
                continue

            if k_len == 1:
                for p in pos_lists[0]:
                    candidates.append(CandidateMatch(cmd, p, p, (p,), True, 1))

            elif k_len == 2:
                for p0 in pos_lists[0]:
                    for p1 in pos_lists[1]:
                        if p0 == p1:
                            continue
                        gap = abs(p0 - p1) - 1
                        if gap > max_gap:
                            continue
                        start = min(p0, p1)
                        end = max(p0, p1)
                        in_order = (p0 < p1)
                        candidates.append(CandidateMatch(cmd, start, end, (p0, p1), in_order, 2))

            elif k_len == 3:
                for p0 in pos_lists[0]:
                    for p1 in pos_lists[1]:
                        if p0 == p1:
                            continue
                        for p2 in pos_lists[2]:
                            if p2 == p0 or p2 == p1:
                                continue
                            indices = (p0, p1, p2)
                            start = min(indices)
                            end = max(indices)
                            span = end - start + 1
                            if span - 3 > max_gap * 2:
                                continue
                            in_order = (p0 < p1 < p2)
                            candidates.append(CandidateMatch(cmd, start, end, indices, in_order, 3))

            else:
                def search_comb(group_idx, current_indices):
                    if group_idx == k_len:
                        start = min(current_indices)
                        end = max(current_indices)
                        span = end - start + 1
                        if span - k_len <= max_gap * (k_len - 1):
                            in_order = all(current_indices[i] < current_indices[i + 1] for i in range(k_len - 1))
                            candidates.append(CandidateMatch(cmd, start, end, tuple(current_indices), in_order, k_len))
                        return
                    for p in pos_lists[group_idx]:
                        if p not in current_indices:
                            search_comb(group_idx + 1, current_indices + [p])

                search_comb(0, [])

        if not candidates:
            if len(self._query_cache) < 1000:
                self._query_cache[request] = []
            return []

        # Sort candidates by end index, then by score descending
        candidates.sort(key=lambda c: (c.end, -c.score))

        # Dynamic Programming for Weighted Non-Overlapping Intervals
        n = len(candidates)
        dp: List[Tuple[float, List[CandidateMatch]]] = [(0, [])] * (n + 1)

        for i in range(1, n + 1):
            curr = candidates[i - 1]
            curr_indices_set = set(curr.matched_indices)

            # Option 1: Do not include candidate curr
            best_without = dp[i - 1]

            # Option 2: Include candidate curr; find best non-overlapping predecessor
            best_prev_score = 0
            best_prev_list = []
            for j in range(i - 1, 0, -1):
                prev_cands = dp[j][1]
                overlap = False
                for p in prev_cands:
                    if not set(p.matched_indices).isdisjoint(curr_indices_set):
                        overlap = True
                        break
                    if max(p.start, curr.start) <= min(p.end, curr.end):
                        overlap = True
                        break
                if not overlap:
                    if dp[j][0] > best_prev_score:
                        best_prev_score = dp[j][0]
                        best_prev_list = prev_cands

            with_score = curr.score + best_prev_score
            with_list = best_prev_list + [curr]

            if with_score > best_without[0]:
                dp[i] = (with_score, with_list)
            else:
                dp[i] = best_without

        selected = dp[n][1]
        selected.sort(key=lambda c: c.start)

        final_results = []
        m = len(selected)

        for i, match in enumerate(selected):
            cmd = match.command
            next_start = selected[i + 1].start if i + 1 < m else len(tokens)

            subsequent_words = [tokens[idx] for idx in range(match.end + 1, next_start)]

            # If there's a next command, strip trailing connector words before the next command
            if i + 1 < m:
                while subsequent_words and subsequent_words[-1].clean in CONNECTORS:
                    subsequent_words.pop()

            if cmd.continues:
                while subsequent_words and subsequent_words[0].clean in CONNECTORS:
                    subsequent_words.pop(0)
                payload_words = [t.text for t in subsequent_words]
                context_str = " ".join(payload_words).strip()
            else:
                filtered = [t for t in subsequent_words if t.clean not in CONNECTORS]
                clean_words = [t.clean for t in filtered]
                common_noise = {
                    "right", "now", "the", "a", "an", "please", "just", "for",
                    "thank", "you", "so", "much", "thanks", "very",
                    "сейчас", "прямо", "пожалуйста", "спасибо", "большое"
                }
                if not filtered or all(w in common_noise for w in clean_words):
                    context_str = ""
                else:
                    context_str = " ".join(t.text for t in filtered).strip()

            final_results.append([cmd, context_str])

        if len(self._query_cache) < 1000:
            self._query_cache[request] = [[c[0], c[1]] for c in final_results]

        return final_results

    @staticmethod
    def is_constructed(keywords, constructed, synonyms):
        if len(constructed) > len(keywords):
            return False

        for i, sub_item in enumerate(constructed):
            main_item = keywords[i]
            if sub_item != main_item and sub_item not in synonyms.get(main_item, []):
                return False

        return True

    @staticmethod
    def map_words_to_indexes(words, word_list):
        word_map = {}
        for index in range(len(words) - 1, -1, -1):
            w = words[index]
            if w in word_list:
                word_map[index] = w
        return word_map

    def get_matching_commands(self, keywords):
        if not keywords:
            return self.commands
        first = keywords[0]
        candidates = self._commands_by_first_kw.get(first, [])
        if not candidates:
            return []
        if len(keywords) == 1:
            return candidates
        commands = []
        for cmd in candidates:
            if self.is_constructed(cmd.keywords, keywords, cmd.synonyms):
                commands.append(cmd)

        return commands

