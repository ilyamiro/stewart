import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

from .config import DEFAULT_PROFILE_DIR


def clean_stale_profile_locks(profile_dir: Path) -> None:
    """Removes stale Firefox lock files if no Firefox process is locking it."""
    lock_file = profile_dir / "lock"
    parentlock_file = profile_dir / ".parentlock"
    for f in (lock_file, parentlock_file):
        if f.is_symlink() or f.exists():
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass


@contextmanager
def get_browser(
    profile_dir: Optional[Path] = None,
    headless: bool = True,
    download_dir: Optional[Path] = None,
    window_size: tuple[int, int] = (1440, 900),
) -> Generator[webdriver.Firefox, None, None]:
    """Provides a managed Selenium Firefox WebDriver instance with persistent profile."""
    profile_path = Path(profile_dir or DEFAULT_PROFILE_DIR).expanduser().resolve()
    profile_path.mkdir(parents=True, exist_ok=True)
    clean_stale_profile_locks(profile_path)

    options = Options()
    if headless:
        options.add_argument("-headless")
    options.add_argument("-profile")
    options.add_argument(str(profile_path))
    options.add_argument(f"--width={window_size[0]}")
    options.add_argument(f"--height={window_size[1]}")

    if download_dir:
        dl_path = Path(download_dir).resolve()
        dl_path.mkdir(parents=True, exist_ok=True)
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", str(dl_path))
        options.set_preference("browser.download.useDownloadDir", True)
        options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf,application/octet-stream,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword,text/plain")
        options.set_preference("pdfjs.disabled", True)

    driver = webdriver.Firefox(options=options)
    try:
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        clean_stale_profile_locks(profile_path)
