"""Google Drive MCP Server implementation."""

import sys
import json
import logging
from typing import Dict, Any

from gdrive.client import get_drive_client

logger = logging.getLogger("gdrive_mcp")

TOOLS = [
    {
        "name": "gdrive_check_auth",
        "description": "Checks Google Drive authentication and storage quota.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "gdrive_list_files",
        "description": "Lists files and folders in Drive with optional folder_id, query filter, and limit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string", "description": "Optional parent folder ID"},
                "query": {"type": "string", "description": "Drive query filter"},
                "page_size": {"type": "integer", "default": 20, "description": "Max files to return"},
                "order_by": {"type": "string", "default": "modifiedTime desc", "description": "Sort order"},
                "owned_only": {"type": "boolean", "default": False, "description": "Only return files owned by user"}
            }
        }
    },
    {
        "name": "gdrive_search_files",
        "description": "Searches Drive files by name substring and file_type category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string", "description": "Name search substring"},
                "file_type": {"type": "string", "enum": ["pdf", "doc", "sheet", "slide", "image", "folder", "audio", "video"], "description": "File type filter"},
                "folder_id": {"type": "string", "description": "Optional parent folder ID"},
                "page_size": {"type": "integer", "default": 20, "description": "Max results"}
            }
        }
    },
    {
        "name": "gdrive_get_file_info",
        "description": "Gets metadata and download links for a Drive file by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "Drive file ID"}
            },
            "required": ["file_id"]
        }
    },
    {
        "name": "gdrive_download_file",
        "description": "Downloads a file to disk (auto-exports Docs/Sheets/Slides to PDF/docx/xlsx).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "Drive file ID"},
                "destination_path": {"type": "string", "description": "Optional destination path"}
            },
            "required": ["file_id"]
        }
    },
    {
        "name": "gdrive_upload_file",
        "description": "Uploads a local file to Google Drive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Source file path"},
                "folder_id": {"type": "string", "description": "Destination folder ID (default root)"},
                "file_name": {"type": "string", "description": "Optional custom file name"},
                "description": {"type": "string", "description": "Optional description"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "gdrive_create_folder",
        "description": "Creates a new folder on Google Drive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder_name": {"type": "string", "description": "Folder name"},
                "parent_id": {"type": "string", "description": "Parent folder ID (default root)"}
            },
            "required": ["folder_name"]
        }
    },
    {
        "name": "gdrive_delete_file",
        "description": "Moves a file/folder to trash (or permanently deletes if permanent=True).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "File or folder ID"},
                "permanent": {"type": "boolean", "default": False, "description": "Permanent deletion"}
            },
            "required": ["file_id"]
        }
    },
    {
        "name": "gdrive_move_file",
        "description": "Moves a file or folder to another destination folder in Drive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "File or folder ID"},
                "target_folder_id": {"type": "string", "description": "Destination folder ID"}
            },
            "required": ["file_id", "target_folder_id"]
        }
    },
    {
        "name": "gdrive_share_file",
        "description": "Shares a file/folder with an email or enables link access.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "Drive file ID"},
                "role": {"type": "string", "enum": ["reader", "commenter", "writer"], "default": "reader", "description": "Permission role"},
                "email": {"type": "string", "description": "Optional user email"},
                "anyone_with_link": {"type": "boolean", "default": False, "description": "Allow public link access"}
            },
            "required": ["file_id"]
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    client = get_drive_client()
    try:
        if name == "gdrive_check_auth":
            return json.dumps(client.check_auth())

        elif name == "gdrive_list_files":
            folder_id = args.get("folder_id")
            query = args.get("query")
            page_size = args.get("page_size", 20)
            order_by = args.get("order_by", "modifiedTime desc")
            owned_only = args.get("owned_only", False)
            return json.dumps(client.list_files(query=query, folder_id=folder_id, page_size=page_size, order_by=order_by, owned_only=owned_only))

        elif name == "gdrive_search_files":
            name_contains = args.get("name_contains")
            file_type = args.get("file_type")
            folder_id = args.get("folder_id")
            page_size = args.get("page_size", 20)
            return json.dumps(client.search_files(
                name_contains=name_contains,
                file_type=file_type,
                folder_id=folder_id,
                page_size=page_size
            ))

        elif name == "gdrive_get_file_info":
            file_id = args.get("file_id")
            if not file_id:
                return json.dumps({"error": "file_id is required"})
            return json.dumps(client.get_file_info(file_id))

        elif name == "gdrive_download_file":
            file_id = args.get("file_id")
            if not file_id:
                return json.dumps({"error": "file_id is required"})
            dest = args.get("destination_path")
            return json.dumps(client.download_file(file_id, destination_path=dest))

        elif name == "gdrive_upload_file":
            file_path = args.get("file_path")
            if not file_path:
                return json.dumps({"error": "file_path is required"})
            folder_id = args.get("folder_id")
            file_name = args.get("file_name")
            desc = args.get("description")
            return json.dumps(client.upload_file(file_path, folder_id=folder_id, file_name=file_name, description=desc))

        elif name == "gdrive_create_folder":
            folder_name = args.get("folder_name")
            if not folder_name:
                return json.dumps({"error": "folder_name is required"})
            parent_id = args.get("parent_id")
            return json.dumps(client.create_folder(folder_name, parent_id=parent_id))

        elif name == "gdrive_delete_file":
            file_id = args.get("file_id")
            if not file_id:
                return json.dumps({"error": "file_id is required"})
            perm = args.get("permanent", False)
            return json.dumps(client.delete_file(file_id, permanent=perm))

        elif name == "gdrive_move_file":
            file_id = args.get("file_id")
            target_folder_id = args.get("target_folder_id")
            if not file_id or not target_folder_id:
                return json.dumps({"error": "file_id and target_folder_id are required"})
            return json.dumps(client.move_file(file_id, target_folder_id))

        elif name == "gdrive_share_file":
            file_id = args.get("file_id")
            if not file_id:
                return json.dumps({"error": "file_id is required"})
            role = args.get("role", "reader")
            email = args.get("email")
            anyone = args.get("anyone_with_link", False)
            return json.dumps(client.share_file(file_id, role=role, email=email, anyone_with_link=anyone))

        else:
            return json.dumps({"error": f"Unknown Google Drive tool: {name}"})

    except Exception as e:
        logger.exception(f"Error handling {name}: {e}")
        return json.dumps({"error": f"Google Drive error: {str(e)}"})


def main():
    logging.info(f"Starting Google Drive MCP Server with {len(TOOLS)} tools...")
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
            continue

        resp = {"jsonrpc": "2.0", "id": req_id}

        try:
            if method == "initialize":
                resp["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "gdrive-mcp",
                        "version": "1.0.0"
                    }
                }
            elif method == "tools/list":
                resp["result"] = {"tools": TOOLS}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
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
            resp["error"] = {
                "code": -32603,
                "message": str(e)
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
