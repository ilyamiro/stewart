import logging
import time
import traceback

start_time = time.time()

from logs import logging_setup, set_logging
from utils import system_setup, import_plugins, find_plugins, admin, clear

log = logging.getLogger("main")

if admin():
    log.error("Program should not be run with super user (sudo or admin) privileges. Exiting...")
    sys.exit()

from data.constants import PLUGINS_FOLDER


def main():
    # noinspection PyBroadException
    try:
        log.debug("Started running...")

        system_setup()
        set_logging(True)

        from app import App
        from api import app as app_api
        from api import tree

        app = App(app_api, tree)
        app.start(start_time)
        app.run()

    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")


if __name__ == "__main__":
    main()
