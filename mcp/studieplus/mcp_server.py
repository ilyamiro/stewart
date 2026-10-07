import sys
import json
import logging
from typing import Dict, Any, List

from studieplus.gateway import StudiePlusGateway
from studieplus.config import Config
from studieplus.ib_resources import IBResourcesClient
from studieplus.study_assistant import StudyAssistant

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

gateway = StudiePlusGateway()
ib_client = IBResourcesClient()
study_assistant = StudyAssistant(gateway=gateway, ib_client=ib_client)

TOOLS = [
    {
        "name": "studieplus_get_schedule",
        "description": "Gets school timetable (classes, rooms, teachers, homework notes) for a day or week.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "default": "today", "description": "'today', 'tomorrow', or 'YYYY-MM-DD'"},
                "mode": {"type": "string", "enum": ["day", "week"], "default": "day", "description": "'day' or 'week'"}
            }
        }
    },
    {
        "name": "studieplus_get_assignments",
        "description": "Queries school assignments with deadlines and descriptions. (Note: Maths AA HL submitted on paper).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "graded", "submitted", "all"], "default": "open", "description": "Assignment status filter"},
                "due_date": {"type": "string", "description": "'today', 'tomorrow', or 'YYYY-MM-DD'"},
                "days_ahead": {"type": "integer", "description": "Upcoming days window"},
                "from_date": {"type": "string", "description": "Start date ('YYYY-MM-DD')"},
                "to_date": {"type": "string", "description": "End date ('YYYY-MM-DD')"},
                "subject": {"type": "string", "description": "Subject filter (e.g. 'Maths', 'Physics')"},
                "with_details": {"type": "boolean", "default": False, "description": "Include full descriptions and attachments"}
            }
        }
    },
    {
        "name": "studieplus_get_conversations",
        "description": "Fetches school messages and announcements with thread content and attachments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10, "description": "Max conversations to fetch"},
                "with_content": {"type": "boolean", "default": True, "description": "Fetch message body and attachments"},
                "view_all": {"type": "boolean", "default": False, "description": "Fetch beyond 14 days"}
            }
        }
    },
    {
        "name": "studieplus_check_session",
        "description": "Checks if Studie+ web session is authenticated.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "study_get_ib_resources",
        "description": "Searches, downloads, and opens IB past papers and markschemes from official mirrors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "default": "math aa", "description": "Subject (e.g. 'math aa', 'physics', 'economics')"},
                "level": {"type": "string", "enum": ["HL", "SL", "both"], "default": "HL", "description": "HL or SL"},
                "paper_num": {"type": "integer", "description": "Paper number (1, 2, 3)"},
                "year": {"type": "string", "description": "Exam year (e.g. '2025')"},
                "session": {"type": "string", "description": "'May' or 'November'"},
                "component": {"type": "string", "enum": ["paper", "markscheme", "all"], "default": "paper", "description": "'paper' or 'markscheme'"},
                "query": {"type": "string", "description": "Title search keyword"},
                "download": {"type": "boolean", "default": True, "description": "Download matching PDF"},
                "open_after_download": {"type": "boolean", "default": True, "description": "Open PDF in system viewer"}
            }
        }
    },
    {
        "name": "study_prepare_test",
        "description": "Prepares for an IB test: scans covered curriculum topics from schedule cache and opens target past papers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "default": "Maths AA HL", "description": "Subject name"},
                "test_date": {"type": "string", "default": "2026-10-27", "description": "Test date ('YYYY-MM-DD')"},
                "from_date": {"type": "string", "default": "2026-08-10", "description": "Start of term date"},
                "auto_download_papers": {"type": "boolean", "default": True, "description": "Download past papers"},
                "open_after_download": {"type": "boolean", "default": True, "description": "Open downloaded papers"}
            }
        }
    },
    {
        "name": "study_get_past_topics",
        "description": "Lists covered curriculum topics and lessons taught from schedule cache.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "default": "Maths AA HL", "description": "Subject name"},
                "from_date": {"type": "string", "default": "2026-08-10", "description": "Start date"},
                "to_date": {"type": "string", "description": "End date (defaults to today)"}
            }
        }
    }
]


def handle_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    if name == "studieplus_get_schedule":
        target_date = arguments.get("date", "today")
        mode = arguments.get("mode", "day")
        if mode == "week":
            week = gateway.get_week(target_date=target_date)
            return week.model_dump_json(exclude_none=True)
        else:
            day = gateway.get_day(target_date=target_date)
            return day.model_dump_json(exclude_none=True)

    elif name == "studieplus_get_assignments":
        status = arguments.get("status", "open")
        due_date = arguments.get("due_date")
        days_ahead = arguments.get("days_ahead")
        from_date = arguments.get("from_date")
        to_date = arguments.get("to_date")
        subject = arguments.get("subject")
        with_details = arguments.get("with_details", False)

        assignments = gateway.get_assignments(
            status=status,
            due_date=due_date,
            days_ahead=days_ahead,
            from_date=from_date,
            to_date=to_date,
            subject=subject,
            with_details=with_details
        )
        return json.dumps([a.model_dump(exclude_none=True) for a in assignments], ensure_ascii=False)

    elif name == "studieplus_get_conversations":
        limit = arguments.get("limit", 10)
        with_content = arguments.get("with_content", True)
        view_all = arguments.get("view_all", False)

        convs = gateway.get_conversations(
            limit=limit,
            with_content=with_content,
            view_all=view_all
        )
        return json.dumps([c.model_dump(exclude_none=True) for c in convs], ensure_ascii=False)

    elif name == "studieplus_check_session":
        is_logged = gateway.is_logged_in()
        return json.dumps({"authenticated": is_logged, "profile_dir": str(gateway.config.profile_dir)})

    elif name == "study_get_ib_resources":
        subject = arguments.get("subject", "math aa")
        level = arguments.get("level", "HL")
        paper_num = arguments.get("paper_num")
        year = arguments.get("year")
        session = arguments.get("session")
        component = arguments.get("component", "paper")
        query = arguments.get("query")
        download = arguments.get("download", True)
        open_after_download = arguments.get("open_after_download", True)

        papers = ib_client.search_papers(
            subject=subject,
            level=level if level != "both" else None,
            paper_num=paper_num,
            year=year,
            session=session,
            component=component if component != "all" else None,
            query=query
        )

        download_result = None
        if download and papers:
            download_result = ib_client.download_paper(papers[0], open_after_download=open_after_download)

        return json.dumps({
            "subject": subject,
            "total_matches": len(papers),
            "papers": papers[:10],
            "downloaded": download_result
        }, ensure_ascii=False)

    elif name == "study_prepare_test":
        subject = arguments.get("subject", "Maths AA HL")
        test_date = arguments.get("test_date", "2026-10-27")
        from_date = arguments.get("from_date", "2026-08-10")
        auto_download_papers = arguments.get("auto_download_papers", True)
        open_after_download = arguments.get("open_after_download", True)

        res = study_assistant.prepare_test(
            subject=subject,
            test_date=test_date,
            from_date=from_date,
            auto_download_papers=auto_download_papers,
            open_after_download=open_after_download
        )
        return json.dumps(res, ensure_ascii=False)

    elif name == "study_get_past_topics":
        subject = arguments.get("subject", "Maths AA HL")
        from_date = arguments.get("from_date", "2026-08-10")
        to_date = arguments.get("to_date")

        res = study_assistant.get_subject_topics(
            subject=subject,
            from_date=from_date,
            to_date=to_date
        )
        return json.dumps(res, ensure_ascii=False)

    else:
        raise ValueError(f"Unknown tool: {name}")


def main():
    logging.info("Studie+ MCP Server starting on stdio...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON: {line}")
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
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "studieplus-mcp",
                        "version": "0.1.0"
                    }
                }
            elif method == "tools/list":
                resp["result"] = {
                    "tools": TOOLS
                }
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
