import sqlite3
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from .models import DaySchedule, WeekSchedule, Lesson, Conversation

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "studieplus"
DB_PATH = DEFAULT_CACHE_DIR / "schedule_cache.db"


class ScheduleCache:
    """Persistent SQLite cache for past schedules and lessons.

    Past schedules are immutable: once a lesson or day is in the past, it does not change.
    This cache stores past days and lessons, ensuring instant retrieval without hitting UDData.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS days (
                    date TEXT PRIMARY KEY,
                    day_name TEXT,
                    lesson_count INTEGER,
                    data JSON,
                    cached_at TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT,
                    date TEXT,
                    day_name TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    subject TEXT,
                    teacher TEXT,
                    teacher_name TEXT,
                    room TEXT,
                    class_group TEXT,
                    homework TEXT,
                    note TEXT,
                    is_cancelled INTEGER,
                    PRIMARY KEY (date, start_time, subject)
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_lessons_date ON lessons(date);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_lessons_subject ON lessons(subject);
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    sender TEXT,
                    sender_name TEXT,
                    date TEXT,
                    subject TEXT,
                    is_announcement INTEGER,
                    data JSON,
                    cached_at TEXT
                );
            """)
            conn.commit()

    @staticmethod
    def is_past(target_date: str) -> bool:
        """Returns True if the given ISO date (YYYY-MM-DD) is strictly before today."""
        today_iso = date.today().isoformat()
        return target_date < today_iso

    def save_day(self, day: DaySchedule) -> bool:
        """Saves a past day schedule and its individual lessons to cache.
        Returns False if day is today or future.
        """
        if not self.is_past(day.date):
            return False

        now_iso = datetime.now().isoformat()
        day_json = day.model_dump_json()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO days (date, day_name, lesson_count, data, cached_at)
                VALUES (?, ?, ?, ?, ?)
            """, (day.date, day.day_name, len(day.lessons), day_json, now_iso))

            for l in day.lessons:
                cursor.execute("""
                    INSERT OR REPLACE INTO lessons (
                        id, date, day_name, start_time, end_time, subject,
                        teacher, teacher_name, room, class_group, homework,
                        note, is_cancelled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    l.id, l.date, l.day_name, l.start_time, l.end_time, l.subject,
                    l.teacher, l.teacher_name, l.room, l.group, l.homework,
                    l.note, 1 if l.is_cancelled else 0
                ))
            conn.commit()
        return True

    def save_week_past_days(self, week: WeekSchedule) -> int:
        """Saves all past days in a given week schedule to cache. Returns number of days cached."""
        count = 0
        for day in week.days:
            if self.is_past(day.date):
                if self.save_day(day):
                    count += 1
        return count

    def get_day(self, target_date: str) -> Optional[DaySchedule]:
        """Retrieves a cached past day schedule if available."""
        if not self.is_past(target_date):
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM days WHERE date = ?", (target_date,))
            row = cursor.fetchone()
            if row:
                return DaySchedule.model_validate_json(row["data"])
        return None

    def get_lessons_by_subject(
        self,
        subject: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries historical lessons for a subject and/or date range."""
        query = "SELECT * FROM lessons WHERE 1=1"
        params = []

        if subject:
            query += " AND subject LIKE ?"
            params.append(f"%{subject}%")

        if from_date:
            query += " AND date >= ?"
            params.append(from_date)

        if to_date:
            query += " AND date <= ?"
            params.append(to_date)

        query += " ORDER BY date ASC, start_time ASC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_cached_dates_range(self) -> Dict[str, Optional[str]]:
        """Returns earliest and latest cached dates."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MIN(date) as min_d, MAX(date) as max_d FROM days")
            row = cursor.fetchone()
            if row:
                return {"min_date": row["min_d"], "max_date": row["max_d"]}
        return {"min_date": None, "max_date": None}

    def save_conversations(self, conversations: List[Conversation]) -> int:
        """Saves conversations to cache. Conversations are immutable history."""
        saved_count = 0
        now_iso = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for c in conversations:
                if not c.id:
                    continue
                conv_json = c.model_dump_json()
                cursor.execute("""
                    INSERT OR REPLACE INTO conversations (
                        id, sender, sender_name, date, subject,
                        is_announcement, data, cached_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c.id, c.sender, c.sender_name, c.date, c.subject,
                    1 if c.is_announcement else 0, conv_json, now_iso
                ))
                saved_count += 1
            conn.commit()
        return saved_count

    def get_cached_conversations(self, limit: int = 20) -> List[Conversation]:
        """Retrieves cached conversations ordered by rowid descending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM conversations ORDER BY rowid DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [Conversation.model_validate_json(r["data"]) for r in rows]

    def get_conversation_by_id(self, conv_id: str) -> Optional[Conversation]:
        """Retrieves a single conversation by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM conversations WHERE id = ?", (conv_id,))
            row = cursor.fetchone()
            if row:
                return Conversation.model_validate_json(row["data"])
        return None

