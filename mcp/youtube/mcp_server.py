"""YouTube MCP Server implementation."""

import sys
import json
import logging
from typing import Dict, Any

from youtube.client import get_youtube_client

logger = logging.getLogger("youtube_mcp")

TOOLS = [
    {
        "name": "youtube_search",
        "description": "Searches YouTube for videos, channels, or playlists.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 10, "description": "Max results"},
                "search_type": {"type": "string", "enum": ["video", "channel", "playlist"], "default": "video", "description": "Item type"},
                "order": {"type": "string", "enum": ["relevance", "date", "viewCount", "rating"], "default": "relevance", "description": "Sort order"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "youtube_get_video_details",
        "description": "Gets metadata, view count, and description for a video URL or ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id_or_url": {"type": "string", "description": "YouTube video ID or URL"}
            },
            "required": ["video_id_or_url"]
        }
    },
    {
        "name": "youtube_get_transcript",
        "description": "Extracts subtitle transcript text from a YouTube video.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id_or_url": {"type": "string", "description": "YouTube video ID or URL"},
                "language": {"type": "string", "default": "en", "description": "Language code (e.g. 'en', 'ru', 'da')"}
            },
            "required": ["video_id_or_url"]
        }
    },
    {
        "name": "youtube_check_auth",
        "description": "Checks YouTube authorization and channel stats.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "youtube_get_my_channel",
        "description": "Gets details of your YouTube channel.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "youtube_list_my_videos",
        "description": "Lists videos uploaded to your channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "default": 20, "description": "Max videos"}
            }
        }
    },
    {
        "name": "youtube_list_my_playlists",
        "description": "Lists your YouTube playlists.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "default": 20, "description": "Max playlists"}
            }
        }
    },
    {
        "name": "youtube_list_my_subscriptions",
        "description": "Lists subscribed channels.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "default": 20, "description": "Max subscriptions"}
            }
        }
    },
    {
        "name": "youtube_get_playlist_items",
        "description": "Lists videos in a playlist by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "playlist_id": {"type": "string", "description": "Playlist ID"},
                "max_results": {"type": "integer", "default": 20, "description": "Max items"}
            },
            "required": ["playlist_id"]
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    client = get_youtube_client()
    try:
        if name == "youtube_search":
            query = args.get("query")
            if not query:
                return json.dumps({"error": "query is required"})
            max_results = args.get("max_results", 10)
            search_type = args.get("search_type", "video")
            order = args.get("order", "relevance")
            return json.dumps(client.search(query=query, max_results=max_results, search_type=search_type, order=order))

        elif name == "youtube_get_video_details":
            vid = args.get("video_id_or_url")
            if not vid:
                return json.dumps({"error": "video_id_or_url is required"})
            return json.dumps(client.get_video_details(vid))

        elif name == "youtube_get_transcript":
            vid = args.get("video_id_or_url")
            if not vid:
                return json.dumps({"error": "video_id_or_url is required"})
            lang = args.get("language", "en")
            return json.dumps(client.get_transcript(vid, language=lang))

        elif name == "youtube_check_auth":
            return json.dumps(client.check_auth())

        elif name == "youtube_get_my_channel":
            return json.dumps(client.get_my_channel())

        elif name == "youtube_list_my_videos":
            max_results = args.get("max_results", 20)
            return json.dumps(client.list_my_videos(max_results=max_results))

        elif name == "youtube_list_my_playlists":
            max_results = args.get("max_results", 20)
            return json.dumps(client.list_my_playlists(max_results=max_results))

        elif name == "youtube_list_my_subscriptions":
            max_results = args.get("max_results", 20)
            return json.dumps(client.list_my_subscriptions(max_results=max_results))

        elif name == "youtube_get_playlist_items":
            pl_id = args.get("playlist_id")
            if not pl_id:
                return json.dumps({"error": "playlist_id is required"})
            max_results = args.get("max_results", 20)
            return json.dumps(client.get_playlist_items(pl_id, max_results=max_results))

        else:
            return json.dumps({"error": f"Unknown YouTube tool: {name}"})

    except Exception as e:
        logger.exception(f"Error handling {name}: {e}")
        return json.dumps({"error": f"YouTube error: {str(e)}"})


def main():
    logging.info(f"Starting YouTube MCP Server with {len(TOOLS)} tools...")
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
                        "name": "youtube-mcp",
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
