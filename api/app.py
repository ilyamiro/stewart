import json
import os.path
import time
import logging
import re
import random
import subprocess
import mpv
import yaml
import socket
import inspect
import threading
import types
import typing
import hashlib
from importlib import import_module
from pathlib import Path
from multiprocessing import Process
from playsound import playsound

from pynput.keyboard import Controller as Keyboard
from pynput.keyboard import Key as KeyboardKey

from pynput.mouse import Controller as Mouse
from pynput.mouse import Button as MouseButton

from data.constants import PROJECT_DIR, CONFIG_FILE, CONFIG_DIR, PLUGINS_DIR
from audio.tts import TTS
from utils import load_yaml, filter_lang_config, load_lang, notify, sanitize_filename, parse_config_answers

from .commands.tree import Manager
from .commands.scenarios import Trigger, Timeline, Scenario
from .events.events import Event, EventLogger
from .locales.service import Locale, LocaleService
from .files.caching import Runtime

log = logging.getLogger("API: app")

__GPT_CALLBACK_TYPE__ = typing.Callable[[str], str]


# runtime = Runtime()

class AudioInterface:
    def __init__(self):
        try:
            self.player = mpv.MPV(
                ytdl=True,
                input_default_bindings=True,
                video=False,
                input_ipc_server="/tmp/mpv-socket"
            )

        except Exception as e:
            log.error(f"Failed to initialize MPV player: {e}")
            self.player = None

        self.equalizer_values = [
            {"frequency": 20, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 30, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 40, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 50, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 60, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 70, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 80, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 100, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 120, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 140, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 160, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 180, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 200, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 250, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 300, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 350, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 400, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 450, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 500, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 600, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 700, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 800, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 900, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 1000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 1500, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 2000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 2500, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 3000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 3500, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 4000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 5000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 6000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 7000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 8000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 9000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 10000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 12000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 14000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 16000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 18000, "width": 80, "gain": 0.0, "width_type": "h"},
            {"frequency": 20000, "width": 80, "gain": 0.0, "width_type": "h"},
        ]

    def update_equalizer(self, bands=None):
        """
        Updates the MPV equalizer with specified bands or clears it if bands are empty.

        :param bands: A list of dictionaries with 'frequency', 'width', and 'gain' values.
        """
        if not self.player:
            log.error("MPV player not initialized")
            return

        if bands is None or not bands:
            try:
                self.player.command('af', 'clr', '')
                log.info("Equalizer reset to default settings")
            except Exception as e:
                log.error(f"Failed to reset equalizer: {e}")
            return

        try:
            for band in bands:
                frequency = band.get('frequency')
                width = band.get('width', 80)
                gain = band.get('gain', 0.0)
                width_type = band.get('width_type', 'h')

                eq_filter = f"equalizer=f={frequency}:width_type={width_type}:w={width}:g={gain}"
                self.player.command("af", "add", eq_filter)

        except Exception as e:
            log.error(f"Failed to apply equalizer settings: {e}")

    def stream(self, value):
        """
        Stream audio from a given URL or path.

        :param value: URL or file path to stream
        """
        if not self.player:
            log.error("MPV player not initialized")
            return

        try:
            self.player.stop()

            self.player.play(value)

        except Exception as e:
            log.error(f"Error streaming {value}: {e}")

    def play(self, path: str):
        """
        Plays a sound file using mpv.

        :param path: Path to the sound file to be played.
        """
        if not self.player:
            log.error("MPV player not initialized")
            return

        if not os.path.exists(path):
            raise FileNotFoundError(f"The file {path} does not exist.")

        try:
            self.player.stop()

            self.player.play(path)

        except Exception as e:
            log.error(f"Failed to play sound: {e}")

    def stop(self):
        """
        Stop the currently playing media.
        """
        if self.player:
            self.player.stop()

    def pause(self):
        if self.player:
            self.player.pause()

    @staticmethod
    def is_mpv():
        """
        Check if MPV is currently running.

        :return: Boolean indicating if MPV is running
        """
        try:
            output = subprocess.check_output(["pgrep", "-a", "mpv"], text=True)
            return bool(output.strip())
        except subprocess.CalledProcessError:
            return False

    def __send_ipc_command__(self, command):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(self.ipc_socket_path)
                command_with_id = {**command, "request_id": 1}
                s.sendall(json.dumps(command_with_id).encode('utf-8') + b'\n')
                response = s.recv(4096).decode('utf-8')
                return json.loads(response)
        except Exception as e:
            print(f"IPC Command Error: {e}")
            return None


class AppAPI:
    def __init__(self):
        self.ttsi = TTS()

        self.runtime = Runtime()

        self.manager = Manager()
        self.Command = self.manager.Command

        self.Trigger = Trigger
        self.Timeline = Timeline
        self.Scenario = Scenario

        self.Event = Event
        self.eventLogger = EventLogger()

        self.mouse = Mouse()
        self.keyboard = Keyboard()

        self.audio = AudioInterface()

        self.MouseButton = MouseButton
        self.Key = KeyboardKey

        self.lang = self.get_lang()

        self.localeService = LocaleService(self.lang)
        self.Locale = Locale

        self.config = self.get_config()

        self.__pre_init_callbacks__: list = []
        self.__post_init_callbacks__: list = []

        self.__no_command_callback__ = self.__no_command_default__
        self.__trigger_callback__ = self.__blank__

        self.__actions__: dict = {}

        self.scenarios: list = []

    def __no_command_default__(self, context, history):
        answer = random.choice(self.config[f"answers"]["default"])
        self.say(parse_config_answers(answer))

        self.eventLogger.record(self.Event(
            "wake_word_used",
            {"answer": answer}
        ))

    def say(self, text: str, no_audio=False, prosody=94, speaker=None):
        if not text:
            return

        if not self.ttsi.active:
            log.debug(f"No sound: {text}")
            return

        def call_tts_in_thread(**kwargs):
            process = threading.Thread(target=self.ttsi.say, kwargs=kwargs)
            process.start()

        if self.config["audio"]["tts"]["enable-caching"]:
            tts_cache: Path = self.runtime.mkdir_cache("tts")

            normalized = text.strip().lower()
            hash_input = str(f"{normalized}|prosody={prosody}|speaker={speaker or ''}")
            phrase_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            filename = tts_cache / sanitize_filename(f"{phrase_hash}.wav")

            cached_hash = self.runtime.read(f"tts:{hash_input}")
            if cached_hash:
                cached_file = tts_cache / f"{cached_hash}.wav"
                if cached_file.exists():
                    log.debug(f"Using cached tts file {cached_file} for text: {text}")
                    self.runtime.write(f"tts:{hash_input}", cached_hash)  # Reinforce mapping
                    playsound(str(cached_file), block=False)
                    return

            call_tts_in_thread(text=text, path=str(filename), no_audio=no_audio, prosody=prosody, speaker=speaker)
            self.runtime.write(f"tts:{hash_input}", phrase_hash)
        else:
            call_tts_in_thread(text=text, path=f"{PROJECT_DIR}/audio/tts/audio.wav", no_audio=no_audio,
                               prosody=prosody, speaker=speaker)

    @staticmethod
    def __blank__(context, history):
        pass

    def set_post_init(self, func: types.FunctionType, index: int = -1) -> None:
        """
        :param index: indicates and index at which the hook will be placed at to modify the queue
        :param func: the hook itself (the link to it)
        """
        self.__post_init_callbacks__.insert(index, func)

    def set_pre_init(self, func: types.FunctionType, index: int = -1) -> None:
        """
        :param index: indicates and index at which the hook will be placed at to modify the queue
        :param func: the hook itself (the link to it)
        """
        self.__pre_init_callbacks__.insert(index, func)

    @staticmethod
    def __run_hooks__(collection: list):
        for hook in collection:
            try:
                hook()
            except Exception as e:
                log.warning(f"Hook {hook.__name__} threw an error: {e}")

    # < ------------------- Modules ------------------- >
    def add_func_for_search(self, *args):
        log.info(f"Added functions to actions: {args}")
        for func in args:
            self.__actions__.update({func.__name__: func})

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
                self.__actions__.update(filtered_dict)
                log.info(f"Added functions to actions: {list(filtered_dict.keys())}")
            else:
                self.__actions__.update(functions)
                log.info(f"Added functions to actions: {list(functions.keys())}")
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

    def endpoint(self, func: types.FunctionType):
        self.__setattr__(func.__name__, func)
        log.info(f"Added API endpoint: {func.__name__}")

    # < ------------------- Plugins ------------------- >
    @staticmethod
    def _load_plugin_modules(directory):
        modules = []

        for root, _, files in os.walk(directory):
            for filename in files:
                if filename.endswith('.py'):
                    rel_path = os.path.relpath(root, directory)
                    if rel_path == '.':
                        module_path = directory.replace(os.sep, ".") + "." + filename[:-3]
                    else:
                        # For subdirectories, include the subdirectory in the module path
                        module_path = directory.replace(os.sep, ".") + "." + rel_path.replace(os.sep,
                                                                                              ".") + "." + filename[:-3]
                    modules.append(module_path)

        for path in modules:
            try:
                import_module(path)
            except ImportError as e:
                log.info(f"Failed to import {path}: {e}")

    def _import_plugin(self, directory, manifest):
        name = manifest.get("name")

        locales = manifest.get("locales")
        if locales:
            loaded_locales = []
            for lang, path in locales.items():
                locale = self.Locale(lang, f"{directory}/{path}")
                # locale.load()
                loaded_locales.append(locale)
            self.localeService.add(name, loaded_locales)

        if self.localeService.exists(name):
            log.info(f"Locale found, loading {directory}")
            self._load_plugin_modules(directory)

    @staticmethod
    def _load_plugin_manifest(path):
        file_path = os.path.join(path, 'manifest.yaml')
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return None
        try:
            content = load_yaml(file_path)
            log.info(f"manifest.yaml found in {path}, proceeding")
            return content
        except Exception as e:
            log.info(f"Error reading manifest.yaml for plugin {directory}: {e}")
            return None

    def load_plugins(self):

        skip_dirs = ["__pycache__", ".idea", "venv", "locales"]
        plugin_list = []
        base_directory = Path(PLUGINS_DIR)

        for path in base_directory.iterdir():
            if path.is_dir() and path.name not in skip_dirs:
                plugin_list.append(str(path.relative_to(Path(PROJECT_DIR))))

        for plugin_dir in plugin_list:
            manifest = self._load_plugin_manifest(plugin_dir)
            if manifest:
                self._import_plugin(plugin_dir, manifest)
            else:
                log.info(f"There was an error loading manifest.yaml for plugin {plugin_dir}")

    #
    # # <! ----------------------- get ----------------------- !>
    @staticmethod
    def get_lang():
        """
        Returns language settings
        """
        return load_lang()

    # <! ----------------------- config ----------------------- !>
    @staticmethod
    def deep_merge(base: dict, lang: dict):
        merged = base.copy()
        specs = lang.get("specifications")

        merged["audio"]["stt"].update(specs.get("audio").get("stt"))
        merged["settings"]["trigger"]["triggers"] = (specs.get("triggers"))
        merged["settings"]["user"] = specs.get("user")
        merged["start-up"].update(specs.get("start-up"))
        merged["answers"] = lang.get("answers")
        merged["commands"] = lang.get("commands")

        return merged

    def get_config(self):
        base_config = load_yaml(CONFIG_FILE)
        lang_config_path = f'{CONFIG_DIR}/langs/{self.lang}.yaml'

        if os.path.exists(lang_config_path):
            lang_config = load_yaml(lang_config_path)
            return self.deep_merge(base_config, lang_config)

        return self.deep_merge(base_config,
                               load_yaml(f'{CONFIG_DIR}/langs/en.yaml'))  # TODO MAKE A DEFAULT ROLLBACK LANGUAGE

    def update_config(self, config: dict):
        self.config["plugins"].update(config)
        self.__save_config_plugins__()

    def update_config_with_yaml_file(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

            self.config.update(data)
        else:
            raise FileNotFoundError()

    def __save_config_plugins__(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
            data["plugins"].update(self.config["plugins"])
            with open(CONFIG_FILE, "w", encoding="utf-8") as file:
                yaml.safe_dump(data, file, allow_unicode=True)

    # <! --------------- background processes --------------- !>
    @staticmethod
    def start_background_process(func: types.FunctionType):
        log.info(f"added {func.__name__}")
        bg_thread = threading.Thread(target=func, name=func.__name__)
        bg_thread.start()

    # <! --------------- scenarios --------------- !>
    def add_scenario(self, scenario):
        for el in self.scenarios[:]:
            if el.name == scenario.name:
                self.scenarios.insert(self.scenarios.index(el), scenario)
                self.scenarios.remove(el)
                return
        self.scenarios.append(scenario)

    def remove_scenario(self, name):
        for el in self.scenarios[:]:
            if el.name == name:
                self.scenarios.remove(el)


app = AppAPI()
