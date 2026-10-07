import json
import logging
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .browser import fetch_rendered_html, is_selenium_available

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}


@dataclass
class MediaItem:
    title: str
    id: str
    media_type: str
    tmdb_id: Optional[int] = None
    year: Optional[int] = None
    poster: Optional[str] = None
    cast: List[str] = field(default_factory=list)
    overview: Optional[str] = None
    extra_sources: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "media_type": self.media_type,
            "year": self.year,
            "poster": self.poster,
            "cast": self.cast,
            "overview": self.overview,
            "extra_sources": self.extra_sources
        }


def get_tmdb_id(imdb_id: str, media_type: str = "movie") -> Optional[int]:
    """Fetches TMDB ID from cinemeta for a given IMDb ID."""
    if not imdb_id or not imdb_id.startswith("tt"):
        return None
    c_type = "series" if media_type == "series" else "movie"
    url = f"https://v3-cinemeta.strem.io/meta/{c_type}/{imdb_id}.json"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            meta = data.get("meta", {})
            return meta.get("moviedb_id")
    except Exception:
        return None


def search_imdb(query: str, limit: int = 10) -> List[MediaItem]:
    """Fast, accurate search using IMDb's suggestion API."""
    cleaned = query.strip()
    if not cleaned:
        return []
    
    first_char = cleaned[0].lower()
    encoded = urllib.parse.quote(cleaned.lower())
    url = f"https://v3.sg.media-imdb.com/suggestion/x/{encoded}.json"

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            items: List[MediaItem] = []
            for d in data.get("d", []):
                media_id = d.get("id")
                if not media_id or not media_id.startswith("tt"):
                    continue
                q_type = d.get("q", "").lower()
                if "series" in q_type or "tv" in q_type:
                    m_type = "series"
                elif q_type in ("feature", "movie", "tvmovie", "video"):
                    m_type = "movie"
                else:
                    m_type = "movie" if not any(x in q_type for x in ("series", "show", "mini")) else "series"

                poster_info = d.get("i", {})
                poster_url = poster_info.get("imageUrl") if isinstance(poster_info, dict) else None

                stars = d.get("s", "")
                cast_list = [s.strip() for s in stars.split(",") if s.strip()] if stars else []

                item = MediaItem(
                    title=d.get("l", cleaned),
                    id=media_id,
                    media_type=m_type,
                    year=d.get("y"),
                    poster=poster_url,
                    cast=cast_list
                )
                items.append(item)
                if len(items) >= limit:
                    break
            return items
    except Exception as e:
        logger.warning(f"IMDb suggestion search failed: {e}")
        return []


def search_tvmaze(query: str, limit: int = 5) -> List[MediaItem]:
    """Search TV shows using TVMaze API for detailed episode/season counts."""
    encoded = urllib.parse.quote(query.strip())
    url = f"https://api.tvmaze.com/search/shows?q={encoded}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            items: List[MediaItem] = []
            for entry in data:
                show = entry.get("show", {})
                externals = show.get("externals", {})
                imdb_id = externals.get("imdb")
                show_id = imdb_id or f"tvmaze_{show.get('id')}"
                
                premiered = show.get("premiered", "")
                year = int(premiered.split("-")[0]) if premiered and "-" in premiered else None
                image = show.get("image", {})
                poster = image.get("medium") or image.get("original") if isinstance(image, dict) else None

                import re
                summary_raw = show.get("summary") or ""
                summary = re.sub(r"<[^>]+>", "", summary_raw).strip() if summary_raw else None

                items.append(MediaItem(
                    title=show.get("name", query),
                    id=show_id,
                    media_type="series",
                    year=year,
                    poster=poster,
                    overview=summary,
                    extra_sources={"tvmaze_id": show.get("id")}
                ))
                if len(items) >= limit:
                    break
            return items
    except Exception as e:
        logger.warning(f"TVMaze search failed: {e}")
        return []


def search_media(query: str, media_type: str = "all", limit: int = 10) -> List[MediaItem]:
    """Searches across available sources with fallback."""
    results = search_imdb(query, limit=limit)
    
    if media_type == "series" or not results:
        tv_results = search_tvmaze(query, limit=limit)
        existing_ids = {r.id for r in results}
        for tv in tv_results:
            if tv.id not in existing_ids:
                results.append(tv)

    if media_type in ("movie", "series"):
        results = [r for r in results if r.media_type == media_type]

    return results[:limit]
