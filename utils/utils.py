import subprocess
import logging

import vosk
# loggers
from vosk import SetLogLevel
from voicesynth import disable_logging


def run(*args, stdout: bool = False):
    subprocess.run(
        args,
        stdout=subprocess.DEVNULL if not stdout else None,
        stderr=subprocess.STDOUT
    )


def verbose_off():
    SetLogLevel(-1)
    disable_logging()
    logging.getLogger("root").setLevel(logging.DEBUG)
