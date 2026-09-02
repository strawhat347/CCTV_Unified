"""
Client for the Sentinel Camera Grid API.
Fetches available cameras and their RTSP stream URLs.
"""
import requests
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SentinelClient:
    def __init__(self, host_url: str, api_key: str = None):
        """
        Initialize the client with the base host URL and optional API key.
        Example: http://sentinel.example.com
        """
        # Ensure we don't end with a slash
        self.host_url = host_url.rstrip("/")
        self.api_key = api_key

    def get_cameras(self) -> List[Dict[str, Any]]:
        """
        Fetches the catalogue of available cameras.
        Returns a list of dictionaries containing camera metadata.
        """
        try:
            session = requests.Session()
            login_url = f"{self.host_url}/auth/login"
            session.post(login_url, data={'username': 'admin', 'password': self.api_key})
            
            cameras_url = f"{self.host_url}/cameras.json"
            response = session.get(cameras_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if isinstance(data, dict) and "cameras" in data:
                data = data["cameras"]
                
            formatted_cameras = []
            for cam in data:
                raw_id = cam.get("id", "")
                num_id = int(raw_id.replace("cam", "")) if raw_id.startswith("cam") else int(raw_id)
                formatted_cameras.append({
                    "id": num_id,
                    "location": cam.get("name", ""),
                    "rtsp_url": f"rtsp://103.250.160.189:8554/stream/{raw_id}",
                    "url": f"{self.host_url}/{raw_id}/index.m3u8"
                })
            return formatted_cameras
            
        except Exception as e:
            logger.error(f"Failed to fetch camera catalogue: {e}")
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
