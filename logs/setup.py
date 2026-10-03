import logging
import os
import glob
import warnings
from datetime import datetime

try:
    from vosk import SetLogLevel
except ImportError:
    SetLogLevel = None

from data.constants import LOG_DIR, LOG_FILENAME

# Suppress noisy warnings from third-party libraries (PyTorch, HuggingFace, Plyer dbus)
warnings.filterwarnings("ignore", category=UserWarning, module=r"torch\..*")
warnings.filterwarnings("ignore", category=FutureWarning, module=r"torch\..*")
warnings.filterwarnings("ignore", category=UserWarning, module=r"plyer\..*")
warnings.filterwarnings("ignore", category=UserWarning, module=r".*weight_norm.*")
warnings.filterwarnings("ignore", message=r".*repo_id.*")
warnings.filterwarnings("ignore", message=r".*unauthenticated requests.*")
warnings.filterwarnings("ignore", message=r".*dbus package is not installed.*")

# Prevent noisy third-party libraries from polluting stdout
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

NOISY_LOGGERS = [
    "httpcore",
    "httpx",
    "huggingface_hub",
    "urllib3",
    "torch",
    "filelock",
    "asyncio",
    "kokoro",
    "transformers",
    "fsspec",
    "pynput",
]


def logging_clear_files():
    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "log_*.log")), key=os.path.getmtime)

    # Keep only the last 10 log files
    if len(log_files) > 10:
        for log_file in log_files[:-10]:
            os.remove(log_file)


def logging_imports_disable():
    if SetLogLevel is not None:
        SetLogLevel(-1)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def logging_setup():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logging.basicConfig(
        level=logging.DEBUG,
        format='stewart - %(name)s -  %(asctime)s:  (%(levelname)s) - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILENAME),
            logging.StreamHandler()
        ]
    )

    logging_imports_disable()
    logging_clear_files()

    logging.debug("Logging system setup ended successfully. Application started")


def set_logging(enable: bool):
    """
    Enable or disable logging
    """
    logging.disable(logging.NOTSET if enable else logging.CRITICAL)
    if enable:
        logging_imports_disable()


logging_setup()