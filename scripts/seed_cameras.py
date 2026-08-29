"""
scripts/seed_cameras.py — Seed the cameras table with mock camera entries
mapped to the existing mock video files for Video Wall demo.

Run from project root:
    python -m scripts.seed_cameras
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection_pool import get_pool, get_connection
from db.dao_cameras import insert_camera, get_all_cameras

MOCK_CAMERAS = [
    {
        "name": "Gate 1 — Main Entrance",
        "location": "Gandhinagar Secretariat",
        "department": "Police",
        "latitude": 23.2156,
        "longitude": 72.6369,
        "camera_type": "ANPR",
        "connectivity": "Fiber",
        "storage_details": "Local 7-day",
        "stream_url": str(Path("data/mock_videos/camera_1_gate.mp4").resolve()),
        "status": "active",
    },
    {
        "name": "Lobby — Visitor Entry",
        "location": "Sector 11 Office Complex",
        "department": "Civil Supplies",
        "latitude": 23.2100,
        "longitude": 72.6400,
        "camera_type": "Dome",
        "connectivity": "LAN",
        "storage_details": "Cloud 15-day",
        "stream_url": str(Path("data/mock_videos/camera_2_lobby.mp4").resolve()),
        "status": "active",
    },
    {
        "name": "Parking Zone A",
        "location": "Sargasan Cross Road",
        "department": "RTO",
        "latitude": 23.1800,
        "longitude": 72.6200,
        "camera_type": "PTZ",
        "connectivity": "4G",
        "storage_details": "Local 7-day",
        "stream_url": str(Path("data/mock_videos/camera_3_test.mp4").resolve()),
        "status": "active",
    },
    {
        "name": "Highway Overpass — NH48",
        "location": "Ahmedabad RTO Circle",
        "department": "Police",
        "latitude": 23.0600,
        "longitude": 72.5800,
        "camera_type": "ANPR",
        "connectivity": "Fiber",
        "storage_details": "Cloud 15-day",
        "stream_url": str(Path("data/mock_videos/camera_3_test_2.mp4").resolve()),
        "status": "active",
    },
]


def seed():
    """Insert mock cameras if the table is empty or only has one row."""
    get_pool()  # Initialize connection pool

    existing = get_all_cameras()
    if len(existing) >= 4:
        print(f"✓ Cameras table already has {len(existing)} rows — skipping seed.")
        for cam in existing:
            print(f"  [{cam['camera_id']}] {cam['name']} ({cam['status']})")
        return

    print(f"Seeding {len(MOCK_CAMERAS)} mock cameras...")
    for cam_data in MOCK_CAMERAS:
        # Check if a camera with this name already exists
        already = [c for c in existing if c["name"] == cam_data["name"]]
        if already:
            print(f"  ⤳ Skipping '{cam_data['name']}' (already exists)")
            continue

        cam_id = insert_camera(**cam_data)
        print(f"  ✓ Inserted camera_id={cam_id}: {cam_data['name']}")

    # Verify
    all_cams = get_all_cameras()
    print(f"\n✓ Cameras table now has {len(all_cams)} rows:")
    for cam in all_cams:
        print(f"  [{cam['camera_id']}] {cam['name']} — {cam['status']}")


if __name__ == "__main__":
    seed()
