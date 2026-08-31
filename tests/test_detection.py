"""
tests/test_detection.py — Unit tests for Step 4 (Detection Pipeline).

Covers:
  1. FrameSampler — interval logic + crop utility
  2. DetectionPipeline — full chain with mock detector, mock OCR, mock source
     (no real models, no DB needed)
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from detection.base_detector import BaseDetector, BoundingBox
from detection.base_ocr_engine import BaseOcrEngine, OcrResult
from detection.frame_sampler import FrameSampler
from sources.base_camera_source import BaseCameraSource


# =====================================================================
# FrameSampler tests
# =====================================================================


class TestFrameSampler:
    """Tests for FrameSampler interval logic and crop utility."""

    def test_every_frame_when_interval_is_1(self):
        sampler = FrameSampler(sample_interval=1)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        results = [sampler.should_process(frame) for _ in range(5)]
        assert results == [True, True, True, True, True]

    def test_every_nth_frame(self):
        sampler = FrameSampler(sample_interval=3)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        results = [sampler.should_process(frame) for _ in range(9)]
        # Frames 3, 6, 9 should be True
        assert results == [False, False, True, False, False, True, False, False, True]

    def test_frames_seen_counter(self):
        sampler = FrameSampler(sample_interval=5)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        for _ in range(7):
            sampler.should_process(frame)
        assert sampler.frames_seen == 7

    def test_reset(self):
        sampler = FrameSampler(sample_interval=5)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        for _ in range(7):
            sampler.should_process(frame)
        sampler.reset()
        assert sampler.frames_seen == 0

    def test_invalid_interval_raises(self):
        with pytest.raises(ValueError):
            FrameSampler(sample_interval=0)
        with pytest.raises(ValueError):
            FrameSampler(sample_interval=-1)


class TestCropRegion:
    """Tests for FrameSampler.crop_region() static helper."""

    def _make_frame(self, h: int = 200, w: int = 300) -> np.ndarray:
        """Create a simple test frame with predictable pixel values."""
        return np.arange(h * w * 3, dtype=np.uint8).reshape(h, w, 3)

    def test_basic_crop(self):
        frame = self._make_frame()
        crop = FrameSampler.crop_region(frame, 10, 20, 50, 60)
        assert crop.shape == (40, 40, 3)  # (60-20) x (50-10)

    def test_crop_with_padding(self):
        frame = self._make_frame()
        crop = FrameSampler.crop_region(frame, 10, 20, 50, 60, padding=5)
        assert crop.shape == (50, 50, 3)  # (65-15) x (55-5)

    def test_crop_clamped_to_frame_bounds(self):
        frame = self._make_frame(h=100, w=100)
        crop = FrameSampler.crop_region(frame, 0, 0, 120, 120, padding=10)
        # Should clamp to frame bounds: (0,0) to (100,100)
        assert crop.shape == (100, 100, 3)

    def test_degenerate_box_returns_empty(self):
        frame = self._make_frame()
        crop = FrameSampler.crop_region(frame, 50, 50, 30, 30)  # x2 < x1
        assert crop.size == 0

    def test_crop_is_a_copy(self):
        """Crop should be a copy, not a view — modifying it must not affect the original frame."""
        frame = self._make_frame()
        crop = FrameSampler.crop_region(frame, 10, 10, 20, 20)
        original_pixel = frame[10, 10, 0].copy()
        crop[0, 0, 0] = 255
        assert frame[10, 10, 0] == original_pixel


# =====================================================================
# Fake implementations for DetectionPipeline integration test
# =====================================================================


class FakeSource(BaseCameraSource):
    """Yields a fixed number of dummy frames with edge content, then stops."""

    def __init__(self, num_frames: int = 30):
        # Create frames with strong horizontal lines so they pass the
        # Laplacian sharpness check in the tracking pipeline.
        frames = []
        for _ in range(num_frames):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            for y in range(0, 480, 4):
                frame[y, :, :] = 255  # alternating bright lines
            frames.append(frame)
        self._frames = frames
        self._index = 0
        self._connected = False

    def connect(self) -> None:
        self._connected = True
        self._index = 0

    def read_frame(self) -> Optional[np.ndarray]:
        if not self._connected or self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def get_metadata(self) -> dict[str, Any]:
        return {"camera_id": 1, "frame_index": self._index, "source_type": "fake"}

    def release(self) -> None:
        self._connected = False


class FakeDetector(BaseDetector):
    """Returns one fixed bounding box for every frame, with tracking support."""

    def __init__(self, boxes: list[BoundingBox] | None = None):
        self._boxes = boxes or [
            BoundingBox(x1=100, y1=200, x2=250, y2=260, confidence=0.92,
                        class_id=0, class_name="plate")
        ]
        self._track_counter = 0

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        return self._boxes

    def track(self, frame: np.ndarray, persist: bool = True) -> list[BoundingBox]:
        """Return boxes with track_id assigned.  Each unique box position
        gets a stable track_id (simulates ByteTrack for tests)."""
        # For simplicity in tests, assign track_id = 1 for each box
        # (simulating a single tracked vehicle)
        tracked = []
        for box in self._boxes:
            tracked.append(
                BoundingBox(
                    x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2,
                    confidence=box.confidence, class_id=box.class_id,
                    class_name=box.class_name, track_id=1,
                )
            )
        return tracked

    def load_model(self, model_path: str) -> None:
        pass  # no-op — "model" is the hardcoded boxes


class FakeOcrEngine(BaseOcrEngine):
    """Returns a fixed plate read for every crop."""

    def __init__(self, text: str = "GJ01AB1234", confidence: float = 0.95):
        self._result = OcrResult(text=text, confidence=confidence)

    def read_text(self, cropped_img: np.ndarray) -> Optional[OcrResult]:
        if cropped_img.size == 0:
            return None
        return self._result

    def load_model(self) -> None:
        pass  # no-op


# =====================================================================
# DetectionPipeline tests (mock DB, real pipeline logic)
# =====================================================================


class TestDetectionPipeline:
    """Integration tests for pipeline.detection_pipeline.DetectionPipeline."""

    def _build_pipeline(self, num_frames=30, sample_interval=10, max_frames=None,
                        detector=None, ocr=None):
        """Helper to build a pipeline with fakes and mocked DB."""
        from pipeline.detection_pipeline import DetectionPipeline

        source = FakeSource(num_frames=num_frames)
        return DetectionPipeline(
            camera_id=1,
            source=source,
            detector=detector or FakeDetector(),
            ocr_engine=ocr or FakeOcrEngine(),
            sample_interval=sample_interval,
            max_frames=max_frames,
            min_detection_confidence=0.4,
            min_ocr_confidence=0.5,
            save_crops=False,
        )

    @patch("pipeline.detection_pipeline.insert_detection", return_value=1)
    @patch("pipeline.detection_pipeline.get_camera_by_id", return_value={"name": "test", "status": "active"})
    @patch("pipeline.detection_pipeline.insert_camera", return_value=1)
    def test_pipeline_runs_end_to_end(self, mock_insert_cam, mock_get_cam, mock_insert_det):
        """Pipeline should read all frames, process sampled ones, and write detections.
        With tracking, all frames for the same track_id are aggregated into
        a single finalized detection (written on shutdown flush)."""
        pipeline = self._build_pipeline(num_frames=30, sample_interval=10)
        pipeline.ensure_camera_row("test cam", "test://url")
        pipeline.run()

        assert pipeline.stats["frames_read"] == 30
        # With interval=10, frames 10, 20, 30 get processed → 3
        assert pipeline.stats["frames_processed"] == 3
        # All 3 frames have the same track_id=1 → 1 finalized track
        assert pipeline.stats["detections_written"] == 1
        assert mock_insert_det.call_count == 1

    @patch("pipeline.detection_pipeline.insert_detection", return_value=1)
    @patch("pipeline.detection_pipeline.get_camera_by_id", return_value={"name": "test", "status": "active"})
    @patch("pipeline.detection_pipeline.insert_camera", return_value=1)
    def test_max_frames_respected(self, mock_insert_cam, mock_get_cam, mock_insert_det):
        """Pipeline should stop early when max_frames is reached."""
        pipeline = self._build_pipeline(num_frames=100, sample_interval=5, max_frames=20)
        pipeline.ensure_camera_row("test cam", "test://url")
        pipeline.run()

        assert pipeline.stats["frames_read"] == 20

    @patch("pipeline.detection_pipeline.insert_detection", return_value=1)
    @patch("pipeline.detection_pipeline.get_camera_by_id", return_value={"name": "test", "status": "active"})
    @patch("pipeline.detection_pipeline.insert_camera", return_value=1)
    def test_low_confidence_boxes_filtered(self, mock_insert_cam, mock_get_cam, mock_insert_det):
        """Boxes below min_detection_confidence should be dropped."""
        low_conf_detector = FakeDetector(boxes=[
            BoundingBox(x1=10, y1=10, x2=50, y2=50, confidence=0.1,
                        class_id=0, class_name="plate")
        ])
        pipeline = self._build_pipeline(
            num_frames=10, sample_interval=1, detector=low_conf_detector
        )
        pipeline.ensure_camera_row("test cam", "test://url")
        pipeline.run()

        # All 10 frames processed, but no detections should be written
        assert pipeline.stats["frames_processed"] == 10
        assert pipeline.stats["detections_written"] == 0

    @patch("pipeline.detection_pipeline.insert_detection", return_value=1)
    @patch("pipeline.detection_pipeline.get_camera_by_id", return_value={"name": "test", "status": "active"})
    @patch("pipeline.detection_pipeline.insert_camera", return_value=1)
    def test_low_ocr_confidence_still_writes_detection(self, mock_insert_cam, mock_get_cam, mock_insert_det):
        """
        When OCR confidence is below threshold, detection should still be
        written as 'plate_detected_no_ocr'.  With tracking, all 5 frames
        for the same track_id aggregate into 1 finalized track.
        """
        low_ocr = FakeOcrEngine(text="???", confidence=0.1)
        pipeline = self._build_pipeline(
            num_frames=5, sample_interval=1, ocr=low_ocr
        )
        pipeline.ensure_camera_row("test cam", "test://url")
        pipeline.run()

        # 1 finalized track (all 5 frames had track_id=1)
        assert pipeline.stats["detections_written"] == 1
        assert pipeline.stats["ocr_reads"] == 0  # none above threshold

        # Verify the object_type in the DB call
        call_kwargs = mock_insert_det.call_args_list[0]
        assert call_kwargs[1]["object_type"] == "plate_detected_no_ocr" or \
               call_kwargs[0][1] == "plate_detected_no_ocr"

    @patch("pipeline.detection_pipeline.insert_detection", return_value=1)
    @patch("pipeline.detection_pipeline.get_camera_by_id", return_value={"name": "test", "status": "active"})
    @patch("pipeline.detection_pipeline.insert_camera", return_value=1)
    def test_successful_ocr_writes_plate_text(self, mock_insert_cam, mock_get_cam, mock_insert_det):
        """When OCR succeeds, the finalized track should have plate_text set.
        With tracking, all 5 frames aggregate into 1 finalized detection."""
        pipeline = self._build_pipeline(
            num_frames=5, sample_interval=1,
            ocr=FakeOcrEngine(text="GJ05CD6789", confidence=0.88)
        )
        pipeline.ensure_camera_row("test cam", "test://url")
        pipeline.run()

        assert pipeline.stats["ocr_reads"] == 5
        # 1 finalized track with consensus plate text
        assert pipeline.stats["detections_written"] == 1
        # Check the call's plate_text
        for call in mock_insert_det.call_args_list:
            assert call.kwargs.get("plate_text") == "GJ05CD6789"

    @patch("pipeline.detection_pipeline.insert_detection", return_value=1)
    @patch("pipeline.detection_pipeline.get_camera_by_id", return_value=None)
    @patch("pipeline.detection_pipeline.insert_camera", return_value=42)
    def test_ensure_camera_row_creates_when_missing(self, mock_insert_cam, mock_get_cam, mock_insert_det):
        """When no camera row exists, ensure_camera_row should insert one."""
        pipeline = self._build_pipeline(num_frames=5, sample_interval=1)
        pipeline.ensure_camera_row("New Camera", "test://new")

        mock_insert_cam.assert_called_once_with(
            name="New Camera", stream_url="test://new", status="active"
        )
        assert pipeline.camera_id == 42  # updated to the DB-assigned id

    @patch("pipeline.detection_pipeline.insert_detection", return_value=1)
    @patch("pipeline.detection_pipeline.get_camera_by_id", return_value={"name": "test", "status": "active"})
    @patch("pipeline.detection_pipeline.insert_camera", return_value=1)
    def test_no_detections_on_empty_source(self, mock_insert_cam, mock_get_cam, mock_insert_det):
        """A source with 0 frames should produce 0 detections."""
        pipeline = self._build_pipeline(num_frames=0, sample_interval=1)
        pipeline.ensure_camera_row("test cam", "test://url")
        pipeline.run()

        assert pipeline.stats["frames_read"] == 0
        assert pipeline.stats["detections_written"] == 0
