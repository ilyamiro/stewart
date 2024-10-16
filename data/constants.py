import os
from pathlib import Path
from datetime import datetime

PROJECT_FOLDER = Path(__file__).resolve().parent.parent

# config
CONFIG_FILE = f"{PROJECT_FOLDER}/private_config.yaml"

# plugins
PLUGINS_FOLDER = f"{PROJECT_FOLDER}/plugins"

# logs
LOG_DIR = f"{PROJECT_FOLDER}/logs/app_log"
LOG_FILENAME = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.log")

# MY PHONE LOCAL IP (ahh security)
ADB_DEVICE_IP = "192.168.1.160"
