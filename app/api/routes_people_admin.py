"""Clasificacion de personas en tres bases (por revisar / empleados / invitados), parecidos y asistencia."""
import csv
import io
import os
import time
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()
CATEGORIES = ("revisar", "empleado", "invitado")
ATTENDANCE_EXTRA = {c.strip() for c in os.environ.get("ATTENDANCE_EXTRA_CAMS", "cam-228").split(",") if c.strip()}   # acceso peatonal: Garage frontal
GAP_S = 600   # huecos menores a 10 min dentro de una cámara interna cuentan como presencia continua


def _db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "sin base de datos")
    return db


def ensure_schema(db) -> None:
    with db._lock:
        try:
            db._conn.execute("ALTER TABLE subjects ADD COLUMN category TEXT NOT NULL DEFAULT 'revisar'")
        except Exception:
            pass
        db._conn.execute("CREATE INDEX IF NOT EXISTS idx_subjects_cat ON subjects(category)")
        db._conn.commit()


def _embeddings(db) -> tuple:
    with db._lock:
        rows = db._conn.execute("SELECT id, embedding FROM subjects WHERE embedding IS NOT NULL AND n_emb > 0").fetchall()
    ids, vecs = [], []
    for sid, blob in rows:
        v = np.frombuffer(blob, dtype=np.float32)
        if v.size == 512 and np.isfinite(v).all():
            n = float(np.linalg.norm(v))
            if n > 0:
                ids.append(sid)
                vecs.append(v / n)
    return ids, (np.stack(vecs) if vecs else np.zeros((0, 512), np.float32))


def _subject_rows(db, where="", args=(), limit=200) -> list:
    sql = ("SELECT s.id, COALESCE(s.name, 'Persona #' || s.id), s.named, s.category, s.created_ts, s.last_ts, "
           "(SELECT COUNT(*) FROM person_visits v WHERE v.subject_id=s.id AND v.fp=0 AND v.static=0), "
           "(SELECT group_concat(DISTINCT v.cam_id) FROM person_visits v WHERE v.subject_id=s.id AND v.fp=0 AND v.static=0), "
           "(SELECT COUNT(*) FROM person_visits v WHERE v.subject_id=s.id AND v.face IS NOT NULL) "
           "FROM subjects s WHERE 1=1 " + where + " ORDER BY s.last_ts DESC LIMIT ?")
    with db._lock:
        rows = db._conn.execute(sql, (*args, min(limit, 500))).fetchall()
    return rows


@router.get("/api/people/overview")
def overview(request: Request):
    db = _db(request)
    with db._lock:
        rows = db._conn.execute("SELECT category, COUNT(*), SUM(named) FROM subjects GROUP BY category").fetchall()
    d = {c: {"total": 0, "named": 0} for c in CATEGORIES}
    for cat, n, nm in rows:
        d.setdefault(cat, {"total": 0, "named": 0}).update(total=n, named=int(nm or 0))
    return {"categories": d}


@router.get("/api/people")
def people(request: Request, category: str = "revisar", q: Optional[str] = None, only_named: int = 0, limit: int = 200,
           scope: str = "interior"):
    if category not in CATEGORIES:
        raise HTTPException(400, f"categoria invalida; usa {list(CATEGORIES)}")
    db = _db(request)
    names = {c.id: c.name for c in request.app.state.config.cameras}
    where, args = " AND s.category=?", [category]
    if only_named:
        where += " AND s.named=1"
    if scope == "interior":
        ext = [c.id for c in request.app.state.config.cameras if getattr(c, "zone", "") == "exterior"]
        if ext:
            where += (" AND (s.named=1 OR EXISTS (SELECT 1 FROM person_visits v WHERE v.subject_id=s.id AND v.fp=0 AND v.static=0 AND v.cam_id NOT IN ("
                      + ",".join("?" * len(ext)) + ")))")
            args.extend(ext)
    if q:
        where += " AND lower(COALESCE(s.name,'')) LIKE ?"
        args.append(f"%{q.lower()}%")
    out = []
    for sid, name, named, cat, created, last, visits, cams, faces in _subject_rows(db, where, tuple(args), limit):
        out.append({"id": sid, "name": name, "named": bool(named), "category": cat, "created_ts": created, "last_ts": last,
                    "visits": visits, "cams": [names.get(c, c) for c in (cams or "").split(",") if c],
                    "has_face": faces > 0, "suggested": "empleado" if (named and cat == "revisar") else None})
    return {"category": category, "people": out}


class CategoryBody(BaseModel):
    category: str


class BulkBody(BaseModel):
    ids: list
    category: str


@router.patch("/api/people/{sid}/category")
def set_category(sid: int, body: CategoryBody, request: Request):
    if body.category not in CATEGORIES:
        raise HTTPException(400, f"categoria invalida; usa {list(CATEGORIES)}")
    db = _db(request)
    with db._lock:
        cur = db._conn.execute("UPDATE subjects SET category=? WHERE id=?", (body.category, sid))
        db._conn.commit()
    if not cur.rowcount:
        raise HTTPException(404, "sujeto inexistente")
    return {"ok": True}


@router.post("/api/people/bulk-category")
def bulk_category(body: BulkBody, request: Request):
    if body.category not in CATEGORIES:
        raise HTTPException(400, f"categoria invalida; usa {list(CATEGORIES)}")
    ids = [int(i) for i in body.ids][:500]
    if not ids:
        raise HTTPException(400, "ids vacio")
    db = _db(request)
    with db._lock:
        cur = db._conn.execute(f"UPDATE subjects SET category=? WHERE id IN ({','.join('?' * len(ids))})", (body.category, *ids))
        db._conn.commit()
    return {"ok": True, "updated": cur.rowcount}


@router.get("/api/people/{sid}/similar")
def similar(sid: int, request: Request, min_sim: float = 0.32, limit: int = 12):
    db = _db(request)
    ids, E = _embeddings(db)
    if sid not in ids:
        return {"similar": [], "note": "este sujeto aun no tiene embedding facial"}
    i = ids.index(sid)
    sims = E @ E[i]
    order = [j for j in np.argsort(-sims) if ids[j] != sid and sims[j] >= min_sim][:limit]
    rows = {r[0]: r for r in _subject_rows(db, f" AND s.id IN ({','.join('?' * len(order))})" if order else " AND 0", tuple(ids[j] for j in order), 500)} if order else {}
    out = []
    for j in order:
        r = rows.get(ids[j])
        if r:
            out.append({"id": ids[j], "name": r[1], "named": bool(r[2]), "category": r[3], "visits": r[6], "last_ts": r[5],
                        "similarity": round(float(sims[j]), 3)})
    return {"similar": out, "auto_merge_threshold": 0.45}


@router.get("/api/people/duplicates")
def duplicates(request: Request, min_sim: float = 0.38, limit: int = 40):
    """Pares de sujetos que se parecen entre si (candidatos a fusionar)."""
    db = _db(request)
    ids, E = _embeddings(db)
    if len(ids) < 2:
        return {"pairs": []}
    S = E @ E.T
    iu = np.triu_indices(len(ids), 1)
    vals = S[iu]
    keep = np.where(vals >= min_sim)[0]
    keep = keep[np.argsort(-vals[keep])][:limit]
    with db._lock:
        meta = {r[0]: r for r in db._conn.execute("SELECT id, COALESCE(name,'Persona #'||id), named, category FROM subjects").fetchall()}
    return {"pairs": [{"a": ids[iu[0][k]], "b": ids[iu[1][k]], "similarity": round(float(vals[k]), 3),
                       "a_name": meta[ids[iu[0][k]]][1], "b_name": meta[ids[iu[1][k]]][1],
                       "a_cat": meta[ids[iu[0][k]]][3], "b_cat": meta[ids[iu[1][k]]][3]} for k in keep]}


def _merge(intervals, gap=GAP_S):
    out = []
    for a, b in sorted(intervals):
        if out and a - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _day_bounds(date: Optional[str]) -> tuple:
    lt = time.localtime() if not date else time.strptime(date, "%Y-%m-%d")
    day0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return day0, day0 + 86400


def build_attendance(request: Request, date: Optional[str]) -> dict:
    db = _db(request)
    try:
        t0, t1 = _day_bounds(date)
    except ValueError:
        raise HTTPException(400, "fecha invalida; usa YYYY-MM-DD")
    cams = request.app.state.config.cameras
    names = {c.id: c.name for c in cams}
    internal = [c.id for c in cams if getattr(c, "zone", "interior") == "interior" or c.id in ATTENDANCE_EXTRA]
    now = time.time()
    with db._lock:
        emp = db._conn.execute("SELECT id, COALESCE(name,'Persona #'||id) FROM subjects WHERE category='empleado' ORDER BY name").fetchall()
        vis = db._conn.execute(
            "SELECT v.subject_id, v.cam_id, v.start_ts, COALESCE(v.end_ts, v.start_ts) FROM person_visits v JOIN subjects s ON s.id=v.subject_id "
            "WHERE s.category='empleado' AND v.fp=0 AND v.static=0 AND v.start_ts>=? AND v.start_ts<? "
            f"AND v.cam_id IN ({','.join('?' * len(internal)) or 'NULL'})", (t0, t1, *internal)).fetchall()
        gst = db._conn.execute(
            "SELECT v.subject_id, COALESCE(s.name,'Invitado #'||s.id), MIN(v.start_ts), MAX(COALESCE(v.end_ts,v.start_ts)), COUNT(*), group_concat(DISTINCT v.cam_id) "
            "FROM person_visits v JOIN subjects s ON s.id=v.subject_id WHERE s.category='invitado' AND v.fp=0 AND v.static=0 "
            "AND v.start_ts>=? AND v.start_ts<? GROUP BY v.subject_id ORDER BY MIN(v.start_ts)", (t0, t1)).fetchall()
        pend = db._conn.execute(
            "SELECT COUNT(DISTINCT v.subject_id) FROM person_visits v JOIN subjects s ON s.id=v.subject_id WHERE s.category='revisar' "
            "AND v.fp=0 AND v.static=0 AND v.start_ts>=? AND v.start_ts<?", (t0, t1)).fetchone()[0]
    by: dict = {}
    for sid, cam, a, b in vis:
        by.setdefault(sid, []).append((a, b, cam))
    rows = []
    for sid, name in emp:
        v = by.get(sid, [])
        segs = _merge([(a, b) for a, b, _ in v])
        present = sum(b - a for a, b in segs)
        rows.append({"id": sid, "name": name, "present": bool(v), "first_ts": min((a for a, _, _ in v), default=None),
                     "last_ts": max((b for _, b, _ in v), default=None), "minutes": round(present / 60),
                     "segments": len(segs), "cams": sorted({names.get(c, c) for _, _, c in v})})
    return {"date": time.strftime("%Y-%m-%d", time.localtime(t0)), "internal_cams": [names[c] for c in internal],
            "partial_day": t0 <= now < t1,
            "employees": rows,
            "guests": {"count": len(gst), "people": [{"id": g[0], "name": g[1], "first_ts": g[2], "last_ts": g[3], "visits": g[4],
                                                      "cams": [names.get(c, c) for c in (g[5] or "").split(",") if c],
                                                      "snapshot": f"/api/subjects/{g[0]}/face"} for g in gst]},
            "pending_review": pend}


@router.get("/api/attendance")
def attendance(request: Request, date: Optional[str] = None):
    return build_attendance(request, date)


@router.get("/api/attendance.csv")
def attendance_csv(request: Request, date: Optional[str] = None):
    d = build_attendance(request, date)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["fecha", "empleado", "presente", "primera_vez", "ultima_vez", "minutos_en_oficina", "camaras"])
    hm = lambda ts: time.strftime("%H:%M", time.localtime(ts)) if ts else ""
    for e in d["employees"]:
        w.writerow([d["date"], e["name"], "si" if e["present"] else "no", hm(e["first_ts"]), hm(e["last_ts"]), e["minutes"], "; ".join(e["cams"])])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="asistencia_{d["date"]}.csv"'})


@router.get("/api/people/{sid}/visits")
def person_visits(sid: int, request: Request, limit: int = 24):
    db = _db(request)
    names = {c.id: c.name for c in request.app.state.config.cameras}
    with db._lock:
        rows = db._conn.execute(
            "SELECT id, cam_id, start_ts, COALESCE(end_ts,start_ts), (face IS NOT NULL), (body IS NOT NULL) FROM person_visits "
            "WHERE subject_id=? AND fp=0 AND static=0 ORDER BY start_ts DESC LIMIT ?", (sid, min(limit, 100))).fetchall()
    return {"visits": [{"id": i, "cam": names.get(c, c), "start": a, "end": b, "has_face": bool(f), "has_body": bool(bd)}
                       for i, c, a, b, f, bd in rows]}


@router.get("/api/people/today")
def people_today(request: Request):
    """Resumen del dia: cuantos empleados presentes, invitados vistos y personas por revisar."""
    d = build_attendance(request, None)
    emp = d["employees"]
    return {"date": d["date"], "employees_present": sum(1 for e in emp if e["present"]), "employees_total": len(emp),
            "guests": d["guests"]["count"], "pending_review": d["pending_review"]}
