"""
Central configuration for the CCTV Unified Surveillance MVP.

Loads settings from environment variables (see .env.example).
No business logic lives here -- just config values used across modules.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# --- Monkey-patch for Windows asyncio ProactorEventLoop ---
# Uvicorn on Windows overrides the event loop policy back to Proactor,
# which notoriously crashes with WinError 10054 when a client disconnects early.
if sys.platform == 'win32':
    try:
        from functools import wraps
        from asyncio.proactor_events import _ProactorBasePipeTransport

        def silence_connection_reset(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except (ConnectionResetError, OSError):
                    pass
            return wrapper

        _ProactorBasePipeTransport._call_connection_lost = silence_connection_reset(
            _ProactorBasePipeTransport._call_connection_lost
        )
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

# --- Mode toggle ---
# "mock" -> use local video files + seeded mock registry table
# "real" -> (future) use RTSP camera feeds + real registry API
MODE = os.getenv("MODE", "mock")

# --- Sentinel Camera Grid API ---
SENTINEL_API_HOST = os.getenv("SENTINEL_API_HOST", "https://cctv.corp8.cloud")
SENTINEL_API_KEY = os.getenv("SENTINEL_API_KEY")
SENTINEL_EMAIL = os.getenv("SENTINEL_EMAIL", "")

# --- Database ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "cctv_unified")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))

# --- API Security ---
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError(
        "API_KEY is not set. Generate one with: "
        "python -c \"import secrets; print(secrets.token_urlsafe(32))\" "
        "and put it in your .env file as API_KEY=... (see .env.example)."
    )
API_PORT = int(os.getenv("API_PORT", "8002"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")

# --- Distributed Processing ---
# Number of centralized GPU OCR workers to spawn. Each takes ~800MB VRAM.
OCR_WORKER_COUNT = int(os.getenv("OCR_WORKER_COUNT", "5"))

# --- Model paths ---
# Prefer custom trained model if present, fallback to models/plate_yolov8n.pt or yolov8n.pt
_default_trained_plate = BASE_DIR / "runs" / "detect" / "unified_alpr_v1-6" / "weights" / "best.pt"
_default_model_plate = BASE_DIR / "models" / "plate_yolov8n.pt"

if _default_trained_plate.exists():
    _plate_model_default = str(_default_trained_plate)
elif _default_model_plate.exists():
    _plate_model_default = str(_default_model_plate)
else:
    _plate_model_default = str(BASE_DIR / "yolov8n.pt")

YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", _plate_model_default)



# --- Tiled inference (SAHI-style) ---
TILE_SIZE = int(os.getenv("TILE_SIZE", "1280"))
TILE_OVERLAP = float(os.getenv("TILE_OVERLAP", "0.2"))
TILE_IOU_THRESHOLD = float(os.getenv("TILE_IOU_THRESHOLD", "0.5"))

# --- Hierarchical (two-stage) detector ---
# Stage 1 uses a COCO-pretrained model to find vehicles, then Stage 2
# runs the plate detector on native-resolution vehicle crops.
VEHICLE_MODEL_PATH = os.getenv(
    "VEHICLE_MODEL_PATH",
    str(BASE_DIR / "models" / "yolov8n.pt"),
)
# COCO class IDs: 2=car, 3=motorcycle, 5=bus, 7=truck
VEHICLE_CLASSES = [int(c) for c in os.getenv("VEHICLE_CLASSES", "2,3,5,7").split(",")]
VEHICLE_PADDING = float(os.getenv("VEHICLE_PADDING", "0.2"))  # 20% pad around vehicle box
USE_HIERARCHICAL = os.getenv("USE_HIERARCHICAL", "true").lower() in ("true", "1", "yes")

# --- Paths ---
MOCK_VIDEO_DIR = os.getenv("MOCK_VIDEO_DIR", str(BASE_DIR / "data" / "mock_videos"))
SEED_REGISTRY_CSV = os.getenv("SEED_REGISTRY_CSV", str(BASE_DIR / "data" / "seed_registry.csv"))
TEST_IMAGES_DIR = os.getenv("TEST_IMAGES_DIR", str(BASE_DIR / "test_images"))

# --- Streaming ---
MJPEG_FPS = int(os.getenv("MJPEG_FPS", "15"))
MJPEG_QUALITY = int(os.getenv("MJPEG_QUALITY", "70"))
HLS_SEGMENT_TIME = int(os.getenv("HLS_SEGMENT_TIME", "2"))
HLS_LIST_SIZE = int(os.getenv("HLS_LIST_SIZE", "5"))
STREAM_IDLE_TIMEOUT = int(os.getenv("STREAM_IDLE_TIMEOUT", "30"))
MAX_CONCURRENT_STREAMS = int(os.getenv("MAX_CONCURRENT_STREAMS", "100"))

# --- AI Copilot ---
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.1"))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))


def is_mock_mode() -> bool:
    """Convenience helper used throughout the codebase to branch mock/real behavior."""
    return MODE.lower() == "mock"


# --- Hardware Acceleration ---
# Set USE_GPU to "true" in your .env file when you have a capable GPU setup for YOLO.
USE_GPU_ENV = os.getenv("USE_GPU", "false").lower() in ("true", "1", "yes")

# Set OCR_USE_GPU to "true" in .env if you have paddlepaddle-gpu installed with CUDA.
OCR_USE_GPU_ENV = os.getenv("OCR_USE_GPU", "false").lower() in ("true", "1", "yes")

def should_use_gpu() -> bool:
    """
    Convenience helper used to decide whether to load YOLO models onto GPU or CPU.
    Returns True if USE_GPU is enabled in env and PyTorch detects CUDA.
    """
    if not USE_GPU_ENV:
        return False
    
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False

def should_ocr_use_gpu() -> bool:
    """
    Returns True if OCR_USE_GPU is enabled in .env and PaddlePaddle detects CUDA.
    Does NOT import torch, avoiding Windows DLL collisions in OCR workers.
    """
    if not OCR_USE_GPU_ENV:
        return False
    try:
        import paddle
        return bool(paddle.is_compiled_with_cuda())
    except Exception:
        return False


import re

def sanitize_url(url: str) -> str:
    """Mask embedded username and password in RTSP/HTTP URLs to prevent credential leakage in logs."""
    if not url or not isinstance(url, str):
        return url
    return re.sub(r'://([^:@/]+):([^@/]+)@', r'://\1:***@', url)

