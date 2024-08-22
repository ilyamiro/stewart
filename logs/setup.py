import logging
import os.path
from datetime import datetime
import glob

from vosk import SetLogLevel
from voicesynth import disable_logging

LOG_DIR = os.path.join(os.path.dirname(__file__), "app_log")
LOG_FILENAME = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def verbose_off():
    SetLogLevel(-1)
    disable_logging()
    logging.getLogger("root").setLevel(logging.DEBUG)


def get_logger(name):

    logging.basicConfig(level=logging.DEBUG,
                        format=LOG_FORMAT,
                        filename=LOG_FILENAME,
                        filemode='w')

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger(name).addHandler(console)
    return logging.getLogger(name)


def logging_setup():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "log_*.log")), key=os.path.getmtime)

    # Keep only the last 5 log files
    if len(log_files) > 3:
        for log_file in log_files[:-3]:
            os.remove(log_file)

    logger = get_logger("logs")

    logger.debug("Logging system setup ended successfully. Application started")
