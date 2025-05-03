import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent.parent

# config
CONFIG_DIR = f"{PROJECT_DIR}/config"

CONFIG_FILE = f"{CONFIG_DIR}/config.yaml"
LANG_FILE = f"{CONFIG_DIR}/lang.txt"

# plugins
PLUGINS_DIR = f"{PROJECT_DIR}/plugins"

# logs
LOG_DIR = f"{PROJECT_DIR}/logs/app_log"
LOG_FILENAME = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.log")

# MY PHONE LOCAL IP
ADB_DEVICE_IP = "192.168.1.160"

# Caching
CACHING_DIR = os.path.join(os.path.expanduser("~"), ".cache/stewart")

# Weather
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENWEATHER_API = "https://api.openweathermap.org/data/2.5/weather"
MY_CITY_LAT = os.getenv("MY_CITY_LAT")
MY_CITY_LON = os.getenv("MY_CITY_LON")

