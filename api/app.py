import os.path
import logging
import inspect
import threading
import yaml
import types
import typing
from importlib import import_module

from pynput.keyboard import Controller as Keyboard
from pynput.keyboard import Key as KeyboardKey

from pynput.mouse import Controller as Mouse
from pynput.mouse import Button as MouseButton

from data.constants import PROJECT_FOLDER, CONFIG_FILE
from audio.tts import TTS
from utils import load_yaml, filter_lang_config, load_lang

log = logging.getLogger("API: app")

__GPT_CALLBACK_TYPE__ = typing.Callable[[str], str]


class AppAPI:
    def __init__(self):
        ttsi = TTS()

        self.say = ttsi.say
        self.say: Callable

        self.mouse = Mouse()
        self.keyboard = Keyboard()

        self.Button = MouseButton
        self.Key = KeyboardKey

        self.lang = self.__get_lang__()

        self.config = load_yaml(CONFIG_FILE)

        self.__pre_init_callbacks__: list = []
        self.__post_init_callbacks__: list = []

        self.__no_command_callback__ = self.__blank__
        self.__trigger_callback__ = self.__blank__

        self.__search_functions__: dict = {}

        self.scenarios: list = []

    @staticmethod
    def __blank__(value=None):
        pass

    def set_post_init(self, func: types.FunctionType, index: int = -1) -> None:
        """
        :param index: indicates and index at which the hook will be placed at to modify the queue
        :param func: the hook itself (the link to it)
        """
        self.__set_hook__(func, self.__post_init_callbacks__, index)

    def set_pre_init(self, func: types.FunctionType, index: int = -1) -> None:
        """
        :param index: indicates and index at which the hook will be placed at to modify the queue
        :param func: the hook itself (the link to it)
        """
        self.__set_hook__(func, self.__pre_init_callbacks__, index)

    @staticmethod
    def __set_hook__(func: types.FunctionType, callback_list, index: int = -1):
        callback_list.insert(index, func)

    @staticmethod
    def __run_hooks__(collection: list):
        for hook in collection:
            try:
                hook()
            except Exception as e:
                log.warning(f"Add command hook {hook.__name__} threw an error: {e}")

    # < ------------------- Modules ------------------- >

    def add_func_for_search(self, *args: typing.Tuple[types.FunctionType]):
        for func in args:
            self.__search_functions__.update({func.__name__: func})

    def add_module_for_search(self, path: str = None, module=None, include_private: bool = False):
        """
        :param path: a project relative path for a module that would be added to search in when looking for execution module
        :param module: a module itself as a python object
        :param include_private: whether to include functions that start with __
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
            functions = {
                member[0]: member[1]
                for member in members
                if inspect.isfunction(member[1]) and member[1].__module__ == module.__name__
            }
            if not include_private:
                filtered_dict = {k: v for k, v in functions.items() if not k.startswith('__')}
                self.__search_functions__.update(filtered_dict)
            else:
                self.__search_functions__.update(functions)
        else:
            log.warning(f"module: {module} is not a module object, try again")
            return

    def add_dir_for_search(self, path: str, include_private: bool = False):
        """
        Iterates over all Python files in the given directory and calls `add_module_for_search` on each.

        :param path: The directory to search for Python modules
        :param include_private: whether to include functions that start with __
        """
        if not os.path.exists(path):
            log.warning(f"The directory: {path} does not exist.")
            return

        if not os.path.isdir(path):
            log.warning(f"The path: {path} is not a directory.")
            return

        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    self.add_module_for_search(file_path, include_private=include_private)

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
        return load_lang()

    def get_config(self):
        return filter_lang_config(self.config, self.lang)

    # <! ----------------------- config ----------------------- !>
    def update_config(self, config: dict):
        self.config["plugins"].update(config)
        self.__save_config__()

    def update_config_with_yaml_file(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

            self.config.update(data)
            self.__save_config__()
        else:
            raise FileNotFoundError()

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

    # <! --------------- background processes --------------- !>
    @staticmethod
    def start_background_process(func: types.FunctionType):
        print("added ", func.__name__)
        bg_thread = threading.Thread(target=func, name=func.__name__)
        bg_thread.start()

    # <! --------------- scenarios --------------- !>
    def add_scenario(self, scenario):
        if hasattr(scenario, "name"):
            self.scenarios.append(scenario)


app = AppAPI()
