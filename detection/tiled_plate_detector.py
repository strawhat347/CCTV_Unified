"""
detection/tiled_plate_detector.py — SAHI-style tiled inference for
high-resolution frames.

Wraps a YoloPlateDetector, slicing the input frame into overlapping tiles,
running batched GPU detection on each tile batch at the model's native resolution,
then merging results back into full-frame coordinates with NMS de-duplication.

After NMS, a vehicle-level grouping pass clusters nearby plate detections that
likely belong to the same vehicle (e.g. front + rear plates visible, or
overlapping detections from adjacent tiles that survived NMS).  Only the
highest-confidence plate per vehicle cluster is kept.

Implements BaseDetector so it's a drop-in replacement in DetectionPipeline.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from detection.base_detector import BaseDetector, BoundingBox
from detection.yolo_plate_detector import YoloPlateDetector

logger = logging.getLogger(__name__)


class TiledPlateDetector(BaseDetector):
    """
    SAHI-style wrapper around YoloPlateDetector with GPU batching and
    per-vehicle plate deduplication.

    Usage::

        detector = TiledPlateDetector(
            tile_size=1280,
            overlap_ratio=0.2,
        )
        detector.load_model("runs/detect/train-8/weights/best.pt")
        boxes = detector.detect(huge_frame)   # returns full-frame coords
    """

    def __init__(
        self,
        tile_size: int = 1280,
        overlap_ratio: float = 0.2,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.5,
        full_frame_pass: bool = True,
        full_frame_imgsz: int = 2560,
        batch_size: int = 16,
        device: str | None = None,
        vehicle_merge: bool = False,
        vehicle_proximity_factor: float = 2.0,
    ):
        """
        Args:
            tile_size:        Width & height of each tile in pixels.
            overlap_ratio:    Fraction of tile_size that adjacent tiles
                              overlap (0.2 = 256 px overlap for 1280 tiles).
            conf_threshold:   YOLO confidence threshold per tile.
            iou_threshold:    IoU threshold for NMS when merging tiles.
            full_frame_pass:  Also run a full-frame inference at
                              ``full_frame_imgsz`` and merge.  Catches
                              large close-up plates that span tile seams.
            full_frame_imgsz: imgsz for the optional full-frame pass.
            batch_size:       Number of tiles to process simultaneously on GPU.
            device:           Torch device (e.g. 'cuda:0', 'cpu', or None for auto).
            vehicle_merge:    If True, group nearby plates that likely belong
                              to the same vehicle and keep only the best one.
            vehicle_proximity_factor:
                              Two plates whose centres are within
                              ``factor * max(plate_diagonal)`` pixels of each
                              other are considered to belong to the same
                              vehicle.  Default 2.0 works well for typical
                              CCTV viewing angles where one vehicle can
                              produce multiple overlapping or nearby
                              detections.
        """
        self.tile_size = tile_size
        self.overlap_ratio = overlap_ratio
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.full_frame_pass = full_frame_pass
        self.full_frame_imgsz = full_frame_imgsz
        self.batch_size = batch_size
        self.vehicle_merge = vehicle_merge
        self.vehicle_proximity_factor = vehicle_proximity_factor

        self._yolo = YoloPlateDetector(device=device)

    # ------------------------------------------------------------------
    # BaseDetector interface
    # ------------------------------------------------------------------
    def load_model(self, model_path: str) -> None:
        self._yolo.load_model(model_path)

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        Slice *frame* into overlapping tiles, detect in GPU batches, translate
        coordinates back, merge with NMS, optionally deduplicate per-vehicle,
        and return full-frame boxes.

        **Adaptive resolution**: automatically selects the best strategy based
        on frame size relative to ``tile_size``:

        - Frame ≤ tile_size → single direct inference (no tiling overhead).
        - Frame ≤ 2× tile_size → full-frame pass only (few tiles, heavy overlap).
        - Frame > 2× tile_size → full tiled scan + optional full-frame pass.
        """
        h, w = frame.shape[:2]
        max_dim = max(h, w)

        # --- Adaptive resolution selection ---
        if max_dim <= self.tile_size:
            # Small frame (e.g. 480p, 720p): run direct inference, no tiling.
            logger.debug(
                f"Frame {w}×{h} ≤ tile_size {self.tile_size}: direct inference"
            )
            boxes = self._yolo.detect(
                frame,
                imgsz=max(320, (max_dim // 32) * 32),  # Round down to nearest 32
                conf=self.conf_threshold,
            )
            if self.vehicle_merge and len(boxes) > 1:
                boxes = self._merge_vehicle_plates(boxes, self.vehicle_proximity_factor)
            return boxes

        if max_dim <= self.tile_size * 2:
            # Mid-res frame (e.g. 1080p, 2K): full-frame pass at native res.
            logger.debug(
                f"Frame {w}×{h} ≤ 2× tile_size: full-frame pass only"
            )
            infer_size = max(640, (max_dim // 32) * 32)
            boxes = self._yolo.detect(
                frame,
                imgsz=infer_size,
                conf=self.conf_threshold,
            )
            if self.vehicle_merge and len(boxes) > 1:
                boxes = self._merge_vehicle_plates(boxes, self.vehicle_proximity_factor)
            return boxes

        # --- Large frame: full tiled scan ---
        stride = int(self.tile_size * (1.0 - self.overlap_ratio))
        all_boxes: list[BoundingBox] = []

        # 1. Collect all valid tiles and their coordinates
        tiles: list[np.ndarray] = []
        tile_coords: list[tuple[int, int]] = []

        for y_start in range(0, h, stride):
            for x_start in range(0, w, stride):
                x_end = min(x_start + self.tile_size, w)
                y_end = min(y_start + self.tile_size, h)

                tile = frame[y_start:y_end, x_start:x_end]

                # Skip tiny edge slivers (< 25% of tile area).
                if tile.shape[0] * tile.shape[1] < (self.tile_size ** 2) * 0.25:
                    continue

                tiles.append(tile)
                tile_coords.append((x_start, y_start))

        # 2. Process tiles in GPU batches
        for i in range(0, len(tiles), self.batch_size):
            batch = tiles[i : i + self.batch_size]
            batch_results = self._yolo.detect_batch(
                batch,
                imgsz=self.tile_size,
                conf=self.conf_threshold,
            )

            for j, tile_boxes in enumerate(batch_results):
                x_off, y_off = tile_coords[i + j]
                for box in tile_boxes:
                    all_boxes.append(
                        BoundingBox(
                            x1=box.x1 + x_off,
                            y1=box.y1 + y_off,
                            x2=box.x2 + x_off,
                            y2=box.y2 + y_off,
                            confidence=box.confidence,
                            class_id=box.class_id,
                            class_name=box.class_name,
                        )
                    )

        # 3. Optional full-frame pass (catches large/nearby plates)
        if self.full_frame_pass:
            ff_boxes = self._yolo.detect(
                frame,
                imgsz=self.full_frame_imgsz,
                conf=self.conf_threshold,
            )
            all_boxes.extend(ff_boxes)

        # 4. NMS merge
        merged = self._nms(all_boxes, self.iou_threshold)

        # 5. Vehicle-level deduplication (combine multiple plates from same vehicle)
        if self.vehicle_merge and len(merged) > 1:
            merged = self._merge_vehicle_plates(merged, self.vehicle_proximity_factor)

        logger.debug(
            f"Tiled detection: {len(tiles)} tiles → {len(all_boxes)} raw → {len(merged)} final"
        )
        return merged

    def get_config(self) -> dict[str, Any]:
        return {
            "type": "TiledPlateDetector",
            "tile_size": self.tile_size,
            "overlap_ratio": self.overlap_ratio,
            "conf_threshold": self.conf_threshold,
            "iou_threshold": self.iou_threshold,
            "full_frame_pass": self.full_frame_pass,
            "full_frame_imgsz": self.full_frame_imgsz,
            "batch_size": self.batch_size,
            "vehicle_merge": self.vehicle_merge,
            "vehicle_proximity_factor": self.vehicle_proximity_factor,
            "inner_detector": self._yolo.get_config(),
        }

    # ------------------------------------------------------------------
    # NMS implementation (no external dependency)
    # ------------------------------------------------------------------
    @staticmethod
    def _nms(
        boxes: list[BoundingBox],
        iou_threshold: float,
    ) -> list[BoundingBox]:
        """
        Greedy Non-Maximum Suppression on a flat list of BoundingBox.
        """
        if not boxes:
            return []

        sorted_boxes = sorted(boxes, key=lambda b: b.confidence, reverse=True)
        keep: list[BoundingBox] = []

        while sorted_boxes:
            best = sorted_boxes.pop(0)
            keep.append(best)
            remaining: list[BoundingBox] = []
            for other in sorted_boxes:
                if _iou(best, other) < iou_threshold:
                    remaining.append(other)
            sorted_boxes = remaining

        return keep

    # ------------------------------------------------------------------
    # Vehicle-level plate grouping
    # ------------------------------------------------------------------
    @staticmethod
    def _merge_vehicle_plates(
        boxes: list[BoundingBox],
        proximity_factor: float = 2.0,
    ) -> list[BoundingBox]:
        """
        Group nearby plate detections that likely belong to the same vehicle
        and keep only the highest-confidence box per group.

        Two plates are considered to be from the same vehicle if the Euclidean
        distance between their centres is less than
        ``proximity_factor * max(diagonal_a, diagonal_b)``.

        This catches:
        - Front & rear plates both visible (typical in angled CCTV views).
        - Slightly different crops of the same plate that survived NMS
          (IoU just below threshold due to coordinate rounding).

        Uses single-linkage clustering: if plate A is close to B, and B is
        close to C, then A-B-C are all in the same vehicle cluster.

        Returns:
            A filtered list with one BoundingBox per vehicle (highest confidence).
        """
        n = len(boxes)
        if n <= 1:
            return list(boxes)

        # Pre-compute centres and diagonals
        centres = []
        diagonals = []
        for b in boxes:
            cx = (b.x1 + b.x2) / 2.0
            cy = (b.y1 + b.y2) / 2.0
            diag = ((b.x2 - b.x1) ** 2 + (b.y2 - b.y1) ** 2) ** 0.5
            centres.append((cx, cy))
            diagonals.append(diag)

        # Union-Find for single-linkage clustering
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j in range(i + 1, n):
                dist = (
                    (centres[i][0] - centres[j][0]) ** 2
                    + (centres[i][1] - centres[j][1]) ** 2
                ) ** 0.5
                max_diag = max(diagonals[i], diagonals[j])
                if dist < proximity_factor * max_diag:
                    union(i, j)

        # Group boxes by cluster root
        clusters: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            clusters.setdefault(root, []).append(i)

        # Keep the highest-confidence box from each cluster
        result: list[BoundingBox] = []
        for idxs in clusters.values():
            best_idx = max(idxs, key=lambda i: boxes[i].confidence)
            result.append(boxes[best_idx])

        if len(result) < n:
            logger.info(
                f"Vehicle merge: {n} plates → {len(result)} unique vehicles"
            )

        return result


# ------------------------------------------------------------------
# IoU helper (module-level, shared by NMS)
# ------------------------------------------------------------------
def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """Compute Intersection-over-Union between two boxes."""
    inter_x1 = max(a.x1, b.x1)
    inter_y1 = max(a.y1, b.y1)
    inter_x2 = min(a.x2, b.x2)
    inter_y2 = min(a.y2, b.y2)

    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    if inter_area == 0.0:
        return 0.0

    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    return inter_area / (area_a + area_b - inter_area)
