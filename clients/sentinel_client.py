"""
Client for the Sentinel Camera Grid API.
Fetches available cameras and their RTSP stream URLs.
"""
import requests
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SentinelClient:
    def __init__(self, host_url: str):
        """
        Initialize the client with the base host URL.
        Example: http://sentinel.example.com
        """
        # Ensure we don't end with a slash
        self.host_url = host_url.rstrip("/")

    def get_cameras(self) -> List[Dict[str, Any]]:
        """
        Fetches the catalogue of available cameras.
        Returns a list of dictionaries containing camera metadata.
        """
        url = f"{self.host_url}/api/ingest"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # The guide says "It returns every camera with its id, location, codec, live status..."
            data = response.json()
            
            # Unwrap {"cameras": [...]} if the API wrapped the list in a dictionary
            if isinstance(data, dict) and "cameras" in data:
                return data["cameras"]
            elif isinstance(data, list):
                return data
            else:
                logger.error(f"Unexpected JSON format returned from {url}")
                return []
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch camera catalogue from {url}: {e}")
            return []

    def get_camera_by_id(self, camera_id: str) -> Dict[str, Any] | None:
        """
        Helper method to find a specific camera by ID from the catalogue.
        """
        cameras = self.get_cameras()
        # Handle both list responses and dicts with a 'cameras' key depending on API structure
        if isinstance(cameras, dict) and "cameras" in cameras:
            camera_list = cameras["cameras"]
        elif isinstance(cameras, list):
            camera_list = cameras
        else:
            logger.error("Unexpected format returned from /api/ingest")
            return None

        for cam in camera_list:
            if str(cam.get("id")) == str(camera_id):
                return cam
        return None
