# standart library imports
import logging
import traceback
# third-party imports

# inside imports
from logs import logging_setup, set_logging
from utils import system_setup, import_plugins, find_plugins
from app import App
from api import app as app_api

from data.constants import PLUGINS_FOLDER
# from gui import main


log = logging.getLogger("main")


def main():
    # noinspection PyBroadException
    try:
        system_setup()
        set_logging(True)
        app = App(app_api)

        # plugins
        found_plugins = find_plugins(PLUGINS_FOLDER)
        import_plugins(found_plugins)

        # main app and api initialization
        app.initialize()
        app.start()

    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")


if __name__ == "__main__":
    main()
