"""
tests/test_sources.py — Unit tests for camera sources.
Run with: pytest tests/test_sources.py
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from sources.mock_video_source import MockVideoSource


@pytest.fixture
def mock_cv2():
    """Mocks cv2.VideoCapture to return a dummy frame twice, then fail (simulate EOF)."""
    with patch("sources.mock_video_source.cv2") as mock_cv:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        
        # .read() returns (True, frame) twice, then (False, None)
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [(True, dummy_frame), (True, dummy_frame), (False, None)]
        
        mock_cap.get.return_value = 30.0  # Dummy FPS
        mock_cv.VideoCapture.return_value = mock_cap
        
        # Also mock Path.exists so it doesn't look for a real file
        with patch("sources.mock_video_source.Path.exists", return_value=True):
            yield mock_cv, mock_cap


def test_mock_video_source_no_loop(mock_cv2):
    _, mock_cap = mock_cv2
    
    source = MockVideoSource(camera_id=1, video_path="dummy.mp4", loop=False)
    with source:
        frame1 = source.read_frame()
        frame2 = source.read_frame()
        frame3 = source.read_frame()
        
    assert frame1 is not None
    assert frame2 is not None
    assert frame3 is None  # EOF reached, no loop
    assert source.get_metadata()["frame_index"] == 1


def test_mock_video_source_looping(mock_cv2):
    mock_cv, mock_cap = mock_cv2
    
    # Change side_effect to simulate EOF, then a successful read after looping
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap.read.side_effect = [
        (True, dummy_frame),  # Frame 0
        (False, None),        # EOF
        (True, dummy_frame)   # Frame 0 again (after loop reset)
    ]
    
    source = MockVideoSource(camera_id=2, video_path="dummy.mp4", loop=True)
    with source:
        frame1 = source.read_frame()
        frame2 = source.read_frame()  # This should trigger the loop
        
    assert frame1 is not None
    assert frame2 is not None
    # Verify the cap position was reset using the mock's attribute
    mock_cap.set.assert_called_with(mock_cv.CAP_PROP_POS_FRAMES, 0)
    assert source.get_metadata()["frame_index"] == 0