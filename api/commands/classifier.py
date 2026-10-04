import os
import re
import json
import random
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Set

log = logging.getLogger("API: classifier")

try:
    import spacy
    from spacy.training import Example
    SPACY_AVAILABLE = True
except ImportError:
    spacy = None
    Example = None
    SPACY_AVAILABLE = False


POLAR_ANTONYM_PAIRS = [
    # Russian verbs & opposites
    (
        frozenset(["закрой", "закрыть", "закрывай", "заверши", "останови", "удали"]),
        frozenset(["открой", "открыть", "открывай", "запусти", "создай", "включи"])
    ),
    (
        frozenset(["выключи", "выключить", "выключай", "погаси", "отключи", "заглуши"]),
        frozenset(["включи", "включить", "включай", "зажги", "активируй", "запусти"])
    ),
    (
        frozenset(["тише", "убавь", "убавить", "убавляй", "понизь", "уменьши", "уменьшить"]),
        frozenset(["громче", "прибавь", "прибавить", "прибавляй", "повысь", "увеличь", "увеличить"])
    ),
    # English verbs & opposites
    (
        frozenset(["close", "shut", "stop", "terminate", "exit", "quit", "kill", "remove"]),
        frozenset(["open", "launch", "start", "create", "spawn"])
    ),
    (
        frozenset(["off", "turn off", "switch off", "power off", "disable", "mute"]),
        frozenset(["on", "turn on", "switch on", "power on", "enable", "unmute"])
    ),
    (
        frozenset(["down", "quieter", "lower", "decrease", "reduce"]),
        frozenset(["up", "louder", "raise", "increase", "boost"])
    ),
]


class SpacyActionClassifier:
    """
    Ultra-fast (<2ms), command-level intent classification & entity extraction model.
    Classifies user queries into specific, concrete command targets (e.g. subprocess::open-files,
    hotkey::open-tab, tell_time) preventing cross-action misclassification.
    """
    def __init__(self, model_path: Optional[str] = None, lang: str = "en"):
        self.model_path = Path(model_path) if model_path else None
        self.lang = lang
        self.nlp = None
        self._cmd_labels: Set[str] = set()
        self._cmd_meta: Dict[str, Dict[str, Any]] = {}

    def is_loaded(self) -> bool:
        return self.nlp is not None

    def load_model(self, path: Optional[Path] = None) -> bool:
        if not SPACY_AVAILABLE:
            log.warning("SpaCy is not available in the current environment.")
            return False

        target_path = path or self.model_path
        if target_path and target_path.exists():
            try:
                self.nlp = spacy.load(str(target_path))
                if "textcat" in self.nlp.pipe_names:
                    tc = self.nlp.get_pipe("textcat")
                    self._cmd_labels = set(tc.labels)

                meta_file = target_path / "cmd_meta.json"
                if meta_file.exists():
                    with open(meta_file, "r", encoding="utf-8") as f:
                        self._cmd_meta = json.load(f)

                log.info(f"Loaded SpaCy command classifier from {target_path} with {len(self._cmd_labels)} intents.")
                return True
            except Exception as e:
                log.warning(f"Failed to load existing SpaCy model from {target_path}: {e}")

        return False

    def build_training_dataset(self, config_commands: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, Dict[str, Dict[str, float]]]], Set[str]]:
        """
        Generates comprehensive synthetic training samples mapped to distinct command intents.
        """
        samples = []
        labels = set()
        self._cmd_meta.clear()

        en_prefixes = ["", "please ", "could you please ", "can you ", "stewart please ", "hey stewart "]
        ru_prefixes = ["", "пожалуйста ", "стюарт пожалуйста ", "можешь ", "сделай ", "стюарт "]
        prefixes = en_prefixes + ru_prefixes

        for cmd_entry in config_commands:
            action = cmd_entry.get("action")
            if not action or action.startswith("_"):
                continue

            base_kw = cmd_entry.get("command") or []
            kw_str = "-".join(str(w) for w in base_kw)
            cmd_id = f"{action}::{kw_str}" if kw_str else action
            labels.add(cmd_id)

            self._cmd_meta[cmd_id] = {
                "action": action,
                "keywords": [str(w) for w in base_kw],
                "parameters": cmd_entry.get("parameters", {}),
                "responses": cmd_entry.get("responses", []),
                "continues": cmd_entry.get("continues", False),
                "tts": cmd_entry.get("tts", False)
            }

            synonyms = cmd_entry.get("synonyms") or {}
            equivalents = cmd_entry.get("equivalents") or []

            def expand_combinations(words, syn_map, depth=0, max_depth=10):
                if not words or depth >= len(words) or depth > max_depth:
                    return [words] if words else []
                word = str(words[depth])
                variants = [word]
                if syn_map and word in syn_map and syn_map[word]:
                    variants.extend([str(v) for v in syn_map[word]])
                results = []
                for v in variants[:4]:
                    new_w = list(words)
                    new_w[depth] = v
                    results.extend(expand_combinations(new_w, syn_map, depth + 1, max_depth))
                return results[:15]

            candidate_phrases = []
            if base_kw:
                for comb in expand_combinations(base_kw, synonyms):
                    if isinstance(comb, (list, tuple)):
                        candidate_phrases.append(" ".join(str(w) for w in comb))
                    elif isinstance(comb, str):
                        candidate_phrases.append(comb)

            for eq in equivalents:
                if eq:
                    for comb in expand_combinations(eq, synonyms):
                        if isinstance(comb, (list, tuple)):
                            candidate_phrases.append(" ".join(str(w) for w in comb))
                        elif isinstance(comb, str):
                            candidate_phrases.append(comb)

            # Deduplicate phrases for this command entry
            unique_phrases = list(set(candidate_phrases))
            selected_phrases = unique_phrases[:8]
            for phrase in selected_phrases:
                samples.append((phrase, cmd_id))
                samples.append((f"please {phrase}", cmd_id))
                samples.append((f"пожалуйста {phrase}", cmd_id))

        # Add natural conversational templates for frequent commands
        additional_templates = [
            ("what time is it", "tell_time"),
            ("what time is it now", "tell_time"),
            ("tell me the time", "tell_time"),
            ("current time please", "tell_time"),
            ("what is the time right now", "tell_time"),
            ("сколько сейчас времени", "tell_time"),
            ("сколько времени", "tell_time"),
            ("который сейчас час", "tell_time"),
            ("подскажи точное время", "tell_time"),
            ("скажи время", "tell_time"),
            ("pause the music", "media_control"),
            ("pause video", "media_control"),
            ("resume playback", "media_control"),
            ("skip to next track", "media_control"),
            ("previous song please", "media_control"),
            ("поставь музыку на паузу", "media_control"),
            ("пауза музыки", "media_control"),
            ("поставь на паузу", "media_control"),
            ("включи следующий трек", "media_control"),
            ("переключи песню", "media_control"),
            ("turn the volume up", "volume"),
            ("make it louder", "volume"),
            ("turn down the sound", "volume"),
            ("set volume to fifty", "volume"),
            ("сделай погромче звук", "volume"),
            ("прибавь громкость", "volume"),
            ("сделай тише", "volume"),
            ("открой файлы", "subprocess::открой-файлы"),
            ("открой проводник", "subprocess::открой-файлы"),
            ("open files", "subprocess::open-files"),
            ("open file manager", "subprocess::open-files"),
            ("открой вкладку", "hotkey::открой-вкладку"),
            ("закрой вкладку", "hotkey::закрой-вкладку"),
            ("open tab", "hotkey::open-tab"),
            ("close tab", "hotkey::close-tab"),
            ("what is the weather today", "say_weather"),
            ("how is the weather outside", "say_weather"),
            ("какая сегодня погода", "say_weather"),
            ("set a timer for 10 minutes", "timer"),
            ("поставь таймер на 10 минут", "timer"),
            ("take a screenshot", "screenshot"),
            ("сделай скриншот", "screenshot"),
            ("lock the screen", "lock_session"),
            ("заблокируй экран", "lock_session"),
        ]

        for text, target in additional_templates:
            matched_label = None
            if target in labels:
                matched_label = target
            else:
                words = set(text.lower().split())
                best_match = None
                best_overlap = 0
                for l in labels:
                    if l.startswith(f"{target}::") or l == target:
                        parts = l.split("::", 1)
                        if len(parts) > 1:
                            l_words = set(parts[1].split("-"))
                            overlap = len(words.intersection(l_words))
                            if overlap > best_overlap:
                                best_overlap = overlap
                                best_match = l
                        elif best_match is None:
                            best_match = l
                matched_label = best_match

            if matched_label and matched_label in labels:
                samples.append((text, matched_label))
                samples.append((f"please {text}", matched_label))
                samples.append((f"пожалуйста {text}", matched_label))

        # Generate contrastive negative examples for polar commands (e.g. 'открой окно' for 'закрой окно')
        contrastive_negatives = []
        for phrase, target_cmd in samples:
            phrase_tokens = phrase.split()
            for group_a, group_b in POLAR_ANTONYM_PAIRS:
                for a_word in group_a:
                    if a_word in phrase_tokens:
                        for b_word in list(group_b)[:2]:
                            neg_phrase = " ".join([b_word if w == a_word else w for w in phrase_tokens])
                            contrastive_negatives.append((neg_phrase, "__incomplete__"))
                for b_word in group_b:
                    if b_word in phrase_tokens:
                        for a_word in list(group_a)[:2]:
                            neg_phrase = " ".join([a_word if w == b_word else w for w in phrase_tokens])
                            contrastive_negatives.append((neg_phrase, "__incomplete__"))

        samples.extend(contrastive_negatives)

        # Add incomplete / neutral examples so isolated verbs or wake words without an object don't misfire
        incomplete_examples = [
            "открой", "закрой", "включи", "выключи", "сделай", "поставь", "установи", "переключи",
            "запусти", "покажи", "open", "close", "start", "stop", "switch", "turn", "set", "make",
            "стюарт открой", "стюарт закрой", "стюарт включи", "стюард открой", "стюард закрой",
            "stewart open", "stewart close", "привет", "как дела", "hello", "hi", "hey"
        ]
        labels.add("__incomplete__")
        for inc in incomplete_examples:
            samples.append((inc, "__incomplete__"))

        # Format into SpaCy cats dictionary
        formatted_data = []
        for text, target_cmd in samples:
            cats = {label: (1.0 if label == target_cmd else 0.0) for label in labels}
            formatted_data.append((text, {"cats": cats}))

        random.seed(42)
        random.shuffle(formatted_data)
        return formatted_data, labels

    def train(self, config_commands: List[Dict[str, Any]], save_path: Optional[Path] = None, epochs: int = 12) -> bool:
        if not SPACY_AVAILABLE:
            log.warning("SpaCy is not available; cannot train model.")
            return False

        log.info("Building synthetic command dataset from Stewart configs...")
        train_data, labels = self.build_training_dataset(config_commands)
        if len(labels) < 2:
            log.warning("Not enough command labels to train text classifier.")
            return False

        log.info(f"Generated {len(train_data)} training examples across {len(labels)} distinct command intents.")

        target_lang = self.lang if self.lang in ("ru", "en") else "xx"
        try:
            self.nlp = spacy.blank(target_lang)
        except Exception:
            self.nlp = spacy.blank("xx")

        textcat = self.nlp.add_pipe("textcat")
        for label in sorted(labels):
            textcat.add_label(label)
        self._cmd_labels = set(labels)

        examples = [Example.from_dict(self.nlp.make_doc(text), annot) for text, annot in train_data]

        optimizer = self.nlp.initialize()
        log.info(f"Training SpaCy command classifier for {epochs} epochs...")

        for epoch in range(epochs):
            losses = {}
            batches = spacy.util.minibatch(examples, size=32)
            for batch in batches:
                self.nlp.update(batch, sgd=optimizer, losses=losses)

        log.info(f"Training finished. Final textcat loss: {losses.get('textcat', 0.0):.4f}")

        # Save model and command metadata to disk
        target_path = save_path or self.model_path
        if target_path:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.nlp.to_disk(target_path)
            meta_file = target_path / "cmd_meta.json"
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(self._cmd_meta, f, ensure_ascii=False, indent=2)
            log.info(f"Model and command metadata saved successfully to {target_path}")

        return True

    def extract_entities_and_parameters(self, text: str, cmd_id: str) -> Tuple[str, Dict[str, Any], str]:
        """
        Extracts parameters and payload context based on the specific command intent.
        """
        meta = self._cmd_meta.get(cmd_id, {})
        action = meta.get("action", cmd_id.split("::")[0])
        params = dict(meta.get("parameters") or {})
        clean_text = text.lower().strip()
        context = ""

        if action == "volume":
            nums = re.findall(r"\b\d+\b", clean_text)
            if nums:
                context = nums[0]
                params["command"] = "set"
            elif any(w in clean_text for w in ["up", "louder", "higher", "громче", "прибавь", "повысь"]):
                params["command"] = "up"
            elif any(w in clean_text for w in ["down", "quieter", "lower", "тише", "убавь", "понизь"]):
                params["command"] = "down"

        elif action == "brightness":
            if any(w in clean_text for w in ["up", "brighter", "поярче", "прибавь", "ярче"]):
                params["command"] = "up"
            elif any(w in clean_text for w in ["down", "dimmer", "тусклее", "убавь", "темнее"]):
                params["command"] = "down"

        elif action == "media_control":
            if any(w in clean_text for w in ["pause", "stop", "resume", "play", "пауза", "паузу", "стоп", "продолжи"]):
                params["control"] = "play-pause"
            elif any(w in clean_text for w in ["next", "следующий", "переключи", "вперед", "вперёд"]):
                params["control"] = "next"
            elif any(w in clean_text for w in ["previous", "предыдущий", "назад"]):
                params["control"] = "previous"

        elif action == "timer":
            match = re.search(r"(\d+)\s*(hour|minute|second|min|sec|ч|мин|сек|минут|секунд|часов|часа)", clean_text)
            if match:
                context = f"{match.group(1)} {match.group(2)}"
            else:
                nums = re.findall(r"\b\d+\b", clean_text)
                if nums:
                    context = f"{nums[0]} minutes"

        elif action in ("typing", "find_video", "play_song"):
            payload = clean_text
            for prefix in ["type ", "write down ", "write ", "search for ", "play ", "find ",
                           "напечатай ", "напиши ", "найди ", "включи песню ", "включи "]:
                if payload.startswith(prefix):
                    payload = payload[len(prefix):].strip()
                    break
            context = payload

        return action, params, context

    def predict(self, text: str, threshold: float = 0.55) -> Optional[Tuple[str, str, float, Dict[str, Any], str]]:
        """
        Runs model inference on input text.
        Returns (cmd_id, action_name, confidence, parameters, context) or None.
        """
        if not self.is_loaded():
            if not self.load_model():
                return None

        doc = self.nlp(text)
        cats = doc.cats
        if not cats:
            return None

        best_cmd_id, best_score = max(cats.items(), key=lambda item: item[1])

        # Reject explicitly learned incomplete commands or scores below threshold
        if best_cmd_id == "__incomplete__" or best_score < threshold:
            log.debug(f"Input '{text}' classified as incomplete or score {best_score:.3f} below threshold {threshold}")
            return None

        meta = self._cmd_meta.get(best_cmd_id, {})
        req_kw = [k.lower() for k in meta.get("keywords", [])]
        tokens = set(re.findall(r"[^\s,!?;:()[\]{}\"'`~*.]+", text.lower()))

        # Guard 1: Polarity Contradiction Check
        # If command requires verb A (e.g. 'закрой'), and input has opposing verb B ('открой'), reject immediately!
        for group_a, group_b in POLAR_ANTONYM_PAIRS:
            if any(kw in group_a for kw in req_kw):
                if any(t in group_b for t in tokens) and not any(t in group_a for t in tokens):
                    log.info(f"Input '{text}' rejected for '{best_cmd_id}': Polarity contradiction (input has opposing verb from {group_b})")
                    return None
            if any(kw in group_b for kw in req_kw):
                if any(t in group_a for t in tokens) and not any(t in group_b for t in tokens):
                    log.info(f"Input '{text}' rejected for '{best_cmd_id}': Polarity contradiction (input has opposing verb from {group_a})")
                    return None

        # Guard 2: Keyword presence check for multi-keyword commands
        if len(req_kw) >= 2:
            generic_verbs = {
                "открой", "закрой", "включи", "выключи", "сделай", "поставь",
                "open", "close", "turn", "set", "switch", "start", "stop"
            }
            specific_kw = [k for k in req_kw if k not in generic_verbs]
            if specific_kw and not any(k in tokens for k in specific_kw):
                log.debug(f"Input '{text}' rejected: missing specific object keywords {specific_kw} for {best_cmd_id}")
                return None

            verbs_in_cmd = [k for k in req_kw if k in generic_verbs]
            if verbs_in_cmd and not any(v in tokens for v in verbs_in_cmd):
                syn_map = meta.get("synonyms", {})
                matched_verb = False
                for v in verbs_in_cmd:
                    syns = [s.lower() for s in syn_map.get(v, [])]
                    if any(s in tokens for s in syns):
                        matched_verb = True
                        break
                if not matched_verb and best_score < 0.85:
                    log.info(f"Input '{text}' rejected for '{best_cmd_id}': Required verb {verbs_in_cmd} not found in query")
                    return None

        action, params, context = self.extract_entities_and_parameters(text, best_cmd_id)
        return best_cmd_id, action, best_score, params, context
