import os
from pathlib import Path
from pydantic import BaseModel

DEFAULT_PROFILE_DIR = Path.home() / ".mozilla" / "firefox" / "schedule.special"
DEFAULT_BASE_URL = "https://all.uddataplus.dk"
DEFAULT_SCHEDULE_URL = "https://all.uddataplus.dk/skema/?id=id_menu_skema#u:e!99217!2026-10-04"
DEFAULT_ASSIGNMENTS_URL = "https://all.uddataplus.dk/opgave/?id=id_menu_opgaver#menu_opgaver:"
DEFAULT_CONVERSATIONS_URL = "https://all.uddataplus.dk/besked/?id=id_menu_samtaler#menu_samtaler:"

class Config(BaseModel):
    profile_dir: Path = DEFAULT_PROFILE_DIR
    base_url: str = DEFAULT_BASE_URL
    schedule_url: str = DEFAULT_SCHEDULE_URL
    assignments_url: str = DEFAULT_ASSIGNMENTS_URL
    conversations_url: str = DEFAULT_CONVERSATIONS_URL
    headless_by_default: bool = True
    timeout_seconds: int = 30
