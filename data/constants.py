import os
import hashlib

from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent.parent

with open(f"{PROJECT_DIR}/version.txt", "r", encoding="utf-8") as file:
    APP_VERSION  = file.read()
APP_NAME = "stewart"
APP_ID = hashlib.sha256(f"{APP_NAME}:{APP_VERSION}".encode()).hexdigest()[:16]  # Unique but readable
CACHING_MARKER_FILENAME = ".stewart_cache_info.json"

# config
CONFIG_DIR = f"{PROJECT_DIR}/config"

CONFIG_FILE = f"{CONFIG_DIR}/config.yaml"
LANG_FILE = f"{CONFIG_DIR}/lang.txt"

# plugins
PLUGINS_DIR = f"{PROJECT_DIR}/plugins"

# logs
LOG_DIR = f"/home/ilyamiro/.cache/stewart/logs/"
LOG_FILENAME = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.log")

# MY PHONE LOCAL IP
ADB_DEVICE_IP = "192.168.1.160"

# Caching
# CACHING_DIR = os.path.join(os.path.expanduser("~"), ".cache/stewart")

# Weather
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENWEATHER_API = "https://api.openweathermap.org/data/2.5/weather"
MY_CITY_LAT = os.getenv("MY_CITY_LAT")
MY_CITY_LON = os.getenv("MY_CITY_LON")

