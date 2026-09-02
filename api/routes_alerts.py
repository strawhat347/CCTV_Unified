"""
api/routes_alerts.py - REST endpoints for alerts.
"""
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from api.schemas import Alert, InternalAlertPush
from api.ws_alerts import manager
from db import dao_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("/", response_model=List[Alert])
def get_recent_alerts(limit: int = Query(default=50, ge=1, le=500)):
    return dao_alerts.get_unacknowledged_alerts(limit=limit)

@router.get("/all", response_model=List[Alert])
def get_all_alerts(limit: int = Query(default=200, ge=1, le=1000)):
    return dao_alerts.get_all_alerts(limit=limit)

@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int):
    success = dao_alerts.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acknowledged"}

@router.post("/internal/push")
async def internal_push_alert(alert_data: InternalAlertPush):
    """
    Called by alerting/alert_dispatcher.py (running in pipeline processes)
    to broadcast an alert to all connected WebSocket clients.

    Authenticated via the global X-API-Key middleware.
    """
    # mode="json" so created_at (a datetime) serializes to an ISO string
    # WebSocket.send_json() can't encode a raw datetime object.
    payload = {
        "type": "alert",
        "data": alert_data.model_dump(mode="json")
    }
    await manager.broadcast_message(payload)
    return {"status": "broadcasted"}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for the Desktop GUI client to receive real-time alerts.
    """
    api_key = websocket.query_params.get("api_key")
    import secrets
    import config
    if not api_key or not secrets.compare_digest(api_key, config.API_KEY):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    connected = await manager.connect(websocket)
    if not connected:
        # Already closed (with code 1013) by manager.connect() — server is
        # at MAX_WS_CONNECTIONS capacity.
        return
    try:
        while True:
            # Keep connection alive, wait for client to disconnect
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
