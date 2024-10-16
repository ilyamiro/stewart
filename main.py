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

from data.constants import PLUGINS_FOLDER
from gui import gui_main


def main():
    # noinspection PyBroadException
    try:
        # system preparations
        log.debug("started running...")

        system_setup()
        set_logging(True)

        gui_main(start_time)

    #
    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")


if __name__ == "__main__":
    main()
