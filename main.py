# standart library imports
import logging
# third-party imports

# inside imports
from logs import logging_setup
from utils import system_setup

from gui import main


if __name__ == "__main__":
    system_setup()
    main()
