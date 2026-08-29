"""
pipeline/ingestion_pipeline.py — Step 3 vertical slice.

Proves the full chain works end-to-end:
    mock camera source -> read frames -> write metadata to MySQL

Writes a placeholder detection row every N frames to confirm the DB
write path (dao_detections.insert_detection) works against a live
camera source — real YOLO/OCR replaces the placeholder in Step 4.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sources.base_camera_source import BaseCameraSource
from sources.mock_video_source import MockVideoSource  # noqa: F401 — kept for backward compat
from db.dao_cameras import get_camera_by_id, insert_camera
from db.dao_detections import insert_detection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingestion_pipeline")


class IngestionPipeline:
    """
    Wires one CameraSource (any BaseCameraSource implementation) to the DB.
    Written against MockVideoSource today; swapping in RTSPCameraSource
    later (Step 8) needs no changes here.
    """

    def __init__(
        self,
        camera_id: int,
        source: BaseCameraSource,
        sample_every_n_frames: int = 30,
        max_frames: int | None = None,
    ):
        self.camera_id = camera_id
        self.source = source
        self.sample_every_n_frames = sample_every_n_frames
        self.max_frames = max_frames

        self._frames_read = 0
        self._detections_written = 0
        self.camera_location = None

    def ensure_camera_row(self, name: str, stream_url: str) -> None:
        """
        Make sure a `cameras` row exists for this camera_id before we try
        to insert detections that FK-reference it. Call once before run().

        If no row exists yet, inserts one and re-points self.camera_id at
        whatever id MySQL actually assigned (AUTO_INCREMENT) — otherwise
        every insert_detection() call below would keep using the old,
        nonexistent camera_id and fail its FK constraint.
        """
        existing = get_camera_by_id(self.camera_id)
        if existing is None:
            new_id = insert_camera(name=name, stream_url=stream_url, status="active")
            logger.info(f"No camera row for camera_id={self.camera_id}; inserted new row id={new_id}.")
            self.camera_id = new_id
            self.source.camera_id = new_id  # keep source's metadata in sync
            self.camera_location = None
        else:
            logger.info(f"Camera row confirmed: {existing['name']} (status={existing['status']})")
            self.camera_location = existing.get("location")

    def _write_placeholder_detection(self, frame) -> None:
        """
        Placeholder detection row to prove the DB write path end-to-end
        before YOLO/OCR exist. bbox is a rough center box of the frame;
        confidence=1.0 marks it clearly as a placeholder, not a real
        model output.
        """
        h, w = frame.shape[:2]
        bbox_w, bbox_h = w // 4, h // 4
        bbox_x, bbox_y = (w - bbox_w) // 2, (h - bbox_h) // 2

        meta = self.source.get_metadata()

        detection_id = insert_detection(
            camera_id=self.camera_id,
            object_type="mock_frame_sample",
            confidence=1.0,
            bbox_x=bbox_x,
            bbox_y=bbox_y,
            bbox_w=bbox_w,
            bbox_h=bbox_h,
            image_path=None,
            location=self.camera_location,
        )
        self._detections_written += 1
        logger.info(
            f"[camera {self.camera_id}] frame_index={meta['frame_index']}: "
            f"wrote placeholder detection_id={detection_id}"
        )

    def run(self) -> None:
        self.source.connect()

        logger.info(
            f"Starting ingestion for camera_id={self.camera_id} "
            f"(sample_every_n_frames={self.sample_every_n_frames}, max_frames={self.max_frames})"
        )

        try:
            while True:
                if self.max_frames is not None and self._frames_read >= self.max_frames:
                    logger.info(f"Reached max_frames={self.max_frames}, stopping.")
                    break

                frame = self.source.read_frame()
                if frame is None:
                    logger.warning("Source returned no frame (not looping / exhausted). Stopping.")
                    break

                self._frames_read += 1

                if self._frames_read % self.sample_every_n_frames == 0:
                    self._write_placeholder_detection(frame)

        finally:
            self.source.release()
            logger.info(
                f"Ingestion stopped. frames_read={self._frames_read}, "
                f"detections_written={self._detections_written}"
            )


if __name__ == "__main__":
    # End-to-end smoke test: python pipeline/ingestion_pipeline.py
    # Requires MySQL running and db/schema.sql already applied.
    CAMERA_ID = 1
    VIDEO_PATH = Path("data/mock_videos/camera_1_gate.mp4")

    source = MockVideoSource(camera_id=CAMERA_ID, video_path=VIDEO_PATH, loop=False)

    pipeline = IngestionPipeline(
        camera_id=CAMERA_ID,
        source=source,
        sample_every_n_frames=30,
        max_frames=240,  # exactly one pass through the 240-frame mock video
    )

    pipeline.ensure_camera_row(name="Gate Camera (mock)", stream_url=str(VIDEO_PATH))
    pipeline.run()
    # Expect ~8 placeholder detection rows written (240 // 30) — confirm with:
    # SELECT * FROM detections WHERE camera_id = 1;