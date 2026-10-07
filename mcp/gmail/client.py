import os
import sys
import email
import imaplib
import smtplib
from email.header import decode_header
from email.message import EmailMessage
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULT_ACCOUNT = "ilyamiro.work@gmail.com"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
CONFIG_FILE = Path.home() / ".config" / "gmail" / "config.json"


def load_env_file():
    """Load variables from .env if present."""
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v


load_env_file()


def decode_str(header_value: Optional[str]) -> str:
    """Decode an RFC 2047 encoded email header."""
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    result = []
    for fragment, charset in decoded_fragments:
        if isinstance(fragment, bytes):
            charset = charset or "utf-8"
            try:
                result.append(fragment.decode(charset, errors="replace"))
            except Exception:
                result.append(fragment.decode("latin1", errors="replace"))
        else:
            result.append(str(fragment))
    return "".join(result)


def extract_body(msg: email.message.Message) -> str:
    """Extract plain text or HTML body from an email message."""
    body = ""
    html_fallback = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue

            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if content_type == "text/plain":
                    body += text + "\n"
                elif content_type == "text/html" and not html_fallback:
                    html_fallback = text
            except Exception:
                continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace") if payload else ""
            if msg.get_content_type() == "text/html":
                html_fallback = text
            else:
                body = text
        except Exception:
            body = str(msg.get_payload() or "")

    if not body.strip() and html_fallback:
        import re
        body = re.sub(r"<[^>]+>", " ", html_fallback)
        body = re.sub(r"\s+", " ", body).strip()

    return body.strip()


def get_credentials():
    """Retrieve username and app password from env, ~/.config/gmail/config.json, or .env."""
    load_env_file()
    user = os.environ.get("GMAIL_USER")
    pwd = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_PASSWORD")

    if not pwd and CONFIG_FILE.exists():
        try:
            import json
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                user = user or data.get("user")
                pwd = data.get("app_password") or data.get("password")
        except Exception:
            pass

    return user or DEFAULT_ACCOUNT, pwd


class GmailClient:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self._username = username
        self._password = password

    @property
    def username(self) -> str:
        if self._username:
            return self._username
        u, _ = get_credentials()
        return u

    @property
    def password(self) -> Optional[str]:
        if self._password:
            return self._password
        _, p = get_credentials()
        return p

    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    def _get_imap_connection(self) -> imaplib.IMAP4_SSL:
        if not self.is_configured():
            raise ValueError(
                "Gmail App Password not found. Please set GMAIL_APP_PASSWORD in .env or ~/.config/gmail/config.json."
            )
        clean_password = self.password.replace(" ", "")
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(self.username, clean_password)
        return mail


    def check_connection(self) -> Dict[str, Any]:
        """Test authentication and fetch inbox status."""
        if not self.is_configured():
            return {
                "authenticated": False,
                "account": self.username,
                "error": "GMAIL_APP_PASSWORD is missing. Please set your 16-character App Password."
            }
        try:
            mail = self._get_imap_connection()
            status, counts = mail.select("INBOX", readonly=True)
            mail.logout()
            total_messages = int(counts[0].decode()) if status == "OK" and counts else 0
            return {
                "authenticated": True,
                "account": self.username,
                "inbox_total_messages": total_messages
            }
        except Exception as e:
            return {
                "authenticated": False,
                "account": self.username,
                "error": str(e)
            }

    def search_emails(
        self,
        query: Optional[str] = None,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 10,
        folder: str = "INBOX"
    ) -> List[Dict[str, Any]]:
        """Search emails using IMAP search criteria."""
        mail = self._get_imap_connection()
        try:
            mail.select(folder, readonly=True)
            search_criteria = []

            if unread_only:
                search_criteria.append("UNSEEN")
            if sender:
                search_criteria.extend(["FROM", f'"{sender}"'])
            if subject:
                search_criteria.extend(["SUBJECT", f'"{subject}"'])
            if query:
                search_criteria.extend(["TEXT", f'"{query}"'])

            if not search_criteria:
                search_criteria = ["ALL"]

            search_query = " ".join(search_criteria)
            status, data = mail.search(None, search_query)
            if status != "OK" or not data or not data[0]:
                return []

            msg_ids = data[0].split()
            msg_ids = msg_ids[::-1][:limit]

            results = []
            for msg_id in msg_ids:
                status, msg_data = mail.fetch(msg_id, "(RFC822.HEADER FLAGS)")
                if status != "OK" or not msg_data:
                    continue

                raw_header = None
                flags = ""
                for part in msg_data:
                    if isinstance(part, tuple):
                        raw_header = part[1]
                    elif isinstance(part, bytes):
                        flags = part.decode(errors="ignore")

                if not raw_header:
                    continue

                msg = email.message_from_bytes(raw_header)
                subject_str = decode_str(msg.get("Subject"))
                from_str = decode_str(msg.get("From"))
                to_str = decode_str(msg.get("To"))
                date_str = decode_str(msg.get("Date"))
                is_unread = "\\Seen" not in flags

                results.append({
                    "id": msg_id.decode(),
                    "date": date_str,
                    "from": from_str,
                    "to": to_str,
                    "subject": subject_str,
                    "unread": is_unread
                })

            return results
        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

    def get_email(self, email_id: str, folder: str = "INBOX") -> Dict[str, Any]:
        """Fetch full details and body of an email by ID."""
        mail = self._get_imap_connection()
        try:
            mail.select(folder, readonly=True)
            status, msg_data = mail.fetch(email_id.encode(), "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                raise ValueError(f"Email with ID {email_id} not found.")

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            attachments = []
            if msg.is_multipart():
                for part in msg.walk():
                    disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in disposition or part.get_filename():
                        filename = decode_str(part.get_filename())
                        size = len(part.get_payload(decode=True) or b"")
                        attachments.append({"filename": filename, "size_bytes": size})

            body = extract_body(msg)

            return {
                "id": email_id,
                "date": decode_str(msg.get("Date")),
                "from": decode_str(msg.get("From")),
                "to": decode_str(msg.get("To")),
                "subject": decode_str(msg.get("Subject")),
                "body": body,
                "attachments": attachments
            }
        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        attachments: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Send an email using Gmail SMTP with SSL, supporting optional file attachments."""
        if not self.is_configured():
            raise ValueError("Gmail credentials missing.")

        clean_password = self.password.replace(" ", "")
        msg = EmailMessage()
        msg["From"] = self.username
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        msg.set_content(body)

        if attachments:
            import mimetypes
            for file_path in attachments:
                p = Path(file_path).expanduser().resolve()
                if not p.exists():
                    raise FileNotFoundError(f"Attachment file not found: {file_path}")
                ctype, encoding = mimetypes.guess_type(str(p))
                if ctype is None or encoding is not None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)
                with open(p, "rb") as f:
                    file_data = f.read()
                msg.add_attachment(
                    file_data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=p.name
                )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.username, clean_password)
            server.send_message(msg)

        return {
            "success": True,
            "to": to,
            "subject": subject,
            "attachments": [str(Path(a).name) for a in attachments] if attachments else [],
            "message": "Email sent successfully."
        }

