"""
detection/track_manager.py - Multi-frame track aggregation, blur rejection,
and decoupled track accumulation for ALPR.

Tracks individual plate detections across frames using YOLO-assigned track
IDs.  For each tracked plate:

  1. Blur rejection: Calculates Variance of Laplacian on each crop.
  2. Crop accumulation: Stores the sharpest crops to be processed by a centralized OCR worker.
  3. Track Finalization: When a track ends, the payload is emitted.
"""

from __future__ import annotations
import logging
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("track_manager")

@dataclass
class TrackState:
    track_id: int
    sharp_crops: list[np.ndarray] = field(default_factory=list)
    best_crop: Optional[np.ndarray] = None
    best_sharpness: float = 0.0
    best_bbox: Optional[tuple[int, int, int, int]] = None
    best_confidence: float = 0.0
    last_seen_frame: int = 0
    first_seen_frame: int = 0
    total_detections: int = 0
    blurry_skips: int = 0

@dataclass
class FinalizedTrack:
    track_id: int
    sharp_crops: list[np.ndarray]
    best_crop: Optional[np.ndarray]
    bbox: Optional[tuple[int, int, int, int]]
    detection_confidence: float
    total_detections: int
    blurry_skips: int

class TrackManager:
    def __init__(self, sharpness_threshold: float = 100.0, stale_after_frames: int = 30, max_crops: int = 20):
        self.sharpness_threshold = sharpness_threshold
        self.stale_after_frames = stale_after_frames
        self.max_crops = max_crops
        self._tracks: dict[int, TrackState] = {}

    @staticmethod
    def compute_sharpness(crop: np.ndarray) -> float:
        if crop is None or crop.size == 0:
            return 0.0
        if len(crop.shape) == 3:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = crop
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        return float(laplacian.var())

    def is_sharp(self, crop: np.ndarray) -> tuple[bool, float]:
        score = self.compute_sharpness(crop)
        return score >= self.sharpness_threshold, score

    def update(self, track_id: int, crop: np.ndarray, bbox: tuple[int, int, int, int], detection_confidence: float, frame_idx: int, sharpness: float, was_blurry: bool) -> None:
        if track_id not in self._tracks:
            self._tracks[track_id] = TrackState(track_id=track_id, first_seen_frame=frame_idx)
        
        ts = self._tracks[track_id]
        ts.last_seen_frame = frame_idx
        ts.total_detections += 1
        
        if was_blurry:
            ts.blurry_skips += 1
            
        if sharpness > ts.best_sharpness:
            ts.best_sharpness = sharpness
            ts.best_crop = crop.copy() if crop is not None else None
            ts.best_bbox = bbox
            ts.best_confidence = detection_confidence
            
        if not was_blurry and crop is not None:
            if len(ts.sharp_crops) < self.max_crops:
                ts.sharp_crops.append(crop.copy())

    def finalize_stale(self, current_frame: int) -> list[FinalizedTrack]:
        stale_ids = [tid for tid, ts in self._tracks.items() if (current_frame - ts.last_seen_frame) > self.stale_after_frames]
        finalized = []
        for tid in stale_ids:
            ts = self._tracks.pop(tid)
            finalized.append(self._build_finalized(ts))
        return finalized

    def flush_all(self) -> list[FinalizedTrack]:
        finalized = []
        for ts in list(self._tracks.values()):
            finalized.append(self._build_finalized(ts))
        self._tracks.clear()
        return finalized

    @property
    def active_track_count(self) -> int:
        return len(self._tracks)

    def _build_finalized(self, ts: TrackState) -> FinalizedTrack:
        return FinalizedTrack(
            track_id=ts.track_id,
            sharp_crops=ts.sharp_crops,
            best_crop=ts.best_crop,
            bbox=ts.best_bbox,
            detection_confidence=ts.best_confidence,
            total_detections=ts.total_detections,
            blurry_skips=ts.blurry_skips,
        )

