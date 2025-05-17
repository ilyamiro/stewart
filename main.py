import logging
import random
import subprocess
import threading
import os
import time
import sys
import traceback

import utils
from logs import logging_setup, set_logging
from utils import system_setup, admin, clear, run

log = logging.getLogger("main")

if admin():
    log.error("Program should not be run with super user (sudo or admin) privileges. Exiting...")
    sys.exit()

from data.constants import PLUGINS_DIR
from audio.input import STT
from gui.animation import animation
from app import App
from api import app as iapp

utils.import_utils(iapp.lang, globals())


def main():
    try:
        log.debug("Started running...")

        start_time = time.time()

        system_setup()
        set_logging(True)

        app = App(iapp)
        config = app.api.get_config()

        if config["settings"]["text-mode"]:
            app.start(start_time)
            app.run()
        else:
            stt = STT(app.api.lang)
            app.start(start_time)

            if config["start-up"]["sound-enable"]:
                app.api.audio.play(config["start-up"]["sound-path"])
                log.info("Played startup sound")
            if config["start-up"]["voice-enable"]:
                app.api.say(random.choice(config[f"start-up"]["answers"]))
                log.info("Played startup voice synthesis")

            thread = threading.Thread(target=animation)
            thread.daemon = True
            thread.start()

            app.run(stt, None)
            last_time = time.time()

            buffer = b""
            while True:
                data = stt.stream.read(512, exception_on_overflow=False)
                if stt.vad(data):
                    buffer += data
                else:
                    if len(buffer) > 16000:
                        result = stt.check_speaker(buffer)
                        if result:
                            run("loginctl", "unlock-session")
                            log.debug("Going out of the sleeping mode")
                            elapsed_time = time.time() - last_time
                            if elapsed_time < 600:
                                app.api.say(random.choice(config["answers"]["default"]))
                            elif elapsed_time < 3600:
                                app.api.say(random.choice(config["answers"]["short_away"]))
                            elif elapsed_time < 7200:
                                app.api.say(random.choice(config["answers"]["under_hour"]))
                            elif elapsed_time < 21600:
                                app.api.say(random.choice(config["answers"]["over_hour"]))
                            elif elapsed_time < 43200:
                                app.api.say(random.choice(config["answers"]["multiple_hours"]))
                            else:
                                app.api.say(random.choice(config["answers"]["half_day"]))

                            app.run(stt, last_time)

                            log.info("Successfully went into sleeping mode")

                            last_time = time.time()

                    buffer = b""

    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")


if __name__ == "__main__":
    main()
