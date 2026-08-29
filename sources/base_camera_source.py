"""
Abstract interface for all camera/video sources.

Any concrete source (mock video file, real RTSP stream, future API-based
feed) must implement this contract so the rest of the pipeline
(ingestion_pipeline.py, main.py, etc.) can treat every source identically,
regardless of whether it's reading a local .mp4 or a live camera feed.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
import numpy as np


class BaseCameraSource(ABC):
    """
    Contract for a single camera/video input.

    Lifecycle expected by callers:
        source.connect()
        while True:
            frame = source.read_frame()
            if frame is None:
                break
            metadata = source.get_metadata()
        source.release()
    """

    camera_id: int  # Subclasses must set this in __init__

    @abstractmethod
    def connect(self) -> None:
        """
        Establish the connection to the underlying source.

        For a mock source, this might mean opening a local video file.
        For a real source, this might mean opening an RTSP/HTTP stream
        or authenticating against a camera API.

        Should raise a clear exception if the connection cannot be made.
        """
        raise NotImplementedError

    @abstractmethod
    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read and return the next available frame.

        Returns:
            A frame as a numpy array (e.g. BGR image from OpenCV),
            or None if there are no more frames (end of file / stream
            disconnected).
        """
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """
        Return metadata describing the current frame/source state.

        Expected keys (at minimum):
            - camera_id: str
            - timestamp: float or datetime
            - frame_index: int (optional, useful for mock sources)

        Concrete implementations may include additional fields
        (e.g. resolution, fps, source_type).
        """
        raise NotImplementedError

    def release(self) -> None:
        """
        Optional cleanup hook (close file handles, release streams, etc.).

        Not marked @abstractmethod since some sources may not need
        explicit cleanup -- but subclasses should override this if they do.
        """
        pass
