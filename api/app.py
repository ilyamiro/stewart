import json
import sys
import os.path
import time
import logging
import re
import random
import subprocess
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

from data.constants import (
    PROJECT_DIR, CONFIG_FILE, CONFIG_DIR, PLUGINS_DIR,
    USER_CONFIG_DIR, DEFAULT_CONFIG_DIR, USER_PLUGINS_DIR,
    DEFAULT_PLUGINS_DIR, TTS_CACHE_DIR
)
from audio.tts import TTS
from utils import load_yaml, filter_lang_config, load_lang, notify, sanitize_filename

from .commands.tree import Manager
from .commands.tools import ToolRegistry, ActionTool
from .commands.router import CommandRouter
from .commands.actions import BaseAction, ActionParameters, ActionResult, ExecutionContext, Field
from .services.desktop import DesktopService, get_desktop_service
from .commands.ollama import OllamaToolCaller
from .events.events import Event, EventLogger
from .locales.service import Locale, LocalePluginService
from .files.caching import Runtime

log = logging.getLogger("API: app")



class AudioInterface:
    def __init__(self):
        self.ipc_socket_path = "/tmp/mpv-socket"
        self._player = None

    @property
    def player(self):
        if self._player is None:
            try:
                import mpv
                self._player = mpv.MPV(
                    ytdl=True,
                    input_default_bindings=True,
                    video=False,
                    input_ipc_server=self.ipc_socket_path
                )
            except Exception as e:
                log.error(f"Failed to initialize MPV player: {e}")
                self._player = None
        return self._player

    @player.setter
    def player(self, val):
        self._player = val

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
        self.lang = self.get_lang()
        self.config = self.get_config()

        self.Event = Event

        self.runtime = Runtime()

        self.manager = Manager()
        self.Command = self.manager.Command
        self.tool_registry = ToolRegistry(self)
        self.router = CommandRouter(self.manager, self.tool_registry, self.config)
        self.manager.set_router(self.router)
        self.ActionTool = ActionTool
        self.BaseAction = BaseAction
        self.ActionParameters = ActionParameters
        self.ActionResult = ActionResult
        self.ExecutionContext = ExecutionContext
        self.Field = Field
        self.desktop = get_desktop_service(api=self)

        self.eventLogger = EventLogger()

        self._mouse = None
        self._keyboard = None
        self.audio = AudioInterface()

        self.localeService = LocalePluginService(self.lang)
        self.Locale = Locale

        self.tts = TTS(self.config, self.lang)
        self.is_speaking = False
        self._tts_lock = threading.Lock()

        self.__pre_init_callbacks__: list = []
        self.__post_init_callbacks__: list = []

        self.__no_command_callback__ = self.__no_command_default__ if self.config["settings"]["react-no-command"] else self.__blank__

        self.__trigger_callback__ = self.__blank__

        self.__actions__: dict = {}

    @property
    def mouse(self):
        if self._mouse is None:
            try:
                from pynput.mouse import Controller as Mouse
                self._mouse = Mouse()
            except Exception as e:
                log.warning(f"Could not initialize Mouse controller: {e}")
                self._mouse = None
        return self._mouse

    @mouse.setter
    def mouse(self, val):
        self._mouse = val

    @property
    def keyboard(self):
        if self._keyboard is None:
            try:
                from pynput.keyboard import Controller as Keyboard
                self._keyboard = Keyboard()
            except Exception as e:
                log.warning(f"Could not initialize Keyboard controller: {e}")
                self._keyboard = None
        return self._keyboard

    @keyboard.setter
    def keyboard(self, val):
        self._keyboard = val

    @property
    def MouseButton(self):
        try:
            from pynput.mouse import Button
            return Button
        except Exception:
            return None

    @property
    def Key(self):
        try:
            from pynput.keyboard import Key
            return Key
        except Exception:
            return None

    @staticmethod
    def __blank__(context, history):
        pass

    def __no_command_default__(self, context, history):
        answer = random.choice(self.config[f"answers"]["default"])
        self.say(answer)

        self.eventLogger.record(self.Event(
            "wake_word_used",
            {"answer": answer}
        ))

    def get_cached_audio_path(self, text: str, prosody=94, speaker=None):
        """Returns the file path of the cached audio file if it exists, otherwise None."""
        if not text or not self.config.get("audio", {}).get("tts", {}).get("enable-caching", True):
            return None
        parsed = self.tts.parse_config_answers(text)
        normalized = parsed.strip().lower()
        engine = getattr(self.tts, "engine", "kokoro")
        hash_input = str(f"engine={engine}|{normalized}|prosody={prosody}|speaker={speaker or ''}")
        cached_hash = self.runtime.read(f"tts:{hash_input}")
        if cached_hash:
            tts_cache: Path = self.runtime.mkdir_cache("tts")
            cached_file = tts_cache / f"{cached_hash}.wav"
            if cached_file.exists():
                return str(cached_file)
        return None

    def get_cached_answers(self, answers: list, prosody=94, speaker=None):
        """Batch-evaluates a list of answer templates and returns (raw_template, parsed_text, wav_path) for cached ones."""
        if not answers or not self.config.get("audio", {}).get("tts", {}).get("enable-caching", True):
            return []
        tts_cache: Path = self.runtime.mkdir_cache("tts")
        cached = []
        engine = getattr(self.tts, "engine", "kokoro")
        for text in answers:
            parsed = self.tts.parse_config_answers(text)
            normalized = parsed.strip().lower()
            hash_input = f"engine={engine}|{normalized}|prosody={prosody}|speaker={speaker or ''}"
            cached_hash = self.runtime.read(f"tts:{hash_input}")
            if cached_hash:
                wav_file = tts_cache / f"{cached_hash}.wav"
                if wav_file.exists():
                    cached.append((text, parsed, str(wav_file)))
        return cached

    def is_cached(self, text: str, prosody=94, speaker=None) -> bool:
        """Returns True if the text audio is already synthesized and present on disk."""
        return self.get_cached_audio_path(text, prosody=prosody, speaker=speaker) is not None

    def say_sync(self, text: str, no_audio=False, prosody=94, speaker=None):
        """Synchronously synthesizes and plays audio, waiting for playback to finish."""
        if not text or not self.tts.active:
            if not text:
                return
            log.debug(f"No sound: {text}")
            return

        text = self.tts.parse_config_answers(text)
        self.is_speaking = True
        try:
            cached_file = self.get_cached_audio_path(text, prosody=prosody, speaker=speaker)
            if cached_file and os.path.exists(cached_file):
                from audio.tts.synthesis import play_audio
                play_audio(cached_file)
                return

            if self.config.get("audio", {}).get("tts", {}).get("enable-caching", True):
                tts_cache: Path = self.runtime.mkdir_cache("tts")
                normalized = text.strip().lower()
                engine = getattr(self.tts, "engine", "kokoro")
                hash_input = str(f"engine={engine}|{normalized}|prosody={prosody}|speaker={speaker or ''}")
                phrase_hash = hashlib.sha256(hash_input.encode()).hexdigest()
                filename = tts_cache / sanitize_filename(f"{phrase_hash}.wav")

                self.tts.say(text=text, path=str(filename), no_audio=no_audio, prosody=prosody, speaker=speaker)
                self.runtime.write(f"tts:{hash_input}", phrase_hash)
            else:
                self.tts.say(text=text, no_audio=no_audio, prosody=prosody, speaker=speaker)
        finally:
            self.is_speaking = False

    def say(self, text: str, no_audio=False, prosody=94, speaker=None):
        if not text:
            return

        if not self.tts.active:
            log.debug(f"No sound: {text}")
            return

        text = self.tts.parse_config_answers(text)

        def call_tts_in_thread(**kwargs):
            with self._tts_lock:
                self.is_speaking = True
                try:
                    self.tts.say(**kwargs)
                finally:
                    self.is_speaking = False

        if self.config["audio"]["tts"]["enable-caching"]:
            tts_cache: Path = self.runtime.mkdir_cache("tts")

            normalized = text.strip().lower()
            engine = getattr(self.tts, "engine", "kokoro")
            hash_input = str(f"engine={engine}|{normalized}|prosody={prosody}|speaker={speaker or ''}")
            phrase_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            filename = tts_cache / sanitize_filename(f"{phrase_hash}.wav")

            cached_hash = self.runtime.read(f"tts:{hash_input}")
            if cached_hash:
                cached_file = tts_cache / f"{cached_hash}.wav"
                if cached_file.exists():
                    log.debug(f"Using cached tts file {cached_file} for text: {text}")
                    self.runtime.write(f"tts:{hash_input}", cached_hash)
                    def play_cached():
                        with self._tts_lock:
                            self.is_speaking = True
                            try:
                                from audio.tts.synthesis import play_audio
                                play_audio(str(cached_file))
                            finally:
                                self.is_speaking = False
                    threading.Thread(target=play_cached, daemon=True, name="TTS-Cached").start()
                    return

            call_process = threading.Thread(target=call_tts_in_thread, kwargs=dict(text=text, path=str(filename), no_audio=no_audio, prosody=prosody, speaker=speaker), daemon=True)
            call_process.start()
            self.runtime.write(f"tts:{hash_input}", phrase_hash)
        else:
            fallback_wav = str(TTS_CACHE_DIR / "audio.wav")
            TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            call_process = threading.Thread(target=call_tts_in_thread, kwargs=dict(text=text, path=fallback_wav, no_audio=no_audio,
                                               prosody=prosody, speaker=speaker), daemon=True)
            call_process.start()


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

    def add_func_for_search(self, *args):
        log.info(f"Added functions to actions: {args}")
        for func in args:
            self.__actions__.update({func.__name__: func})

    def register_action(self, action: BaseAction):
        """Registers a BaseAction instance directly into the action registry."""
        if isinstance(action, BaseAction):
            if action.api is None:
                action.api = self
            if action.desktop is None:
                action.desktop = self.desktop
            self.__actions__[action.name] = action
            log.info(f"Registered action '{action.name}'")
        else:
            log.warning(f"Expected BaseAction instance, got {type(action)}")

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
            discovered = {}
            for member_name, member_obj in members:
                if not include_private and member_name.startswith('__'):
                    continue
                if isinstance(member_obj, BaseAction):
                    if member_obj.api is None:
                        member_obj.api = self
                    if member_obj.desktop is None:
                        member_obj.desktop = self.desktop
                    discovered[member_obj.name or member_name] = member_obj
                elif inspect.isclass(member_obj) and issubclass(member_obj, BaseAction) and member_obj is not BaseAction:
                    try:
                        instance = member_obj(api=self, desktop=self.desktop)
                        discovered[instance.name or member_name] = instance
                    except Exception as e:
                        log.debug(f"Could not auto-instantiate action class {member_name}: {e}")
                elif inspect.isfunction(member_obj) and getattr(member_obj, "__module__", None) == module.__name__:
                    discovered[member_name] = member_obj

            self.__actions__.update(discovered)
            log.info(f"Added actions from {module.__name__}: {list(discovered.keys())}")
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

    @staticmethod
    def _load_plugin_modules(directory):
        import importlib.util
        plugin_base = os.path.basename(directory)

        for root, _, files in os.walk(directory):
            for filename in files:
                if filename.endswith('.py') and not filename.startswith('__'):
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, directory)
                    mod_suffix = rel_path[:-3].replace(os.sep, ".")
                    mod_name = f"plugins.{plugin_base}.{mod_suffix}"
                    try:
                        spec = importlib.util.spec_from_file_location(mod_name, file_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            sys.modules[mod_name] = module
                            spec.loader.exec_module(module)
                    except Exception as e:
                        log.debug(f"Optional module {file_path} skipped: {e}")

    def _import_plugin(self, directory, manifest):
        name = manifest.get("name")

        locales = manifest.get("locales")
        if locales:
            loaded_locales = []
            for lang, path in locales.items():
                if not path:
                    continue
                locale = self.Locale(lang, f"{directory}/{path}")
                loaded_locales.append(locale)
            if loaded_locales:
                self.localeService.add(name, loaded_locales)
            else:
                log.info(f"Loading plugin {directory} without locales")
                self._load_plugin_modules(directory)

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
            log.info(f"Error reading manifest.yaml for plugin {path}: {e}")
            return None

    def load_plugins(self):
        skip_dirs = ["__pycache__", ".idea", "venv", "locales"]
        plugin_sources = []
        if Path(PLUGINS_DIR).exists():
            plugin_sources.append(Path(PLUGINS_DIR))
        if USER_PLUGINS_DIR.exists() and USER_PLUGINS_DIR != Path(PLUGINS_DIR):
            plugin_sources.append(USER_PLUGINS_DIR)

        for base_dir in plugin_sources:
            for path in base_dir.iterdir():
                if path.is_dir() and path.name not in skip_dirs:
                    manifest = self._load_plugin_manifest(str(path))
                    if manifest:
                        self._import_plugin(str(path), manifest)
                    else:
                        log.info(f"There was an error loading manifest.yaml for plugin {path}")

    @staticmethod
    def get_lang():
        """
        Returns language settings
        """
        return load_lang()

    @staticmethod
    def _recursive_merge(base: dict, override: dict) -> dict:
        merged = base.copy()
        for k, v in override.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = AppAPI._recursive_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    @staticmethod
    def deep_merge(base: dict, lang: dict):
        merged = base.copy()
        specs = lang.get("specifications", {}) if lang else {}

        if "audio" in merged and specs.get("audio"):
            merged["audio"].setdefault("stt", {}).update(specs.get("audio", {}).get("stt", {}))
        if "settings" in merged and specs.get("triggers"):
            if not isinstance(merged.get("settings"), dict):
                merged["settings"] = {}
            if "trigger" not in merged["settings"] or not isinstance(merged["settings"]["trigger"], dict):
                merged["settings"]["trigger"] = {}
            merged["settings"]["trigger"]["triggers"] = specs.get("triggers")
        if "settings" in merged and specs.get("user"):
            merged["settings"]["user"] = specs.get("user")
        if "start-up" in merged and specs.get("start-up"):
            merged.setdefault("start-up", {}).update(specs.get("start-up", {}))
        if lang and "answers" in lang:
            merged["answers"] = lang.get("answers")
        if lang and "commands" in lang:
            merged["commands"] = lang.get("commands")

        return merged

    def get_config(self):
        base_config_path = DEFAULT_CONFIG_DIR / "config.yaml"
        base_config = load_yaml(str(base_config_path)) or {}

        dot_stewart_cfg = Path.home() / ".stewart" / "config.yaml"
        if dot_stewart_cfg.exists():
            stewart_config = load_yaml(str(dot_stewart_cfg)) or {}
            base_config = self._recursive_merge(base_config, stewart_config)

        user_config_file = USER_CONFIG_DIR / "config.yaml"
        if user_config_file.exists() and user_config_file != base_config_path and user_config_file != dot_stewart_cfg:
            user_config = load_yaml(str(user_config_file)) or {}
            base_config = self._recursive_merge(base_config, user_config)

        lang_config_path = USER_CONFIG_DIR / f"langs/{self.lang}.yaml"
        if not lang_config_path.exists():
            lang_config_path = DEFAULT_CONFIG_DIR / f"langs/{self.lang}.yaml"

        if lang_config_path.exists():
            lang_config = load_yaml(str(lang_config_path))
            return self.deep_merge(base_config, lang_config)

        fallback_lang = DEFAULT_CONFIG_DIR / "langs/en.yaml"
        return self.deep_merge(base_config, load_yaml(str(fallback_lang)) or {})

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
        try:
            USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            user_config_file = USER_CONFIG_DIR / "config.yaml"
            data = {}
            if user_config_file.exists():
                with open(user_config_file, "r", encoding="utf-8") as file:
                    data = yaml.safe_load(file) or {}
            if "plugins" not in data:
                data["plugins"] = {}
            data["plugins"].update(self.config.get("plugins", {}))
            with open(user_config_file, "w", encoding="utf-8") as file:
                yaml.safe_dump(data, file, allow_unicode=True)
        except Exception as e:
            log.warning(f"Could not save plugins config to user config: {e}")

    @staticmethod
    def start_background_process(func: types.FunctionType):
        log.info(f"added {func.__name__}")
        bg_thread = threading.Thread(target=func, name=func.__name__)
        bg_thread.start()

app = AppAPI()