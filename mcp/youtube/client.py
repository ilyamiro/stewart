"""YouTube API & Search Client for Unified Life Assistant."""

import os
import re
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube_client")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube"
]

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv():
    if ENV_FILE.exists():
        try:
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
        except Exception:
            pass


load_dotenv()


def get_token_path() -> Path:
    custom = os.getenv("YOUTUBE_TOKEN")
    if custom:
        p = Path(custom).expanduser().resolve()
    else:
        p = Path.home() / ".config" / "life" / "youtube_token.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_credentials_path() -> Optional[Path]:
    custom = os.getenv("YOUTUBE_CREDENTIALS") or os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
    candidates = [
        Path(custom).expanduser().resolve() if custom else None,
        Path.home() / ".config" / "life" / "youtube_credentials.json",
        Path.home() / ".config" / "life" / "calendar_credentials.json",
        Path(__file__).resolve().parent.parent / "credentials.json",
        Path(__file__).resolve().parent.parent / "calendar_credentials.json"
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


def extract_video_id(video_id_or_url: str) -> str:
    """Extract YouTube video ID from various URL formats or raw ID."""
    raw = video_id_or_url.strip()
    if re.match(r"^[a-zA-Z0-9_-]{11}$", raw):
        return raw

    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$"
    ]
    for p in patterns:
        m = re.search(p, raw)
        if m:
            return m.group(1)
    return raw


def parse_iso8601_duration(duration_str: str) -> str:
    """Convert ISO 8601 duration (e.g. PT1H2M3S or PT4M20S) to readable format (e.g. 1:02:03 or 4:20)."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not match:
        return duration_str
    hours, minutes, seconds = match.groups()
    h = int(hours) if hours else 0
    m = int(minutes) if minutes else 0
    s = int(seconds) if seconds else 0

    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class YouTubeClient:
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
                logger.warning(f"Failed to load existing YouTube token: {e}")

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self.token_path.write_text(creds.to_json(), encoding="utf-8")
                logger.info("Successfully refreshed YouTube token.")
            except Exception as e:
                logger.warning(f"Failed to refresh YouTube token: {e}")
                creds = None

        return creds

    def is_authenticated(self) -> bool:
        creds = self.get_credentials()
        return creds is not None and creds.valid

    def get_service(self):
        """Build or return cached YouTube v3 resource."""
        if self._service is None:
            creds = self.get_credentials()
            if not creds or not creds.valid:
                raise RuntimeError(
                    "YouTube is not authenticated. Run 'bin/youtube-auth' to authenticate."
                )
            self._service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def check_auth(self) -> Dict[str, Any]:
        """Verify authentication and retrieve user's channel details."""
        try:
            if not self.is_authenticated():
                return {
                    "authenticated": False,
                    "message": "YouTube is not authenticated. Run 'bin/youtube-auth' to authorize.",
                    "credentials_found": self.credentials_path is not None,
                    "token_file": str(self.token_path)
                }

            service = self.get_service()
            resp = service.channels().list(
                mine=True,
                part="snippet,contentDetails,statistics"
            ).execute()

            items = resp.get("items", [])
            if not items:
                return {
                    "authenticated": True,
                    "message": "Authenticated with Google, but no YouTube channel found for this account.",
                    "has_channel": False,
                    "token_file": str(self.token_path)
                }

            ch = items[0]
            snip = ch.get("snippet", {})
            stats = ch.get("statistics", {})

            return {
                "authenticated": True,
                "has_channel": True,
                "channel": {
                    "id": ch.get("id"),
                    "title": snip.get("title"),
                    "custom_url": snip.get("customUrl"),
                    "description": snip.get("description", "")[:200],
                    "subscribers": int(stats.get("subscriberCount", 0)),
                    "views": int(stats.get("viewCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                    "url": f"https://www.youtube.com/{snip.get('customUrl', 'channel/' + ch.get('id', ''))}"
                },
                "token_file": str(self.token_path)
            }
        except Exception as e:
            return {"authenticated": False, "error": str(e)}

    def authenticate_interactive(self) -> Dict[str, Any]:
        """Run interactive OAuth 2.0 flow via local web server."""
        creds_file = self.credentials_path
        if not creds_file or not creds_file.exists():
            client_id = os.getenv("GOOGLE_CLIENT_ID")
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
            if not (client_id and client_secret):
                return {
                    "error": (
                        "No credentials file or client ID found. Place client JSON at "
                        "~/.config/life/calendar_credentials.json or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
                    )
                }
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
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)

        try:
            creds = flow.run_local_server(port=0, prompt="consent")
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
            self._service = None
            return self.check_auth()
        except Exception as e:
            return {"error": f"Interactive authentication failed: {str(e)}"}

    def search(
        self,
        query: str,
        max_results: int = 10,
        search_type: str = "video",
        order: str = "relevance"
    ) -> Dict[str, Any]:
        """Search YouTube for videos, channels, or playlists.
        Uses authenticated YouTube Data API v3 if authorized, or falls back to yt-dlp search.
        """
        if self.is_authenticated():
            try:
                service = self.get_service()
                resp = service.search().list(
                    q=query,
                    part="snippet",
                    maxResults=min(max_results, 50),
                    type=search_type,
                    order=order
                ).execute()

                items = resp.get("items", [])
                results = []
                for it in items:
                    id_obj = it.get("id", {})
                    kind = id_obj.get("kind", "")
                    snip = it.get("snippet", {})

                    if "video" in kind:
                        vid_id = id_obj.get("videoId")
                        results.append({
                            "type": "video",
                            "id": vid_id,
                            "title": snip.get("title"),
                            "channel_title": snip.get("channelTitle"),
                            "channel_id": snip.get("channelId"),
                            "published_at": snip.get("publishedAt"),
                            "description": snip.get("description"),
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "thumbnail": snip.get("thumbnails", {}).get("medium", {}).get("url")
                        })
                    elif "channel" in kind:
                        ch_id = id_obj.get("channelId")
                        results.append({
                            "type": "channel",
                            "id": ch_id,
                            "title": snip.get("title"),
                            "description": snip.get("description"),
                            "url": f"https://www.youtube.com/channel/{ch_id}",
                            "thumbnail": snip.get("thumbnails", {}).get("medium", {}).get("url")
                        })
                    elif "playlist" in kind:
                        pl_id = id_obj.get("playlistId")
                        results.append({
                            "type": "playlist",
                            "id": pl_id,
                            "title": snip.get("title"),
                            "channel_title": snip.get("channelTitle"),
                            "url": f"https://www.youtube.com/playlist?list={pl_id}",
                            "thumbnail": snip.get("thumbnails", {}).get("medium", {}).get("url")
                        })

                return {
                    "query": query,
                    "count": len(results),
                    "provider": "youtube_api",
                    "results": results
                }
            except Exception as e:
                logger.warning(f"YouTube Data API search failed: {e}. Falling back to yt-dlp search.")

        return self._search_via_ytdlp(query, max_results=max_results)

    def _search_via_ytdlp(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search YouTube using yt-dlp without needing an API key or auth token."""
        try:
            cmd = [
                "yt-dlp",
                "--default-search", f"ytsearch{max_results}",
                "--dump-json",
                "--flat-playlist",
                "--skip-download",
                query
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode != 0 and not res.stdout:
                return {"error": f"Search failed: {res.stderr}"}

            results = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    vid_id = data.get("id")
                    dur_sec = data.get("duration")
                    dur_str = f"{int(dur_sec // 60)}:{int(dur_sec % 60):02d}" if dur_sec else None
                    results.append({
                        "type": "video",
                        "id": vid_id,
                        "title": data.get("title"),
                        "channel_title": data.get("uploader") or data.get("channel"),
                        "channel_url": data.get("uploader_url") or data.get("channel_url"),
                        "duration": dur_str,
                        "view_count": data.get("view_count"),
                        "url": data.get("url") or f"https://www.youtube.com/watch?v={vid_id}",
                        "description": data.get("description", "")[:200]
                    })
                except Exception:
                    continue

            return {
                "query": query,
                "count": len(results),
                "provider": "yt-dlp",
                "results": results
            }
        except Exception as e:
            return {"error": f"Failed to search YouTube: {str(e)}"}

    def get_video_details(self, video_id_or_url: str) -> Dict[str, Any]:
        """Retrieve full details, statistics, and description for a video."""
        vid_id = extract_video_id(video_id_or_url)

        if self.is_authenticated():
            try:
                service = self.get_service()
                resp = service.videos().list(
                    id=vid_id,
                    part="snippet,contentDetails,statistics"
                ).execute()

                items = resp.get("items", [])
                if items:
                    v = items[0]
                    snip = v.get("snippet", {})
                    stats = v.get("statistics", {})
                    cd = v.get("contentDetails", {})

                    return {
                        "id": vid_id,
                        "title": snip.get("title"),
                        "channel_title": snip.get("channelTitle"),
                        "channel_id": snip.get("channelId"),
                        "published_at": snip.get("publishedAt"),
                        "duration": parse_iso8601_duration(cd.get("duration", "")),
                        "view_count": int(stats.get("viewCount", 0)),
                        "like_count": int(stats.get("likeCount", 0)) if "likeCount" in stats else None,
                        "comment_count": int(stats.get("commentCount", 0)) if "commentCount" in stats else None,
                        "tags": snip.get("tags", [])[:15],
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "description": snip.get("description")
                    }
            except Exception as e:
                logger.warning(f"API video details failed: {e}. Trying yt-dlp fallback.")

        try:
            cmd = ["yt-dlp", "-J", "--skip-download", f"https://www.youtube.com/watch?v={vid_id}"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                dur_sec = data.get("duration")
                dur_str = f"{int(dur_sec // 60)}:{int(dur_sec % 60):02d}" if dur_sec else None
                return {
                    "id": vid_id,
                    "title": data.get("title"),
                    "channel_title": data.get("uploader") or data.get("channel"),
                    "channel_id": data.get("channel_id"),
                    "published_at": data.get("upload_date"),
                    "duration": dur_str,
                    "view_count": data.get("view_count"),
                    "like_count": data.get("like_count"),
                    "comment_count": data.get("comment_count"),
                    "tags": data.get("tags", [])[:15],
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "description": data.get("description")
                }
        except Exception as e:
            return {"error": f"Failed to get video details: {str(e)}"}

        return {"error": f"Video not found: {vid_id}"}

    def get_transcript(self, video_id_or_url: str, language: str = "en") -> Dict[str, Any]:
        """Extract subtitles/transcript for a video using yt-dlp."""
        vid_id = extract_video_id(video_id_or_url)
        url = f"https://www.youtube.com/watch?v={vid_id}"

        try:
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--write-auto-sub",
                "--write-sub",
                "--sub-lang", f"{language},en,ru,da",
                "--sub-format", "vtt/best",
                "-o", f"/tmp/yt_sub_{vid_id}.%(ext)s",
                url
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

            sub_files = list(Path("/tmp").glob(f"yt_sub_{vid_id}.*"))
            if sub_files:
                sub_path = sub_files[0]
                content = sub_path.read_text(encoding="utf-8", errors="ignore")
                try:
                    sub_path.unlink()
                except Exception:
                    pass

                cleaned_lines = []
                for line in content.splitlines():
                    line = line.strip()
                    if not line or "-->" in line or line.startswith("WEBVTT") or line.isdigit():
                        continue
                    cleaned = re.sub(r"<[^>]+>", "", line).strip()
                    if cleaned and (not cleaned_lines or cleaned != cleaned_lines[-1]):
                        cleaned_lines.append(cleaned)

                full_text = " ".join(cleaned_lines)
                return {
                    "video_id": vid_id,
                    "url": url,
                    "subtitle_file": sub_path.name,
                    "char_count": len(full_text),
                    "transcript": full_text[:4000] if len(full_text) > 4000 else full_text
                }

            return {"error": f"No subtitles or transcript found for video {vid_id} in {language}."}
        except Exception as e:
            return {"error": f"Failed to extract transcript: {str(e)}"}

    def get_my_channel(self) -> Dict[str, Any]:
        """Retrieve details about user's own channel."""
        auth_status = self.check_auth()
        if not auth_status.get("authenticated"):
            return auth_status
        return auth_status.get("channel", {})

    def list_my_videos(self, max_results: int = 20) -> Dict[str, Any]:
        """List videos uploaded by the user to their own channel."""
        service = self.get_service()
        resp = service.channels().list(mine=True, part="contentDetails").execute()
        items = resp.get("items", [])
        if not items:
            return {"error": "No channel found for this account"}

        uploads_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not uploads_id:
            return {"error": "Uploads playlist not found"}

        pl_resp = service.playlistItems().list(
            playlistId=uploads_id,
            part="snippet,contentDetails",
            maxResults=min(max_results, 50)
        ).execute()

        videos = []
        for it in pl_resp.get("items", []):
            snip = it.get("snippet", {})
            vid_id = it.get("contentDetails", {}).get("videoId")
            videos.append({
                "id": vid_id,
                "title": snip.get("title"),
                "published_at": snip.get("publishedAt"),
                "description": snip.get("description", "")[:150],
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "thumbnail": snip.get("thumbnails", {}).get("medium", {}).get("url")
            })

        return {
            "count": len(videos),
            "videos": videos
        }

    def list_my_playlists(self, max_results: int = 20) -> Dict[str, Any]:
        """List playlists owned by the user."""
        service = self.get_service()
        resp = service.playlists().list(
            mine=True,
            part="snippet,contentDetails,status",
            maxResults=min(max_results, 50)
        ).execute()

        playlists = []
        for it in resp.get("items", []):
            snip = it.get("snippet", {})
            cd = it.get("contentDetails", {})
            status = it.get("status", {})
            pl_id = it.get("id")
            playlists.append({
                "id": pl_id,
                "title": snip.get("title"),
                "item_count": cd.get("itemCount", 0),
                "privacy": status.get("privacyStatus"),
                "published_at": snip.get("publishedAt"),
                "url": f"https://www.youtube.com/playlist?list={pl_id}"
            })

        return {
            "count": len(playlists),
            "playlists": playlists
        }

    def list_my_subscriptions(self, max_results: int = 20) -> Dict[str, Any]:
        """List channels the user is subscribed to."""
        service = self.get_service()
        resp = service.subscriptions().list(
            mine=True,
            part="snippet",
            maxResults=min(max_results, 50),
            order="relevance"
        ).execute()

        subs = []
        for it in resp.get("items", []):
            snip = it.get("snippet", {})
            res_id = snip.get("resourceId", {})
            ch_id = res_id.get("channelId")
            subs.append({
                "channel_id": ch_id,
                "title": snip.get("title"),
                "description": snip.get("description", "")[:150],
                "url": f"https://www.youtube.com/channel/{ch_id}",
                "thumbnail": snip.get("thumbnails", {}).get("default", {}).get("url")
            })

        return {
            "count": len(subs),
            "subscriptions": subs
        }

    def get_playlist_items(self, playlist_id: str, max_results: int = 20) -> Dict[str, Any]:
        """Retrieve items from a specific playlist."""
        service = self.get_service()
        resp = service.playlistItems().list(
            playlistId=playlist_id,
            part="snippet,contentDetails",
            maxResults=min(max_results, 50)
        ).execute()

        items = []
        for it in resp.get("items", []):
            snip = it.get("snippet", {})
            vid_id = it.get("contentDetails", {}).get("videoId")
            items.append({
                "id": vid_id,
                "title": snip.get("title"),
                "channel_title": snip.get("channelTitle"),
                "published_at": snip.get("publishedAt"),
                "url": f"https://www.youtube.com/watch?v={vid_id}"
            })

        return {
            "playlist_id": playlist_id,
            "count": len(items),
            "videos": items
        }


_client_instance = None


def get_youtube_client() -> YouTubeClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = YouTubeClient()
    return _client_instance
