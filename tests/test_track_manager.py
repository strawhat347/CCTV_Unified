"""
tests/test_track_manager.py — Unit tests for the TrackManager,
covering blur rejection, crop accumulation, and stale track finalization.
"""

import sys
import os
import numpy as np
import pytest

# Ensure project root is on sys.path so imports work from tests/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from detection.track_manager import TrackManager, TrackState, FinalizedTrack


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _make_sharp_crop(h: int = 64, w: int = 200) -> np.ndarray:
    """Create a synthetic sharp crop (high edge variance)."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Draw strong horizontal lines (high Laplacian variance)
    for y in range(0, h, 4):
        img[y, :, :] = 255
    return img


def _make_blurry_crop(h: int = 64, w: int = 200) -> np.ndarray:
    """Create a synthetic blurry crop (uniform gray, near-zero variance)."""
    img = np.full((h, w, 3), 128, dtype=np.uint8)
    return img


# ──────────────────────────────────────────────────────────────────────
# Test: Sharpness computation
# ──────────────────────────────────────────────────────────────────────

class TestSharpness:
    def test_sharp_image_has_high_variance(self):
        crop = _make_sharp_crop()
        score = TrackManager.compute_sharpness(crop)
        assert score > 100.0, f"Sharp image should have high variance, got {score}"

    def test_blurry_image_has_low_variance(self):
        crop = _make_blurry_crop()
        score = TrackManager.compute_sharpness(crop)
        assert score < 10.0, f"Blurry image should have low variance, got {score}"

    def test_empty_image_returns_zero(self):
        empty = np.empty((0, 0, 3), dtype=np.uint8)
        assert TrackManager.compute_sharpness(empty) == 0.0

    def test_none_returns_zero(self):
        assert TrackManager.compute_sharpness(None) == 0.0

    def test_is_sharp_with_threshold(self):
        tm = TrackManager(sharpness_threshold=50.0)
        sharp_crop = _make_sharp_crop()
        blurry_crop = _make_blurry_crop()

        is_s, score_s = tm.is_sharp(sharp_crop)
        is_b, score_b = tm.is_sharp(blurry_crop)

        assert is_s is True
        assert is_b is False


# ──────────────────────────────────────────────────────────────────────
# Test: Track update and finalization
# ──────────────────────────────────────────────────────────────────────

class TestTrackLifecycle:
    def test_update_and_stale_finalization(self):
        tm = TrackManager(stale_after_frames=5, sharpness_threshold=50.0)
        crop = _make_sharp_crop()

        # Simulate track visible for frames 1-3
        for frame_idx in range(1, 4):
            tm.update(
                track_id=1,
                crop=crop,
                bbox=(100, 200, 150, 40),
                detection_confidence=0.85,
                frame_idx=frame_idx,
                sharpness=500.0,
                was_blurry=False,
            )

        # Not stale yet at frame 5
        assert len(tm.finalize_stale(5)) == 0

        # Stale at frame 10 (last seen at 3, stale_after_frames=5)
        finalized = tm.finalize_stale(10)
        assert len(finalized) == 1

        ft = finalized[0]
        assert ft.track_id == 1
        assert ft.total_detections == 3

    def test_blurry_frames_skip_accumulation(self):
        tm = TrackManager(stale_after_frames=5, sharpness_threshold=50.0)
        blurry = _make_blurry_crop()

        # Feed blurry frames
        tm.update(
            track_id=2,
            crop=blurry,
            bbox=(50, 60, 120, 35),
            detection_confidence=0.80,
            frame_idx=1,
            sharpness=2.0,
            was_blurry=True,
        )
        tm.update(
            track_id=2,
            crop=blurry,
            bbox=(50, 60, 120, 35),
            detection_confidence=0.80,
            frame_idx=2,
            sharpness=3.0,
            was_blurry=True,
        )

        finalized = tm.finalize_stale(100)
        assert len(finalized) == 1
        ft = finalized[0]
        assert ft.blurry_skips == 2

    def test_best_crop_retained(self):
        tm = TrackManager(stale_after_frames=5)
        blurry = _make_blurry_crop()
        sharp = _make_sharp_crop()

        # Frame 1: blurry
        tm.update(
            track_id=3, crop=blurry,
            bbox=(10, 20, 100, 30), detection_confidence=0.7,
            frame_idx=1, sharpness=2.0, was_blurry=True,
        )
        # Frame 2: sharp
        tm.update(
            track_id=3, crop=sharp,
            bbox=(10, 20, 100, 30), detection_confidence=0.9,
            frame_idx=2, sharpness=500.0, was_blurry=False,
        )

        finalized = tm.finalize_stale(100)
        ft = finalized[0]
        # The sharpest crop should be retained
        assert ft.best_crop is not None
        assert ft.detection_confidence == 0.9

    def test_flush_all(self):
        tm = TrackManager(stale_after_frames=100)
        crop = _make_sharp_crop()

        for tid in [1, 2, 3]:
            tm.update(
                track_id=tid, crop=crop,
                bbox=(0, 0, 100, 30), detection_confidence=0.80,
                frame_idx=1, sharpness=500.0, was_blurry=False,
            )

        assert tm.active_track_count == 3
        flushed = tm.flush_all()
        assert len(flushed) == 3
        assert tm.active_track_count == 0


# ──────────────────────────────────────────────────────────────────────
# Test: Edge cases
# ──────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_max_crops_cap(self):
        """Ensure sharp crops are capped at max_crops."""
        tm = TrackManager(max_crops=3, stale_after_frames=5)
        crop = _make_sharp_crop()

        for i in range(10):
            tm.update(
                track_id=1, crop=crop,
                bbox=(0, 0, 100, 30), detection_confidence=0.80,
                frame_idx=i + 1, sharpness=500.0, was_blurry=False,
            )

        finalized = tm.finalize_stale(100)
        ft = finalized[0]
        assert len(ft.sharp_crops) == 3  # capped

    def test_multiple_concurrent_tracks(self):
        tm = TrackManager(stale_after_frames=5)
        crop = _make_sharp_crop()

        # Two vehicles in frame simultaneously
        for frame in range(1, 6):
            tm.update(
                track_id=100, crop=crop,
                bbox=(0, 0, 100, 30), detection_confidence=0.85,
                frame_idx=frame, sharpness=500.0, was_blurry=False,
            )
            tm.update(
                track_id=200, crop=crop,
                bbox=(200, 0, 100, 30), detection_confidence=0.82,
                frame_idx=frame, sharpness=500.0, was_blurry=False,
            )

        assert tm.active_track_count == 2
        finalized = tm.finalize_stale(100)
        assert len(finalized) == 2
