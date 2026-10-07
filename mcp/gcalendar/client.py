import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("gcalendar_client")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv():
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v


load_dotenv()


def get_token_path() -> Path:
    custom = os.getenv("GOOGLE_CALENDAR_TOKEN")
    if custom:
        p = Path(custom).expanduser().resolve()
    else:
        p = Path.home() / ".config" / "life" / "calendar_token.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_credentials_path() -> Optional[Path]:
    custom = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
    candidates = [
        Path(custom).expanduser().resolve() if custom else None,
        Path.home() / ".config" / "life" / "calendar_credentials.json",
        Path(__file__).resolve().parent.parent / "credentials.json",
        Path(__file__).resolve().parent.parent / "calendar_credentials.json"
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


class GoogleCalendarClient:
    def __init__(self, token_path: Optional[Path] = None, credentials_path: Optional[Path] = None):
        self.token_path = token_path or get_token_path()
        self.credentials_path = credentials_path or get_credentials_path()
        self._service = None

    def get_credentials(self) -> Optional[Credentials]:
        """Load and refresh credentials if available."""
        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load existing token: {e}")

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(self.token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                logger.warning(f"Failed to refresh token: {e}")
                creds = None

        return creds

    def is_authenticated(self) -> bool:
        creds = self.get_credentials()
        return bool(creds and creds.valid)

    def get_service(self):
        if self._service is None:
            creds = self.get_credentials()
            if not creds or not creds.valid:
                raise ValueError(
                    "Google Calendar is not authenticated. Please run 'bin/calendar-auth' to authenticate."
                )
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def check_auth(self) -> Dict[str, Any]:
        """Check authentication status and return calendar account details."""
        if not self.is_authenticated():
            creds_file = self.credentials_path
            msg = "Not authenticated with Google Calendar."
            if not creds_file and not (os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")):
                msg += (
                    " No client credentials found. Please place your 'credentials.json' (from Google Cloud Console) "
                    "at ~/.config/life/calendar_credentials.json, or configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
                )
            else:
                msg += " Credentials found. Please run 'bin/calendar-auth' in your terminal to complete one-time authorization."
            return {
                "authenticated": False,
                "token_path": str(self.token_path),
                "credentials_path": str(creds_file) if creds_file else None,
                "message": msg
            }

        try:
            service = self.get_service()
            cal = service.calendars().get(calendarId="primary").execute()
            return {
                "authenticated": True,
                "primary_calendar": {
                    "id": cal.get("id"),
                    "summary": cal.get("summary"),
                    "timeZone": cal.get("timeZone")
                },
                "token_path": str(self.token_path),
                "message": f"Successfully connected to Google Calendar ({cal.get('summary')} - {cal.get('id')})."
            }
        except Exception as e:
            return {
                "authenticated": False,
                "error": str(e),
                "token_path": str(self.token_path)
            }

    def authenticate_interactive(self, port: int = 0) -> Dict[str, Any]:
        """Run interactive local server OAuth flow."""
        flow = None
        creds_file = get_credentials_path()

        if creds_file and creds_file.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
        else:
            client_id = os.getenv("GOOGLE_CLIENT_ID")
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
            if client_id and client_secret:
                client_config = {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            else:
                return {
                    "error": (
                        "No OAuth credentials found. Please download OAuth 2.0 Client credentials from Google Cloud Console "
                        "and save to ~/.config/life/calendar_credentials.json (or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env)."
                    )
                }

        creds = flow.run_local_server(port=port)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        self._service = None
        return self.check_auth()

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 20,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """List upcoming events from calendar."""
        service = self.get_service()

        if not time_min:
            time_min = datetime.now(timezone.utc).isoformat()
        elif "T" not in time_min:
            time_min = f"{time_min}T00:00:00Z"
        elif not time_min.endswith("Z") and "+" not in time_min and "-" not in time_min[10:]:
            time_min = f"{time_min}Z"

        if time_max:
            if "T" not in time_max:
                time_max = f"{time_max}T23:59:59Z"
            elif not time_max.endswith("Z") and "+" not in time_max and "-" not in time_max[10:]:
                time_max = f"{time_max}Z"

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
            q=query
        ).execute()

        items = events_result.get("items", [])
        events = []
        for item in items:
            start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            events.append({
                "id": item.get("id"),
                "summary": item.get("summary", "No Title"),
                "description": item.get("description", ""),
                "location": item.get("location", ""),
                "start": start,
                "end": end,
                "status": item.get("status"),
                "html_link": item.get("htmlLink")
            })

        return {
            "calendar_id": calendar_id,
            "total_events": len(events),
            "events": events
        }

    def _format_time_field(self, t: str) -> Dict[str, str]:
        """Format datetime or date into Google Calendar API schema."""
        t_clean = t.strip()
        if len(t_clean) == 10 and "-" in t_clean and "T" not in t_clean:
            return {"date": t_clean}

        if " " in t_clean and "T" not in t_clean:
            parts = t_clean.split(" ", 1)
            date_p = parts[0]
            time_p = parts[1]
            if len(time_p) == 5:
                time_p += ":00"
            t_clean = f"{date_p}T{time_p}"

        if "T" in t_clean:
            date_part, time_part = t_clean.split("T", 1)
            time_base = time_part.split("+")[0].split("-")[0].rstrip("Z")
            if len(time_base) == 5:
                tz_suffix = time_part[5:]
                t_clean = f"{date_part}T{time_base}:00{tz_suffix}"

        if "+" not in t_clean and "-" not in t_clean[10:] and not t_clean.endswith("Z"):
            t_clean += "+02:00"

        return {"dateTime": t_clean}

    def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: str = "primary",
        attendees: Optional[List[str]] = None,
        color_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new event in Google Calendar."""
        service = self.get_service()

        body: Dict[str, Any] = {
            "summary": summary,
            "start": self._format_time_field(start_time),
            "end": self._format_time_field(end_time),
        }

        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if color_id:
            body["colorId"] = color_id
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]

        created = service.events().insert(calendarId=calendar_id, body=body).execute()

        start = created.get("start", {}).get("dateTime") or created.get("start", {}).get("date")
        end = created.get("end", {}).get("dateTime") or created.get("end", {}).get("date")

        return {
            "status": "created",
            "id": created.get("id"),
            "summary": created.get("summary"),
            "start": start,
            "end": end,
            "location": created.get("location"),
            "html_link": created.get("htmlLink"),
            "message": f"Successfully created event '{summary}' ({start} - {end})."
        }

    def quick_add(self, text: str, calendar_id: str = "primary") -> Dict[str, Any]:
        """Create an event using Google Calendar natural language quickAdd."""
        service = self.get_service()
        created = service.events().quickAdd(calendarId=calendar_id, text=text).execute()

        start = created.get("start", {}).get("dateTime") or created.get("start", {}).get("date")
        end = created.get("end", {}).get("dateTime") or created.get("end", {}).get("date")

        return {
            "status": "created",
            "id": created.get("id"),
            "summary": created.get("summary"),
            "start": start,
            "end": end,
            "html_link": created.get("htmlLink"),
            "message": f"Quick added event '{created.get('summary')}' ({start} - {end})."
        }

    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Update an existing event."""
        service = self.get_service()
        patch_body: Dict[str, Any] = {}

        if summary is not None:
            patch_body["summary"] = summary
        if start_time is not None:
            patch_body["start"] = self._format_time_field(start_time)
        if end_time is not None:
            patch_body["end"] = self._format_time_field(end_time)
        if description is not None:
            patch_body["description"] = description
        if location is not None:
            patch_body["location"] = location

        updated = service.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body=patch_body
        ).execute()

        return {
            "status": "updated",
            "id": updated.get("id"),
            "summary": updated.get("summary"),
            "start": updated.get("start", {}).get("dateTime") or updated.get("start", {}).get("date"),
            "end": updated.get("end", {}).get("dateTime") or updated.get("end", {}).get("date"),
            "html_link": updated.get("htmlLink")
        }

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
        """Delete an event by ID."""
        service = self.get_service()
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {
            "status": "deleted",
            "event_id": event_id,
            "message": f"Successfully deleted event {event_id} from calendar."
        }


_calendar_client: Optional[GoogleCalendarClient] = None


def get_calendar_client() -> GoogleCalendarClient:
    global _calendar_client
    if _calendar_client is None:
        _calendar_client = GoogleCalendarClient()
    return _calendar_client
