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
    events += _street_traffic(db, config, since, until)
    events.sort(key=lambda e: e["ts"])
    iot = getattr(request.app.state, "iot", None)
    if iot is not None:
        cams += [{"id": d["alias"], "name": d["name"].replace(" (Tuya)", " (Tuya)"), "zone": "tuya"} for d in iot.devices.values() if d.get("alias")]
    return {"since": since, "until": until, "cams": cams, "events": events, "truncated": truncated}


def _street_traffic(db, config, since, until) -> list:
    """Personas que pasan por las camaras de la calle (y el videoportero): quedan como registro en la linea de tiempo, no en la ocupacion interior."""
    ext = [c.id for c in config.cameras if getattr(c, "zone", "") == "exterior"]
    if not ext:
        return []
    with db._lock:
        rows = db._conn.execute(
            "SELECT v.id, v.start_ts, v.cam_id, COALESCE(s.name, 'Persona #'||s.id), s.named, v.vlm_desc FROM person_visits v LEFT JOIN subjects s ON s.id=v.subject_id "
            f"WHERE v.fp=0 AND v.static=0 AND v.start_ts>=? AND v.start_ts<=? AND v.cam_id IN ({','.join('?' * len(ext))}) "
            "AND (s.named=1 OR v.end_ts - v.start_ts >= 8) ORDER BY v.start_ts DESC LIMIT 600", (since, until, *ext)).fetchall()
    out = []
    for vid, ts, cam, name, named, desc in rows:
        who = name if named else "Persona sin identificar"
        out.append({"id": f"v{vid}", "ts": ts, "cam": cam, "people": 1, "type": "trafico_calle", "sev": "none",
                    "text": (f"{who} en la calle" + (f": {desc}" if desc else ""))[:160], "review": None,
                    "img": f"/api/person-visits/{vid}/body"})
    return out



@router.get("/api/correlation")
def correlation(request: Request, ts: Optional[float] = None, event_id: Optional[int] = None, before: int = 120, after: int = 300):
    """Todo lo que paso alrededor de un momento (o de una alerta): timbre, visitas con o sin nombre, alertas, puertas y camaras Tuya, en orden."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        return {"items": []}
    names = {c.id: c.name for c in request.app.state.config.cameras}
    with db._lock:
        if event_id is not None:
            row = db._conn.execute("SELECT ts FROM events WHERE id=?", (event_id,)).fetchone()
            ts = row[0] if row else ts
    if ts is None:
        return {"items": [], "note": "indica ts o event_id"}
    t0, t1 = ts - min(before, 1800), ts + min(after, 3600)
    items = []
    with db._lock:
        c = db._conn
        for eid, t, cam, data in c.execute("SELECT id, ts, cam_id, data FROM events WHERE type='nemotron' AND has_alert=1 AND ts BETWEEN ? AND ?", (t0, t1)):
            try:
                d = json.loads(data or "{}")
            except ValueError:
                d = {}
            items.append({"ts": t, "kind": "alerta", "cam": names.get(cam, cam), "text": d.get("activity") or "", "type": (d.get("alert_types") or [""])[0], "event_id": eid})
        for vid, a, b, cam, nm, named in c.execute(
                "SELECT v.id, v.start_ts, v.end_ts, v.cam_id, COALESCE(s.name,'Persona #'||s.id), s.named FROM person_visits v LEFT JOIN subjects s ON s.id=v.subject_id "
                "WHERE v.fp=0 AND v.static=0 AND v.start_ts BETWEEN ? AND ?", (t0, t1)):
            items.append({"ts": a, "kind": "persona", "cam": names.get(cam, cam), "text": (nm if named else "persona sin identificar") + f" ({int(b - a)} s)", "visit_id": vid,
                          "img": f"/api/person-visits/{vid}/body"})
        for t, ep, topic, state in c.execute("SELECT ts, endpoint, topic, state FROM onvif_events WHERE topic LIKE 'dahua/%' AND ts BETWEEN ? AND ?", (t0, t1)):
            items.append({"ts": t, "kind": "videoportero", "cam": "Videoportero", "text": topic.split("/", 1)[1] + (f" ({state})" if state else "")})
        for t, name, kind, code, val in c.execute("SELECT ts, name, kind, code, value FROM iot_events WHERE source!='sync' AND ts BETWEEN ? AND ? "
                                                  "AND code IN ('doorcontact_state','cerrada','ipc_motion','ipc_bang')", (t0, t1)):
            items.append({"ts": t, "kind": "sensor", "cam": name, "text": f"{code} = {val}"[:80]})
    items.sort(key=lambda i: i["ts"])
    return {"ts": ts, "window": [t0, t1], "items": items[:300]}
