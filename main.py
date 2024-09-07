# standart library imports
import logging
import traceback
# third-party imports

# inside imports
from logs import logging_setup
from utils import system_setup

from app import App
# from gui import main

log = logging.getLogger("execute file")

if __name__ == "__main__":
    # noinspection PyBroadException
    try:
        system_setup()
        app = App()
        app.start()
    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")
