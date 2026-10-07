import sys
import json
import logging
from typing import Dict, Any, List

from github_service.client import get_github_client

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

github_client = get_github_client()

TOOLS = [
    {
        "name": "github_check_auth",
        "description": "Checks if GitHub account is authenticated.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "github_set_token",
        "description": "Sets and verifies GitHub Personal Access Token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "GitHub PAT"}
            },
            "required": ["token"]
        }
    },
    {
        "name": "github_list_repos",
        "description": "Lists repositories with visibility ('all', 'public', 'private') and sort filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "visibility": {"type": "string", "enum": ["all", "public", "private"], "default": "all", "description": "Visibility filter"},
                "sort": {"type": "string", "enum": ["updated", "created", "pushed", "full_name"], "default": "updated", "description": "Sort field"},
                "limit": {"type": "integer", "default": 20, "description": "Max repos to return"}
            }
        }
    },
    {
        "name": "github_get_repo_info",
        "description": "Gets repository details by 'owner/repo'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository ('owner/repo')"}
            },
            "required": ["repo"]
        }
    },
    {
        "name": "github_list_issues",
        "description": "Lists issues across repos or for a specific 'owner/repo'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Optional 'owner/repo'"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open", "description": "Issue state"},
                "limit": {"type": "integer", "default": 20, "description": "Max issues"}
            }
        }
    },
    {
        "name": "github_create_issue",
        "description": "Creates an issue in 'owner/repo'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Target 'owner/repo'"},
                "title": {"type": "string", "description": "Issue title"},
                "body": {"type": "string", "description": "Issue description"},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional labels"
                }
            },
            "required": ["repo", "title"]
        }
    },
    {
        "name": "github_list_pull_requests",
        "description": "Lists pull requests for 'owner/repo'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Target 'owner/repo'"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open", "description": "PR state"},
                "limit": {"type": "integer", "default": 20, "description": "Max PRs"}
            },
            "required": ["repo"]
        }
    },
    {
        "name": "github_get_notifications",
        "description": "Fetches GitHub notifications across repositories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "all": {"type": "boolean", "default": False, "description": "Include read notifications"},
                "limit": {"type": "integer", "default": 20, "description": "Max notifications"}
            }
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    if name == "github_check_auth":
        res = github_client.check_auth()
        return json.dumps(res, ensure_ascii=False)

    elif name == "github_set_token":
        token = args.get("token")
        if not token:
            return json.dumps({"error": "token is required"})
        res = github_client.set_token(token)
        return json.dumps(res, ensure_ascii=False)

    elif name == "github_list_repos":
        visibility = args.get("visibility", "all")
        sort = args.get("sort", "updated")
        limit = args.get("limit", 20)
        res = github_client.list_repos(visibility=visibility, sort=sort, limit=limit)
        return json.dumps(res, ensure_ascii=False)

    elif name == "github_get_repo_info":
        repo = args.get("repo")
        if not repo:
            return json.dumps({"error": "repo is required"})
        res = github_client.get_repo_info(repo)
        return json.dumps(res, ensure_ascii=False)

    elif name == "github_list_issues":
        repo = args.get("repo")
        state = args.get("state", "open")
        limit = args.get("limit", 20)
        res = github_client.list_issues(repo_name=repo, state=state, limit=limit)
        return json.dumps(res, ensure_ascii=False)

    elif name == "github_create_issue":
        repo = args.get("repo")
        title = args.get("title")
        body = args.get("body")
        labels = args.get("labels")
        if not repo or not title:
            return json.dumps({"error": "repo and title are required"})
        res = github_client.create_issue(repo_name=repo, title=title, body=body, labels=labels)
        return json.dumps(res, ensure_ascii=False)

    elif name == "github_list_pull_requests":
        repo = args.get("repo")
        state = args.get("state", "open")
        limit = args.get("limit", 20)
        if not repo:
            return json.dumps({"error": "repo is required"})
        res = github_client.list_pull_requests(repo_name=repo, state=state, limit=limit)
        return json.dumps(res, ensure_ascii=False)

    elif name == "github_get_notifications":
        all_notifs = args.get("all", False)
        limit = args.get("limit", 20)
        res = github_client.get_notifications(all=all_notifs, limit=limit)
        return json.dumps(res, ensure_ascii=False)

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


def main():
    logging.info("Starting GitHub MCP Server...")
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
                        "name": "github-mcp",
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
