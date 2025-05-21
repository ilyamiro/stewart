import datetime
from typing import List, Dict, Optional, Any


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

        self.keywords = keywords
        self.synonyms = synonyms
        self.responses = responses
        self.action = action
        self.parameters = parameters
        self.continues = continues
        self.equivalents = equivalents
        self.tts = tts

    def copy(self, keywords):
        return Command(keywords, self.action, self.synonyms, self.responses, self.parameters, self.continues,
                       tts=self.tts)


class Manager:
    def __init__(self):
        self.Command = Command
        self.commands = []

    def add(self, *commands: Command):
        """
        Add one or more Command instances to the manager.
        """
        for command in commands:
            if isinstance(command, Command):
                for cmd in self.commands[:]:
                    if cmd.keywords == command.keywords:
                        self.commands.remove(cmd)
                self.commands.append(command)
                for equivalent in command.equivalents:
                    self.commands.append(command.copy(equivalent))
            else:
                raise TypeError(f"Expected Command instance, got {type(command).__name__}")

    def construct_recognizer_string(self):
        words = []
        for command in self.commands:
            words.extend(command.keywords)
            for synonyms in command.synonyms.values():
                words.extend(synonyms)
        return " ".join(set(words))

    def find(self, request: str):
        request = request.lower().strip()
        words = request.split()

        results = {}

        first_keywords = {}
        for command in self.commands:
            first_keywords[command.keywords[0]] = command
            for synonym in command.synonyms.get(command.keywords[0], []):
                first_keywords[synonym] = command

        mapping = self.map_words_to_indexes(words, first_keywords)
        found_command = len(words)
        previous_index = None

        for index, keyword in mapping.items():
            if results and previous_index is not None and results.get(previous_index, None) is not None:
                if results.get(previous_index).continues:
                    results = {previous_index: results.get(previous_index)}

            previous_index = index
            constructed = [keyword]

            matches = self.get_matching_commands(constructed)

            keyword_index = 1
            last_index = 0
            for command in matches:
                if len(command.keywords) == 1 and not words[index + 1:found_command] and self.is_constructed(
                        command.keywords, constructed, command.synonyms):
                    results[index] = command
                    found_command = index + 1
                    constructed = []

            for word_index, word in enumerate(words[index + 1:found_command]):
                matches = self.get_matching_commands(constructed)
                matches.sort(key=lambda cmd: len(cmd.keywords), reverse=True)

                found_word = False
                if word_index - last_index > 2:
                    break
                for command in matches:
                    if found_word:
                        break
                    if len(command.keywords) == 1 and self.is_constructed(command.keywords, constructed,
                                                                          command.synonyms):
                        results[index] = command
                        found_command = index + 1
                        keyword_index = 1
                        break
                    if (word == command.keywords[keyword_index] or word in command.synonyms.get(
                            command.keywords[keyword_index], [])) and self.is_constructed(command.keywords, constructed,
                                                                                          command.synonyms):
                        keyword_index += 1
                        constructed.append(word)
                        last_index = word_index
                        found_word = True
                        if keyword_index == len(command.keywords):
                            results[index] = command
                            found_command = index + 1
                            keyword_index = 1
                            break

        if results and previous_index is not None and results.get(previous_index, None) is not None:
            if results.get(previous_index).continues:
                results = {previous_index: results.get(previous_index)}

        used_indices = set()

        def matches_keyword(word1, keyword1, synonyms):
            if word1 == keyword1:
                return True
            if keyword1 in synonyms and word1 in synonyms[keyword1]:
                return True
            return False

        for start_index in sorted(results.keys()):
            command = results[start_index]
            command_keywords = command.keywords
            command_synonyms = command.synonyms
            temp_used_indices = set()
            word_index = 0

            for keyword in command_keywords:
                while word_index < len(words):
                    if (
                            word_index not in used_indices
                            and matches_keyword(words[word_index], keyword, command_synonyms)
                    ):
                        temp_used_indices.add(word_index)
                        word_index += 1
                        break
                    word_index += 1
                else:
                    del results[start_index]
                    break

            if start_index in results:
                used_indices.update(temp_used_indices)

        sorted_keys = sorted(results.keys())
        number = 1
        context = {number + i: [key, ""] for i, key in enumerate(results.values())}

        for index, result in results.items():
            if result.continues:
                boundary = len(words)
            else:
                sorted_index = sorted_keys.index(index)

                if sorted_index < len(sorted_keys) - 1:
                    boundary = sorted_keys[sorted_index + 1]
                else:
                    boundary = len(words)

            found = False
            track_command = []

            for word in words[index:boundary]:
                if word not in result.keywords and all(word not in synonyms for synonyms in result.synonyms.values()):
                    found = True
                    context[number] = [result, context.get(number)[1] + " " + word]
                else:
                    track_command.append(next((key for key, value in result.synonyms.items() if word in value), word))
                    if word in track_command and result.keywords[:len(track_command)] != track_command:
                        found = True
                        context[number] = [result, context.get(number)[1] + " " + word]

            if not found:
                context[number] = [result, ""]

            number += 1

        context = {key: context[len(context) - key + 1] for key in context}

        return list(context.values())

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

        for index, word in enumerate(words):
            if word in word_list:
                word_map[index] = word

        word_map = dict(sorted(word_map.items(), key=lambda item: item[0], reverse=True))
        return word_map

    def get_matching_commands(self, keywords):
        if not keywords:
            return self.commands
        commands = []
        for cmd in self.commands:
            if self.is_constructed(cmd.keywords, keywords, cmd.synonyms):
                commands.append(cmd)

        return commands
