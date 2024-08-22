# standart library imports
import logging

# third-party imports

# inside imports
from logs import logging_setup
from utils import system_setup

from audio.input import STT

logging_setup(verbose=False)


def main():
    system_setup()


if __name__ == "__main__":
    main()
