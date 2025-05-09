import os
import platform
import json
import hashlib
import logging
import time

from pathlib import Path
from datetime import datetime
from typing import Union

from data.constants import APP_NAME, APP_ID, APP_VERSION, CACHING_MARKER_FILENAME

log = logging.getLogger("runtime")


class Runtime:
    def __init__(self):
        self.path = self._get_cache_dir()
        self.runtime_file = self.path / "runtime.json"
        log.info(f"Using preferable caching directory: {self.path}")

    def _load(self):
        if self.runtime_file.exists():
            try:
                with open(self.runtime_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                log.warning(f"Failed to load runtime file: {e}")
        return {}

    def _save(self, data):
        try:
            with open(self.runtime_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Failed to write runtime file: {e}")

    def write(self, key, value):
        data = self._load()
        data[key] = value
        self._save(data)

    def read(self, key, default=None):
        data = self._load()
        return data.get(key, default)

    def delete(self, key):
        data = self._load()
        if key in data:
            del data[key]
            self._save(data)

    def clear(self):
        if self.runtime_file.exists():
            self.runtime_file.unlink()

    @staticmethod
    def _get_possible_cache_paths():
        paths = []

        if platform.system() == "Windows":
            base_win = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if base_win:
                paths.append(Path(base_win) / APP_NAME)
        else:
            home = os.environ.get("HOME")
            if home:
                paths.append(Path(home) / ".cache" / APP_NAME)

        paths.append(Path(".cache"))  # Fallback
        return paths

    @staticmethod
    def _is_valid_stewart_cache(path: Path) -> bool:
        marker = path / CACHING_MARKER_FILENAME
        if not marker.exists():
            return False
        try:
            with open(marker, "r") as f:
                data = json.load(f)
            return data.get("app_id") == APP_ID
        except Exception:
            return False

    @staticmethod
    def _write_marker_file(path: Path):
        marker = path / CACHING_MARKER_FILENAME
        data = {
            "app_id": APP_ID,
            "app_name": APP_NAME,
            "version": APP_VERSION,
            "created": datetime.now().isoformat() + "Z",
            "user": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        }
        with open(marker, "w") as f:
            json.dump(data, f)

    def _get_cache_dir(self):
        for path in self._get_possible_cache_paths():
            if self._is_valid_stewart_cache(path):
                return path

        for path in self._get_possible_cache_paths():
            try:
                path.mkdir(parents=True, exist_ok=True)
                self._write_marker_file(path)
                return path
            except Exception:
                continue

        fallback = Path(".cache")
        fallback.mkdir(parents=True, exist_ok=True)
        self._write_marker_file(fallback)
        return fallback

    def mkdir_cache(self, name: str) -> Path:
        """
        Creates a subdirectory in the cache directory (e.g., 'audio', 'images').
        Ensures the path is safe and writable.
        """
        safe_name = Path(name).name  # prevent path traversal like "../../etc"
        full_path = self.path / safe_name
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            return full_path
        except Exception as e:
            log.warning(f"Failed to create cache subdirectory '{safe_name}': {e}")
            raise

    def cleanup(self, name: str, **kwargs):
        """
        Cleans up the cache subdirectory `name` under flexible conditions.

        Keyword arguments:
            - max_files: int — Keep only the most recent N files.
            - if_file_exists: str | list[str] — Trigger cleanup only if these files exist.
            - only_extensions: list[str] — Only consider files with these extensions (e.g., [".wav", ".json"]).
            - older_than: int — Delete files older than N seconds.
        """
        dir_path = self.path / Path(name).name
        if not dir_path.exists() or not dir_path.is_dir():
            log.warning(f"Directory {dir_path} does not exist for cleanup.")
            return

        files = list(dir_path.iterdir())
        files = [f for f in files if f.is_file()]

        if "only_extensions" in kwargs:
            exts = kwargs["only_extensions"]
            files = [f for f in files if f.suffix in exts]

        if "if_file_exists" in kwargs:
            targets = kwargs["if_file_exists"]
            if isinstance(targets, str):
                targets = [targets]
            if not any((dir_path / t).exists() for t in targets):
                return

        if "older_than" in kwargs:
            cutoff = time.time() - kwargs["older_than"]
            for f in files:
                if f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                        log.info(f"Deleted old file: {f}")
                    except Exception as e:
                        log.warning(f"Failed to delete old file {f}: {e}")
            return

        if "max_files" in kwargs:
            max_files = kwargs["max_files"]
            if len(files) > max_files:
                files.sort(key=lambda f: f.stat().st_mtime)
                to_delete = files[:-max_files]
                for f in to_delete:
                    try:
                        f.unlink()
                        log.info(f"Deleted excess file: {f}")
                    except Exception as e:
                        log.warning(f"Failed to delete file {f}: {e}")


