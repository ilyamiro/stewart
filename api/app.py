import os.path
import logging
import inspect
import yaml
import types
from typing import Callable
from importlib import import_module

from data.constants import PROJECT_FOLDER, CONFIG_FILE
from audio.output import ttsi
from utils import load_yaml, filter_lang_config

log = logging.getLogger("API: app")

# Types
__GPT_CALLBACK_TYPE__ = Callable[[str], str]


class AppAPI:
    def __init__(self):
        self.say = ttsi.say
        self.say: Callable

        self.lang = self.__get_lang__()

        self.config = load_yaml(CONFIG_FILE)

        self.__pre_init_callbacks__: list = []
        self.__post_init_callbacks__: list = []

        self.__no_command_callback__ = self.__blank__
        self.__trigger_callback__ = self.__blank__

        self.__search_functions__: dict = {}

    @staticmethod
    def __blank__(value=None):
        pass

    def set_post_init(self, func: types.FunctionType, index: int = -1) -> None:
        """
        :param index: indicates and index at which the hook will be placed at to modify the queue
        :param func: the hook itself (the link to it)
        """
        self.__add_hook__(func, self.__post_init_callbacks__, index)

    def set_pre_init(self, func: types.FunctionType, index: int = -1) -> None:
        """
        :param index: indicates and index at which the hook will be placed at to modify the queue
        :param func: the hook itself (the link to it)
        """
        self.__set_hook__(func, self.__pre_init_callbacks__, index)

    @staticmethod
    def __set_hook__(func: types.FunctionType, callback_list, index: int = -1):
        callback_list.insert(index, func)

    def __run_pre_init_callbacks__(self):
        for callback in self.__pre_init_callbacks__:
            callback()

    def __run_post_init_callbacks__(self):
        for callback in self.__post_init_callbacks__:
            callback()

    # < ------------------- Modules ------------------- >

    def add_func_for_search(self, name: str, func: types.FunctionType):
        self.__search_functions__[name] = func

    def add_module_for_search(self, path: str = None, module=None):
        """
        :param path: a project relative path for a module that would be added to search in when looking for execution module
        :param module: a module itself as a python object
        """
        if not module:
            if os.path.exists(path):
                if path.endswith(".py"):
                    path = path[:-3]
                try:
                    module_path = path.replace("/", ".")
                    module = import_module(module_path)
                except ImportError as e:
                    log.warning(f"Failed to import {path} for search: {e}")
                    return
            else:
                log.warning(f"The path: {path} does not exist. Failed to add module for search")
                return
        if isinstance(module, types.ModuleType):
            members = inspect.getmembers(module)
            functions = {member[0]: member[1] for member in members if inspect.isfunction(member[1])}
            self.__search_functions__.update(functions)
        else:
            log.warning(f"module: {module} is not a module object, try again")
            return

    def set_no_command_callback(self, func: types.FunctionType):
        """A function that will run if no command was recognized"""
        self.__no_command_callback__ = func

    def set_trigger_callback(self, func: types.FunctionType):
        """A function that will run when a command was recognized"""
        self.__trigger_callback__ = func

    def set_command_processor(self, func: types.FunctionType):
        self.__command_processor__ = func

    # <! ----------------------- get ----------------------- !>
    @staticmethod
    def __get_lang__():
        """
        Returns language settings
        """
        with open(f"{PROJECT_FOLDER}/lang.txt", "r", encoding="utf-8") as file:
            return file.read()

    # <! ----------------------- config ----------------------- !>
    def update_config(self, config: dict):
        self.config.update(config)
        self.__save_config__()

    def get_config(self):
        return filter_lang_config(self.config, self.lang)

    def __save_config__(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

            data.update(self.config)

            with open(CONFIG_FILE, "w", encoding="utf-8") as file:
                yaml.dump(data, file, allow_unicode=True)
    # <! ----------------------- use ----------------------- !>

    def use_command_processor(self, request):
        return self.__command_processor__(request)


app = AppAPI()
