import sys
import json
import logging
from typing import Dict, Any, List

from gmail.client import GmailClient

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

client = GmailClient()

TOOLS = [
    {
        "name": "gmail_check_status",
        "description": "Checks Gmail connection and message count for ilyamiro.work@gmail.com.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "gmail_search_emails",
        "description": "Searches Gmail inbox by query keywords, sender, subject, or unread status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword in body/subject"},
                "sender": {"type": "string", "description": "Filter by sender email or name"},
                "subject": {"type": "string", "description": "Filter by subject keyword"},
                "unread_only": {"type": "boolean", "default": False, "description": "Only unread emails"},
                "limit": {"type": "integer", "default": 10, "description": "Max emails to return"}
            }
        }
    },
    {
        "name": "gmail_get_email",
        "description": "Gets full email body text, headers, and attachments by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "Email message ID"}
            },
            "required": ["email_id"]
        }
    },
    {
        "name": "gmail_send_email",
        "description": "Sends an email from ilyamiro.work@gmail.com.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body content"},
                "cc": {"type": "string", "description": "Optional CC recipient"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to attach"
                }
            },
            "required": ["to", "subject", "body"]
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    if name == "gmail_check_status":
        res = client.check_connection()
        return json.dumps(res, ensure_ascii=False)

    elif name == "gmail_search_emails":
        emails = client.search_emails(
            query=args.get("query"),
            sender=args.get("sender"),
            subject=args.get("subject"),
            unread_only=args.get("unread_only", False),
            limit=args.get("limit", 10)
        )
        return json.dumps(emails, ensure_ascii=False)

    elif name == "gmail_get_email":
        email_id = args.get("email_id")
        if not email_id:
            return json.dumps({"error": "email_id is required"})
        email_data = client.get_email(email_id)
        return json.dumps(email_data, ensure_ascii=False)

    elif name == "gmail_send_email":
        to = args.get("to")
        subject = args.get("subject")
        body = args.get("body")
        cc = args.get("cc")
        attachments = args.get("attachments")
        res = client.send_email(to=to, subject=subject, body=body, cc=cc, attachments=attachments)
        return json.dumps(res, ensure_ascii=False)

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


def main():
    logging.info("Starting Gmail MCP Server...")

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
                        "name": "gmail-mcp",
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
