"""
detection/frame_sampler.py — Decides which frames from a camera source
actually get sent to the (expensive) detection pipeline.

Running YOLO + PaddleOCR on *every* 30-fps frame is both unnecessary and
unaffordable on a CPU-only demo machine.  FrameSampler sits between the
camera source and DetectionPipeline, letting only every Nth frame through.

Also provides a static crop helper used by the detection pipeline to
extract the plate region once YOLO returns a bounding box.
"""

from __future__ import annotations

import threading

import numpy as np


class FrameSampler:
    """
    Passes through every `sample_interval`-th frame for detection,
    skipping the rest.

    Usage:
        sampler = FrameSampler(sample_interval=10)
        while True:
            frame = source.read_frame()
            if frame is None:
                break
            if sampler.should_process(frame):
                boxes = detector.detect(frame)
                ...
    """

    def __init__(self, sample_interval: int = 10):
        """
        Args:
            sample_interval: Process one out of every N frames.
                             1 = process every frame (no skipping).
        """
        if sample_interval < 1:
            raise ValueError(f"sample_interval must be >= 1, got {sample_interval}")

        self.sample_interval = sample_interval
        self._frame_count = 0
        self._lock = threading.Lock()

    def should_process(self, frame: np.ndarray) -> bool:
        """
        Call once per frame read from the source.  Returns True when this
        frame should be forwarded to YOLO detection, False to skip.

        The frame arg isn't inspected today (decision is purely count-based),
        but the signature accepts it so a future subclass could add
        motion-delta or blur-check gating without changing the pipeline's
        call site.
        """
        with self._lock:
            self._frame_count += 1
            count = self._frame_count
        return (count % self.sample_interval) == 0

    @property
    def frames_seen(self) -> int:
        """Total frames passed to should_process() since construction."""
        with self._lock:
            return self._frame_count

    def reset(self) -> None:
        """Reset the internal counter (e.g. when the source loops)."""
        with self._lock:
            self._frame_count = 0

    # ------------------------------------------------------------------
    # Static crop utility — lives here rather than in the pipeline so
    # it's unit-testable in isolation without needing a DB or models.
    # ------------------------------------------------------------------
    @staticmethod
    def crop_region(
        frame: np.ndarray,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        padding: int = 0,
    ) -> np.ndarray:
        """
        Crop a rectangular region from *frame* using pixel coords returned
        by BaseDetector.detect().

        Args:
            frame:   The full-resolution frame (HxWxC numpy array).
            x1, y1:  Top-left corner of the bounding box.
            x2, y2:  Bottom-right corner of the bounding box.
            padding: Optional extra pixels added around the crop on each
                     side — a small pad (2-5 px) helps OCR engines that
                     struggle when text runs right to the crop edge.

        Returns:
            A numpy array containing the cropped region, or an empty
            (0,0,3) array if the box is degenerate after clamping.
        """
        h, w = frame.shape[:2]

        # Clamp to frame bounds after applying padding.
        cx1 = max(0, int(x1) - padding)
        cy1 = max(0, int(y1) - padding)
        cx2 = min(w, int(x2) + padding)
        cy2 = min(h, int(y2) + padding)

        if cx2 <= cx1 or cy2 <= cy1:
            # Degenerate box — return empty array so callers don't crash.
            return np.empty((0, 0, 3), dtype=frame.dtype)

        return frame[cy1:cy2, cx1:cx2].copy()
