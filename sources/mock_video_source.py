"""
sources/mock_video_source.py — Mock camera source, reads frames from a
local .mp4 file instead of a live RTSP/HTTP stream.

Implements BaseCameraSource (sources/base_camera_source.py) so the rest
of the pipeline is written against the ABC and never knows or cares
whether frames come from a real camera or a recorded mock video.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from sources.base_camera_source import BaseCameraSource


class MockVideoSource(BaseCameraSource):
    """
    Feeds frames from a recorded .mp4 as if it were a live camera stream.

    Loops back to frame 0 when the video ends (loop=True) so the ingestion
    pipeline can run indefinitely during a demo — the same way a real RTSP
    camera never "runs out" of frames.
    """

    def __init__(self, camera_id: int, video_path: str | Path, loop: bool = True):
        self.camera_id = camera_id  # kept as int — matches cameras.camera_id (FK) in DB
        self.video_path = Path(video_path)
        self.loop = loop

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_index = -1  # -1 until connect(); becomes 0 on first read_frame()
        self._connected = False

        if not self.video_path.exists():
            raise FileNotFoundError(f"Mock video not found: {self.video_path}")

    def connect(self) -> None:
        self._cap = cv2.VideoCapture(str(self.video_path))
        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open mock video: {self.video_path}")
        self._connected = True
        self._frame_index = -1

    def read_frame(self) -> Optional[np.ndarray]:
        if not self._connected or self._cap is None:
            return None

        ok, frame = self._cap.read()

        if not ok:
            if not self.loop:
                return None
            # End of file — loop back to the start.
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            if not ok:
                return None
            self._frame_index = 0
            return frame

        self._frame_index += 1
        return frame

    def get_metadata(self) -> dict[str, Any]:
        """
        camera_id is stringified here to satisfy the ABC's documented
        contract (camera_id: str); self.camera_id itself stays an int
        for DAO calls that need the real FK value.
        """
        return {
            "camera_id": str(self.camera_id),
            "timestamp": time.time(),
            "frame_index": self._frame_index,
            "source_type": "mock_video",
            "video_path": str(self.video_path),
            "fps": self.fps,
            "total_frames": self.total_frames,
        }

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._connected = False

    @property
    def total_frames(self) -> int:
        if self._cap is None:
            return 0
        return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    @property
    def fps(self) -> float:
        if self._cap is None:
            return 0.0
        return self._cap.get(cv2.CAP_PROP_FPS)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


if __name__ == "__main__":
    # Quick smoke test: python sources/mock_video_source.py
    # Reads past the 240-frame mark on purpose to prove looping works.
    src = MockVideoSource(camera_id=1, video_path="data/mock_videos/camera_1_gate.mp4")
    with src:
        print(f"Opened: {src.video_path.name} | fps={src.fps} total_frames={src.total_frames}")
        count = 0
        while count < 250:
            frame = src.read_frame()
            if frame is None:
                print("No frame returned, stopping.")
                break
            count += 1
        print(f"Read {count} frames (loop={src.loop}) — should be 250 if looping worked.")
        print("Last metadata:", src.get_metadata())