import logging
import re
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple

from .providers import STREAMING_PROVIDERS, Provider
from .search import search_media, get_tmdb_id, MediaItem

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
}


def check_url_reachability(url: str, timeout: float = 2.5) -> Tuple[bool, int, str]:
    """Tests if a URL is reachable. Returns (is_reachable, status_code, message)."""
    try:
        req = urllib.request.Request(url, headers=HEADERS, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if 200 <= status < 400:
                return True, status, "OK"
            return False, status, f"HTTP {status}"
    except urllib.error.HTTPError as e:
        return False, e.code, f"HTTP {e.code}"
    except Exception as e:
        return False, 0, str(e)


class StreamingService:
    def __init__(self, providers: Optional[List[Provider]] = None):
        self.providers = providers or sorted(STREAMING_PROVIDERS, key=lambda p: p.priority)

    def search(self, query: str, media_type: str = "all", limit: int = 8) -> List[Dict[str, Any]]:
        """Searches for movies and series with quick player links for each."""
        items = search_media(query, media_type=media_type, limit=limit)
        results = []
        for item in items:
            entry = item.to_dict()
            entry["quick_players"] = self.generate_player_links(
                media_id=item.id,
                tmdb_id=item.tmdb_id,
                media_type=item.media_type,
                verify=False
            )[:3]
            results.append(entry)
        return results

    def generate_player_links(
        self,
        media_id: str,
        tmdb_id: Optional[int] = None,
        media_type: str = "movie",
        season: int = 1,
        episode: int = 1,
        verify: bool = False
    ) -> List[Dict[str, Any]]:
        """Generates streaming player URLs across top FMHY providers."""
        links: List[Dict[str, Any]] = []

        for p in self.providers:
            if not p.supports_direct_player:
                continue
            if media_type == "movie":
                url = p.get_movie_url(media_id, tmdb_id=tmdb_id)
            else:
                url = p.get_tv_url(media_id, season=season, episode=episode, tmdb_id=tmdb_id)

            if not url:
                continue

            links.append({
                "provider": p.name,
                "url": url,
                "priority": p.priority,
                "features": p.features,
                "reachable": None
            })

        if verify and links:
            with ThreadPoolExecutor(max_workers=min(len(links), 6)) as executor:
                future_to_link = {
                    executor.submit(check_url_reachability, l["url"]): l
                    for l in links
                }
                for future in as_completed(future_to_link):
                    link = future_to_link[future]
                    try:
                        ok, status, msg = future.result()
                        link["reachable"] = ok
                        link["status_code"] = status
                        link["check_msg"] = msg
                    except Exception as e:
                        link["reachable"] = False
                        link["status_code"] = 0
                        link["check_msg"] = str(e)

            links.sort(key=lambda x: (not x["reachable"], x["priority"]))

        return links

    def resolve_media_id(
        self,
        title: Optional[str] = None,
        media_id: Optional[str] = None,
        media_type: str = "movie"
    ) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[int], str]:
        """Resolves title to IMDb ID, TMDB ID, canonical title, year, and media type."""
        if media_id and media_id.startswith("tt"):
            tmdb_id = get_tmdb_id(media_id, media_type)
            return media_id, tmdb_id, title or media_id, None, media_type

        query = title or media_id
        if not query:
            return None, None, None, None, media_type

        cleaned_query = query
        detected_season = None
        detected_episode = None
        m = re.search(r"\b[sS](\d+)\s*[eE](\d+)\b", query)
        if m:
            detected_season = int(m.group(1))
            detected_episode = int(m.group(2))
            cleaned_query = re.sub(r"\b[sS]\d+\s*[eE]\d+\b", "", query).strip()
            media_type = "series"

        items = search_media(cleaned_query, media_type="all", limit=5)
        if not items:
            return None, None, query, None, media_type

        best = items[0]
        actual_type = best.media_type or media_type
        tmdb_id = best.tmdb_id or get_tmdb_id(best.id, actual_type)
        return best.id, tmdb_id, best.title, best.year, actual_type

    def get_movie_links(
        self,
        title: Optional[str] = None,
        media_id: Optional[str] = None,
        media_type: str = "movie",
        season: int = 1,
        episode: int = 1,
        verify: bool = True
    ) -> Dict[str, Any]:
        """Finds and verifies direct player links across top FMHY providers."""
        resolved_id, tmdb_id, canonical_title, year, resolved_type = self.resolve_media_id(
            title=title, media_id=media_id, media_type=media_type
        )
        if not resolved_id:
            return {
                "error": f"Could not find movie or series for query: '{title or media_id}'",
                "resolved": False
            }

        player_links = self.generate_player_links(
            media_id=resolved_id,
            tmdb_id=tmdb_id,
            media_type=resolved_type,
            season=season,
            episode=episode,
            verify=verify
        )

        search_fallbacks = []
        search_query = f"{canonical_title} {year}" if year else canonical_title
        for p in self.providers:
            if p.search_template:
                s_url = p.get_search_url(search_query)
                if s_url:
                    search_fallbacks.append({
                        "provider": p.name,
                        "search_url": s_url,
                        "features": p.features
                    })

        return {
            "resolved": True,
            "id": resolved_id,
            "tmdb_id": tmdb_id,
            "title": canonical_title,
            "year": year,
            "media_type": resolved_type,
            "season": season if resolved_type == "series" else None,
            "episode": episode if resolved_type == "series" else None,
            "player_links": player_links,
            "search_fallbacks": search_fallbacks
        }

    def open_movie(
        self,
        query: Optional[str] = None,
        title: Optional[str] = None,
        media_id: Optional[str] = None,
        media_type: str = "movie",
        season: int = 1,
        episode: int = 1,
        preferred_provider: str = "auto"
    ) -> Dict[str, Any]:
        """Tries top streaming sites down the FMHY list until a reachable one is found, then opens it in the browser."""
        target_name = query or title or media_id
        if not target_name:
            return {"error": "A movie title, search query, or media ID must be provided."}

        m = re.search(r"\b[sS](\d+)\s*[eE](\d+)\b", target_name)
        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            media_type = "series"

        resolved_id, tmdb_id, canonical_title, year, resolved_type = self.resolve_media_id(
            title=title or query, media_id=media_id, media_type=media_type
        )

        if not resolved_id:
            for p in self.providers:
                if p.search_template:
                    search_url = p.get_search_url(target_name)
                    self._launch_in_browser(search_url)
                    return {
                        "status": "opened_search",
                        "provider": p.name,
                        "url": search_url,
                        "query": target_name,
                        "note": "Exact movie ID not found, opened direct search on top FMHY streaming site."
                    }
            return {"error": f"Could not find or resolve: '{target_name}'"}

        candidates = self.generate_player_links(
            media_id=resolved_id,
            tmdb_id=tmdb_id,
            media_type=resolved_type,
            season=season,
            episode=episode,
            verify=False
        )

        if preferred_provider and preferred_provider.lower() != "auto":
            matched = [c for c in candidates if c["provider"].lower() == preferred_provider.lower()]
            if matched:
                candidates = matched + [c for c in candidates if c["provider"].lower() != preferred_provider.lower()]

        tried_providers = []
        selected_link = None

        for item in candidates:
            url = item["url"]
            p_name = item["provider"]
            logger.info(f"Checking reachability for {p_name}: {url}")
            is_reachable, status, msg = check_url_reachability(url, timeout=3.0)
            tried_providers.append({
                "provider": p_name,
                "url": url,
                "reachable": is_reachable,
                "status": status,
                "error": msg if not is_reachable else None
            })

            if is_reachable:
                selected_link = item
                break

        if not selected_link:
            logger.warning("All direct players failed fast reachability; falling back to top provider Flixer/Movy")
            selected_link = candidates[0] if candidates else None

        if not selected_link:
            return {
                "error": f"No playable streaming source found for {canonical_title}",
                "tried": tried_providers
            }

        target_url = selected_link["url"]
        opened = self._launch_in_browser(target_url)

        backup_links = [c["url"] for c in candidates if c["url"] != target_url][:4]

        return {
            "status": "success" if opened else "url_generated",
            "message": f"Opened '{canonical_title}' ({year or 'N/A'}) on {selected_link['provider']}" if opened else f"Stream URL generated for {canonical_title}",
            "title": canonical_title,
            "year": year,
            "id": resolved_id,
            "media_type": resolved_type,
            "season": season if resolved_type == "series" else None,
            "episode": episode if resolved_type == "series" else None,
            "provider": selected_link["provider"],
            "url": target_url,
            "tried_providers": tried_providers,
            "backup_links": backup_links
        }

    def _launch_in_browser(self, url: str) -> bool:
        """Launches URL using system_control or desktop browser dispatch."""
        try:
            from life.system_control import execute_system_control
            res = execute_system_control(command=f"system / open / browser / {url}")
            if res.get("status") == "success":
                return True
        except Exception as e:
            logger.warning(f"system_control browser open failed: {e}")

        try:
            import subprocess
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logger.error(f"Failed to open browser with xdg-open: {e}")
            return False

    def list_providers(self) -> List[Dict[str, Any]]:
        """Returns the list of adapted FMHY providers and their capabilities."""
        return [
            {
                "name": p.name,
                "base_url": p.base_url,
                "priority": p.priority,
                "features": p.features,
                "supports_direct_player": p.supports_direct_player,
                "has_search": p.search_template is not None
            }
            for p in self.providers
        ]
