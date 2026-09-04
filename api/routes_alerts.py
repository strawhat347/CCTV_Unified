"""
api/routes_alerts.py - REST endpoints for alerts.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from api.rbac import get_current_user, require_role

from api.schemas import Alert, InternalAlertPush
from api.ws_alerts import manager
from db import dao_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("/", response_model=List[Alert])
def get_recent_alerts(limit: int = Query(default=50, ge=1, le=500), user: dict = Depends(require_role(['admin', 'operator', 'auditor']))):
    return dao_alerts.get_unacknowledged_alerts(limit=limit)

@router.get("/all", response_model=List[Alert])
def get_all_alerts(limit: int = Query(default=200, ge=1, le=1000), user: dict = Depends(require_role(['admin', 'operator', 'auditor']))):
    return dao_alerts.get_all_alerts(limit=limit)

@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int, user: dict = Depends(require_role(['admin', 'operator']))):
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
    
    Security:
      - Origin header validation (CSWSH prevention) — only localhost origins accepted.
      - JWT access token required via ?token= query parameter.
      - Connection cap enforced by ConnectionManager (MAX_WS_CONNECTIONS).
    """
    # --- CSWSH Prevention: Validate Origin header ---
    import re
    origin = websocket.headers.get("origin", "")
    allowed_origin = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")
    if origin and not allowed_origin.match(origin):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    try:
        from api.auth import decode_token
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=1008, reason="Invalid token type")
            return
    except Exception:
        await websocket.close(code=1008, reason="Invalid token")
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
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)
