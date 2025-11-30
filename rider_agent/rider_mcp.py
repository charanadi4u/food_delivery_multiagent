"""
rider_mcp.py

MCP server that wraps Google Routes API to compute
distance and ETA between origin and destination.
"""

import os
from typing import Dict, Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("maps")

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

http_client = httpx.AsyncClient(timeout=15.0)


def _parse_duration_to_seconds(duration: str) -> float:
    """
    Routes API duration is usually like "1234s" or "1234.5s".
    Convert to float seconds.
    """
    if not duration:
        return 0.0
    s = duration.strip()
    if s.endswith("s"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


@mcp.tool()
async def get_directions(origin: str, destination: str) -> Dict[str, Any]:
    """
    Get driving directions between two locations using Google Routes API.

    origin / destination can be full addresses or "lat,lng" pairs.

    Returns:
        {
          "status": "ok" | "error",
          "distance_km": float,
          "eta_minutes": float,
          "raw": <raw API response (optional)>
        }
    """
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        # We only need distanceMeters & duration in the response
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
    }

    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        # You can tweak preferences if you want:
        "routingPreference": "TRAFFIC_AWARE",
    }

    resp = await http_client.post(ROUTES_URL, json=body, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    routes = data.get("routes", [])
    if not routes:
        # Most likely API key / enablement / billing issue
        return {"status": "error", "raw": data}

    route = routes[0]
    distance_meters = route.get("distanceMeters")
    duration_str = route.get("duration")

    distance_km = None
    if distance_meters is not None:
        distance_km = round(float(distance_meters) / 1000.0, 2)

    duration_seconds = _parse_duration_to_seconds(duration_str)
    eta_minutes = round(duration_seconds / 60.0, 1) if duration_seconds else None

    return {
        "status": "ok",
        "distance_meters": distance_meters,
        "distance_km": distance_km,
        "duration_seconds": duration_seconds,
        "eta_minutes": eta_minutes,
        "raw": data,  # keep the raw for debugging; you can remove if you like
    }


async def _shutdown():
    await http_client.aclose()


if __name__ == "__main__":
    mcp.run(transport="stdio")
