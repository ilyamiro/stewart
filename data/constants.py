import os
from datetime import datetime

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# config
CONFIG_FILE = f"{PROJECT_FOLDER}/private_config.yaml"

# logs
LOG_DIR = f"{PROJECT_FOLDER}/logs/app_log"
LOG_FILENAME = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.log")
