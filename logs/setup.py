import logging
import os.path
from datetime import datetime
import glob

from vosk import SetLogLevel
from voicesynth import disable_logging

from data.constants import LOG_DIR, LOG_FILENAME


def logging_clear_files():
    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "log_*.log")), key=os.path.getmtime)

    # Keep only the last 3 log files
    if len(log_files) > 3:
        for log_file in log_files[:-3]:
            os.remove(log_file)


def logging_imports_disable():
    SetLogLevel(-1)
    disable_logging()


def logging_setup():
    # ensure that log directory is existent
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logging.basicConfig(
        level=logging.DEBUG,
        format='stewart - %(name)s -  %(asctime)s:  (%(levelname)s) - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILENAME),
            logging.StreamHandler()
        ]
    )

    logging_imports_disable()
    logging_clear_files()

    logging.debug("Logging system setup ended successfully. Application started")


def set_logging(enable: bool):
    """
    Enable or disable logging
    """
    logging.disable(logging.NOTSET if enable else logging.CRITICAL)


logging_setup()
