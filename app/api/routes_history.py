"""
Endpoints para consultar la persistencia: eventos, snapshots, chat history.
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, Request, Response, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


def _db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Storage not initialized")
    return db


def _snapshots(request: Request):
    sm = getattr(request.app.state, "snapshots", None)
    if sm is None:
        raise HTTPException(503, "Snapshot manager not initialized")
    return sm


# ── Events ───────────────────────────────────────────────────────────────

@router.get("/api/events")
def list_events(
    request: Request,
    cam_id:    Optional[str]   = None,
    type:      Optional[str]   = None,
    since:     Optional[float] = None,
    until:     Optional[float] = None,
    has_alert: Optional[int]   = None,    # 0 | 1
    limit:     int             = 200,
):
    db = _db(request)
    rows = db.query_events(
        cam_id    = cam_id,
        type      = type,
        since     = since,
        until     = until,
        has_alert = bool(has_alert) if has_alert is not None else None,
        limit     = limit,
    )
    return {"count": len(rows), "events": rows}


# ── Snapshots ────────────────────────────────────────────────────────────

@router.get("/api/snapshots")
def list_snapshots(
    request: Request,
    cam_id:  Optional[str]   = None,
    since:   Optional[float] = None,
    until:   Optional[float] = None,
    trigger: Optional[str]   = None,
    limit:   int             = 100,
):
    db = _db(request)
    rows = db.query_snapshots(
        cam_id  = cam_id,
        since   = since,
        until   = until,
        trigger = trigger,
        limit   = limit,
    )
    return {"count": len(rows), "snapshots": rows}


@router.get("/api/snapshots/file/{snapshot_id}")
def serve_snapshot(snapshot_id: int, request: Request):
    db = _db(request)
    sm = _snapshots(request)

    row = db.get_snapshot(snapshot_id)
    if row is None:
        raise HTTPException(404, "Snapshot not found in index")

    abs_path = sm.absolute_path(row["path"])
    if not abs_path.exists():
        raise HTTPException(404, f"Snapshot file missing: {row['path']}")

    try:
        data = abs_path.read_bytes()
    except OSError as e:
        raise HTTPException(500, f"Read error: {e}")

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/api/snapshots/{cam_id}")
def trigger_snapshot(cam_id: str, request: Request):
    """Trigger manual de snapshot — guarda el frame actual."""
    manager = request.app.state.capture_manager
    sm      = _snapshots(request)

    frame = manager.get_frame(cam_id)
    if frame is None:
        raise HTTPException(404, f"No frame available for {cam_id}")

    rel_path = sm.save(cam_id, frame, trigger="api", event_id=None)
    if rel_path is None:
        raise HTTPException(500, "Snapshot save failed")

    abs_path = sm.absolute_path(rel_path)
    try:
        size = abs_path.stat().st_size
    except OSError:
        size = 0

    return {
        "cam_id":     cam_id,
        "path":       rel_path,
        "size_bytes": size,
    }


# ── Chat history ─────────────────────────────────────────────────────────

@router.get("/api/chat/history")
def chat_history(request: Request, session_id: str, limit: int = 50):
    db = _db(request)
    rows = db.query_chat_history(session_id=session_id, limit=limit)
    return {"session_id": session_id, "count": len(rows), "messages": rows}


# ── Storage stats ────────────────────────────────────────────────────────

@router.get("/api/storage/stats")
def storage_stats(request: Request):
    db = _db(request)
    sm = _snapshots(request)
    stats = db.stats()

    # Calcular tamaño total de snapshots en disco
    snap_bytes = 0
    try:
        for cam_dir in sm.base.iterdir():
            if not cam_dir.is_dir(): continue
            for day_dir in cam_dir.iterdir():
                if not day_dir.is_dir(): continue
                for f in day_dir.iterdir():
                    try:
                        snap_bytes += f.stat().st_size
                    except OSError:
                        pass
    except OSError:
        pass

    stats["snapshots_gb"] = round(snap_bytes / (1024 ** 3), 2)
    return stats


# ── Admin: trigger retention manual ──────────────────────────────────────

@router.post("/api/admin/rotate")
def admin_rotate(request: Request):
    """Trigger manual de retention (no espera 1h)."""
    db = _db(request)
    sm = _snapshots(request)
    t0 = time.monotonic()
    db_res   = db.rotate()
    snap_res = sm.rotate()
    return {
        "ms":         round((time.monotonic() - t0) * 1000),
        "db":         db_res or "no-op",
        "snapshots":  snap_res,
    }
