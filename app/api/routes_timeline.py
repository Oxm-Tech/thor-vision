"""Linea de tiempo de alertas: eventos con tipo y captura para el carril general y uno por camara."""
import json
import time
from typing import Optional

from fastapi import APIRouter, Request

router = APIRouter()

_MAX_EVENTS = 4000
_MAX_SPAN_S = 8 * 86400


@router.get("/api/timeline")
def timeline(request: Request, since: Optional[float] = None, until: Optional[float] = None):
    until = until or time.time()
    since = since or until - 86400
    since = max(since, until - _MAX_SPAN_S)
    db = getattr(request.app.state, "db", None)
    config = request.app.state.config
    cams = [{"id": c.id, "name": c.name, "zone": c.zone} for c in config.cameras]
    if db is None:
        return {"since": since, "until": until, "cams": cams, "events": [], "truncated": False}
    with db._lock:
        rows = db._conn.execute(
            "SELECT e.id, e.ts, e.cam_id, e.people, e.data, e.review_label, "
            "(SELECT s.id FROM snapshots s WHERE s.event_id = e.id ORDER BY s.id DESC LIMIT 1) "
            "FROM events e WHERE e.type='nemotron' AND e.has_alert=1 AND e.ts>=? AND e.ts<=? "
            "ORDER BY e.ts DESC LIMIT ?", (since, until, _MAX_EVENTS + 1)).fetchall()
    truncated = len(rows) > _MAX_EVENTS
    events = []
    for eid, ts, cam, people, data, label, sid in rows[:_MAX_EVENTS]:
        try:
            d = json.loads(data or "{}")
        except ValueError:
            d = {}
        events.append({"id": eid, "ts": ts, "cam": cam, "people": people or 0,
                       "type": (d.get("alert_types") or ["sin_tipo"])[0],
                       "sev": d.get("severity") or "", "text": (d.get("activity") or "")[:160],
                       "review": label, "img": f"/api/snapshots/file/{sid}" if sid else None})
    events.reverse()
    return {"since": since, "until": until, "cams": cams, "events": events, "truncated": truncated}
