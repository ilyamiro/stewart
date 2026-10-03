import os
import hashlib
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "stewart"
PROJECT_DIR = Path(__file__).resolve().parent.parent

version_file = PROJECT_DIR / "version.txt"
if version_file.exists():
    try:
        with open(version_file, "r", encoding="utf-8") as file:
            APP_VERSION = file.read().strip()
    except Exception:
        APP_VERSION = "1.9.3-1"
else:
    APP_VERSION = "1.9.3-1"

APP_ID = hashlib.sha256(f"{APP_NAME}:{APP_VERSION}".encode()).hexdigest()[:16]
CACHING_MARKER_FILENAME = ".stewart_cache_info.json"

# XDG Base Directory specification
XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
XDG_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
XDG_STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))

# User-specific mutable directories
USER_CONFIG_DIR = Path(os.environ.get("STEWART_CONFIG_DIR", XDG_CONFIG_HOME / APP_NAME))
USER_CACHE_DIR = Path(os.environ.get("STEWART_CACHE_DIR", XDG_CACHE_HOME / APP_NAME))
USER_DATA_DIR = Path(os.environ.get("STEWART_DATA_DIR", XDG_DATA_HOME / APP_NAME))
USER_STATE_DIR = Path(os.environ.get("STEWART_STATE_DIR", XDG_STATE_HOME / APP_NAME))

# Bundled fallback directories
DEFAULT_CONFIG_DIR = PROJECT_DIR / "config"
DEFAULT_DATA_DIR = PROJECT_DIR / "data"
DEFAULT_PLUGINS_DIR = PROJECT_DIR / "plugins"

def get_lang_file() -> Path:
    user_file = USER_CONFIG_DIR / "lang.txt"
    if user_file.exists():
        return user_file
    local_file = Path.cwd() / "config" / "lang.txt"
    if local_file.exists():
        return local_file
    return DEFAULT_CONFIG_DIR / "lang.txt"

# Effective configuration paths
CONFIG_DIR = USER_CONFIG_DIR if (USER_CONFIG_DIR / "config.yaml").exists() else DEFAULT_CONFIG_DIR
CONFIG_FILE = USER_CONFIG_DIR / "config.yaml" if (USER_CONFIG_DIR / "config.yaml").exists() else DEFAULT_CONFIG_DIR / "config.yaml"
LANG_FILE = get_lang_file()

# Plugins
USER_PLUGINS_DIR = USER_DATA_DIR / "plugins"
PLUGINS_DIR = str(DEFAULT_PLUGINS_DIR)

# Logs & Cache
LOG_DIR = str(USER_STATE_DIR / "logs")
TTS_CACHE_DIR = USER_CACHE_DIR / "tts"
LOG_FILENAME = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")

# Assets
SOUNDS_DIR = DEFAULT_DATA_DIR / "sounds"
STARTUP_SOUND = SOUNDS_DIR / "startup.wav"
BEEP_SOUND = SOUNDS_DIR / "beep.wav"

# Device & Network Settings
ADB_DEVICE_IP = os.getenv("ADB_DEVICE_IP", "192.168.1.160")

# Weather
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENWEATHER_API = "https://api.openweathermap.org/data/2.5/weather"
MY_CITY_LAT = os.getenv("MY_CITY_LAT")
MY_CITY_LON = os.getenv("MY_CITY_LON")
