"""Registro continuo de presencia (fase 1): cuantas visitas quedan identificadas por rostro, sugeridas por cuerpo/ropa, y estado de la validacion por esqueleto."""
import threading
import time

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/api/presence/stats")
def stats(request: Request, hours: float = 24.0):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "sin base de datos")
    names = {c.id: c.name for c in request.app.state.config.cameras}
    since = time.time() - min(max(hours, 1), 168) * 3600
    with db._lock:
        rows = db._conn.execute(
            "SELECT cam_id, COUNT(*), SUM(subject_id IS NOT NULL), SUM(subject_id IS NULL AND json_extract(attrs,'$.guess.id') IS NOT NULL), SUM(attrs IS NOT NULL), "
            "SUM(face IS NOT NULL) FROM person_visits WHERE fp=0 AND static=0 AND start_ts>=? GROUP BY cam_id ORDER BY 2 DESC", (since,)).fetchall()
    cams = [{"cam": names.get(c, c), "visits": n, "with_identity": i or 0, "with_guess": g or 0, "with_body": b or 0, "with_face": f or 0,
             "pct_identified": round(100 * (i or 0) / n, 1) if n else 0, "pct_identified_or_guess": round(100 * ((i or 0) + (g or 0)) / n, 1) if n else 0}
            for c, n, i, g, b, f in rows]
    tot = {k: sum(c[k] for c in cams) for k in ("visits", "with_identity", "with_guess", "with_body", "with_face")}
    bid = getattr(getattr(request.app.state, "visits", None), "bodyid", None)
    models = getattr(request.app.state, "vision_models", None)
    return {"hours": hours, "total": tot, "cams": cams, "bodyid": bid.stats if bid else None, "pose": getattr(models, "pose_stats", None)}


@router.post("/api/presence/backfill")
def backfill(request: Request, hours: float = 24.0):
    bid = getattr(getattr(request.app.state, "visits", None), "bodyid", None)
    if bid is None:
        raise HTTPException(503, "reconocimiento de cuerpo apagado")
    threading.Thread(target=lambda: bid.backfill(hours), daemon=True, name="bodyid-backfill").start()
    return {"ok": True, "hours": hours, "note": "procesando en segundo plano; consulta /api/presence/stats"}
