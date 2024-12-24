import subprocess
import re
import os
import logging
import time
import random
import playsound

from data.constants import CONFIG_FILE, PROJECT_FOLDER, ADB_DEVICE_IP
from utils import load_yaml, run, run_stdout, filter_lang_config
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


def play_startup():
    if app.config["start-up"]["sound-enable"]:
        app.audio.play(app.config["start-up"]["sound-path"])
        log.info("Played startup sound")
    if app.config["start-up"]["voice-enable"]:
        app.say(random.choice(app.get_config()[f"start-up"]["answers"]))
        log.info("Played startup voice synthesis")


app.set_pre_init(play_startup, 0)
