import subprocess
import re
import os
import logging
import time
import random
import playsound

from data.constants import CONFIG_FILE, PROJECT_DIR, ADB_DEVICE_IP
from utils import load_yaml, run, run_stdout, filter_lang_config
from api import app

# log = logging.getLogger("core-plugin")

app.add_dir_for_search("plugins/core/actions", include_private=False)

app.update_config(
    {
        "core": {
            "music-download": False,
            "usb-default": ["linux foundation", "webcam", "network", "finger"]
        }
    }
)

