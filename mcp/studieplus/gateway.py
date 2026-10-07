import os
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Union

from .config import Config, DEFAULT_PROFILE_DIR, DEFAULT_SCHEDULE_URL, DEFAULT_ASSIGNMENTS_URL, DEFAULT_CONVERSATIONS_URL
from .browser import get_browser
from .auth import check_session, interactive_login
from .parser import StudiePlusParser, AuthenticationRequiredError, parse_danish_datetime
from .models import Lesson, DaySchedule, WeekSchedule, Assignment, Conversation
from .cache import ScheduleCache


def resolve_date(date_input: Optional[Union[str, date]] = None) -> Optional[str]:
    """Resolves 'today', 'tomorrow', or a date string into YYYY-MM-DD."""
    if not date_input:
        return None
    if date_input == "today":
        return date.today().isoformat()
    if date_input == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    if isinstance(date_input, date):
        return date_input.isoformat()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_input):
        return date_input
    for fmt in ("%d.%m.%Y", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_input, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_input


class StudiePlusGateway:
    """High-level Gateway for retrieving Studie+ schedule, lessons, and assignments."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.student_id = "99217"
        self.cache = ScheduleCache()

    def is_logged_in(self) -> bool:
        """Checks whether the persistent profile holds an active authenticated session."""
        return check_session(
            profile_dir=self.config.profile_dir,
            target_url=self.config.schedule_url
        )

    def login(self, timeout: int = 300) -> bool:
        """Triggers an interactive login flow in a visible browser window."""
        return interactive_login(
            profile_dir=self.config.profile_dir,
            target_url=self.config.schedule_url,
            timeout=timeout
        )

    def _build_url_for_date(self, target_date: str) -> str:
        return f"{self.config.base_url}/skema/?id=id_menu_skema#u:e!{self.student_id}!{target_date}"

    def get_week(self, target_date: Optional[Union[str, date]] = None, headless: bool = True) -> WeekSchedule:
        resolved = resolve_date(target_date) or date.today().isoformat()
        
        try:
            target_dt = datetime.strptime(resolved, "%Y-%m-%d").date()
            monday = target_dt - timedelta(days=target_dt.weekday())
            sunday = monday + timedelta(days=6)
            today = date.today()

            if sunday < today:
                cached_days = []
                all_cached = True
                for i in range(7):
                    d_iso = (monday + timedelta(days=i)).isoformat()
                    c_day = self.cache.get_day(d_iso)
                    if c_day:
                        cached_days.append(c_day)
                    else:
                        all_cached = False
                        break
                if all_cached:
                    week_num = monday.isocalendar()[1]
                    return WeekSchedule(
                        week_info=f"Week {week_num} - {monday.year} (Cached)",
                        days=cached_days
                    )
        except Exception:
            pass

        url = self._build_url_for_date(resolved)
        with get_browser(profile_dir=self.config.profile_dir, headless=headless) as driver:
            driver.get(url)
            parser = StudiePlusParser(driver)
            week_schedule = parser.parse_schedule(target_date_hint=resolved)
            self.cache.save_week_past_days(week_schedule)
            return week_schedule

    def get_day(self, target_date: Optional[Union[str, date]] = None, headless: bool = True) -> DaySchedule:
        resolved = resolve_date(target_date) or date.today().isoformat()

        if self.cache.is_past(resolved):
            cached_day = self.cache.get_day(resolved)
            if cached_day:
                return cached_day

        week = self.get_week(target_date=resolved, headless=headless)

        for day in week.days:
            if day.date == resolved:
                return day

        try:
            target_dt = datetime.strptime(resolved, "%Y-%m-%d")
            weekday_idx = target_dt.weekday()
            if 0 <= weekday_idx < len(week.days):
                return week.days[weekday_idx]
        except Exception:
            pass

        return DaySchedule(date=resolved, lessons=[])

    def sync_history(self, from_date: str, to_date: Optional[str] = None, headless: bool = True) -> int:
        """Prefetches and caches all past weeks between from_date and to_date."""
        start_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        today = date.today()
        end_dt = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else today

        curr_monday = start_dt - timedelta(days=start_dt.weekday())
        weeks_synced = 0

        while curr_monday <= end_dt:
            m_str = curr_monday.isoformat()
            if curr_monday < today:
                self.get_week(target_date=m_str, headless=headless)
                weeks_synced += 1
            curr_monday += timedelta(days=7)

        return weeks_synced

    def get_subject_history(
        self,
        subject: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns all historical lessons and homework for a given subject."""
        return self.cache.get_lessons_by_subject(subject=subject, from_date=from_date, to_date=to_date)

    def get_assignments(
        self,
        status: str = "open",
        due_date: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        days_ahead: Optional[int] = None,
        subject: Optional[str] = None,
        with_details: bool = False,
        download_dir: Optional[Path] = None,
        headless: bool = True,
    ) -> List[Assignment]:
        """
        Retrieves assignments with extensive filtering options.
        """
        resolved_due = resolve_date(due_date)
        resolved_from = resolve_date(from_date)
        resolved_to = resolve_date(to_date)

        if days_ahead is not None:
            resolved_from = date.today().isoformat()
            resolved_to = (date.today() + timedelta(days=days_ahead)).isoformat()

        st = status.lower()
        if st == "all":
            show_open, show_handed_in, show_graded, show_lacking = True, True, True, True
        elif st == "graded":
            show_open, show_handed_in, show_graded, show_lacking = False, False, True, False
        elif st in ("submitted", "handed in"):
            show_open, show_handed_in, show_graded, show_lacking = False, True, False, False
        else:
            show_open, show_handed_in, show_graded, show_lacking = True, False, False, False

        with get_browser(
            profile_dir=self.config.profile_dir,
            headless=headless,
            download_dir=download_dir
        ) as driver:
            driver.get(self.config.assignments_url)
            parser = StudiePlusParser(driver)

            parser.apply_assignment_filters(
                show_open=show_open,
                show_handed_in=show_handed_in,
                show_graded=show_graded,
                show_lackingupload=show_lacking,
            )

            assignments_with_buttons = parser.parse_assignments_overview()

            filtered_pairs = []
            for assignment, btn in assignments_with_buttons:
                if subject and subject.lower() not in assignment.subject.lower():
                    continue

                if st != "all":
                    if st == "graded" and assignment.status != "graded":
                        continue
                    if st in ("submitted", "handed in") and assignment.status != "submitted":
                        continue
                    if st == "open" and assignment.status != "open":
                        continue

                due_dt = parse_danish_datetime(assignment.due_date)
                if due_dt:
                    due_date_str = due_dt.strftime("%Y-%m-%d")
                    if resolved_due and due_date_str != resolved_due:
                        continue
                    if resolved_from and due_date_str < resolved_from:
                        continue
                    if resolved_to and due_date_str > resolved_to:
                        continue
                else:
                    if resolved_due or resolved_from or resolved_to:
                        continue

                filtered_pairs.append((assignment, btn))

            if with_details:
                for assignment, btn in filtered_pairs:
                    parser.populate_details(
                        assignment,
                        button=btn,
                        download_files=bool(download_dir)
                    )

            return [a for a, _ in filtered_pairs]

    def get_conversations(
        self,
        limit: int = 15,
        with_content: bool = True,
        view_all: bool = False,
        headless: bool = True,
        force_refresh: bool = False,
    ) -> List[Conversation]:
        """
        Retrieves conversations and announcements.
        Cached automatically in SQLite as school conversations and announcements are immutable history.
        """
        if not force_refresh:
            cached = self.cache.get_cached_conversations(limit=limit)
            if cached and len(cached) >= limit:
                return cached

        with get_browser(profile_dir=self.config.profile_dir, headless=headless) as driver:
            driver.get(self.config.conversations_url)
            parser = StudiePlusParser(driver)
            convs = parser.parse_conversations(
                limit=limit,
                with_content=with_content,
                view_all=view_all
            )
            self.cache.save_conversations(convs)
            return convs

