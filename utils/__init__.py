import importlib

from .classes import *
from .system import *


def import_utils(lang, target_globals):
    module = importlib.import_module(f"utils.lang.{lang}")

    if hasattr(module, '__all__'):
        names = module.__all__
    else:
        names = [name for name in dir(module) if not name.startswith('_')]

    target_globals.update({name: getattr(module, name) for name in names})