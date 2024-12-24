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
        return Command(keywords, self.action, self.synonyms, self.responses, self.parameters, self.continues, tts=self.tts)


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
                self.commands.append(command)
                for equivalent in command.equivalents:
                    self.commands.append(command.copy(equivalent))
            else:
                raise TypeError(f"Expected Command instance, got {type(command).__name__}")

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
            if results and previous_index and results.get(previous_index, None) is not None:
                if results.get(previous_index).continues:
                    results = {previous_index: results.get(previous_index)}

            previous_index = index
            matches = self.get_matching_commands(keyword)

            constructed = []
            keyword_index = 0
            last_index = 0
            for command in matches:
                if len(command.keywords) == 1 and command.keywords == constructed and not words[index + 1:found_command]:
                    results[index] = command
                    found_command = index + 1
                    constructed = []
            for word_index, word in enumerate(words[index:found_command]):
                if word_index - last_index > 2:
                    break
                for command in matches:
                    if len(command.keywords) == 1:
                        results[index] = command
                        found_command = index + 1
                        constructed = []
                        break
                    if (word == command.keywords[keyword_index] or word in command.synonyms.get(
                            command.keywords[keyword_index], [])) and all(
                            key in command.keywords for key in constructed):
                        keyword_index += 1
                        constructed.append(word)
                        last_index = word_index
                        if keyword_index == len(command.keywords) and constructed == command.keywords:
                            results[index] = command
                            found_command = index + 1
                            keyword_index = 1
                            constructed = []
                            break
                        break

        if results and previous_index and results.get(previous_index, None) is not None:
            if results.get(previous_index).continues:
                results = {previous_index: results.get(previous_index)}

        used_indices = set()

        for start_index in sorted(results.keys()):
            command = results[start_index]
            command_keywords = command.keywords
            temp_used_indices = set()
            word_index = 0

            for keyword in command_keywords:
                while word_index < len(words):
                    if word_index not in used_indices and words[word_index] == keyword:
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
                    track_command.append(word)
                    if word in track_command and result.keywords[:len(track_command)] != track_command:
                        found = True
                        context[number] = [result, context.get(number)[1] + " " + word]

            if not found:
                context[number] = [result, ""]

            number += 1

        context = {key: context[len(context) - key + 1] for key in context}

        return list(context.values())

    @staticmethod
    def map_words_to_indexes(words, word_list):
        word_map = {}

        for index, word in enumerate(words):
            if word in word_list:
                word_map[index] = word

        word_map = dict(sorted(word_map.items(), key=lambda item: item[0], reverse=True))
        return word_map

    def get_matching_commands(self, keyword):
        commands = []
        for cmd in self.commands:
            if keyword == cmd.keywords[0] or keyword in cmd.synonyms.get(cmd.keywords[0], []):
                commands.append(cmd)

        return commands

