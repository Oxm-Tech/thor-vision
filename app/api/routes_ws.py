import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.utils.gpu_probe import get_system_metrics

router = APIRouter()

_clients: list[WebSocket] = []


async def broadcast(event: dict) -> None:
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.remove(ws)


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    _clients.append(websocket)
    manager = websocket.app.state.capture_manager
    store = getattr(websocket.app.state, "detection_store", None)
    try:
        while True:
            await asyncio.sleep(3)
            try:
                payload = {
                    "type": "stats_update",
                    "ts": time.time(),
                    "summary": manager.summary(),
                    "cameras": manager.get_all_stats(),
                    "system": get_system_metrics(),
                    "detections": store.as_api() if store else {},
                    "total_persons": store.total_persons() if store else 0,
                }
                await websocket.send_text(json.dumps(payload))
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _clients:
            _clients.remove(websocket)
