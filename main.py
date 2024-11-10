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
from gui import GUI


def start_gui():
    import flet as ft
    instance = GUI(start_time)
    ft.app(instance.start)


def main(gui: bool = False):
    # noinspection PyBroadException
    try:
        # system preparations
        log.debug("started running...")

        system_setup()
        set_logging(True)

        if gui:
            start_gui()
        else:
            from app import App
            from api import app as app_api
            from api import tree

            app = App(app_api, tree)
            app.start(start_time)
            app.run()

    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")


if __name__ == "__main__":
    main(gui=True)
