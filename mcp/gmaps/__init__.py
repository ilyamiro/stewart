"""Open-source Maps & Transit integration for Life Assistant."""
from gmaps.client import OpenMapsClient, get_maps_client

GoogleMapsClient = OpenMapsClient

__all__ = ["OpenMapsClient", "GoogleMapsClient", "get_maps_client"]
