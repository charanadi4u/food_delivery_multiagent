import os
import httpx
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

headers = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
}

body = {
    "origin": {"address": "MG Road, Bengaluru"},
    "destination": {"address": "Indiranagar, Bengaluru"},
    "travelMode": "DRIVE",
    "routingPreference": "TRAFFIC_AWARE",
}

resp = httpx.post(ROUTES_URL, headers=headers, json=body, timeout=15.0)
print(resp.status_code)
print(resp.json())
