import sys
import json
import logging
from typing import Dict, Any, List

from gmaps.client import get_maps_client

logger = logging.getLogger("maps_mcp")

maps_client = get_maps_client()

TOOLS = [
    {
        "name": "maps_check_auth",
        "description": "Checks open-source maps and transit status (OpenStreetMap, Transitous MOTIS, OSRM). No API key required.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "maps_get_directions",
        "description": "Gets route navigation, travel time, and step-by-step directions between origin and destination for driving, transit (bus/train), walking, or bicycling via open-source routing (OSRM/BRouter/Transitous).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Starting address, city, landmark, or 'lat,lon'"},
                "destination": {"type": "string", "description": "Destination address, landmark, or 'lat,lon'"},
                "mode": {
                    "type": "string",
                    "enum": ["driving", "transit", "walking", "bicycling"],
                    "default": "driving",
                    "description": "Travel mode"
                },
                "departure_time": {"type": "string", "description": "Departure time (ISO string, e.g. '2026-10-06 08:30' or 'now')"},
                "arrival_time": {"type": "string", "description": "Target arrival time"},
                "language": {"type": "string", "description": "Language code (e.g. 'en', 'da', 'ru')"}
            },
            "required": ["origin", "destination"]
        }
    },
    {
        "name": "maps_get_bus_schedule",
        "description": "Queries public transit bus schedules, departures, line numbers (e.g. Bus 3A, 114), stops, total travel time, and transfer points via Transitous open transit engine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Starting address, bus stop, or location"},
                "destination": {"type": "string", "description": "Destination address, school, or location"},
                "departure_time": {"type": "string", "default": "now", "description": "Departure time (e.g. 'now', '2026-10-06 08:00', or timestamp)"},
                "arrival_time": {"type": "string", "description": "Desired arrival time"},
                "bus_line": {"type": "string", "description": "Optional filter for a specific bus line (e.g. '3A', '114')"}
            },
            "required": ["origin", "destination"]
        }
    },
    {
        "name": "maps_get_distance_matrix",
        "description": "Calculates travel times and distances. Use mode='all' to compare driving, bus/transit, bicycling, and walking commute times side-by-side.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "origins": {
                    "type": "string",
                    "description": "Origin address or coordinates"
                },
                "destinations": {
                    "type": "string",
                    "description": "Destination address or coordinates"
                },
                "mode": {
                    "type": "string",
                    "enum": ["driving", "transit", "walking", "bicycling", "all"],
                    "default": "driving",
                    "description": "Travel mode or 'all' to compare all commute options"
                },
                "departure_time": {"type": "string", "description": "Departure time ('now' or timestamp)"}
            },
            "required": ["origins", "destinations"]
        }
    },
    {
        "name": "maps_search_places",
        "description": "Searches for places, transit stops, restaurants, shops, or amenities near a location via OpenStreetMap.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g. 'bus stop near Aarhus Gymnasium', 'pharmacy', 'bakery')"},
                "location": {"type": "string", "description": "Optional center location (e.g. 'Aarhus, Denmark')"},
                "language": {"type": "string", "description": "Language code"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "maps_get_place_details",
        "description": "Gets full details for an OpenStreetMap feature (opening hours, phone, address, website, OpenStreetMap URL).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "place_id": {"type": "string", "description": "OSM ID (e.g. 'N12345') or place search query"},
                "language": {"type": "string", "description": "Language code"}
            },
            "required": ["place_id"]
        }
    },
    {
        "name": "maps_geocode",
        "description": "Converts a street address or location name to latitude/longitude coordinates via OpenStreetMap Nominatim.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Address or location name to geocode"},
                "language": {"type": "string", "description": "Language code"}
            },
            "required": ["address"]
        }
    },
    {
        "name": "maps_reverse_geocode",
        "description": "Converts latitude and longitude coordinates into a human-readable street address via OpenStreetMap Nominatim.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Latitude coordinate"},
                "longitude": {"type": "number", "description": "Longitude coordinate"},
                "language": {"type": "string", "description": "Language code"}
            },
            "required": ["latitude", "longitude"]
        }
    },
    {
        "name": "maps_get_static_map",
        "description": "Generates an OpenStreetMap web link and embed map URL for a location or center coordinate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "center": {"type": "string", "description": "Center location/address or coordinates"},
                "zoom": {"type": "integer", "default": 14, "description": "Zoom level (0-19)"},
                "size": {"type": "string", "default": "600x400", "description": "Image dimensions widthxheight"}
            }
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    """Handle all Open-Source Maps MCP tool calls."""
    try:
        if name == "maps_check_auth":
            res = maps_client.check_auth()
            return json.dumps(res)

        elif name == "maps_get_directions":
            origin = args.get("origin")
            destination = args.get("destination")
            if not origin or not destination:
                return json.dumps({"error": "origin and destination are required"})

            res = maps_client.get_directions(
                origin=origin,
                destination=destination,
                mode=args.get("mode", "driving"),
                departure_time=args.get("departure_time"),
                arrival_time=args.get("arrival_time"),
                language=args.get("language")
            )
            return json.dumps(res)

        elif name == "maps_get_bus_schedule":
            origin = args.get("origin")
            destination = args.get("destination")
            if not origin or not destination:
                return json.dumps({"error": "origin and destination are required"})

            res = maps_client.get_bus_schedule(
                origin=origin,
                destination=destination,
                departure_time=args.get("departure_time", "now"),
                arrival_time=args.get("arrival_time"),
                bus_line=args.get("bus_line")
            )
            return json.dumps(res)

        elif name == "maps_get_distance_matrix":
            origins = args.get("origins")
            destinations = args.get("destinations")
            if not origins or not destinations:
                return json.dumps({"error": "origins and destinations are required"})

            res = maps_client.get_distance_matrix(
                origins=origins,
                destinations=destinations,
                mode=args.get("mode", "driving"),
                departure_time=args.get("departure_time")
            )
            return json.dumps(res)

        elif name == "maps_search_places":
            query = args.get("query")
            if not query:
                return json.dumps({"error": "query is required"})

            res = maps_client.search_places(
                query=query,
                location=args.get("location"),
                language=args.get("language")
            )
            return json.dumps(res)

        elif name == "maps_get_place_details":
            place_id = args.get("place_id")
            if not place_id:
                return json.dumps({"error": "place_id is required"})

            res = maps_client.get_place_details(
                place_id=place_id,
                language=args.get("language")
            )
            return json.dumps(res)

        elif name == "maps_geocode":
            address = args.get("address")
            if not address:
                return json.dumps({"error": "address is required"})

            res = maps_client.geocode(address, language=args.get("language"))
            return json.dumps(res)

        elif name == "maps_reverse_geocode":
            lat = args.get("latitude")
            lng = args.get("longitude")
            if lat is None or lng is None:
                return json.dumps({"error": "latitude and longitude are required"})

            res = maps_client.reverse_geocode(lat, lng, language=args.get("language"))
            return json.dumps(res)

        elif name == "maps_get_static_map":
            res = maps_client.get_static_map(
                center=args.get("center"),
                zoom=args.get("zoom", 14),
                size=args.get("size", "600x400")
            )
            return json.dumps(res)

        else:
            return json.dumps({"error": f"Unknown Maps tool: {name}"})

    except Exception as e:
        logger.exception(f"Error executing {name}: {e}")
        return json.dumps({"error": f"Failed to execute {name}: {str(e)}"})


def main():
    logging.info(f"Starting Open-Source Maps MCP Server with {len(TOOLS)} tools...")
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
                        "name": "maps-mcp",
                        "version": "2.0.0"
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
