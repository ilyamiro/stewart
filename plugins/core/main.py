import subprocess
import re
import os
import logging
import time

from data.constants import CONFIG_FILE, PROJECT_FOLDER, ADB_DEVICE_IP
from utils import load_yaml, run, run_stdout
from api import app

log = logging.getLogger("core-plugin")

app.add_dir_for_search("plugins/core/actions", include_private=False)

app.update_config(
    {
        "core": {
            "music-download": False,
            "no-multi-first-words": {
                "en": ["find", "write", "answer", "play"],
                "ru": ["найди", "найти", "запиши", "скажи", "ответь"]
            },
            "usb-default": ["linux foundation", "webcam", "network", "finger"]
        }
    }
)

