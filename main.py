# standart library imports
import logging
# third-party imports

# inside imports
from logs import logging_setup
from utils import system_setup

from app import App


def main():
    system_setup()

    app = App()
    app.start()


if __name__ == "__main__":
    main()
