"""
RTSP Camera Source compliant with Sentinel Camera Grid guidelines.
"""
import os
import time
import logging
from typing import Optional

# CRITICAL: Force TCP transport before cv2 is imported to prevent UDP packet drops and corrupt frames.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
import cv2
import numpy as np

from sources.base_camera_source import BaseCameraSource

logger = logging.getLogger(__name__)

class RTSPCameraSource(BaseCameraSource):
    def __init__(self, camera_id: int, rtsp_url: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.cap = None
        self._frame_index = 0
        self._pts_ms = 0.0

    def connect(self) -> None:
        """Connect to the live RTSP stream using FFmpeg backend."""
        logger.info(f"[{self.camera_id}] Connecting to RTSP stream: {self.rtsp_url}")
        # Use CAP_FFMPEG explicitly
        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to connect to RTSP stream: {self.rtsp_url}")
        
    def _reconnect(self):
        """Reconnect to the stream with exponential backoff as per Sentinel guidelines."""
        logger.warning(f"[{self.camera_id}] Stream disconnected. Attempting to reconnect...")
        backoff = 2.0
        max_backoff = 30.0
        
        while True:
            self.release()
            time.sleep(backoff)
            logger.info(f"[{self.camera_id}] Reconnecting after {backoff}s backoff...")
            
            try:
                self.connect()
                logger.info(f"[{self.camera_id}] Reconnected successfully.")
                break
            except RuntimeError:
                backoff = min(max_backoff, backoff * 2.0)

    def read_frame(self) -> Optional[np.ndarray]:
        """Fetch the next live frame, handling disconnects automatically."""
        if not self.cap:
            return None
            
        ret, frame = self.cap.read()
        
        if not ret:
            # Reconnect on drop, as feeds are supervised and may restart
            self._reconnect()
            # Try reading again after successful reconnect
            if self.cap:
                ret, frame = self.cap.read()
            if not ret:
                return None
                
        self._frame_index += 1
        # CRITICAL: Use buffer PTS for accurate time, not wall-clock or fixed FPS
        self._pts_ms = self.cap.get(cv2.CAP_PROP_POS_MSEC)
        
        return frame

    def get_metadata(self) -> dict:
        """
        Return metadata for the current frame.
        Timestamp uses the stream's PTS (Presentation Timestamp) as required by Sentinel.
        """
        return {
            "camera_id": self.camera_id,
            "timestamp": self._pts_ms / 1000.0, # Convert ms to seconds if pipeline expects seconds
            "frame_index": self._frame_index,
            "source_type": "rtsp",
            "pts_ms": self._pts_ms
        }

    def release(self) -> None:
        """Close the stream connection."""
        if self.cap:
            self.cap.release()
            self.cap = None
