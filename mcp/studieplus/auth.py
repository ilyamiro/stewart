import time
from pathlib import Path
from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from rich.console import Console

from .browser import get_browser
from .config import DEFAULT_SCHEDULE_URL

console = Console()


def is_authenticated_url(url: str, title: str = "") -> bool:
    """Check if the given URL and title indicate an authenticated session."""
    url_lower = url.lower()
    title_lower = title.lower()
    if "login" in url_lower or "dologin" in url_lower:
        return False
    if "mitid" in url_lower or "unilogin" in url_lower:
        return False
    if "login" in title_lower:
        return False
    if "all.uddataplus.dk" in url_lower:
        return True
    return False


def check_session(profile_dir: Optional[Path] = None, target_url: str = DEFAULT_SCHEDULE_URL) -> bool:
    """Checks headlessly whether the current profile has a valid active session."""
    with get_browser(profile_dir=profile_dir, headless=True) as driver:
        driver.get(target_url)
        time.sleep(3)
        return is_authenticated_url(driver.current_url, driver.title)


def interactive_login(
    profile_dir: Optional[Path] = None,
    target_url: str = DEFAULT_SCHEDULE_URL,
    timeout: int = 300,
) -> bool:
    """
    Opens Firefox visibly to allow the user to complete MitID / UniLogin.
    Waits until the user is successfully authenticated and redirected.
    """
    console.print("[bold blue]Launching visible Firefox browser for MitID / Studie+ authentication...[/bold blue]")
    console.print("[yellow]Please select your school and log in using MitID in the opened browser window.[/yellow]")
    console.print(f"[dim]Waiting up to {timeout} seconds for completion...[/dim]")

    with get_browser(profile_dir=profile_dir, headless=False) as driver:
        driver.get(target_url)

        start_time = time.time()
        while time.time() - start_time < timeout:
            current_url = driver.current_url
            title = driver.title

            if is_authenticated_url(current_url, title):
                time.sleep(3)
                console.print("\n[bold green]✓ Login detected successfully![/bold green]")
                console.print(f"[green]Session cookies saved to persistent profile.[/green]")
                return True

            time.sleep(1.5)

        console.print("\n[bold red]✗ Login timed out after {timeout} seconds.[/bold red]")
        return False
