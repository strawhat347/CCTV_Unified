import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients.sentinel_client import SentinelClient
from db.dao_cameras import insert_camera
from db.connection_pool import get_connection
import config

def sync():
    print(f"Connecting to Sentinel Grid at {config.SENTINEL_API_HOST}...")
    client = SentinelClient(config.SENTINEL_API_HOST, config.SENTINEL_API_KEY, config.SENTINEL_EMAIL)
    cameras = client.get_cameras()
    
    if not cameras:
        print("No cameras found or failed to connect.")
        return
        
    print(f"Fetched {len(cameras)} cameras from Sentinel. Inserting into database...")
    
    # First, optional: clear out the old mock cameras so they don't clutter
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cameras")
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Failed to clear old cameras: {e}")
    finally:
        conn.close()
    
    for cam in cameras:
        name = cam.get('location', f"Sentinel Camera {cam.get('id')}")
        stream_url = cam.get('rtsp_url') or cam.get('url')
        
        insert_camera(
            name=name,
            stream_url=stream_url,
            location=cam.get('location', 'Sentinel Grid'),
            status="active"
        )
        print(f" [OK] Added {name} ({stream_url})")

if __name__ == "__main__":
    sync()
