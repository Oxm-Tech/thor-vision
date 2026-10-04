"""Estado y eventos de los dispositivos IoT (Tuya por MQTT, solo lectura)."""
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _l(request: Request):
    m = getattr(request.app.state, "iot", None)
    if m is None:
        raise HTTPException(503, "integracion IoT apagada")
    return m


@router.get("/api/iot/devices")
def devices(request: Request):
    m = _l(request)
    return {"status": m.status, "devices": m.snapshot_state()}


@router.get("/api/iot/events")
def events(request: Request, device_id: str = "", limit: int = 100):
    return {"events": _l(request).recent(device_id, limit)}
