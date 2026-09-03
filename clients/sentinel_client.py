"""
Client for the Sentinel Camera Grid API.
Fetches available cameras and their RTSP stream URLs.
"""
import requests
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SentinelClient:
    def __init__(self, host_url: str, api_key: str = None, email: str = None):
        """
        Initialize the client with the base host URL, optional API key, and email.
        Example: https://cctv.corp8.cloud
        """
        self.host_url = host_url.rstrip("/")
        self.api_key = api_key
        self.email = email

    def get_cameras(self) -> List[Dict[str, Any]]:
        """
        Fetches the catalogue of available cameras from the Sentinel Grid.
        Logs in using email + access password, then pulls the camera directory.
        """
        from urllib.parse import quote
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            login_url = f"{self.host_url}/auth/login"
            
            # Form payload matching Sentinel portal
            login_payload = {"password": self.api_key}
            if self.email:
                login_payload["email"] = self.email
                
            login_res = session.post(login_url, data=login_payload, timeout=10)
            if login_res.status_code not in (200, 302):
                session.post(login_url, json=login_payload, timeout=10)
            
            # Fetch cameras catalogue
            cameras_url = f"{self.host_url}/cameras.json"
            response = session.get(cameras_url, timeout=10)
            
            # Fallback to /api/cameras if cameras.json is not found
            if response.status_code == 404:
                response = session.get(f"{self.host_url}/api/cameras", timeout=10)
                
            response.raise_for_status()
            
            data = response.json()
            if isinstance(data, dict) and "cameras" in data:
                data = data["cameras"]
                
            formatted_cameras = []
            for cam in data:
                raw_id = cam.get("id", "")
                num_id = int(str(raw_id).replace("cam", "")) if str(raw_id).startswith("cam") else int(raw_id or 0)
                
                # Format authenticated RTSP stream URL according to Sentinel Integrator's Guide
                encoded_email = quote(self.email or "")
                rtsp_url = f"rtsp://{encoded_email}:{self.api_key}@103.250.160.189:8554/stream/{raw_id}"
                hls_url = f"{self.host_url}/{raw_id}/index.m3u8"
                
                formatted_cameras.append({
                    "id": num_id,
                    "location": cam.get("name") or cam.get("location", f"Sentinel Cam {raw_id}"),
                    "rtsp_url": rtsp_url,
                    "url": hls_url
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
