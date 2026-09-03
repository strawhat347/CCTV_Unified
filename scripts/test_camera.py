"""
scripts/test_camera.py — Probe a camera stream to check if it is responding.

Usage:
    python scripts/test_camera.py <camera_id>
    python scripts/test_camera.py <stream_url>

Examples:
    python scripts/test_camera.py 1
    python scripts/test_camera.py rtsp://103.250.160.189:8554/stream/cam01
"""

import sys
import os
import time
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force TCP transport and 5-second timeout for fast failure
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
import cv2
from config import sanitize_url

def probe_camera(target: str):
    url = target
    camera_name = None

    # Check if target is a camera ID
    if target.isdigit():
        camera_id = int(target)
        try:
            from db.dao_cameras import get_camera_by_id
            cam = get_camera_by_id(camera_id)
            if not cam:
                print(f"[ERROR] Camera #{camera_id} not found in database.")
                return False
            url = cam["stream_url"]
            camera_name = cam.get("name", f"Camera #{camera_id}")
            print(f"[*] Probing Camera #{camera_id}: '{camera_name}'")
        except Exception as e:
            print(f"[WARNING] Could not query database ({e}). Treating '{target}' as raw target.")
    else:
        print(f"[*] Probing Stream URL directly...")

    print(f"[*] Target URL : {sanitize_url(url)}")
    print(f"[*] Connecting (timeout: 5s, transport: TCP)...")

    start_time = time.perf_counter()
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        elapsed = (time.perf_counter() - start_time) * 1000
        print(f"\n[FAILED] Camera is NOT responding (failed after {elapsed:.0f}ms).")
        print("Possible causes:")
        print("  1. Camera is offline or powered off.")
        print("  2. Incorrect IP, port, or RTSP path.")
        print("  3. Authentication failed (bad username/password).")
        print("  4. Firewall / router is blocking TCP port.")
        return False

    connect_time = (time.perf_counter() - start_time) * 1000
    print(f"[+] Handshake successful in {connect_time:.0f}ms! Fetching test frame...")

    read_start = time.perf_counter()
    ret, frame = cap.read()
    read_time = (time.perf_counter() - read_start) * 1000

    if not ret or frame is None:
        print(f"\n[WARNING] Connected, but could NOT read video frame (codec error or empty stream).")
        cap.release()
        return False

    h, w = frame.shape[:2]
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    cap.release()

    total_time = connect_time + read_time
    print(f"\n==========================================")
    print(f" [SUCCESS] Camera is ALIVE and responding!")
    print(f"==========================================")
    print(f"  - Response Latency : {total_time:.0f} ms (Handshake: {connect_time:.0f}ms, Frame decode: {read_time:.0f}ms)")
    print(f"  - Resolution       : {w} x {h} pixels")
    print(f"  - Stream FPS       : {fps:.1f}")
    print(f"  - Frame Quality    : Valid {frame.dtype} frame captured successfully")
    print(f"==========================================\n")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_camera.py <camera_id_or_url>")
        print("Example: python scripts/test_camera.py 1")
        sys.exit(1)

    success = probe_camera(sys.argv[1].strip())
    sys.exit(0 if success else 1)
