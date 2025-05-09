import json
from typing import List
import random
import yaml


class Locale:
    def __init__(self, lang, path):
        self.lang = lang
        self.path = path

        self._translations = {}

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.translations = self.flatten(data)
        except Exception:
            self.translations = {}

    def flatten(self, d, parent_key='', sep='.'):
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self.flatten(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items

    def get(self, key: str):
        return self.translations.get(key)


class LocaleService:
    def __init__(self, lang: str = "en"):
        self.localisations = {}
        self.lang = lang

    def add(self, plugin: str, locales: List[Locale]):
        for locale in locales:
            if self.lang == locale.lang:
                locale.load()
                self.localisations[plugin] = locale
                break

    def exists(self, plugin: str):
        return bool(self.localisations.get(plugin))

    def translate(self, plugin: str, key: str, **kwargs):
        locale = self.localisations.get(plugin)
        if not locale:
            return f"[{plugin}.{key}]"

        raw = locale.get(key)
        print(raw)
        if raw is None:
            return f"[{plugin}.{key}]"

        if isinstance(raw, list):
            raw = random.choice(raw)

        try:
            return raw.format(**kwargs)
        except Exception:
            return raw










