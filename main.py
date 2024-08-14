# standart library imports
import logging

# third-party imports

# inside imports
from logs import logging_setup
from utils import system_setup

logging_setup(verbose=False)

from audio import STT, ttsi


def main():
    system_setup()
    stt = STT()
    while True:
        for word in stt.listen():
            print(word)


if __name__ == "__main__":
    main()
