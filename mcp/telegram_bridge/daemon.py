import os
import sys
import json
import time
import signal
import socket
import atexit
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Union, Dict
from collections import defaultdict

import fcntl
import sqlite3
import tempfile
import shutil
from telethon import TelegramClient, events

from telegram_bridge.formatter import format_for_telegram, chunk_telegram_text
from telegram_bridge.transcriber import VoiceTranscriber
from telegram.client import execute_action, get_ipc_socket_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("telegram_bridge")

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".config" / "life"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = CONFIG_DIR / "telegram.session"
CONV_ID_FILE = CONFIG_DIR / "telegram_conversation_id.txt"
PID_FILE = Path("/tmp/life-telegram-daemon.pid")
LOCK_FILE = Path("/tmp/life-telegram-daemon.lock")


def find_agy_binary() -> str:
    """Find agy executable in PATH or standard user directories."""
    found = shutil.which("agy")
    if found:
        return found
    user_name = Path.home().name
    candidates = [
        Path.home() / ".local" / "bin" / "agy",
        Path.home() / ".gemini" / "antigravity-cli" / "bin" / "agy",
        Path(f"/etc/profiles/per-user/{user_name}/bin/agy"),
        Path("/run/current-system/sw/bin/agy"),
        Path("/usr/local/bin/agy"),
        Path("/usr/bin/agy"),
    ]
    for c in candidates:
        if c.exists() and os.access(str(c), os.X_OK):
            return str(c)
    return "agy"

_lock_file_obj = None
_owns_ipc_socket = False


def acquire_instance_lock() -> bool:
    """Acquire single-instance OS lock via flock. Returns True if acquired, False otherwise."""
    global _lock_file_obj
    try:
        _lock_file_obj = open(LOCK_FILE, "a+")
        fcntl.flock(_lock_file_obj, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, OSError):
        return False


def release_instance_lock():
    """Release single-instance flock."""
    global _lock_file_obj
    if _lock_file_obj is not None:
        try:
            fcntl.flock(_lock_file_obj, fcntl.LOCK_UN)
            _lock_file_obj.close()
        except Exception:
            pass
        _lock_file_obj = None


API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

TARGET_GROUP_NAME = "Life"
TARGET_GROUP_ID = -5061234006


def build_system_safety_instruction(chat_id: Union[int, str], chat_title: str = "Life") -> str:
    return (
        f"[Telegram: chat_id={chat_id} ('{chat_title}'). Direct Action: Execute target tool on Step 1. "
        f"NEVER read schema .json files or search memory for direct actions (apps, media, schedule, assignments). "
        f"Voice: When asked for voice, call telegram_send_voice_message (1 line, Cyrillic/Latin strictly). "
        f"Response: Maximum 1-2 concise sentences or clean bullets; no conversational filler. Safety: Read-only by default.]\n\n"
    )


def write_pid():
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid():
    if PID_FILE.exists():
        try:
            if PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_FILE.unlink()
        except Exception:
            pass


def get_conversation_id() -> Optional[str]:
    if CONV_ID_FILE.exists():
        try:
            cid = CONV_ID_FILE.read_text(encoding="utf-8").strip()
            if cid:
                return cid
        except Exception:
            pass
    return None


def save_conversation_id(cid: str):
    try:
        CONV_ID_FILE.write_text(cid.strip(), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save conversation id: {e}")


def clear_conversation():
    if CONV_ID_FILE.exists():
        try:
            CONV_ID_FILE.unlink()
            logger.info("Cleared conversation ID.")
        except Exception as e:
            logger.error(f"Failed to clear conversation id: {e}")


def remove_socket():
    global _owns_ipc_socket
    if _owns_ipc_socket:
        try:
            sock_path = get_ipc_socket_path()
            if sock_path.exists():
                sock_path.unlink()
        except Exception:
            pass
        _owns_ipc_socket = False


atexit.register(release_instance_lock)
atexit.register(remove_socket)
atexit.register(remove_pid)


def format_tool_activity(tool_name: str, params: dict, state: str) -> str:
    """Format a tool invocation into a friendly, emoji-prefixed status line without raw JSON."""
    p = params or {}
    called_mcp_tool = None
    server_name = None
    action_desc = None

    if tool_name in ("call_mcp_tool", "mcp_call_tool", "call_tool"):
        called_mcp_tool = (
            p.get("ToolName")
            or p.get("tool_name")
            or p.get("tool")
            or p.get("name")
            or p.get("target_tool")
        )
        server_name = (
            p.get("ServerName")
            or p.get("server_name")
            or p.get("server")
        )
        raw_args = (
            p.get("Arguments")
            or p.get("arguments")
            or p.get("args")
            or p.get("parameters")
            or {}
        )
        action_desc = p.get("toolAction") or p.get("tool_action")

        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    p = parsed
                else:
                    p = {}
            except Exception:
                p = {}
        elif isinstance(raw_args, dict):
            p = raw_args
        else:
            p = {}

        if called_mcp_tool:
            called_mcp_tool = str(called_mcp_tool).strip('"\'')
            tool_name = called_mcp_tool
        else:
            act_text = str(action_desc).strip('"\'') if action_desc else (
                f"Calling MCP ({str(server_name).strip('\"\'')})" if server_name else "Calling MCP tool"
            )
            emoji = "⚙️"
            return f"⏳ {emoji} *{act_text}...*" if state == "ACTIVE" else f"✓ {emoji} {act_text}"

    if tool_name.startswith("mcp_") and tool_name not in ("mcp_call_tool",):
        parts = tool_name.split("_", 2)
        if len(parts) == 3:
            tool_name = parts[2]

    act = ""
    emoji = "⚙️"

    if tool_name == "studieplus_get_schedule":
        d = p.get("date", "today")
        act = f"Checking schedule ({d})"
        emoji = "📅"
    elif tool_name == "studieplus_get_assignments":
        subj = p.get("subject")
        act = f"Checking {subj + ' ' if subj else ''}assignments"
        emoji = "📝"
    elif tool_name == "studieplus_get_conversations":
        act = "Checking school messages"
        emoji = "💬"
    elif tool_name == "studieplus_check_session":
        act = "Verifying school session"
        emoji = "🔑"
    elif tool_name == "study_get_ib_resources":
        subj = p.get("subject", "IB")
        act = f"Searching {subj} past papers"
        emoji = "📚"
    elif tool_name == "study_prepare_test":
        subj = p.get("subject", "exam")
        act = f"Preparing {subj} revision & topics"
        emoji = "🎯"
    elif tool_name == "study_get_past_topics":
        subj = p.get("subject", "syllabus")
        act = f"Reviewing {subj} topics"
        emoji = "📖"
    elif tool_name == "gmail_search_emails":
        q = p.get("query")
        act = f"Searching emails{f' ({q})' if q else ''}"
        emoji = "✉️"
    elif tool_name == "gmail_get_email":
        act = "Reading email"
        emoji = "📨"
    elif tool_name == "gmail_send_email":
        to = p.get("to", "recipient")
        act = f"Sending email to {to}"
        emoji = "📤"
    elif tool_name == "gmail_check_status":
        act = "Checking Gmail inbox"
        emoji = "📬"
    elif tool_name == "telegram_get_unread":
        act = "Checking unread Telegram messages"
        emoji = "💬"
    elif tool_name == "telegram_get_dialogs":
        act = "Checking Telegram chats"
        emoji = "💬"
    elif tool_name == "telegram_get_messages":
        act = "Reading conversation history"
        emoji = "💬"
    elif tool_name == "telegram_send_message":
        act = "Sending Telegram message"
        emoji = "✉️"
    elif tool_name == "telegram_send_voice_message":
        act = "Synthesizing voice response"
        emoji = "🎙️"
    elif tool_name == "tts_synthesize":
        act = "Synthesizing audio"
        emoji = "🎙️"
    elif tool_name == "telegram_forward_messages":
        act = "Forwarding messages"
        emoji = "↗️"
    elif tool_name == "telegram_download_media":
        act = "Downloading Telegram media"
        emoji = "📥"
    elif tool_name == "telegram_send_file":
        act = "Sending file to Telegram"
        emoji = "📎"
    elif tool_name == "calendar_list_events":
        act = "Checking Google Calendar"
        emoji = "📆"
    elif tool_name in ("calendar_create_event", "calendar_quick_add"):
        s = p.get("summary") or p.get("text")
        act = f"Scheduling event{f' ({s})' if s else ''}"
        emoji = "🗓️"
    elif tool_name == "calendar_update_event":
        act = "Updating calendar event"
        emoji = "🗓️"
    elif tool_name == "calendar_delete_event":
        act = "Removing calendar event"
        emoji = "🗑️"
    elif tool_name in ("gdrive_search_files", "gdrive_list_files"):
        q = p.get("name_contains") or p.get("query")
        act = f"Searching Google Drive{f' ({q})' if q else ''}"
        emoji = "📁"
    elif tool_name == "gdrive_download_file":
        act = "Downloading Drive file"
        emoji = "⬇️"
    elif tool_name == "gdrive_upload_file":
        act = "Uploading file to Google Drive"
        emoji = "⬆️"
    elif tool_name == "gdrive_create_folder":
        act = "Creating Google Drive folder"
        emoji = "📁"
    elif tool_name == "github_list_repos":
        act = "Checking GitHub repositories"
        emoji = "🐙"
    elif tool_name == "github_list_issues":
        repo = p.get("repo")
        act = f"Checking GitHub issues{f' in {repo}' if repo else ''}"
        emoji = "🐙"
    elif tool_name == "github_get_notifications":
        act = "Checking GitHub notifications"
        emoji = "🔔"
    elif tool_name == "weather_get_forecast":
        act = "Checking weather forecast"
        emoji = "🌤️"
    elif tool_name == "vision_analyze_image":
        act = "Analyzing image content"
        emoji = "🖼️"
    elif tool_name == "vision_extract_text":
        act = "Extracting text via OCR"
        emoji = "🔍"
    elif tool_name == "vision_inspect_image":
        act = "Inspecting image metadata"
        emoji = "🔍"
    elif tool_name == "convert_file":
        fmt = p.get("target_format", "")
        act = f"Converting file{f' to {fmt}' if fmt else ''}"
        emoji = "🔄"
    elif tool_name == "youtube_search":
        q = p.get("query")
        act = f"Searching YouTube{f' ({q})' if q else ''}"
        emoji = "📺"
    elif tool_name == "youtube_get_transcript":
        act = "Fetching YouTube transcript"
        emoji = "📺"
    elif tool_name in ("system_control", "system_ipc"):
        act_name = p.get("command") or f"{p.get('action', 'desktop')} {p.get('target', '')}".strip()
        act = f"Desktop IPC: {act_name}"
        emoji = "🖥️"
    elif tool_name == "run_command":
        cmd = p.get("CommandLine", "")
        cmd_short = cmd[:35] + ("..." if len(cmd) > 35 else "")
        act = f"Running command{f' (`{cmd_short}`)' if cmd_short else ''}"
        emoji = "⚡"
    else:
        clean = (
            tool_name.replace("studieplus_", "")
            .replace("telegram_", "")
            .replace("study_", "")
            .replace("gmail_", "")
            .replace("github_", "")
            .replace("gdrive_", "")
            .replace("calendar_", "")
            .replace("youtube_", "")
            .replace("_", " ")
            .capitalize()
        )
        if called_mcp_tool:
            if action_desc:
                act = f"{action_desc} ({called_mcp_tool})"
            else:
                act = f"Calling MCP tool: {called_mcp_tool}"
        else:
            act = f"{clean}"
        emoji = "⚙️"

    if called_mcp_tool and called_mcp_tool not in act:
        act = f"{act} ({called_mcp_tool})"

    if state == "ACTIVE":
        return f"⏳ {emoji} *{act}...*"
    else:
        return f"✓ {emoji} {act}"


def build_live_status(
    voice_text: Optional[str],
    image_path: Optional[str],
    tool_history: List[str],
    current_tool: Optional[str],
    streamed_text: str
) -> str:
    """Build the clean live status message text for Telegram."""
    lines = []
    if voice_text:
        lines.append(f"🎙️ *\"{voice_text}\"*")
    elif image_path and not tool_history and not current_tool and not streamed_text:
        lines.append("🖼️ *Inspecting image...*")

    if streamed_text:
        recent_tools = tool_history[-2:] if len(tool_history) > 2 else tool_history
        for t in recent_tools:
            lines.append(t)
        if current_tool:
            lines.append(current_tool)
        if lines:
            lines.append("")

        formatted_stream = format_for_telegram(streamed_text)
        if len(formatted_stream) > 3500:
            formatted_stream = formatted_stream[:3500] + "..."
        lines.append(f"{formatted_stream} ▌")
    else:
        recent_tools = tool_history[-3:] if len(tool_history) > 3 else tool_history
        for t in recent_tools:
            lines.append(t)
        if current_tool:
            lines.append(current_tool)
        elif not tool_history:
            lines.append("⏳ *Thinking...*")

    return "\n".join(lines).strip()


class TelegramBridge:
    def __init__(self):
        session_str = str(SESSION_PATH)
        if session_str.endswith(".session"):
            session_str = session_str[:-8]
        self.client = TelegramClient(session_str, API_ID, API_HASH)
        self.target_peer = None
        self.busy = False
        self.current_conv_id = get_conversation_id()
        self.conv_turn_count = 0
        self.last_turn_time = time.time()
        self._lock = asyncio.Lock()
        self.ipc_server: Optional[asyncio.AbstractServer] = None
        self._auth_state = {}
        self.transcriber = VoiceTranscriber()
        self.voice_messages_sent = 0
        self.sent_voice_chats = defaultdict(int)

    async def start_ipc_server(self):
        """Start local Unix Domain Socket server to handle tool calls from other processes."""
        sock_path = get_ipc_socket_path()
        if sock_path.exists():
            try:
                test_s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_s.settimeout(0.5)
                test_s.connect(str(sock_path))
                test_s.close()
                logger.warning(f"Existing socket {sock_path} is still responsive. Another daemon might be active.")
            except (ConnectionRefusedError, socket.timeout, OSError):
                try:
                    sock_path.unlink()
                except Exception:
                    pass

        global _owns_ipc_socket
        self.ipc_server = await asyncio.start_unix_server(self._handle_ipc_client, path=str(sock_path))
        _owns_ipc_socket = True
        logger.info(f"Telegram IPC server listening on {sock_path}")

    async def stop_ipc_server(self):
        """Close and cleanup Unix Domain Socket IPC server."""
        if self.ipc_server:
            try:
                self.ipc_server.close()
                await self.ipc_server.wait_closed()
            except Exception as e:
                logger.warning(f"Error closing IPC server: {e}")
            self.ipc_server = None
        remove_socket()

    async def _handle_ipc_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming IPC requests from Telegram MCP or other processes."""
        try:
            line = await reader.readline()
            if not line:
                return
            req = json.loads(line.decode("utf-8"))
            action = req.get("action")
            args = req.get("args", {})
            logger.info(f"Telegram IPC request received: {action}")
            result = await execute_action(
                self.client,
                action,
                args,
                session_file_str=str(SESSION_PATH),
                state=self._auth_state
            )
            if action == "send_voice_message" and isinstance(result, dict) and result.get("status") == "sent":
                self.voice_messages_sent += 1
                sent_to = str(result.get("chat_id", ""))
                self.sent_voice_chats[sent_to] += 1
                logger.info(f"Recorded voice message sent to chat: {sent_to} (total for chat: {self.sent_voice_chats[sent_to]})")

            resp = json.dumps({"success": True, "result": result}, ensure_ascii=False)
            writer.write(resp.encode("utf-8") + b"\n")
            await writer.drain()
        except Exception as e:
            logger.error(f"Error handling IPC request: {e}", exc_info=True)
            err_resp = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
            try:
                writer.write(err_resp.encode("utf-8") + b"\n")
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self):
        write_pid()
        logger.info(f"Connecting to Telegram with session: {SESSION_PATH}")
        try:
            await self.client.connect()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                logger.error(
                    "Telegram session database is locked by another process! "
                    "Make sure no other Telegram client or daemon is running. "
                    "Run 'bin/life-telegram-daemon restart' to reset."
                )
                remove_pid()
                sys.exit(1)
            raise
        if not await self.client.is_user_authorized():
            logger.error("Telegram session is not authorized! Please run bin/telegram-auth first.")
            remove_pid()
            remove_socket()
            sys.exit(1)

        me = await self.client.get_me()
        logger.info(f"Logged in as {me.first_name} (@{me.username or me.id})")

        await self.start_ipc_server()

        await self.resolve_target_group()

        self.client.add_event_handler(self.on_new_message, events.NewMessage(chats=self.target_peer))

        logger.info("Telegram Bridge Voice Assistant is active and listening for messages...")
        try:
            await self.client.run_until_disconnected()
        finally:
            await self.stop_ipc_server()
            remove_pid()

    async def resolve_target_group(self):
        """Find the target 'Life' group chat peer."""
        dialogs = await self.client.get_dialogs(limit=50)
        for d in dialogs:
            if d.id == TARGET_GROUP_ID or d.name == TARGET_GROUP_NAME:
                self.target_peer = d.entity
                logger.info(f"Found target group: '{d.name}' (ID: {d.id})")
                return

        try:
            self.target_peer = await self.client.get_entity(TARGET_GROUP_ID)
            logger.info(f"Resolved target group by ID: {TARGET_GROUP_ID}")
        except Exception as e:
            logger.warning(f"Could not resolve entity by ID: {e}. Will match incoming chat title.")


    async def on_new_message(self, event):
        """Handle incoming messages in the Life group."""
        msg = event.message
        text = (msg.text or "").strip()
        is_voice = bool(msg.voice or (msg.audio and not text))

        if not text and is_voice:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_f:
                tmp_path = tmp_f.name

            try:
                async with self.client.action(event.chat_id, "record-audio"):
                    logger.info("Downloading incoming voice message...")
                    await event.message.download_media(file=tmp_path)
                    logger.info("Transcribing voice message with faster-whisper...")
                    transcribed = await self.transcriber.transcribe(tmp_path)
                    text = (transcribed or "").strip()
                    logger.info(f"Transcribed voice text: '{text}'")
            except Exception as e:
                logger.error(f"Voice transcription error: {e}", exc_info=True)
                await event.reply(f"⚠️ *Could not transcribe voice message:* `{e}`")
                return
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

            if not text:
                await event.reply("🎙️ I couldn't hear any words in that voice message. Please try again.")
                return

        image_path = None
        is_photo = bool(msg.photo or (msg.file and getattr(msg.file, "mime_type", "") and msg.file.mime_type.startswith("image/")))
        if is_photo:
            media_dir = Path.home() / ".cache" / "life" / "telegram_media"
            media_dir.mkdir(parents=True, exist_ok=True)
            img_file = media_dir / f"photo_{msg.id}.jpg"
            try:
                logger.info(f"Downloading incoming Telegram photo to {img_file}...")
                await event.message.download_media(file=str(img_file))
                image_path = str(img_file)
                logger.info(f"Downloaded photo to: {image_path}")
            except Exception as e:
                logger.error(f"Failed to download incoming Telegram photo: {e}", exc_info=True)

        if not text and image_path:
            text = "Please inspect and analyze this attached image, extract all text and formulas, and explain what is in it."

        if not text:
            return

        if text.lower() in ("/exit", "/clear", "/reset", "/new", "exit", "clear", "reset"):
            clear_conversation()
            self.current_conv_id = None
            self.conv_turn_count = 0
            await event.reply("🔄 **Conversation context reset.** Starting fresh on your next message!")
            return

        now = time.time()
        if self.current_conv_id and (now - self.last_turn_time > 2700 or self.conv_turn_count >= 15):
            logger.info(f"Auto-rolling over conversation context (turns: {self.conv_turn_count}, idle: {now - self.last_turn_time:.1f}s) to preserve speed.")
            clear_conversation()
            self.current_conv_id = None
            self.conv_turn_count = 0
        self.last_turn_time = now

        if self.busy:
            await event.reply("⏳ I'm still processing your previous request. Just a moment...")
            return

        prompt_body = text
        if image_path:
            prompt_body = f"[User attached an image file: {image_path}]\n{prompt_body}"

        chat_id = event.chat_id
        chat_title = getattr(getattr(event, "chat", None), "title", "Life") or "Life"
        context_note = build_system_safety_instruction(chat_id, chat_title)

        if prompt_body.startswith("/"):
            parts = prompt_body.split(maxsplit=1)
            slash_cmd = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            full_prompt = f"{slash_cmd} {context_note}{rest}"
        else:
            full_prompt = f"/life {context_note}{prompt_body}"
        asyncio.create_task(self.process_agent_turn(
            event,
            full_prompt,
            voice_text=text if is_voice else None,
            image_path=image_path
        ))

    async def _keep_typing(self, chat_id: int, stop_ev: asyncio.Event):
        """Send typing status periodically while the agent works."""
        while not stop_ev.is_set():
            try:
                async with self.client.action(chat_id, "typing"):
                    await asyncio.sleep(4)
            except Exception:
                await asyncio.sleep(4)

    async def process_agent_turn(
        self,
        event,
        prompt: str,
        voice_text: Optional[str] = None,
        image_path: Optional[str] = None
    ):
        """Execute Antigravity CLI turn with auto-approved permissions and clean output."""
        async with self._lock:
            self.busy = True
            chat_id = event.chat_id
            chat_id_str = str(chat_id)
            initial_chat_voice_count = self.sent_voice_chats[chat_id_str]
            initial_total_voice_count = self.voice_messages_sent
            logger.info(f"Processing turn in chat {chat_id} with prompt: {prompt[:80]}...")

            stop_typing = asyncio.Event()
            typing_task = asyncio.create_task(self._keep_typing(chat_id, stop_typing))

            status_msg = None
            tool_history: List[str] = []
            current_tool: Optional[str] = None
            streamed_text = ""
            last_edit_time = 0.0
            last_rendered_text = ""
            edit_in_flight = False

            async def maybe_update_telegram_status(force: bool = False):
                nonlocal last_edit_time, last_rendered_text, edit_in_flight, status_msg
                if edit_in_flight:
                    return
                now = time.time()
                if not force and (now - last_edit_time < 1.3):
                    return

                text_to_show = build_live_status(
                    voice_text, image_path, tool_history, current_tool, streamed_text
                )
                if not text_to_show or text_to_show == last_rendered_text:
                    return

                edit_in_flight = True
                try:
                    if status_msg is None:
                        status_msg = await event.reply(text_to_show)
                        last_edit_time = time.time()
                        last_rendered_text = text_to_show
                    else:
                        try:
                            await status_msg.edit(text_to_show)
                        except Exception:
                            await status_msg.edit(text_to_show, parse_mode=None)
                        last_edit_time = time.time()
                        last_rendered_text = text_to_show
                except Exception as e:
                    logger.debug(f"Status update skipped: {e}")
                finally:
                    edit_in_flight = False

            async def show_delayed_status():
                await asyncio.sleep(1.5)
                if not stop_typing.is_set() and status_msg is None:
                    try:
                        await maybe_update_telegram_status(force=True)
                    except Exception:
                        pass

            status_task = asyncio.create_task(show_delayed_status())

            agy_bin = find_agy_binary()
            logger.info(f"Resolved agy binary: {agy_bin}")
            cmd = [
                agy_bin,
                "--model", "gemini-3.8-flash-low",
                "--effort", "low",
                "--output-format", "stream-json",
                "--dangerously-skip-permissions",
                "-p", prompt
            ]
            if self.current_conv_id:
                cmd.extend(["--conversation", self.current_conv_id])

            env = os.environ.copy()
            env["AGY_TELEGRAM_SESSION"] = "1"
            env["TELEGRAM_IPC_SOCKET"] = str(get_ipc_socket_path())
            env["PYTHONPATH"] = f"{PROJECT_DIR}:{env.get('PYTHONPATH', '')}"

            extra_paths = [
                str(Path.home() / ".local" / "bin"),
                str(Path.home() / ".gemini" / "antigravity-cli" / "bin"),
                f"/etc/profiles/per-user/{Path.home().name}/bin",
                "/run/wrappers/bin",
                "/run/current-system/sw/bin",
            ]
            current_path = env.get("PATH", "")
            for p in reversed(extra_paths):
                if p not in current_path.split(":"):
                    current_path = f"{p}:{current_path}"
            env["PATH"] = current_path

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(PROJECT_DIR),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                final_response = ""

                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="ignore").strip()
                    if not line_str:
                        continue

                    try:
                        ev = json.loads(line_str)
                    except Exception:
                        continue

                    event_type = ev.get("event")

                    if event_type == "init":
                        cid = ev.get("conversation_id")
                        if cid:
                            self.current_conv_id = cid
                            save_conversation_id(cid)

                    elif event_type == "step_update":
                        su = ev.get("step_update", {})
                        stype = su.get("step_type")
                        sstate = su.get("state")

                        if stype == "tool":
                            tname = su.get("tool_name", "") or su.get("name", "")
                            tinfo = su.get("tool_info", {})
                            tparams = {}
                            if isinstance(tinfo, dict):
                                tparams = (
                                    tinfo.get("parameters")
                                    or tinfo.get("args")
                                    or tinfo.get("arguments")
                                    or {}
                                )
                            if not tparams:
                                tparams = su.get("parameters") or su.get("args") or {}
                            if isinstance(tparams, str):
                                try:
                                    tparams = json.loads(tparams)
                                except Exception:
                                    tparams = {}
                            if sstate == "ACTIVE":
                                current_tool = format_tool_activity(tname, tparams, "ACTIVE")
                                await maybe_update_telegram_status(force=True)
                            elif sstate == "DONE":
                                done_line = format_tool_activity(tname, tparams, "DONE")
                                tool_history.append(done_line)
                                current_tool = None
                                await maybe_update_telegram_status(force=True)

                        elif stype == "agent_response":
                            delta = su.get("text_delta")
                            if delta:
                                streamed_text += delta
                                await maybe_update_telegram_status(force=False)

                    elif event_type == "result":
                        res = ev.get("result", {})
                        final_response = res.get("response", "")
                        cid = res.get("conversation_id")
                        if cid:
                            self.current_conv_id = cid
                            save_conversation_id(cid)

                await proc.wait()
                if not final_response and streamed_text:
                    final_response = streamed_text

                stop_typing.set()
                status_task.cancel()
                typing_task.cancel()

                voice_sent_to_this_chat = (self.sent_voice_chats[chat_id_str] > initial_chat_voice_count)

                if voice_sent_to_this_chat:
                    logger.info(f"Voice note was sent directly to chat {chat_id} via telegram_send_voice_message tool.")
                    if status_msg:
                        try:
                            await status_msg.delete()
                        except Exception:
                            pass
                    clean_res = final_response.strip().lower()
                    redundant_markers = [
                        "отправил", "голосовое", "отправлен", "voice message", "sent", "готов", "done"
                    ]
                    is_purely_redundant = (
                        len(final_response.strip()) < 120 and
                        any(m in clean_res for m in redundant_markers)
                    )
                    if final_response and not is_purely_redundant and len(final_response.strip()) > 150:
                        formatted = format_for_telegram(final_response)
                        chunks = chunk_telegram_text(formatted)
                        for ch in chunks:
                            await self.client.send_message(chat_id, ch)

                elif final_response:
                    formatted = format_for_telegram(final_response)
                    chunks = chunk_telegram_text(formatted)

                    if status_msg and chunks:
                        try:
                            await status_msg.edit(chunks[0])
                            for ch in chunks[1:]:
                                await self.client.send_message(chat_id, ch)
                        except Exception:
                            try:
                                await status_msg.delete()
                            except Exception:
                                pass
                            for ch in chunks:
                                await self.client.send_message(chat_id, ch)
                    else:
                        if status_msg:
                            try:
                                await status_msg.delete()
                            except Exception:
                                pass
                        for ch in chunks:
                            await self.client.send_message(chat_id, ch)

                else:
                    stderr_data = await proc.stderr.read()
                    err = stderr_data.decode("utf-8", errors="ignore").strip()
                    if status_msg:
                        try:
                            await status_msg.delete()
                        except Exception:
                            pass

                    if err:
                        logger.error(f"Process error: {err}")
                        clean_err = format_for_telegram(f"⚠️ **Assistant error:**\n{err[-400:]}")
                        await self.client.send_message(chat_id, clean_err)
                    else:
                        await self.client.send_message(chat_id, "✅ Done.")

            except Exception as e:
                stop_typing.set()
                status_task.cancel()
                typing_task.cancel()
                logger.error(f"Error running agent turn: {e}", exc_info=True)
                if status_msg:
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                await self.client.send_message(chat_id, f"❌ An error occurred: `{e}`")

            finally:
                self.conv_turn_count += 1
                self.last_turn_time = time.time()
                self.busy = False


def sig_handler(sig, frame):
    remove_socket()
    remove_pid()
    release_instance_lock()
    os._exit(0)


def main():
    if not acquire_instance_lock():
        existing_pid = "unknown"
        if PID_FILE.exists():
            try:
                existing_pid = PID_FILE.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        logger.warning(
            f"Life Telegram Daemon is already running (PID: {existing_pid}). Exiting duplicate process."
        )
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    bridge = TelegramBridge()
    try:
        asyncio.run(bridge.start())
    finally:
        remove_socket()
        remove_pid()
        release_instance_lock()


if __name__ == "__main__":
    main()
