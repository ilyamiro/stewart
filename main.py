import logging
import time
import traceback

from logs import logging_setup, set_logging
from utils import system_setup, import_plugins, find_plugins, admin, clear

log = logging.getLogger("main")

if admin():
    log.error("Program should not be run with super user (sudo or admin) privileges. Exiting...")
    sys.exit()

start_time = time.time()

from app import App
from api import app as app_api

from data.constants import PLUGINS_FOLDER
# from gui import main


def main():
    # noinspection PyBroadException
    try:
        # system preparations
        log.debug("started running...")

        system_setup()
        set_logging(True)

        app = App(app_api)

        # plugins
        found_plugins = find_plugins(PLUGINS_FOLDER)
        import_plugins(found_plugins)

        # main app and api initialization
        app.initialize()
        app.start(start_time)

    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")


if __name__ == "__main__":
    main()
