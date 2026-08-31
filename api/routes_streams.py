"""
api/routes_streams.py — Live video streaming endpoints for the Video Wall.

Provides two streaming modes:
  1. HLS (primary, future-proof) — ffmpeg transcodes source → H.264 HLS segments
     served via FastAPI. Low bandwidth, CDN-ready, industry standard.
  2. MJPEG (fallback) — OpenCV reads frames, JPEG-encodes, streams as
     multipart/x-mixed-replace. Works without ffmpeg.

StreamManager maintains ONE capture/process per camera shared across all
viewers. When the last viewer disconnects, the source is released after
a grace period.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import io
from PIL import Image

# ── MJPEG Stream Source (fallback mode) ───────────────────────────────────────

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

import config
from db.dao_cameras import get_camera_by_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api.routes_streams")

router = APIRouter(prefix="/streams", tags=["streams"])

# ── Configuration ─────────────────────────────────────────
MJPEG_FPS = 15           # Max frames per second for MJPEG mode
MJPEG_QUALITY = 70       # JPEG quality (0-100) for MJPEG mode
HLS_SEGMENT_TIME = 2     # Seconds per HLS segment
HLS_LIST_SIZE = 5        # Number of segments in the playlist
STREAM_IDLE_TIMEOUT = 30 # Seconds to keep stream alive after last viewer leaves
MAX_CONCURRENT_STREAMS = 8  # Max distinct cameras streamed at once (per mode)
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

if FFMPEG_AVAILABLE:
    logger.info("ffmpeg found — HLS streaming mode available.")
else:
    logger.warning("ffmpeg not found — falling back to MJPEG streaming mode.")


# ═══════════════════════════════════════════════════════════
#  MJPEG Stream Source (fallback mode)
# ═══════════════════════════════════════════════════════════

class MJPEGStreamSource:
    """
    Hybrid MJPEG source that uses Pillow for image‑directory mock data
    and OpenCV for real video files / RTSP streams.
    This preserves high performance and accuracy for live streams while
    avoiding the NumPy/ABI issue for mock image sequences.
    """

    def __init__(self, camera_id: int, source_url: str):
        self.camera_id = camera_id
        self.source_url = source_url
        self.viewer_count = 0
        self.last_viewer_left_at: Optional[float] = None

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[bytes] = None  # JPEG bytes for both backends

        # Detect backend
        self._use_opencv = False
        if os.path.isdir(self.source_url):
            # Pillow backend – load ordered image files
            files = sorted(
                f for f in os.listdir(self.source_url)
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            )
            if not files:
                raise RuntimeError(f"Image directory for camera {self.camera_id} is empty: {self.source_url}")
            self._image_paths = [os.path.join(self.source_url, f) for f in files]
        else:
            # Assume video file or RTSP URL – use OpenCV
            self._use_opencv = True
            self._image_paths = []  # not used

        self._index = 0

    def start(self):
        """Start the background thread (or OpenCV capture)."""
        if self._running:
            return

        if self._use_opencv:
            try:
                import cv2  # type: ignore
                self._cv2 = cv2
            except Exception as e:
                raise RuntimeError(f"OpenCV backend required but cannot be imported: {e}")

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info(f"[MJPEG] Started stream source for camera {self.camera_id} (backend={'opencv' if self._use_opencv else 'pillow'})")

    def _read_loop(self):
        """Read frames from the selected backend and store JPEG bytes."""
        if self._use_opencv:
            # Follow Sentinel Guide rules: Force TCP to bypass UDP firewall issues
            if self.source_url.startswith("rtsp://"):
                # Use a 5 second timeout to fail fast on unreachable streams
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
                self._cap = self._cv2.VideoCapture(self.source_url, self._cv2.CAP_FFMPEG)
            else:
                self._cap = self._cv2.VideoCapture(self.source_url)
                
            if not getattr(self, "_cap", None) or not self._cap.isOpened():
                logger.error(f"Cannot open video source for camera {self.camera_id}: {self.source_url}")
                self._running = False
                return

        while self._running:
            if self._use_opencv:
                ok, frame = self._cap.read()  # type: ignore
                if not ok:
                    # If it's a file, loop back to start
                    if os.path.isfile(self.source_url):
                        self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)  # type: ignore
                        ok, frame = self._cap.read()
                    if not ok:
                        time.sleep(0.1)
                        continue
                # Encode to JPEG bytes
                ret, buf = self._cv2.imencode('.jpg', frame, [self._cv2.IMWRITE_JPEG_QUALITY, MJPEG_QUALITY])  # type: ignore
                jpeg_bytes = buf.tobytes() if ret else None
                with self._lock:
                    self._latest_frame = jpeg_bytes
                time.sleep(1.0 / MJPEG_FPS)
            else:
                # Pillow backend – read next image
                path = self._image_paths[self._index]
                try:
                    with Image.open(path) as img:
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=MJPEG_QUALITY)
                        jpeg_bytes = buf.getvalue()
                except Exception as e:
                    logger.error(f"[MJPEG] Error loading image for camera {self.camera_id}: {e}")
                    jpeg_bytes = None
                with self._lock:
                    self._latest_frame = jpeg_bytes
                self._index = (self._index + 1) % len(self._image_paths)
                time.sleep(1.0 / MJPEG_FPS)

    def get_jpeg(self) -> Optional[bytes]:
        """Return the most recent JPEG bytes (thread‑safe)."""
        with self._lock:
            return self._latest_frame

    def stop(self):
        """Stop the background thread and release resources."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if getattr(self, "_use_opencv", False) and getattr(self, "_cap", None):
            try:
                self._cap.release()
            except Exception:
                pass
        logger.info(f"[MJPEG] Stopped stream source for camera {self.camera_id}")




# ═══════════════════════════════════════════════════════════
#  HLS Stream Source (primary mode)
# ═══════════════════════════════════════════════════════════

class HLSStreamSource:
    """
    Manages an ffmpeg subprocess that transcodes a video source into
    HLS segments (.ts) and a playlist (.m3u8) in a temporary directory.
    """

    def __init__(self, camera_id: int, source_url: str):
        self.camera_id = camera_id
        self.source_url = source_url
        self.viewer_count = 0
        self.last_viewer_left_at: Optional[float] = None

        self._process: Optional[subprocess.Popen] = None
        self._output_dir: Optional[Path] = None
        self._running = False

    @property
    def output_dir(self) -> Optional[Path]:
        return self._output_dir

    @property
    def playlist_path(self) -> Optional[Path]:
        if self._output_dir:
            return self._output_dir / "stream.m3u8"
        return None

    def start(self):
        """Start the ffmpeg transcoding process."""
        if self._running:
            return

        # Create a temp directory for HLS segments
        self._output_dir = Path(tempfile.mkdtemp(prefix=f"cctv_hls_cam{self.camera_id}_"))

        playlist = str(self._output_dir / "stream.m3u8")
        segment_pattern = str(self._output_dir / "seg_%05d.ts")

        # Build ffmpeg command
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]

        # Input: loop if it's a local file (mock mode)
        if os.path.isfile(self.source_url):
            cmd += ["-stream_loop", "-1", "-re"]

        cmd += ["-i", self.source_url]

        # Output: H.264 HLS with low-latency tuning
        cmd += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-g", "30",                 # Keyframe every 30 frames
            "-sc_threshold", "0",        # Disable scene-change detection for consistent segments
            "-an",                       # No audio (CCTV)
            "-f", "hls",
            "-hls_time", str(HLS_SEGMENT_TIME),
            "-hls_list_size", str(HLS_LIST_SIZE),
            "-hls_flags", "delete_segments+append_list+independent_segments",
            "-hls_segment_filename", segment_pattern,
            playlist,
        ]

        logger.info(f"[HLS] Starting ffmpeg for camera {self.camera_id}: {' '.join(cmd)}")

        # Start ffmpeg as a background process
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._running = True
        logger.info(f"[HLS] ffmpeg started for camera {self.camera_id} (PID: {self._process.pid})")

    def stop(self):
        """Stop the ffmpeg process and clean up temp files."""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        # Clean up temp directory
        if self._output_dir and self._output_dir.exists():
            try:
                shutil.rmtree(self._output_dir)
            except OSError as e:
                logger.warning(f"[HLS] Failed to clean up temp dir: {e}")
            self._output_dir = None

        logger.info(f"[HLS] Stopped stream for camera {self.camera_id}")

    def is_alive(self) -> bool:
        """Check if the ffmpeg process is still running."""
        return self._process is not None and self._process.poll() is None


# ═══════════════════════════════════════════════════════════
#  Stream Manager (singleton, manages all camera streams)
# ═══════════════════════════════════════════════════════════

class StreamManager:
    """
    Central manager for all active camera streams.
    Maintains one stream source per camera, shared across all viewers.
    Auto-cleans idle streams after STREAM_IDLE_TIMEOUT seconds.
    """

    def __init__(self):
        self._hls_streams: dict[int, HLSStreamSource] = {}
        self._mjpeg_streams: dict[int, MJPEGStreamSource] = {}
        self._lock = threading.Lock()

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    @property
    def use_hls(self) -> bool:
        return FFMPEG_AVAILABLE

    def get_stream_mode(self) -> str:
        return "hls" if self.use_hls else "mjpeg"

    def _get_camera_source_url(self, camera_id: int) -> str:
        """Look up the camera's stream_url from the database."""
        camera = get_camera_by_id(camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
        
        url = camera["stream_url"]
        if url.startswith("mock://"):
            base_dir = Path(__file__).parent.parent / "data" / "mock_videos"
            if camera_id == 1:
                return str(base_dir / "camera_1_gate.mp4")
            elif camera_id == 2:
                return str(base_dir / "camera_2_lobby.mp4")
            else:
                return str(base_dir / "camera_3_test.mp4")
                
        return url

    # ── HLS methods ───────────────────────────────────────

    def get_hls_stream(self, camera_id: int) -> HLSStreamSource:
        """Get or create an HLS stream for a camera."""
        with self._lock:
            if camera_id not in self._hls_streams and len(self._hls_streams) >= MAX_CONCURRENT_STREAMS:
                raise HTTPException(status_code=503, detail="Too many active streams")
            if camera_id not in self._hls_streams:
                source_url = self._get_camera_source_url(camera_id)
                stream = HLSStreamSource(camera_id, source_url)
                stream.start()
                self._hls_streams[camera_id] = stream
            stream = self._hls_streams[camera_id]
            stream.viewer_count += 1
            stream.last_viewer_left_at = None
            return stream

    def release_hls_viewer(self, camera_id: int):
        """Decrement viewer count; mark for cleanup if zero."""
        with self._lock:
            if camera_id in self._hls_streams:
                stream = self._hls_streams[camera_id]
                stream.viewer_count = max(0, stream.viewer_count - 1)
                if stream.viewer_count == 0:
                    stream.last_viewer_left_at = time.time()

    # ── MJPEG methods ─────────────────────────────────────

    def get_mjpeg_stream(self, camera_id: int) -> MJPEGStreamSource:
        """Get or create an MJPEG stream for a camera."""
        with self._lock:
            if camera_id not in self._mjpeg_streams and len(self._mjpeg_streams) >= MAX_CONCURRENT_STREAMS:
                raise HTTPException(status_code=503, detail="Too many active streams")
            if camera_id not in self._mjpeg_streams:
                source_url = self._get_camera_source_url(camera_id)
                stream = MJPEGStreamSource(camera_id, source_url)
                stream.start()
                self._mjpeg_streams[camera_id] = stream
            stream = self._mjpeg_streams[camera_id]
            stream.viewer_count += 1
            stream.last_viewer_left_at = None
            return stream

    def release_mjpeg_viewer(self, camera_id: int):
        """Decrement viewer count; mark for cleanup if zero."""
        with self._lock:
            if camera_id in self._mjpeg_streams:
                stream = self._mjpeg_streams[camera_id]
                stream.viewer_count = max(0, stream.viewer_count - 1)
                if stream.viewer_count == 0:
                    stream.last_viewer_left_at = time.time()

    # ── Cleanup ───────────────────────────────────────────

    def _cleanup_loop(self):
        """Periodically stop streams with no viewers."""
        while True:
            time.sleep(10)
            now = time.time()
            with self._lock:
                # Clean HLS streams
                to_remove_hls = []
                for cid, stream in self._hls_streams.items():
                    if (stream.viewer_count == 0 and
                        stream.last_viewer_left_at is not None and
                        now - stream.last_viewer_left_at > STREAM_IDLE_TIMEOUT):
                        stream.stop()
                        to_remove_hls.append(cid)
                for cid in to_remove_hls:
                    del self._hls_streams[cid]

                # Clean MJPEG streams
                to_remove_mjpeg = []
                for cid, stream in self._mjpeg_streams.items():
                    if (stream.viewer_count == 0 and
                        stream.last_viewer_left_at is not None and
                        now - stream.last_viewer_left_at > STREAM_IDLE_TIMEOUT):
                        stream.stop()
                        to_remove_mjpeg.append(cid)
                for cid in to_remove_mjpeg:
                    del self._mjpeg_streams[cid]

    def shutdown(self):
        """Stop all streams. Called on app shutdown."""
        with self._lock:
            for stream in self._hls_streams.values():
                stream.stop()
            self._hls_streams.clear()
            for stream in self._mjpeg_streams.values():
                stream.stop()
            self._mjpeg_streams.clear()


# Module-level singleton
stream_manager = StreamManager()


# ═══════════════════════════════════════════════════════════
#  API Endpoints
# ═══════════════════════════════════════════════════════════

def _verify_stream_api_key(api_key: str):
    """Verify API key from query param (browsers can't set headers on <img>/<video> src)."""
    import secrets
    if not api_key or not secrets.compare_digest(api_key, config.API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")


@router.get("/mode")
def get_stream_mode():
    """GET /streams/mode — returns the active streaming mode (hls or mjpeg)."""
    return {"mode": stream_manager.get_stream_mode(), "ffmpeg_available": FFMPEG_AVAILABLE}


@router.get("/{camera_id}/snapshot")
def get_snapshot(camera_id: int, api_key: str = Query(...)):
    """
    GET /streams/{camera_id}/snapshot?api_key=... — single JPEG frame.
    Useful for thumbnails in the camera panel.
    """
    _verify_stream_api_key(api_key)

    # Always use MJPEG source for snapshots (lighter than spinning up ffmpeg)
    try:
        stream = stream_manager.get_mjpeg_stream(camera_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    try:
        # Wait briefly for the first frame
        for _ in range(50):
            jpeg = stream.get_jpeg()
            if jpeg:
                return Response(content=jpeg, media_type="image/jpeg")
            time.sleep(0.1)
        raise HTTPException(status_code=503, detail="No frame available yet")
    finally:
        stream_manager.release_mjpeg_viewer(camera_id)


@router.get("/{camera_id}/mjpeg")
def mjpeg_stream(camera_id: int, api_key: str = Query(...)):
    """
    GET /streams/{camera_id}/mjpeg?api_key=... — MJPEG stream.
    Used as fallback when ffmpeg is not available, or directly if preferred.
    """
    _verify_stream_api_key(api_key)
    try:
        stream = stream_manager.get_mjpeg_stream(camera_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    def generate():
        try:
            while True:
                jpeg = stream.get_jpeg()
                if jpeg:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n"
                        b"\r\n" + jpeg + b"\r\n"
                    )
                time.sleep(1.0 / MJPEG_FPS)
        except GeneratorExit:
            stream_manager.release_mjpeg_viewer(camera_id)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/{camera_id}/hls/stream.m3u8")
def hls_playlist(camera_id: int, api_key: str = Query(...)):
    """
    GET /streams/{camera_id}/hls/stream.m3u8?api_key=... — HLS playlist.
    Returns the .m3u8 manifest file for the HLS player.
    """
    _verify_stream_api_key(api_key)

    if not FFMPEG_AVAILABLE:
        raise HTTPException(status_code=503, detail="HLS not available — ffmpeg not found")

    try:
        stream = stream_manager.get_hls_stream(camera_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Wait for ffmpeg to produce the first playlist
    playlist_path = stream.playlist_path
    for _ in range(100):  # Wait up to 10 seconds
        if playlist_path and playlist_path.exists() and playlist_path.stat().st_size > 0:
            # Read and return playlist content (don't use FileResponse to avoid caching)
            content = playlist_path.read_text()
            return Response(
                content=content,
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )
        time.sleep(0.1)

    raise HTTPException(status_code=503, detail="HLS playlist not ready yet — ffmpeg may still be starting")


@router.get("/{camera_id}/hls/release")
def hls_release(camera_id: int, api_key: str = Query(...)):
    """
    GET /streams/{camera_id}/hls/release?api_key=... — Release viewer slot.
    Called by the frontend when a video cell is unloaded.
    """
    _verify_stream_api_key(api_key)
    stream_manager.release_hls_viewer(camera_id)
    return {"status": "released"}


@router.get("/{camera_id}/hls/{filename}")
def hls_segment(camera_id: int, filename: str, api_key: Optional[str] = None):
    """
    GET /streams/{camera_id}/hls/{filename}?api_key=... — HLS segment file (.ts).
    api_key is optional because HLS clients don't pass query params to segments.
    """
    if api_key:
        _verify_stream_api_key(api_key)

    if not FFMPEG_AVAILABLE:
        raise HTTPException(status_code=503, detail="HLS not available — ffmpeg not found")

    # Security: only allow .ts files, prevent path traversal
    if not filename.endswith(".ts") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid segment filename")

    with stream_manager._lock:
        stream = stream_manager._hls_streams.get(camera_id)

    if not stream or not stream.output_dir:
        raise HTTPException(status_code=404, detail="Stream not active")

    # Defense in depth: even though the filename check above already blocks
    # slashes and ".." separators, resolve the final path and confirm it's
    # still contained within the stream's own output directory before
    # serving it.
    base_dir = stream.output_dir.resolve()
    segment_path = (base_dir / filename).resolve()
    if not str(segment_path).startswith(str(base_dir) + os.sep) and segment_path != base_dir:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not segment_path.exists():
        raise HTTPException(status_code=404, detail="Segment not found")

    return FileResponse(
        str(segment_path),
        media_type="video/MP2T",
        headers={
            "Cache-Control": "no-cache",
        },
    )
