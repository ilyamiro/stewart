from dataclasses import dataclass, field
from typing import List, Optional, Callable


@dataclass
class Provider:
    name: str
    base_url: str
    priority: int
    features: List[str] = field(default_factory=list)
    mirrors: List[str] = field(default_factory=list)
    supports_direct_player: bool = True
    movie_player_template: Optional[str] = None
    tv_player_template: Optional[str] = None
    search_template: Optional[str] = None

    tv_requires_tmdb: bool = False

    def get_movie_url(self, media_id: str, tmdb_id: Optional[int] = None) -> Optional[str]:
        if self.movie_player_template:
            actual_id = str(tmdb_id) if (tmdb_id and "tmdb" in self.movie_player_template) else media_id
            return self.movie_player_template.format(id=actual_id, base=self.base_url)
        return None

    def get_tv_url(self, media_id: str, season: int = 1, episode: int = 1, tmdb_id: Optional[int] = None) -> Optional[str]:
        if self.tv_player_template:
            actual_id = str(tmdb_id) if (tmdb_id and (self.tv_requires_tmdb or "tmdb" in self.tv_player_template)) else media_id
            if self.tv_requires_tmdb and not tmdb_id and media_id.startswith("tt"):
                return None
            return self.tv_player_template.format(
                id=actual_id,
                season=season,
                episode=episode,
                base=self.base_url
            )
        return None

    def get_search_url(self, query: str) -> Optional[str]:
        if self.search_template:
            import urllib.parse
            encoded = urllib.parse.quote(query)
            return self.search_template.format(query=encoded, base=self.base_url)
        return None


STREAMING_PROVIDERS: List[Provider] = [
    Provider(
        name="VidLink",
        base_url="https://vidlink.pro",
        priority=1,
        features=["Universal Player", "Auto-Next", "Clean Interface", "Subtitles"],
        supports_direct_player=True,
        tv_requires_tmdb=True,
        movie_player_template="{base}/movie/{id}",
        tv_player_template="{base}/tv/{id}/{season}/{episode}",
        search_template=None
    ),
    Provider(
        name="Flixer",
        base_url="https://flixer.su",
        priority=2,
        mirrors=["https://flixer.gd", "https://hexa.su"],
        features=["FMHY Starred", "Aggregator", "Auto-Next", "Multi-Server"],
        supports_direct_player=True,
        movie_player_template="{base}/watch/movie/{id}",
        tv_player_template="{base}/watch/tv/{id}/{season}/{episode}",
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="Cinecat",
        base_url="https://cinecat.eu",
        priority=3,
        features=["FMHY Starred", "P-Stream", "4K", "Auto-Next", "Open Source"],
        supports_direct_player=True,
        movie_player_template="{base}/media/tmdb-movie-{id}",
        tv_player_template="{base}/media/tmdb-show-{id}/{season}/{episode}",
        search_template="{base}/browse/{query}"
    ),
    Provider(
        name="HydraHD",
        base_url="https://hydrahd.ws",
        priority=4,
        mirrors=["https://hydrahd.com"],
        features=["FMHY Multi-Server", "Auto-Next", "Fast HD"],
        supports_direct_player=True,
        movie_player_template="{base}/watch?v={id}",
        tv_player_template="{base}/watch?v={id}&season={season}&episode={episode}",
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="MultiEmbed",
        base_url="https://multiembed.mov",
        priority=5,
        features=["Multi-Server Embed", "Direct Player", "Wide Source Coverage"],
        supports_direct_player=True,
        movie_player_template="{base}/?video_id={id}",
        tv_player_template="{base}/?video_id={id}&s={season}&e={episode}",
        search_template=None
    ),
    Provider(
        name="Rive",
        base_url="https://www.rivestream.app",
        priority=6,
        mirrors=["https://rivestream.ru", "https://rivestream.win"],
        features=["FMHY Starred", "4K", "Auto-Next", "Custom Player"],
        supports_direct_player=True,
        movie_player_template="{base}/watch?type=movie&id={id}",
        tv_player_template="{base}/watch?type=tv&id={id}&season={season}&episode={episode}",
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="Movy",
        base_url="https://www.movy.sx",
        priority=7,
        features=["FMHY #1 Aggregator", "4K", "Auto-Next", "Premium UI"],
        supports_direct_player=False,
        movie_player_template=None,
        tv_player_template=None,
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="Cinejoy",
        base_url="https://cinejoy.pk",
        priority=8,
        features=["FMHY Starred Aggregator", "Auto-Next", "No Ads"],
        supports_direct_player=False,
        movie_player_template=None,
        tv_player_template=None,
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="Atlantic",
        base_url="https://atlantic.st",
        priority=9,
        features=["FMHY Starred", "4K", "Auto-Next"],
        supports_direct_player=False,
        movie_player_template=None,
        tv_player_template=None,
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="7Movies",
        base_url="https://7movies.ac",
        priority=10,
        features=["FMHY Starred", "Fast Streams"],
        supports_direct_player=False,
        movie_player_template=None,
        tv_player_template=None,
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="Stellar",
        base_url="https://stellar.gdn",
        priority=11,
        features=["FMHY Starred", "4K", "Auto-Next"],
        supports_direct_player=False,
        movie_player_template=None,
        tv_player_template=None,
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="67Movies",
        base_url="https://67movies.st",
        priority=12,
        features=["Aggregator", "Auto-Next"],
        supports_direct_player=False,
        movie_player_template=None,
        tv_player_template=None,
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="PressPlay",
        base_url="https://pressplayx.to",
        priority=13,
        features=["Dedicated Server", "No Buffering"],
        supports_direct_player=False,
        movie_player_template=None,
        tv_player_template=None,
        search_template="{base}/search?q={query}"
    ),
    Provider(
        name="1Shows",
        base_url="https://www.1shows.org",
        priority=14,
        mirrors=["http://1shows.bz"],
        features=["FMHY Multi-Server", "4K", "Auto-Next"],
        supports_direct_player=True,
        movie_player_template="{base}/movie/{id}",
        tv_player_template="{base}/series/{id}/{season}/{episode}",
        search_template="{base}/search?q={query}"
    )
]
