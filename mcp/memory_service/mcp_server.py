import sys
import json
import logging
from typing import Dict, Any, List

from memory_service.engine import get_memory_engine

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

TOOLS = [
    {
        "name": "memory_search",
        "description": "Searches persistent memory / notes database using fast full-text search (BM25 ranking). Returns matching excerpts with file, section, and line numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query terms or phrase"
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Max matching snippets to return (default 5)"
                },
                "topic": {
                    "type": "string",
                    "description": "Optional filter by topic or file name"
                },
                "tag": {
                    "type": "string",
                    "description": "Optional filter by tag (e.g. 'study', 'people', 'preference')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_get",
        "description": "Retrieves the full content of a memory file/topic or a specific section.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or file name (without .md)"
                },
                "file_name": {
                    "type": "string",
                    "description": "Specific file path (e.g. 'preferences.md' or 'school/notes.md')"
                },
                "section": {
                    "type": "string",
                    "description": "Specific heading / section title to fetch"
                }
            }
        }
    },
    {
        "name": "memory_list_topics",
        "description": "Lists all available memory files, section headings, tags, and stats without reading the entire content (low token overhead).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "memory_save",
        "description": "Saves, appends, or updates notes/facts in the persistent memory markdown database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information or note content to save"
                },
                "topic": {
                    "type": "string",
                    "default": "notes",
                    "description": "Topic or file name (e.g. 'preferences', 'people', 'school', 'notes')"
                },
                "section": {
                    "type": "string",
                    "description": "Optional markdown section heading (e.g. 'Daily Schedule', 'Coding Rules')"
                },
                "mode": {
                    "type": "string",
                    "enum": ["append", "overwrite"],
                    "default": "append",
                    "description": "Whether to append to the topic/section or overwrite it"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tags"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "memory_delete",
        "description": "Deletes a specific section or an entire topic/file from persistent memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or file name"
                },
                "section": {
                    "type": "string",
                    "description": "Optional specific section heading to delete"
                }
            },
            "required": ["topic"]
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    engine = get_memory_engine()

    try:
        if name == "memory_search":
            query = args.get("query", "")
            limit = int(args.get("limit", 5))
            topic = args.get("topic")
            tag = args.get("tag")
            if not query:
                return json.dumps({"error": "query is required"})
            results = engine.search(query=query, limit=limit, topic=topic, tag=tag)
            return json.dumps({"query": query, "count": len(results), "results": results})

        elif name == "memory_get":
            topic = args.get("topic")
            file_name = args.get("file_name")
            section = args.get("section")
            if not topic and not file_name:
                return json.dumps({"error": "Either topic or file_name must be provided"})
            result = engine.get(topic=topic, file_name=file_name, section=section)
            return json.dumps(result)

        elif name == "memory_list_topics":
            overview = engine.list_topics()
            return json.dumps(overview)

        elif name == "memory_save":
            content = args.get("content", "")
            if not content:
                return json.dumps({"error": "content is required"})
            topic = args.get("topic", "notes")
            section = args.get("section")
            mode = args.get("mode", "append")
            tags = args.get("tags")
            res = engine.save(content=content, topic=topic, section=section, mode=mode, tags=tags)
            return json.dumps(res)

        elif name == "memory_delete":
            topic = args.get("topic", "")
            if not topic:
                return json.dumps({"error": "topic is required"})
            section = args.get("section")
            res = engine.delete(topic=topic, section=section)
            return json.dumps(res)

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        logger.exception(f"Error executing {name}: {e}")
        return json.dumps({"error": str(e)})


def main():
    logging.info(f"Starting Persistent Memory MCP Server with {len(TOOLS)} tools...")
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
                        "name": "memory-mcp",
                        "version": "1.0.0"
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
