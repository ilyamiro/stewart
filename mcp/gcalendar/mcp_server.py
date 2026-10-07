import sys
import json
import logging
from typing import Dict, Any, List

from gcalendar.client import get_calendar_client

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

calendar_client = get_calendar_client()

TOOLS = [
    {
        "name": "calendar_check_auth",
        "description": "Checks if Google Calendar is authenticated.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "calendar_list_events",
        "description": "Lists upcoming Google Calendar events with optional time range and search query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "calendar_id": {"type": "string", "default": "primary", "description": "Calendar ID"},
                "time_min": {"type": "string", "description": "Start time ('YYYY-MM-DD' or ISO)"},
                "time_max": {"type": "string", "description": "End time ('YYYY-MM-DD' or ISO)"},
                "max_results": {"type": "integer", "default": 20, "description": "Max events to return"},
                "query": {"type": "string", "description": "Text search query"}
            }
        }
    },
    {
        "name": "calendar_create_event",
        "description": "Creates a Google Calendar event (times: 'YYYY-MM-DD HH:MM' or ISO format).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title"},
                "start_time": {"type": "string", "description": "Start time"},
                "end_time": {"type": "string", "description": "End time"},
                "description": {"type": "string", "description": "Notes/details"},
                "location": {"type": "string", "description": "Location or room"},
                "calendar_id": {"type": "string", "default": "primary", "description": "Calendar ID"},
                "color_id": {"type": "string", "description": "Color ID (1-11)"}
            },
            "required": ["summary", "start_time", "end_time"]
        }
    },
    {
        "name": "calendar_quick_add",
        "description": "Creates a calendar event from natural language text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Event description with title, date, and time"},
                "calendar_id": {"type": "string", "default": "primary", "description": "Calendar ID"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "calendar_update_event",
        "description": "Updates an existing calendar event's title, time, location, or notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID"},
                "summary": {"type": "string", "description": "Updated title"},
                "start_time": {"type": "string", "description": "Updated start time"},
                "end_time": {"type": "string", "description": "Updated end time"},
                "description": {"type": "string", "description": "Updated notes"},
                "location": {"type": "string", "description": "Updated location"},
                "calendar_id": {"type": "string", "default": "primary", "description": "Calendar ID"}
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "calendar_delete_event",
        "description": "Deletes a Google Calendar event by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID to delete"},
                "calendar_id": {"type": "string", "default": "primary", "description": "Calendar ID"}
            },
            "required": ["event_id"]
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    if name == "calendar_check_auth":
        res = calendar_client.check_auth()
        return json.dumps(res, ensure_ascii=False)

    elif name == "calendar_list_events":
        cal_id = args.get("calendar_id", "primary")
        time_min = args.get("time_min")
        time_max = args.get("time_max")
        max_results = args.get("max_results", 20)
        query = args.get("query")
        res = calendar_client.list_events(
            calendar_id=cal_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            query=query
        )
        return json.dumps(res, ensure_ascii=False)

    elif name == "calendar_create_event":
        summary = args.get("summary")
        start_time = args.get("start_time")
        end_time = args.get("end_time")
        description = args.get("description")
        location = args.get("location")
        calendar_id = args.get("calendar_id", "primary")
        color_id = args.get("color_id")

        if not summary or not start_time or not end_time:
            return json.dumps({"error": "summary, start_time, and end_time are required"})

        res = calendar_client.create_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            calendar_id=calendar_id,
            color_id=color_id
        )
        return json.dumps(res, ensure_ascii=False)

    elif name == "calendar_quick_add":
        text = args.get("text")
        calendar_id = args.get("calendar_id", "primary")
        if not text:
            return json.dumps({"error": "text is required"})
        res = calendar_client.quick_add(text=text, calendar_id=calendar_id)
        return json.dumps(res, ensure_ascii=False)

    elif name == "calendar_update_event":
        event_id = args.get("event_id")
        if not event_id:
            return json.dumps({"error": "event_id is required"})
        res = calendar_client.update_event(
            event_id=event_id,
            summary=args.get("summary"),
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            description=args.get("description"),
            location=args.get("location"),
            calendar_id=args.get("calendar_id", "primary")
        )
        return json.dumps(res, ensure_ascii=False)

    elif name == "calendar_delete_event":
        event_id = args.get("event_id")
        calendar_id = args.get("calendar_id", "primary")
        if not event_id:
            return json.dumps({"error": "event_id is required"})
        res = calendar_client.delete_event(event_id=event_id, calendar_id=calendar_id)
        return json.dumps(res, ensure_ascii=False)

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


def main():
    logging.info("Starting Google Calendar MCP Server...")
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
                        "name": "gcalendar-mcp",
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
