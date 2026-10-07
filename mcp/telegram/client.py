import os
import sys
import json
import socket
import asyncio
import sqlite3
import threading
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    PhoneNumberInvalidError,
    AuthKeyError
)
from telethon.tl.types import (
    User,
    Chat,
    Channel,
    MessageMediaDocument,
    MessageMediaPhoto,
    PeerUser,
    PeerChat,
    PeerChannel
)

logger = logging.getLogger("telegram_client")

def load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
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

DEFAULT_API_ID = 2040
DEFAULT_API_HASH = "b18441a1ff607e10a989891a5462e627"

def get_session_path() -> Path:
    custom_path = os.getenv("TELEGRAM_SESSION_PATH")
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
    else:
        p = Path.home() / ".config" / "life" / "telegram.session"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def get_ipc_socket_path() -> Path:
    custom = os.getenv("TELEGRAM_IPC_SOCKET")
    if custom:
        return Path(custom).expanduser().resolve()
    uid = getattr(os, "getuid", lambda: 1000)()
    return Path(f"/tmp/life-tg-{uid}.sock")

TARGET_LIFE_GROUP_ID = -5061234006

def parse_entity_id(chat_id: Optional[Union[str, int]] = None) -> Any:
    if not chat_id or str(chat_id).strip().lower() in ("default", "current", "life", "none", ""):
        return TARGET_LIFE_GROUP_ID
    if isinstance(chat_id, int):
        return chat_id
    chat_str = str(chat_id).strip()
    try:
        return int(chat_str)
    except ValueError:
        return chat_str

async def ensure_connected(client: TelegramClient):
    if not client.is_connected():
        try:
            await client.connect()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                logger.error(
                    "Telegram session database is locked by another process. "
                    "Ensure Life Telegram Daemon IPC is running."
                )
            raise



async def check_auth_op(client: TelegramClient, session_file_str: str = "") -> Dict[str, Any]:
    await ensure_connected(client)
    is_auth = await client.is_user_authorized()
    if not is_auth:
        return {
            "authorized": False,
            "session_path": session_file_str,
            "message": "Not authenticated with Telegram. Please authenticate via 'telegram_send_login_code' or run 'bin/telegram-auth' in your terminal."
        }
    me = await client.get_me()
    return {
        "authorized": True,
        "session_path": session_file_str,
        "user": {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": me.phone
        }
    }

async def send_login_code_op(client: TelegramClient, phone: str, state: Optional[dict] = None) -> Dict[str, Any]:
    await ensure_connected(client)
    cleaned_phone = phone.strip().replace(" ", "").replace("-", "")
    sent = await client.send_code_request(cleaned_phone)
    if state is not None:
        state["last_phone"] = cleaned_phone
        state["last_phone_code_hash"] = sent.phone_code_hash
    return {
        "status": "code_sent",
        "phone": cleaned_phone,
        "phone_code_hash": sent.phone_code_hash,
        "delivery_type": type(sent.type).__name__,
        "message": f"Verification code sent to {cleaned_phone} via Telegram/SMS. Call 'telegram_sign_in' with the received code."
    }

async def sign_in_op(
    client: TelegramClient,
    code: str,
    phone: Optional[str] = None,
    password: Optional[str] = None,
    phone_code_hash: Optional[str] = None,
    state: Optional[dict] = None
) -> Dict[str, Any]:
    await ensure_connected(client)
    target_phone = phone or (state.get("last_phone") if state else None)
    if not target_phone:
        return {"error": "Phone number is required. Please provide 'phone'."}

    target_hash = phone_code_hash or (state.get("last_phone_code_hash") if state else None)
    cleaned_code = code.strip().replace(" ", "").replace("-", "")

    try:
        await client.sign_in(
            phone=target_phone,
            code=cleaned_code,
            phone_code_hash=target_hash
        )
    except SessionPasswordNeededError:
        if not password:
            return {
                "status": "2fa_required",
                "phone": target_phone,
                "message": "Two-step verification (2FA) is enabled on this account. Please call 'telegram_sign_in' again providing your 2FA password."
            }
        await client.sign_in(password=password)
    except PhoneCodeInvalidError:
        return {"error": "Invalid verification code entered."}
    except PasswordHashInvalidError:
        return {"error": "Invalid 2FA password entered."}
    except PhoneNumberInvalidError:
        return {"error": "Invalid phone number."}
    except Exception as e:
        return {"error": f"Sign-in error: {str(e)}"}

    me = await client.get_me()
    return {
        "status": "authenticated",
        "user": {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": me.phone
        },
        "message": f"Successfully authenticated as {me.first_name} (@{me.username or me.id})."
    }

async def get_dialogs_op(
    client: TelegramClient,
    limit: int = 20,
    unread_only: bool = False,
    dialog_type: str = "all"
) -> Dict[str, Any]:
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth or telegram_send_login_code."}

    results = []
    async for d in client.iter_dialogs():
        if unread_only and d.unread_count == 0 and not d.unread_mentions_count:
            continue

        d_type = "user"
        if d.is_channel:
            d_type = "channel"
        elif d.is_group:
            d_type = "group"

        if dialog_type != "all" and d_type != dialog_type:
            continue

        entity = d.entity
        username = getattr(entity, "username", None)

        last_msg_text = ""
        if d.message and d.message.text:
            last_msg_text = d.message.text[:120].replace("\n", " ")
        elif d.message and d.message.media:
            last_msg_text = f"[{type(d.message.media).__name__}]"

        results.append({
            "id": d.id,
            "title": d.name,
            "type": d_type,
            "username": username,
            "unread_count": d.unread_count,
            "unread_mentions": d.unread_mentions_count,
            "date": d.date.isoformat() if d.date else None,
            "last_message": last_msg_text
        })

        if len(results) >= limit:
            break

    return {
        "total": len(results),
        "dialogs": results
    }

async def get_unread_op(client: TelegramClient, limit: int = 15) -> Dict[str, Any]:
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    unread_dialogs = []
    async for d in client.iter_dialogs():
        if d.unread_count > 0:
            d_type = "channel" if d.is_channel else ("group" if d.is_group else "user")
            fetch_limit = min(d.unread_count, 10)
            messages = []
            try:
                async for msg in client.iter_messages(d.entity, limit=fetch_limit):
                    sender_name = "Unknown"
                    if msg.sender:
                        sender_name = getattr(msg.sender, "first_name", "") or getattr(msg.sender, "title", "Unknown")
                    text_snippet = msg.text or ("[" + type(msg.media).__name__ + "]" if msg.media else "")
                    messages.append({
                        "id": msg.id,
                        "sender_id": msg.sender_id,
                        "sender_name": sender_name,
                        "date": msg.date.isoformat() if msg.date else None,
                        "text": text_snippet,
                        "out": msg.out
                    })
            except Exception as e:
                logger.warning(f"Could not fetch unread messages for {d.name}: {e}")

            unread_dialogs.append({
                "id": d.id,
                "title": d.name,
                "type": d_type,
                "unread_count": d.unread_count,
                "messages": messages
            })
            if len(unread_dialogs) >= limit:
                break

    return {
        "unread_chats_count": len(unread_dialogs),
        "unread_dialogs": unread_dialogs
    }

async def get_messages_op(client: TelegramClient, chat_id: Union[str, int], limit: int = 20) -> Dict[str, Any]:
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    entity_target = parse_entity_id(chat_id)
    try:
        entity = await client.get_entity(entity_target)
    except Exception as e:
        return {"error": f"Failed to find chat or user '{chat_id}': {str(e)}"}

    title = getattr(entity, "title", None) or getattr(entity, "first_name", "Unknown")
    messages = []
    async for msg in client.iter_messages(entity, limit=limit):
        sender_name = "Unknown"
        if msg.sender:
            sender_name = getattr(msg.sender, "first_name", "") or getattr(msg.sender, "title", "Unknown")
        text_content = msg.text or ("[" + type(msg.media).__name__ + "]" if msg.media else "")
        has_media = bool(msg.media)
        media_type = type(msg.media).__name__ if has_media else None
        file_name = None
        file_size = None
        if has_media and getattr(msg, "file", None):
            file_name = getattr(msg.file, "name", None)
            file_size = getattr(msg.file, "size", None)

        messages.append({
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": sender_name,
            "date": msg.date.isoformat() if msg.date else None,
            "text": text_content,
            "has_media": has_media,
            "media_type": media_type,
            "file_name": file_name,
            "file_size": file_size,
            "out": msg.out,
            "reply_to_msg_id": msg.reply_to_msg_id
        })

    return {
        "chat_id": chat_id,
        "chat_title": title,
        "message_count": len(messages),
        "messages": messages
    }

async def send_message_op(client: TelegramClient, chat_id: Union[str, int], text: str) -> Dict[str, Any]:
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    entity_target = parse_entity_id(chat_id)
    try:
        entity = await client.get_entity(entity_target)
        sent = await client.send_message(entity, text)
        return {
            "status": "sent",
            "message_id": sent.id,
            "chat_id": chat_id,
            "date": sent.date.isoformat() if sent.date else None,
            "text": text
        }
    except Exception as e:
        return {"error": f"Failed to send message: {str(e)}"}

async def forward_messages_op(
    client: TelegramClient,
    from_chat_id: Union[str, int],
    to_chat_id: Union[str, int],
    message_ids: Union[int, List[int]],
    drop_author: bool = False
) -> Dict[str, Any]:
    """Forward one or more messages from one chat/user to another."""
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    if isinstance(message_ids, int):
        ids = [message_ids]
    elif isinstance(message_ids, list):
        ids = [int(i) for i in message_ids]
    else:
        try:
            ids = [int(message_ids)]
        except Exception:
            return {"error": f"Invalid message_ids: {message_ids}"}

    try:
        from_entity = await client.get_entity(parse_entity_id(from_chat_id))
        to_entity = await client.get_entity(parse_entity_id(to_chat_id))

        forwarded = await client.forward_messages(
            to_entity,
            messages=ids,
            from_peer=from_entity,
            drop_author=drop_author
        )
        sent_ids = [m.id for m in forwarded] if isinstance(forwarded, list) else [forwarded.id]
        return {
            "status": "forwarded",
            "from_chat_id": str(from_chat_id),
            "to_chat_id": str(to_chat_id),
            "original_message_ids": ids,
            "forwarded_message_ids": sent_ids,
            "drop_author": drop_author
        }
    except Exception as e:
        return {"error": f"Failed to forward message(s): {str(e)}"}

async def download_media_op(
    client: TelegramClient,
    chat_id: Union[str, int],
    message_id: int,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """Downloads attached media or file from a specific message."""
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    try:
        entity = await client.get_entity(parse_entity_id(chat_id))
        msg = await client.get_messages(entity, ids=int(message_id))
        if not msg:
            return {"error": f"Message {message_id} not found in {chat_id}."}
        if not msg.media:
            return {"error": f"Message {message_id} does not contain any media or file attachment."}

        if output_path:
            dest = Path(output_path).expanduser().resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            target = str(dest)
        else:
            dest_dir = Path.home() / "Downloads" / "telegram"
            dest_dir.mkdir(parents=True, exist_ok=True)
            target = str(dest_dir)

        saved = await client.download_media(msg, file=target)
        if not saved:
            return {"error": "Failed to download media."}

        saved_p = Path(saved).resolve()
        return {
            "status": "downloaded",
            "file_path": str(saved_p),
            "file_name": saved_p.name,
            "file_size": saved_p.stat().st_size if saved_p.exists() else None,
            "message_id": message_id,
            "chat_id": str(chat_id)
        }
    except Exception as e:
        return {"error": f"Failed to download media: {str(e)}"}

async def delete_messages_op(
    client: TelegramClient,
    chat_id: Union[str, int],
    message_ids: Optional[Union[int, List[int]]] = None,
    revoke: bool = True
) -> Dict[str, Any]:
    """Delete messages or clear chat history."""
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    entity_target = parse_entity_id(chat_id)
    try:
        entity = await client.get_entity(entity_target)
        if message_ids is not None:
            if isinstance(message_ids, (int, str)):
                ids = [int(message_ids)]
            else:
                ids = [int(i) for i in message_ids]
            res = await client.delete_messages(entity, ids, revoke=revoke)
            return {
                "status": "deleted",
                "chat_id": str(chat_id),
                "count": len(ids)
            }
        else:
            all_ids = []
            async for m in client.iter_messages(entity, limit=500):
                all_ids.append(m.id)
            if all_ids:
                for i in range(0, len(all_ids), 100):
                    batch = all_ids[i:i+100]
                    await client.delete_messages(entity, batch, revoke=revoke)
            return {
                "status": "cleared",
                "chat_id": str(chat_id),
                "count": len(all_ids)
            }
    except Exception as e:
        return {"error": f"Failed to delete messages: {str(e)}"}

async def send_file_op(
    client: TelegramClient,
    chat_id: Union[str, int],
    file_path: str,
    caption: str = ""
) -> Dict[str, Any]:
    """Send an arbitrary document, image, or file to a chat."""
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return {"error": f"File not found: {file_path}"}

    try:
        entity = await client.get_entity(parse_entity_id(chat_id))
        sent = await client.send_file(entity, str(p), caption=caption or None)
        return {
            "status": "sent",
            "message_id": sent.id,
            "chat_id": str(chat_id),
            "file_path": str(p),
            "file_name": p.name,
            "caption": caption
        }
    except Exception as e:
        return {"error": f"Failed to send file: {str(e)}"}

async def send_voice_message_op(
    client: TelegramClient,
    text: Optional[str] = None,
    audio_path: Optional[str] = None,
    chat_id: Optional[Union[str, int]] = None,
    language: str = "auto",
    speaker: Optional[str] = None
) -> Dict[str, Any]:
    """Sends a voice message to a chat, either by synthesizing text with Silero TTS or sending an existing audio file."""
    await ensure_connected(client)
    if not await client.is_user_authorized():
        return {"error": "Not authenticated. Call telegram_check_auth."}

    if not text and not audio_path:
        return {"error": "Either 'text' or 'audio_path' is required."}

    ogg_path = None
    created_temp = False
    used_lang = language

    if audio_path and os.path.exists(audio_path):
        ogg_path = audio_path
    else:
        from telegram_bridge.tts import get_synthesizer
        synth = get_synthesizer()
        loop = asyncio.get_running_loop()
        try:
            ogg_path, used_lang = await loop.run_in_executor(
                None,
                lambda: synth.synthesize(text, lang=language, speaker=speaker, output_format="ogg")
            )
            created_temp = True
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}", exc_info=True)
            return {"error": f"Failed to synthesize voice message: {str(e)}"}

    entity_target = parse_entity_id(chat_id)
    try:
        entity = await client.get_entity(entity_target)
        sent = await client.send_file(entity, ogg_path, voice_note=True)
        return {
            "status": "sent",
            "message_id": sent.id,
            "chat_id": str(entity_target),
            "language": used_lang,
            "voice_note": True,
            "date": sent.date.isoformat() if sent.date else None,
            "text": text or ""
        }
    except Exception as e:
        return {"error": f"Failed to send voice note: {str(e)}"}
    finally:
        if created_temp and ogg_path and os.path.exists(ogg_path):
            try:
                os.unlink(ogg_path)
            except Exception:
                pass

async def execute_action(
    client: TelegramClient,
    action: str,
    args: Dict[str, Any],
    session_file_str: str = "",
    state: Optional[dict] = None
) -> Dict[str, Any]:
    """Execute a recognized telegram action on the given TelegramClient."""
    if action == "check_auth":
        return await check_auth_op(client, session_file_str)
    elif action == "send_login_code":
        return await send_login_code_op(client, phone=args.get("phone", ""), state=state)
    elif action == "sign_in":
        return await sign_in_op(
            client,
            code=args.get("code", ""),
            phone=args.get("phone"),
            password=args.get("password"),
            phone_code_hash=args.get("phone_code_hash"),
            state=state
        )
    elif action == "get_dialogs":
        return await get_dialogs_op(
            client,
            limit=args.get("limit", 20),
            unread_only=args.get("unread_only", False),
            dialog_type=args.get("dialog_type", "all")
        )
    elif action == "get_unread":
        return await get_unread_op(client, limit=args.get("limit", 15))
    elif action == "get_messages":
        return await get_messages_op(client, chat_id=args.get("chat_id"), limit=args.get("limit", 20))
    elif action == "send_message":
        return await send_message_op(client, chat_id=args.get("chat_id"), text=args.get("text", ""))
    elif action == "send_voice_message":
        return await send_voice_message_op(
            client,
            text=args.get("text"),
            audio_path=args.get("audio_path"),
            chat_id=args.get("chat_id"),
            language=args.get("language", "auto"),
            speaker=args.get("speaker")
        )
    elif action == "forward_messages":
        return await forward_messages_op(
            client,
            from_chat_id=args.get("from_chat_id"),
            to_chat_id=args.get("to_chat_id"),
            message_ids=args.get("message_ids"),
            drop_author=args.get("drop_author", False)
        )
    elif action == "download_media":
        return await download_media_op(
            client,
            chat_id=args.get("chat_id"),
            message_id=args.get("message_id"),
            output_path=args.get("output_path")
        )
    elif action == "delete_messages":
        return await delete_messages_op(
            client,
            chat_id=args.get("chat_id"),
            message_ids=args.get("message_ids"),
            revoke=args.get("revoke", True)
        )
    elif action == "send_file":
        return await send_file_op(
            client,
            chat_id=args.get("chat_id"),
            file_path=args.get("file_path"),
            caption=args.get("caption", "")
        )
    else:
        return {"error": f"Unknown action: {action}"}


class AsyncLoopThread:
    """Maintains a persistent background event loop thread for Telethon."""
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TelethonLoop")
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout: Optional[float] = 45.0) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)


class TelegramClientManager:
    """
    Manages Telegram client operations.
    First checks if the Life Telegram daemon is running via Unix Domain Socket IPC.
    If the daemon is active, all requests are transparently executed through the daemon's
    live session, preventing database locking and session conflicts.
    If the daemon is not running, falls back to direct standalone Telethon client access.
    """
    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        session_path: Optional[Union[str, Path]] = None
    ):
        raw_api_id = api_id or os.getenv("TELEGRAM_API_ID") or os.getenv("TG_API_ID") or DEFAULT_API_ID
        self.api_id = int(raw_api_id)
        self.api_hash = api_hash or os.getenv("TELEGRAM_API_HASH") or os.getenv("TG_API_HASH") or DEFAULT_API_HASH

        self.session_file = Path(session_path) if session_path else get_session_path()
        session_str = str(self.session_file)
        if session_str.endswith(".session"):
            session_str = session_str[:-8]
        self._session_str = session_str

        self._runner: Optional[AsyncLoopThread] = None
        self._client: Optional[TelegramClient] = None
        self._auth_state: Dict[str, Any] = {}

    @property
    def runner(self) -> AsyncLoopThread:
        if self._runner is None:
            self._runner = AsyncLoopThread()
        return self._runner

    @property
    def client(self) -> TelegramClient:
        if self._client is None:
            self._client = TelegramClient(self._session_str, self.api_id, self.api_hash, loop=self.runner.loop)
        return self._client

    def _call_ipc(self, action: str, args: Optional[Dict[str, Any]] = None, timeout: float = 35.0) -> Optional[Dict[str, Any]]:
        """Attempt to call running Life Telegram Daemon over local Unix domain socket."""
        sock_path = get_ipc_socket_path()
        if not sock_path.exists():
            return None

        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect(str(sock_path))
            s.settimeout(timeout)
            payload = json.dumps({"action": action, "args": args or {}}, ensure_ascii=False).encode("utf-8") + b"\n"
            s.sendall(payload)

            file_obj = s.makefile("r", encoding="utf-8")
            line = file_obj.readline()
            s.close()
            if not line:
                return None

            data = json.loads(line)
            if data.get("success"):
                return data.get("result")
            else:
                return {"error": data.get("error", "IPC error")}
        except (ConnectionRefusedError, FileNotFoundError):
            return None
        except Exception as e:
            logger.warning(f"IPC request error for '{action}': {e}")
            return None

    def check_auth(self) -> Dict[str, Any]:
        """Check whether the Telegram user is authorized."""
        ipc_res = self._call_ipc("check_auth")
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(check_auth_op(self.client, str(self.session_file)))

    def send_login_code(self, phone: str) -> Dict[str, Any]:
        """Request an authentication code for the given phone number."""
        ipc_res = self._call_ipc("send_login_code", {"phone": phone})
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(send_login_code_op(self.client, phone=phone, state=self._auth_state))

    def sign_in(
        self,
        code: str,
        phone: Optional[str] = None,
        password: Optional[str] = None,
        phone_code_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """Complete sign in using verification code and optional 2FA password."""
        ipc_res = self._call_ipc("sign_in", {
            "code": code,
            "phone": phone,
            "password": password,
            "phone_code_hash": phone_code_hash
        })
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(sign_in_op(
            self.client,
            code=code,
            phone=phone,
            password=password,
            phone_code_hash=phone_code_hash,
            state=self._auth_state
        ))

    def get_dialogs(
        self,
        limit: int = 20,
        unread_only: bool = False,
        dialog_type: str = "all"
    ) -> Dict[str, Any]:
        """List dialogs (chats, direct messages, channels, groups)."""
        ipc_res = self._call_ipc("get_dialogs", {
            "limit": limit,
            "unread_only": unread_only,
            "dialog_type": dialog_type
        })
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(get_dialogs_op(
            self.client,
            limit=limit,
            unread_only=unread_only,
            dialog_type=dialog_type
        ))

    def get_unread(self, limit: int = 15) -> Dict[str, Any]:
        """Fetch all unread messages grouped by chat."""
        ipc_res = self._call_ipc("get_unread", {"limit": limit})
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(get_unread_op(self.client, limit=limit))

    def get_messages(self, chat_id: Union[str, int], limit: int = 20) -> Dict[str, Any]:
        """Fetch recent messages from a specific chat, channel, or contact."""
        ipc_res = self._call_ipc("get_messages", {"chat_id": chat_id, "limit": limit})
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(get_messages_op(self.client, chat_id=chat_id, limit=limit))

    def send_message(self, chat_id: Union[str, int], text: str) -> Dict[str, Any]:
        """Send a message to a user, group, or channel."""
        ipc_res = self._call_ipc("send_message", {"chat_id": chat_id, "text": text})
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(send_message_op(self.client, chat_id=chat_id, text=text))

    def send_voice_message(
        self,
        text: Optional[str] = None,
        audio_path: Optional[str] = None,
        chat_id: Optional[Union[str, int]] = None,
        language: str = "auto",
        speaker: Optional[str] = None
    ) -> Dict[str, Any]:
        """Synthesize speech using Silero TTS or send an existing audio file as a voice note."""
        ipc_res = self._call_ipc("send_voice_message", {
            "chat_id": chat_id,
            "text": text,
            "audio_path": audio_path,
            "language": language,
            "speaker": speaker
        })
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(send_voice_message_op(
            self.client,
            text=text,
            audio_path=audio_path,
            chat_id=chat_id,
            language=language,
            speaker=speaker
        ))

    def forward_messages(
        self,
        from_chat_id: Union[str, int],
        to_chat_id: Union[str, int],
        message_ids: Union[int, List[int]],
        drop_author: bool = False
    ) -> Dict[str, Any]:
        """Forward messages from one chat to another."""
        ipc_res = self._call_ipc("forward_messages", {
            "from_chat_id": from_chat_id,
            "to_chat_id": to_chat_id,
            "message_ids": message_ids,
            "drop_author": drop_author
        })
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(forward_messages_op(
            self.client,
            from_chat_id=from_chat_id,
            to_chat_id=to_chat_id,
            message_ids=message_ids,
            drop_author=drop_author
        ))

    def download_media(
        self,
        chat_id: Union[str, int],
        message_id: int,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Download media/files attached to a specific message."""
        ipc_res = self._call_ipc("download_media", {
            "chat_id": chat_id,
            "message_id": message_id,
            "output_path": output_path
        })
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(download_media_op(
            self.client,
            chat_id=chat_id,
            message_id=message_id,
            output_path=output_path
        ))

    def send_file(
        self,
        chat_id: Union[str, int],
        file_path: str,
        caption: str = ""
    ) -> Dict[str, Any]:
        """Send a document or media file to a chat."""
        ipc_res = self._call_ipc("send_file", {
            "chat_id": chat_id,
            "file_path": file_path,
            "caption": caption
        })
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(send_file_op(
            self.client,
            chat_id=chat_id,
            file_path=file_path,
            caption=caption
        ))

    def delete_messages(
        self,
        chat_id: Union[str, int],
        message_ids: Optional[Union[int, List[int]]] = None,
        revoke: bool = True
    ) -> Dict[str, Any]:
        """Delete messages or clear chat history."""
        ipc_res = self._call_ipc("delete_messages", {
            "chat_id": chat_id,
            "message_ids": message_ids,
            "revoke": revoke
        })
        if ipc_res is not None:
            return ipc_res
        return self.runner.run(delete_messages_op(
            self.client,
            chat_id=chat_id,
            message_ids=message_ids,
            revoke=revoke
        ))


_default_manager: Optional[TelegramClientManager] = None

def get_telegram_manager() -> TelegramClientManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = TelegramClientManager()
    return _default_manager
