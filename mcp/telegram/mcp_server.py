import sys
import json
import logging
from typing import Dict, Any, List

from telegram.client import get_telegram_manager

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

telegram_manager = get_telegram_manager()

TOOLS = [
    {
        "name": "telegram_check_auth",
        "description": "Checks if Telegram user session is authenticated.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "telegram_send_login_code",
        "description": "Sends Telegram login verification code to phone number.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Phone number with country code (e.g. +45...)"}
            },
            "required": ["phone"]
        }
    },
    {
        "name": "telegram_sign_in",
        "description": "Completes Telegram authentication with verification code and optional 2FA password.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Verification code"},
                "phone": {"type": "string", "description": "Phone number"},
                "password": {"type": "string", "description": "Optional 2FA password"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "telegram_get_unread",
        "description": "Fetches unread messages and chats with recent message text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 15, "description": "Max unread chats to retrieve"}
            }
        }
    },
    {
        "name": "telegram_get_dialogs",
        "description": "Lists recent dialogs (chats, direct messages, groups, channels).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20, "description": "Max dialogs to return"},
                "unread_only": {"type": "boolean", "default": False, "description": "Only return chats with unread messages"},
                "dialog_type": {"type": "string", "enum": ["all", "user", "group", "channel"], "default": "all", "description": "Chat filter"}
            }
        }
    },
    {
        "name": "telegram_get_messages",
        "description": "Gets recent messages from a chat, channel, or contact by ID/username.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Chat ID, '@username', or 'me'"},
                "limit": {"type": "integer", "default": 20, "description": "Number of messages to fetch"}
            },
            "required": ["chat_id"]
        }
    },
    {
        "name": "telegram_send_message",
        "description": "Sends a text message to a user or chat.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Target chat ID or username"},
                "text": {"type": "string", "description": "Message text"}
            },
            "required": ["chat_id", "text"]
        }
    },
    {
        "name": "telegram_send_voice_message",
        "description": "Sends audio voice message via Silero TTS or audio file. ru=Cyrillic only (transliterate Latin), en=Latin only, 1 line, no emojis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Spoken text (1 line, no emojis)"},
                "audio_path": {"type": "string", "description": "Optional existing audio file path (.ogg/.wav)"},
                "chat_id": {"type": "string", "description": "Target chat ID (defaults to current chat)"},
                "language": {"type": "string", "enum": ["auto", "ru", "en"], "default": "auto", "description": "'ru' or 'en'"},
                "speaker": {"type": "string", "description": "Optional speaker voice"}
            }
        }
    },
    {
        "name": "telegram_forward_messages",
        "description": "Forwards or copies messages between chats (drop_author=True removes forward header).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_chat_id": {"type": "string", "description": "Source chat ID/username"},
                "to_chat_id": {"type": "string", "description": "Target chat ID/username"},
                "message_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Message IDs to forward"
                },
                "drop_author": {"type": "boolean", "default": False, "description": "Forward as clean copy without author tag"}
            },
            "required": ["from_chat_id", "to_chat_id", "message_ids"]
        }
    },
    {
        "name": "telegram_download_media",
        "description": "Downloads attached media/files from a Telegram message to local disk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Chat ID or username"},
                "message_id": {"type": "integer", "description": "Message ID"},
                "output_path": {"type": "string", "description": "Optional destination path"}
            },
            "required": ["chat_id", "message_id"]
        }
    },
    {
        "name": "telegram_send_file",
        "description": "Uploads and sends a local file, photo, or document to a chat.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Target chat ID or username"},
                "file_path": {"type": "string", "description": "Local file path"},
                "caption": {"type": "string", "description": "Optional caption"}
            },
            "required": ["chat_id", "file_path"]
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    if name == "telegram_check_auth":
        res = telegram_manager.check_auth()
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_send_login_code":
        phone = args.get("phone")
        if not phone:
            return json.dumps({"error": "phone is required"})
        res = telegram_manager.send_login_code(phone=phone)
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_sign_in":
        code = args.get("code")
        phone = args.get("phone")
        password = args.get("password")
        if not code:
            return json.dumps({"error": "code is required"})
        res = telegram_manager.sign_in(code=code, phone=phone, password=password)
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_get_unread":
        limit = args.get("limit", 15)
        res = telegram_manager.get_unread(limit=limit)
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_get_dialogs":
        limit = args.get("limit", 20)
        unread_only = args.get("unread_only", False)
        dialog_type = args.get("dialog_type", "all")
        res = telegram_manager.get_dialogs(limit=limit, unread_only=unread_only, dialog_type=dialog_type)
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_get_messages":
        chat_id = args.get("chat_id")
        limit = args.get("limit", 20)
        if not chat_id:
            return json.dumps({"error": "chat_id is required"})
        res = telegram_manager.get_messages(chat_id=chat_id, limit=limit)
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_send_message":
        chat_id = args.get("chat_id")
        text = args.get("text")
        if not chat_id or not text:
            return json.dumps({"error": "chat_id and text are required"})
        res = telegram_manager.send_message(chat_id=chat_id, text=text)
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_send_voice_message":
        text = args.get("text")
        audio_path = args.get("audio_path")
        if not text and not audio_path:
            return json.dumps({"error": "Either 'text' or 'audio_path' is required"})
        res = telegram_manager.send_voice_message(
            text=text,
            audio_path=audio_path,
            chat_id=args.get("chat_id"),
            language=args.get("language", "auto"),
            speaker=args.get("speaker")
        )
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_forward_messages":
        from_chat = args.get("from_chat_id")
        to_chat = args.get("to_chat_id")
        message_ids = args.get("message_ids")
        if not from_chat or not to_chat or not message_ids:
            return json.dumps({"error": "from_chat_id, to_chat_id, and message_ids are required"})
        res = telegram_manager.forward_messages(
            from_chat_id=from_chat,
            to_chat_id=to_chat,
            message_ids=message_ids,
            drop_author=args.get("drop_author", False)
        )
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_download_media":
        chat_id = args.get("chat_id")
        message_id = args.get("message_id")
        if not chat_id or not message_id:
            return json.dumps({"error": "chat_id and message_id are required"})
        res = telegram_manager.download_media(
            chat_id=chat_id,
            message_id=int(message_id),
            output_path=args.get("output_path")
        )
        return json.dumps(res, ensure_ascii=False)

    elif name == "telegram_send_file":
        chat_id = args.get("chat_id")
        file_path = args.get("file_path")
        if not chat_id or not file_path:
            return json.dumps({"error": "chat_id and file_path are required"})
        res = telegram_manager.send_file(
            chat_id=chat_id,
            file_path=file_path,
            caption=args.get("caption", "")
        )
        return json.dumps(res, ensure_ascii=False)

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


def main():
    logging.info("Starting Telegram MCP Server...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            logging.error(f"Malformed JSON: {e}")
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if req_id is None:
            if method == "notifications/initialized":
                logging.info("Client initialized notification received.")
            continue

        resp = {"jsonrpc": "2.0", "id": req_id}

        try:
            if method == "initialize":
                resp["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "telegram-mcp",
                        "version": "0.1.0"
                    }
                }
            elif method == "tools/list":
                resp["result"] = {"tools": TOOLS}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                logging.info(f"Calling tool {tool_name} with args: {tool_args}")
                text_result = handle_tool_call(tool_name, tool_args)
                resp["result"] = {
                    "content": [
                        {
                            "type": "text",
                            "text": text_result
                        }
                    ]
                }
            elif method == "ping":
                resp["result"] = {}
            else:
                resp["error"] = {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
        except Exception as e:
            logging.exception(f"Error handling method {method}: {e}")
            resp["error"] = {
                "code": -32603,
                "message": str(e)
            }

        response_json = json.dumps(resp)
        sys.stdout.write(response_json + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
