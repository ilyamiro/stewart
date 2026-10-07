import os
import shutil
import tempfile
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False


def is_selenium_available() -> bool:
    """Checks if selenium and geckodriver are available."""
    if not HAS_SELENIUM:
        return False
    has_geckodriver = shutil.which("geckodriver") is not None
    has_firefox = shutil.which("firefox") is not None
    return has_geckodriver and has_firefox


@contextmanager
def get_browser(
    headless: bool = True,
    window_size: tuple[int, int] = (1280, 800),
    timeout: int = 15,
) -> Generator[Optional[object], None, None]:
    """Provides a clean, temporary Selenium Firefox instance for parsing SPAs without requiring any special user profile."""
    if not is_selenium_available():
        yield None
        return

    temp_profile_dir = tempfile.mkdtemp(prefix="life_stream_browser_")
    driver = None
    try:
        options = FirefoxOptions()
        if headless:
            options.add_argument("-headless")
        options.add_argument("-profile")
        options.add_argument(temp_profile_dir)
        options.add_argument(f"--width={window_size[0]}")
        options.add_argument(f"--height={window_size[1]}")
        options.set_preference("media.volume_scale", "0.0")
        options.set_preference("dom.disable_open_during_load", True)
        options.set_preference("permissions.default.desktop-notification", 2)
        
        driver = webdriver.Firefox(options=options)
        driver.set_page_load_timeout(timeout)
        yield driver
    except Exception as e:
        logger.warning(f"Failed to start Selenium Firefox driver: {e}")
        yield None
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        try:
            shutil.rmtree(temp_profile_dir, ignore_errors=True)
        except OSError:
            pass


def fetch_rendered_html(url: str, wait_selector: Optional[str] = None, timeout: int = 10) -> Optional[str]:
    """Fetches dynamically rendered HTML using Selenium if available."""
    with get_browser(headless=True, timeout=timeout) as driver:
        if driver is None:
            return None
        try:
            driver.get(url)
            if wait_selector:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                )
            return driver.page_source
        except Exception as e:
            logger.warning(f"Error fetching rendered HTML for {url}: {e}")
            try:
                return driver.page_source
            except Exception:
                return None
