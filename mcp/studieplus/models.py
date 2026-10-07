from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Lesson(BaseModel):
    id: Optional[str] = None
    date: str
    day_name: Optional[str] = None
    time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    subject: str
    teacher: Optional[str] = None
    teacher_name: Optional[str] = None
    room: Optional[str] = None
    group: Optional[str] = None
    homework: Optional[str] = None
    note: Optional[str] = None
    is_cancelled: bool = False
    raw_text: Optional[str] = None


class DaySchedule(BaseModel):
    date: str
    day_name: Optional[str] = None
    lessons: List[Lesson] = Field(default_factory=list)


class WeekSchedule(BaseModel):
    week_info: Optional[str] = None
    days: List[DaySchedule] = Field(default_factory=list)


class Assignment(BaseModel):
    id: Optional[str] = None
    subject: str
    title: str
    student_time_allocated: Optional[float] = None
    student_time_used: Optional[float] = None
    class_group: Optional[str] = None
    week: Optional[int] = None
    due_date: Optional[str] = None
    due_date_iso: Optional[str] = None
    submitted_date: Optional[str] = None
    grade: Optional[str] = None
    status: str = "open"
    description: Optional[str] = None
    files: List[str] = Field(default_factory=list)


class ConversationComment(BaseModel):
    author: str
    date: Optional[str] = None
    content: str


class Conversation(BaseModel):
    id: Optional[str] = None
    sender: str
    sender_name: Optional[str] = None
    date: str
    subject: str
    preview: Optional[str] = None
    content: Optional[str] = None
    comments: List[ConversationComment] = Field(default_factory=list)
    files: List[str] = Field(default_factory=list)
    is_announcement: bool = False
