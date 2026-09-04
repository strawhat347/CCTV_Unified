"""
api/routes_cameras.py — Read-only routes wrapping db/dao_cameras.py + Bulk Import.
"""

from __future__ import annotations

import csv
import io
from typing import List, Optional  # noqa: UP035

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, BackgroundTasks
from api.rbac import get_current_user, require_role

from slowapi import Limiter
from slowapi.util import get_remote_address

from api.schemas import Camera, CameraCreate, CameraUpdate
from db.dao_cameras import (
    bulk_insert_cameras,
    delete_all_cameras,
    get_all_cameras,
    get_camera_by_id,
    delete_camera as dao_delete_camera,
    update_camera as dao_update_camera,
)

router = APIRouter(prefix="/cameras", tags=["cameras"])
limiter = Limiter(key_func=get_remote_address)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB, tune as needed

def verify_stream_url(url: str):
    import os, cv2
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Failed to connect to camera stream (timed out or unreachable)")
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise HTTPException(status_code=400, detail="Connected but failed to decode video frame")

@router.get("", response_model=List[Camera])
def list_cameras(
    status: Optional[str] = Query(default=None, description="Filter by status: active|inactive|error"),
    q: Optional[str] = Query(default=None, description="Search term for ID, name, or location"),
    limit: int = Query(default=100, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role(['admin', 'operator', 'auditor']))
):
    """GET /cameras  — all cameras, optionally filtered by status."""
    return get_all_cameras(status=status, q=q, limit=limit, offset=offset)


@router.get("/{camera_id}", response_model=Camera)
def get_camera(camera_id: int, user: dict = Depends(require_role(['admin', 'operator', 'auditor']))):
    """GET /cameras/{camera_id} — single camera or 404."""
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    return camera


@router.post("", response_model=dict)
@limiter.limit("10/minute")
def add_camera(request: Request, camera: CameraCreate, user: dict = Depends(require_role(['admin']))):
    """POST /cameras — add a single camera."""
    verify_stream_url(camera.stream_url)
    cameras_data = [(
        camera.name,
        camera.location,
        camera.department,
        camera.department_id,
        camera.city,
        camera.district,
        camera.latitude,
        camera.longitude,
        camera.camera_type,
        camera.connectivity,
        camera.storage_details,
        camera.stream_url,
        camera.status.value,  # unwrap the enum: driver param conversion dispatches
                               # on exact type name, not isinstance(str), so pass
                               # the plain str value rather than the enum member
    )]
    inserted = bulk_insert_cameras(cameras_data)
    return {"status": "success", "inserted": inserted}

@router.delete("")
def delete_cameras(confirm: Optional[str] = Query(None), user: dict = Depends(require_role(['admin']))):
    """
    DELETE /cameras — purge all cameras.

    Requires ?confirm=DELETE_ALL_CAMERAS. Not real role-based auth (there's no
    role system here, and this is a hackathon MVP — that's a fine trade-off),
    but it stops a single fat-fingered or scripted call from wiping everything.
    """
    if confirm != "DELETE_ALL_CAMERAS":
        raise HTTPException(status_code=400, detail="Pass ?confirm=DELETE_ALL_CAMERAS to proceed.")
    deleted_count = delete_all_cameras()
    return {"status": "success", "deleted": deleted_count}


@router.delete("/{camera_id}")
def delete_single_camera(camera_id: int, user: dict = Depends(require_role(['admin']))):
    """DELETE /cameras/{camera_id} — delete a single camera."""
    success = dao_delete_camera(camera_id)
    if not success:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "success"}


@router.put("/{camera_id}")
def update_single_camera(camera_id: int, camera_update: CameraUpdate, user: dict = Depends(require_role(['admin']))):
    """PUT /cameras/{camera_id} — update a single camera."""
    if camera_update.stream_url is not None:
        verify_stream_url(camera_update.stream_url)
        
    # mode="json" unwraps CameraStatus to its plain string .value; the DAO
    # builds a raw parameterized query and shouldn't be handed an enum member.
    update_data = camera_update.model_dump(exclude_unset=True, mode="json")
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields provided for update")
        
    success = dao_update_camera(camera_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "success"}


def background_verify_bulk_streams(cameras_to_test):
    import os, cv2
    from db.dao_cameras import get_all_cameras, update_camera_status
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;2000000"
    
    all_cams = get_all_cameras(limit=10000)
    for cam_info in cameras_to_test:
        matching_cams = [c for c in all_cams if c['name'] == cam_info['name'] and c['stream_url'] == cam_info['stream_url']]
        if not matching_cams:
            continue
            
        cap = cv2.VideoCapture(cam_info['stream_url'], cv2.CAP_FFMPEG)
        works = False
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                works = True
        cap.release()
        
        if not works:
            for mc in matching_cams:
                update_camera_status(mc['camera_id'], 'error')


@router.post("/bulk")
@limiter.limit("3/minute")
async def import_cameras_bulk(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...), user: dict = Depends(require_role(['admin']))):
    """POST /cameras/bulk — import cameras from CSV."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large.")
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid file encoding. Please upload a UTF-8 CSV.")
        
    reader = csv.DictReader(io.StringIO(text))
    cameras_data = []
    for row in reader:
        name = row.get("name", "").strip()
        stream_url = row.get("stream_url", "").strip()
        if not name or not stream_url:
            continue
            
        ALLOWED_PROTOCOLS = ("rtsp://", "rtsps://", "http://", "https://")
        if not any(stream_url.startswith(proto) for proto in ALLOWED_PROTOCOLS):
            continue
            
        location = row.get("location", "").strip()
        department = row.get("department", "").strip()
        city = row.get("city", "").strip()
        district = row.get("district", "").strip()
        
        if not location or not department or not city or not district:
            continue
            
        try:
            department_id = int(row.get("department_id")) if row.get("department_id") else None
            if department_id is None:
                continue
        except ValueError:
            continue

        try:
            latitude = float(row.get("latitude"))
            longitude = float(row.get("longitude"))
        except (ValueError, TypeError):
            continue
            
        camera_type = row.get("camera_type") or None
        connectivity = row.get("connectivity") or None
        storage_details = row.get("storage_details") or None
        status = row.get("status") or "active"
        if status not in ("active", "inactive", "error"):
            status = "active"
            
        cameras_data.append((
            name, location, department, department_id, city, district, latitude, longitude,
            camera_type, connectivity, storage_details, stream_url, status
        ))
        
    if not cameras_data:
        raise HTTPException(status_code=400, detail="No valid camera rows found in CSV.")
        
    inserted = bulk_insert_cameras(cameras_data)
    
    cameras_to_test = [{'name': c[0], 'stream_url': c[11]} for c in cameras_data]
    background_tasks.add_task(background_verify_bulk_streams, cameras_to_test)
    
    return {"status": "success", "inserted": inserted}


@router.get("/{camera_id}/test", response_model=dict)
def test_camera_connection(camera_id: int, user: dict = Depends(require_role(['admin', 'operator']))):
    """Probes the camera stream to verify if it is alive, measuring latency and resolution."""
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
        
    url = camera["stream_url"]
    import os, time
    import cv2
    
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    start_time = time.perf_counter()
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        elapsed = round((time.perf_counter() - start_time) * 1000, 1)
        return {
            "camera_id": camera_id,
            "name": camera.get("name"),
            "alive": False,
            "latency_ms": elapsed,
            "error": "Failed to connect to camera stream (timed out or unreachable)"
        }
        
    ret, frame = cap.read()
    total_time = round((time.perf_counter() - start_time) * 1000, 1)
    if not ret or frame is None:
        cap.release()
        return {
            "camera_id": camera_id,
            "name": camera.get("name"),
            "alive": False,
            "latency_ms": total_time,
            "error": "Connected but failed to decode video frame"
        }
        
    h, w = frame.shape[:2]
    fps = round(cap.get(cv2.CAP_PROP_FPS) or 0.0, 1)
    cap.release()
    
    return {
        "camera_id": camera_id,
        "name": camera.get("name"),
        "alive": True,
        "latency_ms": total_time,
        "resolution": f"{w}x{h}",
        "fps": fps
    }

