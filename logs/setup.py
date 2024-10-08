import logging
import os.path
from datetime import datetime
import glob

from vosk import SetLogLevel
from voicesynth import disable_logging

from data.constants import LOG_DIR, LOG_FILENAME


def logging_setup():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logging.basicConfig(
        level=logging.DEBUG,
        format='STEWART - %(name)s -  %(asctime)s:  (%(levelname)s) - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILENAME),
            logging.StreamHandler()
        ]
    )
    SetLogLevel(-1)

    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "log_*.log")), key=os.path.getmtime)

    # Keep only the last 3 log files
    if len(log_files) > 3:
        for log_file in log_files[:-3]:
            os.remove(log_file)

    logging.debug("Logging system setup ended successfully. Application started")


logging_setup()
