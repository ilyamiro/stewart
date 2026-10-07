import json
import logging
from typing import Dict, Any, List

from .service import StreamingService

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "streaming_search",
        "description": "Searches for movies and TV series across IMDb, TVMaze, and FMHY streaming sources. Returns titles, release years, IMDb IDs, media type (movie/series), posters, cast, and instant player links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Title or search terms (e.g. 'Inception', 'Dune 2', 'Arcane')"},
                "media_type": {"type": "string", "enum": ["all", "movie", "series"], "default": "all", "description": "Filter by 'movie', 'series', or 'all'"},
                "limit": {"type": "integer", "default": 8, "description": "Maximum number of results (default 8)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "streaming_get_player_links",
        "description": "Gets direct streaming player links for any movie or TV series across top FMHY providers (VidLink, Flixer, Cinecat, HydraHD, MultiEmbed, Rive, etc.). Automatically checks reachability so you get working links in priority order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Movie or series title (e.g. 'Interstellar' or 'The Boys')"},
                "id": {"type": "string", "description": "Optional IMDb ID (e.g. 'tt1375666') or TMDB ID"},
                "media_type": {"type": "string", "enum": ["movie", "series"], "default": "movie", "description": "Type: 'movie' or 'series'"},
                "season": {"type": "integer", "default": 1, "description": "Season number for TV series (default 1)"},
                "episode": {"type": "integer", "default": 1, "description": "Episode number for TV series (default 1)"},
                "verify": {"type": "boolean", "default": True, "description": "Whether to verify URL reachability in parallel"}
            }
        }
    },
    {
        "name": "streaming_open",
        "description": "Opens any movie or series directly in the user's browser. Adapts top FMHY streaming sites: if one website is unreachable, it automatically goes down the list to try the next one until a working player opens. Also provides backup links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Movie or series name/query, supports formats like 'Inception', 'Breaking Bad s01e01', 'Arcane'"},
                "title": {"type": "string", "description": "Explicit title (if not using query)"},
                "id": {"type": "string", "description": "Optional IMDb ID (e.g. 'tt1375666')"},
                "media_type": {"type": "string", "enum": ["movie", "series"], "default": "movie", "description": "Type: 'movie' or 'series'"},
                "season": {"type": "integer", "default": 1, "description": "Season number for series (default 1)"},
                "episode": {"type": "integer", "default": 1, "description": "Episode number for series (default 1)"},
                "provider": {"type": "string", "default": "auto", "description": "Specific provider or 'auto' (VidLink, Flixer, Cinecat, HydraHD, MultiEmbed, Rive, etc.)"}
            }
        }
    },
    {
        "name": "streaming_list_providers",
        "description": "Lists all adapted FMHY streaming providers, their base URLs, priority rank, and supported features (Auto-Next, 4K, Multi-Server, Direct Player, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

_service = StreamingService()


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    try:
        if name == "streaming_search":
            query = args.get("query", "")
            if not query:
                return json.dumps({"error": "query parameter is required"})
            media_type = args.get("media_type", "all")
            limit = int(args.get("limit", 8))
            results = _service.search(query=query, media_type=media_type, limit=limit)
            return json.dumps({"query": query, "count": len(results), "results": results})

        elif name == "streaming_get_player_links":
            title = args.get("title")
            media_id = args.get("id")
            media_type = args.get("media_type", "movie")
            season = int(args.get("season", 1))
            episode = int(args.get("episode", 1))
            verify = args.get("verify", True)
            res = _service.get_movie_links(
                title=title,
                media_id=media_id,
                media_type=media_type,
                season=season,
                episode=episode,
                verify=verify
            )
            return json.dumps(res)

        elif name == "streaming_open":
            query = args.get("query")
            title = args.get("title")
            media_id = args.get("id")
            media_type = args.get("media_type", "movie")
            season = int(args.get("season", 1))
            episode = int(args.get("episode", 1))
            provider = args.get("provider", "auto")

            res = _service.open_movie(
                query=query,
                title=title,
                media_id=media_id,
                media_type=media_type,
                season=season,
                episode=episode,
                preferred_provider=provider
            )
            return json.dumps(res)

        elif name == "streaming_list_providers":
            providers = _service.list_providers()
            return json.dumps({"providers": providers, "count": len(providers)})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        logger.exception(f"Error handling streaming tool {name}: {e}")
        return json.dumps({"error": f"Streaming tool failed: {str(e)}"})
