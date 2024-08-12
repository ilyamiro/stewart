import logging
import os.path
from datetime import datetime
import glob

LOG_DIR = os.path.join(os.path.dirname(__file__), "app_log")


def logging_setup():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_filename = os.path.join(LOG_DIR, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    # Set up the logging configuration

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )

    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "log_*.log")), key=os.path.getmtime)

    # Keep only the last 5 log files
    if len(log_files) > 5:
        for log_file in log_files[:-5]:
            os.remove(log_file)

    logging.debug("Logging system setup ended successfully. Application started")
