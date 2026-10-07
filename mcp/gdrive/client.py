"""Google Drive API Client for Unified Life Assistant."""

import io
import os
import sys
import json
import logging
import mimetypes
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

logger = logging.getLogger("gdrive_client")

SCOPES = ["https://www.googleapis.com/auth/drive"]

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
    custom = os.getenv("GOOGLE_DRIVE_TOKEN")
    if custom:
        p = Path(custom).expanduser().resolve()
    else:
        p = Path.home() / ".config" / "life" / "drive_token.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_credentials_path() -> Optional[Path]:
    custom = os.getenv("GOOGLE_DRIVE_CREDENTIALS") or os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
    candidates = [
        Path(custom).expanduser().resolve() if custom else None,
        Path.home() / ".config" / "life" / "drive_credentials.json",
        Path.home() / ".config" / "life" / "calendar_credentials.json",
        Path(__file__).resolve().parent.parent / "credentials.json",
        Path(__file__).resolve().parent.parent / "calendar_credentials.json"
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


class GoogleDriveClient:
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
                logger.warning(f"Failed to load existing drive token: {e}")

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self.token_path.write_text(creds.to_json(), encoding="utf-8")
                logger.info("Successfully refreshed Google Drive token.")
            except Exception as e:
                logger.warning(f"Failed to refresh drive token: {e}")
                creds = None

        return creds

    def get_service(self):
        """Build or return cached Google Drive v3 resource."""
        if self._service is None:
            creds = self.get_credentials()
            if not creds or not creds.valid:
                raise RuntimeError(
                    "Google Drive is not authenticated. Please run 'bin/drive-auth' to authenticate."
                )
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def check_auth(self) -> Dict[str, Any]:
        """Verify authentication and retrieve user and storage quota information."""
        try:
            creds = self.get_credentials()
            if not creds or not creds.valid:
                return {
                    "authenticated": False,
                    "message": "Google Drive is not authenticated. Run 'bin/drive-auth' to authorize.",
                    "credentials_found": self.credentials_path is not None,
                    "token_file": str(self.token_path)
                }

            service = self.get_service()
            about = service.about().get(fields="user,storageQuota").execute()
            user = about.get("user", {})
            quota = about.get("storageQuota", {})

            limit_bytes = int(quota.get("limit", 0))
            usage_bytes = int(quota.get("usage", 0))
            usage_in_drive = int(quota.get("usageInDrive", 0))

            return {
                "authenticated": True,
                "user": {
                    "display_name": user.get("displayName"),
                    "email": user.get("emailAddress"),
                    "photo_url": user.get("photoLink")
                },
                "storage": {
                    "limit_gb": round(limit_bytes / (1024 ** 3), 2) if limit_bytes else "Unlimited",
                    "used_gb": round(usage_bytes / (1024 ** 3), 2),
                    "used_in_drive_gb": round(usage_in_drive / (1024 ** 3), 2),
                    "percent_used": round((usage_bytes / limit_bytes) * 100, 1) if limit_bytes else 0
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

    def list_files(
        self,
        query: Optional[str] = None,
        folder_id: Optional[str] = None,
        page_size: int = 20,
        order_by: str = "modifiedTime desc",
        owned_only: bool = False
    ) -> Dict[str, Any]:
        """List files and folders in Google Drive matching optional query and parent folder."""
        service = self.get_service()
        q_parts = ["trashed = false"]

        if owned_only:
            q_parts.append("'me' in owners")
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if query:
            q_parts.append(query)

        full_q = " and ".join(q_parts)

        fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime, createdTime, webViewLink, iconLink, parents, owners, shared)"
        results = service.files().list(
            q=full_q,
            pageSize=min(page_size, 100),
            orderBy=order_by,
            fields=fields
        ).execute()

        items = results.get("files", [])
        formatted = []
        for f in items:
            size_bytes = int(f.get("size", 0)) if f.get("size") else None
            size_kb = round(size_bytes / 1024, 2) if size_bytes is not None else None
            owner_list = [o.get("emailAddress") or o.get("displayName") for o in f.get("owners", [])]
            formatted.append({
                "id": f.get("id"),
                "name": f.get("name"),
                "mime_type": f.get("mimeType"),
                "is_folder": f.get("mimeType") == "application/vnd.google-apps.folder",
                "size_kb": size_kb,
                "owners": owner_list,
                "shared_with_me": f.get("shared", False),
                "modified_time": f.get("modifiedTime"),
                "web_view_link": f.get("webViewLink"),
                "parents": f.get("parents", [])
            })

        return {
            "count": len(formatted),
            "files": formatted,
            "next_page_token": results.get("nextPageToken")
        }

    def search_files(
        self,
        name_contains: Optional[str] = None,
        file_type: Optional[str] = None,
        folder_id: Optional[str] = None,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """Search files by name substring, common file type, or parent folder."""
        q_parts = ["trashed = false"]

        if name_contains:
            escaped = name_contains.replace("'", "\\'")
            q_parts.append(f"name contains '{escaped}'")

        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")

        if file_type:
            ft = file_type.lower()
            if ft in ("folder", "dir", "directory"):
                q_parts.append("mimeType = 'application/vnd.google-apps.folder'")
            elif ft in ("pdf", "application/pdf"):
                q_parts.append("mimeType = 'application/pdf'")
            elif ft in ("doc", "docx", "word", "document"):
                q_parts.append("(mimeType = 'application/vnd.google-apps.document' or mimeType contains 'wordprocessing')")
            elif ft in ("sheet", "sheets", "excel", "spreadsheet", "csv"):
                q_parts.append("(mimeType = 'application/vnd.google-apps.spreadsheet' or mimeType contains 'spreadsheet' or mimeType = 'text/csv')")
            elif ft in ("slide", "slides", "presentation", "powerpoint"):
                q_parts.append("(mimeType = 'application/vnd.google-apps.presentation' or mimeType contains 'presentation')")
            elif ft in ("image", "photo", "picture", "png", "jpg", "jpeg"):
                q_parts.append("mimeType contains 'image/'")
            elif ft in ("audio", "voice", "mp3"):
                q_parts.append("mimeType contains 'audio/'")
            elif ft in ("video", "mp4"):
                q_parts.append("mimeType contains 'video/'")

        return self.list_files(query=" and ".join(q_parts[1:]) if len(q_parts) > 1 else None, page_size=page_size)

    def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """Get full metadata for a specific Google Drive file or folder."""
        service = self.get_service()
        fields = (
            "id, name, mimeType, description, size, createdTime, modifiedTime, "
            "webViewLink, webContentLink, parents, owners, shared, permissions, trashed"
        )
        try:
            f = service.files().get(fileId=file_id, fields=fields).execute()
            size_bytes = int(f.get("size", 0)) if f.get("size") else None
            return {
                "id": f.get("id"),
                "name": f.get("name"),
                "mime_type": f.get("mimeType"),
                "is_folder": f.get("mimeType") == "application/vnd.google-apps.folder",
                "description": f.get("description"),
                "size_bytes": size_bytes,
                "size_kb": round(size_bytes / 1024, 2) if size_bytes is not None else None,
                "created_time": f.get("createdTime"),
                "modified_time": f.get("modifiedTime"),
                "web_view_link": f.get("webViewLink"),
                "web_content_link": f.get("webContentLink"),
                "parents": f.get("parents", []),
                "shared": f.get("shared", False),
                "trashed": f.get("trashed", False),
                "owners": [o.get("displayName") for o in f.get("owners", [])]
            }
        except HttpError as e:
            return {"error": f"Failed to get file info: {str(e)}"}

    def download_file(self, file_id: str, destination_path: Optional[str] = None) -> Dict[str, Any]:
        """Downloads a file from Google Drive to local disk.
        Supports standard files as well as exporting Google Docs/Sheets/Slides to PDF/docx/xlsx.
        """
        service = self.get_service()
        meta = self.get_file_info(file_id)
        if "error" in meta:
            return meta

        file_name = meta.get("name", f"drive_file_{file_id}")
        mime_type = meta.get("mime_type", "")

        export_mime = None
        export_ext = None
        if mime_type == "application/vnd.google-apps.document":
            export_mime = "application/pdf"
            export_ext = ".pdf"
        elif mime_type == "application/vnd.google-apps.spreadsheet":
            export_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            export_ext = ".xlsx"
        elif mime_type == "application/vnd.google-apps.presentation":
            export_mime = "application/pdf"
            export_ext = ".pdf"
        elif mime_type == "application/vnd.google-apps.drawing":
            export_mime = "image/png"
            export_ext = ".png"

        if destination_path:
            out_p = Path(destination_path).expanduser().resolve()
            if out_p.is_dir():
                clean_name = file_name + (export_ext if export_ext and not file_name.endswith(export_ext) else "")
                out_p = out_p / clean_name
        else:
            download_dir = Path.home() / "Downloads"
            download_dir.mkdir(parents=True, exist_ok=True)
            clean_name = file_name + (export_ext if export_ext and not file_name.endswith(export_ext) else "")
            out_p = download_dir / clean_name

        out_p.parent.mkdir(parents=True, exist_ok=True)

        try:
            if export_mime:
                request = service.files().export_media(fileId=file_id, mimeType=export_mime)
            else:
                request = service.files().get_media(fileId=file_id)

            fh = io.FileIO(str(out_p), "wb")
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            fh.close()
            saved_size = out_p.stat().st_size
            return {
                "status": "success",
                "file_id": file_id,
                "file_name": out_p.name,
                "saved_to": str(out_p),
                "size_bytes": saved_size,
                "size_kb": round(saved_size / 1024, 2),
                "exported_from_google_workspace": export_mime is not None
            }
        except Exception as e:
            return {"error": f"Failed to download file: {str(e)}"}

    def upload_file(
        self,
        file_path: str,
        folder_id: Optional[str] = None,
        file_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Uploads a local file to Google Drive (root or specified folder)."""
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return {"error": f"File does not exist or is not a file: {file_path}"}

        service = self.get_service()
        name = file_name or p.name
        mime_type, _ = mimetypes.guess_type(str(p))
        if not mime_type:
            mime_type = "application/octet-stream"

        body = {
            "name": name,
            "mimeType": mime_type
        }
        if description:
            body["description"] = description
        if folder_id:
            body["parents"] = [folder_id]

        try:
            media = MediaFileUpload(str(p), mimetype=mime_type, resumable=True)
            uploaded = service.files().create(
                body=body,
                media_body=media,
                fields="id, name, mimeType, size, webViewLink, parents"
            ).execute()

            return {
                "status": "success",
                "file_id": uploaded.get("id"),
                "name": uploaded.get("name"),
                "mime_type": uploaded.get("mimeType"),
                "web_view_link": uploaded.get("webViewLink"),
                "parents": uploaded.get("parents", [])
            }
        except Exception as e:
            return {"error": f"Failed to upload file: {str(e)}"}

    def create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new folder in Google Drive."""
        service = self.get_service()
        body = {
            "name": folder_name.strip(),
            "mimeType": "application/vnd.google-apps.folder"
        }
        if parent_id:
            body["parents"] = [parent_id]

        try:
            folder = service.files().create(
                body=body,
                fields="id, name, mimeType, webViewLink, parents"
            ).execute()
            return {
                "status": "success",
                "folder_id": folder.get("id"),
                "name": folder.get("name"),
                "web_view_link": folder.get("webViewLink")
            }
        except Exception as e:
            return {"error": f"Failed to create folder: {str(e)}"}

    def delete_file(self, file_id: str, permanent: bool = False) -> Dict[str, Any]:
        """Deletes a file from Google Drive (moves to trash by default or permanently deletes)."""
        service = self.get_service()
        try:
            if permanent:
                service.files().delete(fileId=file_id).execute()
                return {"status": "success", "message": f"Permanently deleted file {file_id}."}
            else:
                service.files().update(fileId=file_id, body={"trashed": True}).execute()
                return {"status": "success", "message": f"Moved file {file_id} to trash."}
        except Exception as e:
            return {"error": f"Failed to delete file: {str(e)}"}

    def move_file(self, file_id: str, target_folder_id: str) -> Dict[str, Any]:
        """Moves a file to a new target folder."""
        service = self.get_service()
        try:
            file_meta = service.files().get(fileId=file_id, fields="parents").execute()
            previous_parents = ",".join(file_meta.get("parents", []))

            updated = service.files().update(
                fileId=file_id,
                addParents=target_folder_id,
                removeParents=previous_parents,
                fields="id, name, parents, webViewLink"
            ).execute()

            return {
                "status": "success",
                "file_id": updated.get("id"),
                "name": updated.get("name"),
                "new_parents": updated.get("parents", []),
                "web_view_link": updated.get("webViewLink")
            }
        except Exception as e:
            return {"error": f"Failed to move file: {str(e)}"}

    def share_file(
        self,
        file_id: str,
        role: str = "reader",
        email: Optional[str] = None,
        anyone_with_link: bool = False
    ) -> Dict[str, Any]:
        """Shares a file with a specific email or generates a link for anyone."""
        service = self.get_service()
        try:
            if anyone_with_link:
                perm_body = {
                    "role": role,
                    "type": "anyone"
                }
            elif email:
                perm_body = {
                    "role": role,
                    "type": "user",
                    "emailAddress": email.strip()
                }
            else:
                return {"error": "Either email or anyone_with_link=True must be specified."}

            created_perm = service.permissions().create(
                fileId=file_id,
                body=perm_body,
                fields="id, role, type"
            ).execute()

            meta = service.files().get(fileId=file_id, fields="name, webViewLink").execute()

            return {
                "status": "success",
                "file_id": file_id,
                "name": meta.get("name"),
                "role": created_perm.get("role"),
                "type": created_perm.get("type"),
                "web_view_link": meta.get("webViewLink")
            }
        except Exception as e:
            return {"error": f"Failed to share file: {str(e)}"}


_client_instance = None


def get_drive_client() -> GoogleDriveClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = GoogleDriveClient()
    return _client_instance
