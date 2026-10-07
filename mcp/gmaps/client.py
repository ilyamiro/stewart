import sys
import json
import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple
import urllib.parse
import urllib.request

logger = logging.getLogger("maps_client")

USER_AGENT = "Antigravity-Life-Assistant/1.0 (contact: ilyamiro.work@gmail.com; open-source mapping)"

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
OSRM_BASE = "http://router.project-osrm.org"
TRANSITOUS_BASE = "https://api.transitous.org/api/v5"
BROUTER_BASE = "http://brouter.de/brouter"


def format_duration(seconds: float) -> str:
    """Format seconds into readable string (e.g. '15 mins', '1 hour 20 mins')."""
    total_mins = int(round(seconds / 60.0))
    if total_mins < 1:
        return "< 1 min"
    if total_mins < 60:
        return f"{total_mins} mins"
    hours = total_mins // 60
    rem_mins = total_mins % 60
    if rem_mins == 0:
        return f"{hours} hour{'s' if hours > 1 else ''}"
    return f"{hours} hour{'s' if hours > 1 else ''} {rem_mins} mins"


def format_distance(meters: float) -> str:
    """Format meters into readable string (e.g. '350 m', '7.8 km')."""
    if meters < 1000:
        return f"{int(round(meters))} m"
    return f"{meters / 1000.0:.1f} km"


def parse_datetime_to_iso(val: Union[str, int, float, datetime, None]) -> Optional[str]:
    """Parse time value into UTC ISO-8601 string for transit APIs."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(val, str):
        v_clean = val.strip().lower()
        if v_clean in ("now", "current"):
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            ts = float(v_clean)
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
            "%H:%M:%S",
            "%H:%M"
        ):
            try:
                dt = datetime.strptime(val.strip(), fmt)
                if fmt in ("%H:%M:%S", "%H:%M"):
                    today = datetime.now()
                    dt = dt.replace(year=today.year, month=today.month, day=today.day)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(val)


class OpenMapsClient:
    """
    Open-Source Maps, Transit & Navigation Engine.
    - Geocoding & Places: OpenStreetMap (Nominatim)
    - Public Transit & Bus Schedules: Transitous (MOTIS 2)
    - Driving / Cycling / Walking Routing: OSRM & BRouter
    - Zero API keys or billing accounts required.
    """

    def check_auth(self) -> Dict[str, Any]:
        """Verify that the open-source map and transit backends are reachable."""
        try:
            test_res = self.geocode("Aarhus, Denmark")
            if test_res.get("status") == "OK":
                return {
                    "authenticated": True,
                    "status": "ready",
                    "open_source": True,
                    "api_key_required": False,
                    "providers": {
                        "geocoding_and_places": "OpenStreetMap (Nominatim)",
                        "transit_and_bus_schedules": "Transitous (MOTIS 2)",
                        "driving_and_routing": "OSRM & BRouter"
                    },
                    "message": "All open-source mapping & transit services are active and ready. No API key needed."
                }
            return {
                "authenticated": False,
                "status": "error",
                "error": "Failed to connect to OpenStreetMap Nominatim"
            }
        except Exception as e:
            return {
                "authenticated": False,
                "status": "error",
                "error": str(e)
            }

    def _http_get(self, url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Dict[str, Any]:
        """Helper to send HTTP GET requests with custom User-Agent."""
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            full_url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
        else:
            full_url = url

        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content)

    def resolve_location(self, loc: str) -> Optional[Tuple[float, float, str]]:
        """
        Resolves an address or coordinate string into (lat, lon, formatted_name).
        Accepts 'lat,lon' or human-readable address with smart alias fallbacks.
        """
        loc = loc.strip()
        m = re.match(r"^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$", loc)
        if m:
            parts = loc.split(",")
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return (lat, lon, f"{lat:.4f}, {lon:.4f}")

        geo = self.geocode(loc)
        if geo.get("status") == "OK" and geo.get("results"):
            top = geo["results"][0]
            lat = float(top["latitude"])
            lon = float(top["longitude"])
            return (lat, lon, top["formatted_address"])

        aliases = [
            (r"(?i)\bbaneg(aa|\u00e5)rd\b", "station"),
            (r"(?i)\bcentral station\b", "station"),
            (r"(?i)\btrain station\b", "station"),
            (r"(?i)\brailway station\b", "station"),
        ]
        for pattern, replacement in aliases:
            alt_loc = re.sub(pattern, replacement, loc).strip()
            if alt_loc != loc:
                geo_alt = self.geocode(alt_loc)
                if geo_alt.get("status") == "OK" and geo_alt.get("results"):
                    top = geo_alt["results"][0]
                    return (float(top["latitude"]), float(top["longitude"]), top["formatted_address"])

        return None

    def geocode(self, address: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Convert address or place name to coordinates using OpenStreetMap Nominatim."""
        params = {
            "q": address,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 5
        }
        if language:
            params["accept-language"] = language

        try:
            data = self._http_get(f"{NOMINATIM_BASE}/search", params)
            results = []
            for item in data:
                results.append({
                    "name": item.get("name") or item.get("display_name", "").split(",")[0],
                    "formatted_address": item.get("display_name"),
                    "latitude": float(item.get("lat")),
                    "longitude": float(item.get("lon")),
                    "category": item.get("category"),
                    "type": item.get("type"),
                    "osm_id": item.get("osm_id"),
                    "osm_type": item.get("osm_type"),
                    "address_details": item.get("address", {})
                })

            return {
                "status": "OK",
                "query": address,
                "provider": "OpenStreetMap Nominatim",
                "count": len(results),
                "results": results
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Geocoding failed: {str(e)}"}

    def reverse_geocode(self, latitude: float, longitude: float, language: Optional[str] = None) -> Dict[str, Any]:
        """Convert latitude and longitude coordinates into a human-readable street address."""
        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1
        }
        if language:
            params["accept-language"] = language

        try:
            item = self._http_get(f"{NOMINATIM_BASE}/reverse", params)
            if "error" in item:
                return {"status": "ZERO_RESULTS", "error": item["error"]}

            return {
                "status": "OK",
                "coordinates": {"latitude": latitude, "longitude": longitude},
                "formatted_address": item.get("display_name"),
                "name": item.get("name"),
                "category": item.get("category"),
                "type": item.get("type"),
                "address_details": item.get("address", {})
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Reverse geocoding failed: {str(e)}"}

    def search_places(
        self,
        query: str,
        location: Optional[str] = None,
        radius: Optional[int] = None,
        place_type: Optional[str] = None,
        open_now: bool = False,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for places, transit stops, bus stations, restaurants, or businesses using OpenStreetMap.
        """
        full_query = query
        if location:
            full_query = f"{query}, {location}"

        params: Dict[str, Any] = {
            "q": full_query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 10
        }
        if language:
            params["accept-language"] = language

        try:
            data = self._http_get(f"{NOMINATIM_BASE}/search", params)
            results = []
            for item in data:
                results.append({
                    "name": item.get("name") or item.get("display_name", "").split(",")[0],
                    "formatted_address": item.get("display_name"),
                    "latitude": float(item.get("lat")),
                    "longitude": float(item.get("lon")),
                    "category": item.get("category"),
                    "type": item.get("type"),
                    "osm_id": item.get("osm_id"),
                    "osm_type": item.get("osm_type"),
                    "osm_url": f"https://www.openstreetmap.org/{item.get('osm_type')}/{item.get('osm_id')}"
                })

            return {
                "status": "OK",
                "query": query,
                "location_bias": location,
                "count": len(results),
                "results": results
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Place search failed: {str(e)}"}

    def get_place_details(self, place_id: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Get details for an OpenStreetMap feature using its OSM ID or lookup query.
        """
        osm_id = str(place_id).strip()
        params = {"osm_ids": osm_id, "format": "jsonv2", "addressdetails": 1, "extratags": 1}
        if language:
            params["accept-language"] = language

        try:
            data = self._http_get(f"{NOMINATIM_BASE}/lookup", params)
            if not data:
                return self.geocode(place_id, language=language)

            item = data[0]
            extra = item.get("extratags", {})
            return {
                "status": "OK",
                "name": item.get("name") or item.get("display_name", "").split(",")[0],
                "formatted_address": item.get("display_name"),
                "latitude": float(item.get("lat")),
                "longitude": float(item.get("lon")),
                "category": item.get("category"),
                "type": item.get("type"),
                "opening_hours": extra.get("opening_hours"),
                "phone": extra.get("phone") or extra.get("contact:phone"),
                "website": extra.get("website") or extra.get("contact:website"),
                "wheelchair": extra.get("wheelchair"),
                "osm_url": f"https://www.openstreetmap.org/{item.get('osm_type')}/{item.get('osm_id')}"
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Place details failed: {str(e)}"}

    def get_bus_schedule(
        self,
        origin: str,
        destination: str,
        departure_time: Optional[Union[str, int, datetime]] = None,
        arrival_time: Optional[Union[str, int, datetime]] = None,
        bus_line: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Public transit & bus schedules powered by Transitous (MOTIS 2).
        Provides real-time bus numbers, departure/arrival times, stops, transfers, and walking legs.
        """
        from_loc = self.resolve_location(origin)
        to_loc = self.resolve_location(destination)

        if not from_loc:
            return {"status": "NOT_FOUND", "error": f"Could not find origin location: '{origin}'"}
        if not to_loc:
            return {"status": "NOT_FOUND", "error": f"Could not find destination location: '{destination}'"}

        from_lat, from_lon, from_name = from_loc
        to_lat, to_lon, to_name = to_loc

        params: Dict[str, Any] = {
            "fromPlace": f"{from_lat},{from_lon}",
            "toPlace": f"{to_lat},{to_lon}"
        }

        if arrival_time:
            iso_t = parse_datetime_to_iso(arrival_time)
            if iso_t:
                params["time"] = iso_t
                params["arriveBy"] = "true"
        elif departure_time:
            iso_t = parse_datetime_to_iso(departure_time)
            if iso_t:
                params["time"] = iso_t
        else:
            params["time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            data = self._http_get(f"{TRANSITOUS_BASE}/plan", params)
            itineraries = []

            for itin in data.get("itineraries", []):
                legs = itin.get("legs", [])
                bus_segments = []
                lines_used = []
                walking_duration_secs = 0

                for l in legs:
                    mode = (l.get("mode") or "").upper()
                    if mode in ("BUS", "TRAM", "RAIL", "SUBWAY"):
                        line_code = l.get("routeShortName") or l.get("routeLongName") or mode
                        lines_used.append(line_code)
                        bus_segments.append({
                            "line": line_code,
                            "type": mode,
                            "headsign": l.get("headsign"),
                            "board_at": l.get("from", {}).get("name"),
                            "departure_time": l.get("from", {}).get("departure") or l.get("startTime"),
                            "alight_at": l.get("to", {}).get("name"),
                            "arrival_time": l.get("to", {}).get("arrival") or l.get("endTime"),
                            "duration": format_duration(l.get("duration", 0)),
                            "distance": format_distance(l.get("distance", 0))
                        })
                    elif mode == "WALK":
                        walking_duration_secs += l.get("duration", 0)

                if bus_line:
                    needle = bus_line.strip().lower()
                    if not any(needle in (code or "").lower() for code in lines_used):
                        continue

                duration_secs = itin.get("duration", 0)
                itineraries.append({
                    "departure_time": itin.get("startTime"),
                    "arrival_time": itin.get("endTime"),
                    "total_duration": format_duration(duration_secs),
                    "total_duration_seconds": duration_secs,
                    "transfers": itin.get("transfers", 0),
                    "transit_lines": lines_used,
                    "walking_time": format_duration(walking_duration_secs),
                    "legs_count": len(legs),
                    "bus_segments": bus_segments
                })

            return {
                "status": "OK",
                "provider": "Transitous (Open MOTIS 2)",
                "origin": from_name,
                "destination": to_name,
                "bus_line_filter": bus_line,
                "itineraries_count": len(itineraries),
                "itineraries": itineraries
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Transit schedule query failed: {str(e)}"}

    def get_directions(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
        departure_time: Optional[Union[str, int, datetime]] = None,
        arrival_time: Optional[Union[str, int, datetime]] = None,
        alternatives: bool = False,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Turn-by-turn route navigation and travel times.
        Supports driving, transit (bus/train), walking, and bicycling.
        """
        if mode == "transit":
            return self.get_bus_schedule(
                origin=origin,
                destination=destination,
                departure_time=departure_time,
                arrival_time=arrival_time
            )

        from_loc = self.resolve_location(origin)
        to_loc = self.resolve_location(destination)

        if not from_loc:
            return {"status": "NOT_FOUND", "error": f"Could not find origin location: '{origin}'"}
        if not to_loc:
            return {"status": "NOT_FOUND", "error": f"Could not find destination location: '{destination}'"}

        from_lat, from_lon, from_name = from_loc
        to_lat, to_lon, to_name = to_loc

        if mode in ("bicycling", "bike"):
            try:
                brouter_url = f"{BROUTER_BASE}?lonlats={from_lon},{from_lat}|{to_lon},{to_lat}&profile=trekking&format=geojson"
                req = urllib.request.Request(brouter_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    geo = json.loads(resp.read().decode("utf-8"))
                    props = geo["features"][0]["properties"]
                    dist = float(props.get("track-length", 0))
                    dur = float(props.get("total-time", 0))
                    return {
                        "status": "OK",
                        "provider": "BRouter (Open Source Cycling)",
                        "origin": from_name,
                        "destination": to_name,
                        "travel_mode": "bicycling",
                        "distance": format_distance(dist),
                        "distance_meters": dist,
                        "duration": format_duration(dur),
                        "duration_seconds": dur,
                        "instructions_summary": "Bicycle trekking route computed via BRouter."
                    }
            except Exception as e:
                logger.warning(f"BRouter fallback to OSRM: {e}")

        osrm_profile = "driving"
        coords = f"{from_lon},{from_lat};{to_lon},{to_lat}"
        url = f"{OSRM_BASE}/route/v1/{osrm_profile}/{coords}?overview=full&steps=true"

        try:
            data = self._http_get(url)
            if data.get("code") != "Ok" or not data.get("routes"):
                return {
                    "status": "ERROR",
                    "error": data.get("message", "Route calculation failed")
                }

            route = data["routes"][0]
            dist_m = route.get("distance", 0)
            dur_s = route.get("duration", 0)

            if mode == "walking":
                dur_s = dist_m / 1.33

            steps_out = []
            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    man = step.get("maneuver", {})
                    man_type = man.get("type", "")
                    modifier = man.get("modifier", "")
                    street = step.get("name") or "unnamed road"
                    instr = f"{man_type} {modifier} on {street}".strip()
                    steps_out.append({
                        "instruction": instr,
                        "distance": format_distance(step.get("distance", 0)),
                        "duration": format_duration(step.get("duration", 0))
                    })

            return {
                "status": "OK",
                "provider": "OSRM (Open Source Routing Machine)",
                "origin": from_name,
                "destination": to_name,
                "travel_mode": mode,
                "distance": format_distance(dist_m),
                "distance_meters": dist_m,
                "duration": format_duration(dur_s),
                "duration_seconds": dur_s,
                "steps_count": len(steps_out),
                "steps": steps_out
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Directions calculation failed: {str(e)}"}

    def get_distance_matrix(
        self,
        origins: Union[str, List[str]],
        destinations: Union[str, List[str]],
        mode: str = "driving",
        departure_time: Optional[Union[str, int, datetime]] = None
    ) -> Dict[str, Any]:
        """
        Calculate travel times and distances.
        If mode == 'all', compares driving, public transit (bus), cycling, and walking side-by-side!
        """
        orig_str = origins if isinstance(origins, str) else origins[0]
        dest_str = destinations if isinstance(destinations, str) else destinations[0]

        if mode == "all":
            modes_to_test = ["driving", "transit", "bicycling", "walking"]
            comparison: Dict[str, Any] = {
                "origin": orig_str,
                "destination": dest_str,
                "modes": {}
            }
            for m in modes_to_test:
                if m == "transit":
                    t_res = self.get_bus_schedule(orig_str, dest_str, departure_time=departure_time)
                    if t_res.get("status") == "OK" and t_res.get("itineraries"):
                        best = t_res["itineraries"][0]
                        comparison["modes"][m] = {
                            "duration": best.get("total_duration"),
                            "bus_lines": best.get("transit_lines"),
                            "transfers": best.get("transfers"),
                            "status": "OK"
                        }
                    else:
                        comparison["modes"][m] = {"status": "NOT_AVAILABLE"}
                else:
                    d_res = self.get_directions(orig_str, dest_str, mode=m)
                    if d_res.get("status") == "OK":
                        comparison["modes"][m] = {
                            "distance": d_res.get("distance"),
                            "duration": d_res.get("duration"),
                            "status": "OK"
                        }
                    else:
                        comparison["modes"][m] = {"status": "ERROR"}

            return {"status": "OK", "mode_comparison": comparison}

        if mode == "transit":
            return self.get_bus_schedule(orig_str, dest_str, departure_time=departure_time)
        return self.get_directions(orig_str, dest_str, mode=mode)

    def get_static_map(
        self,
        center: Optional[str] = None,
        zoom: int = 14,
        size: str = "600x400"
    ) -> Dict[str, Any]:
        """Generate an OpenStreetMap link or embeddable map view."""
        lat, lon = 56.1629, 10.2039
        if center:
            loc = self.resolve_location(center)
            if loc:
                lat, lon, _ = loc

        osm_url = f"https://www.openstreetmap.org/#map={zoom}/{lat:.4f}/{lon:.4f}"
        embed_url = f"https://www.openstreetmap.org/export/embed.html?bbox={lon-0.03:.4f}%2C{lat-0.02:.4f}%2C{lon+0.03:.4f}%2C{lat+0.02:.4f}&layer=mapnik&marker={lat:.4f}%2C{lon:.4f}"

        return {
            "status": "OK",
            "provider": "OpenStreetMap",
            "map_url": osm_url,
            "embed_url": embed_url,
            "center": {"latitude": lat, "longitude": lon}
        }


_client: Optional[OpenMapsClient] = None


def get_maps_client() -> OpenMapsClient:
    global _client
    if _client is None:
        _client = OpenMapsClient()
    return _client
