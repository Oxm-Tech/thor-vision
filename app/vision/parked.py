"""Registro de vehiculos estacionados en las camaras de calle: llegada, permanencia y (cuando se pueda) placa."""
import logging
import os
import threading
import time
from collections import Counter

import cv2

logger = logging.getLogger(__name__)

VEHICLE_CLASSES = {"auto", "moto", "camion", "autobus"}
CAMS = {c.strip() for c in os.environ.get("PARKED_CAMS", "cam-189,cam-191").split(",") if c.strip()}
MIN_PARKED_S = float(os.environ.get("PARKED_MIN_S", "180"))     # quieto este tiempo => estacionado
GONE_S = float(os.environ.get("PARKED_GONE_S", "900"))          # sin verse este tiempo => se fue
MIN_IOU = float(os.environ.get("PARKED_IOU", "0.40"))
MIN_AREA_FRAC = 0.0015                                           # ignora cajas diminutas (ruido lejano)
RETENTION_DAYS = int(os.environ.get("PARKED_RETENTION_DAYS", "90"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS parked_vehicles (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  cam_id     TEXT NOT NULL,
  cls        TEXT NOT NULL,
  first_ts   REAL NOT NULL,
  last_ts    REAL NOT NULL,
  left_ts    REAL,
  state      TEXT NOT NULL DEFAULT 'parked',
  box        TEXT,
  frame_w    INTEGER,
  frame_h    INTEGER,
  thumb      BLOB,
  plate      TEXT,
  plate_conf REAL,
  note       TEXT
);
CREATE INDEX IF NOT EXISTS idx_parked_state ON parked_vehicles(state, cam_id);
CREATE INDEX IF NOT EXISTS idx_parked_first ON parked_vehicles(first_ts);
"""


def _match(a, b) -> float:
    """Puntaje 0..1 de que dos cajas son el mismo vehiculo quieto (IoU, o centros cercanos y tamano parecido)."""
    v = _iou(a, b)
    wa, ha, wb, hb = a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1]
    cd = (((a[0] + a[2]) - (b[0] + b[2])) ** 2 + ((a[1] + a[3]) - (b[1] + b[3])) ** 2) ** 0.5 / 2
    ratio = (wa * ha) / float(max(1, wb * hb))
    if cd < 0.30 * max(wa, wb) and 0.55 < ratio < 1.8:
        v = max(v, 0.6)
    return v


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if not inter:
        return 0.0
    return inter / float((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


class ParkedTracker:
    def __init__(self, db):
        self.db = db
        self._lock = threading.Lock()
        self._cand: dict = {}
        self._last_gc = 0.0
        with db._lock:
            db._conn.executescript(_SCHEMA)
            rows = db._conn.execute("SELECT id, cam_id, cls, first_ts, last_ts, box FROM parked_vehicles WHERE state='parked'").fetchall()
        for rid, cam, cls, first, last, box in rows:
            try:
                b = tuple(int(v) for v in box.split(","))
            except Exception:
                continue
            self._cand.setdefault(cam, []).append({"cls": Counter({cls: 5}), "anchor": b, "first": first, "last": last,
                                                   "hits": 99, "rec": rid, "saved": last})
        logger.info("ParkedTracker: camaras=%s min=%.0fs, %d vehiculos abiertos recuperados", sorted(CAMS), MIN_PARKED_S, len(rows))

    @staticmethod
    def _thumb(frame, box, max_side=360):
        try:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = box
            pw, ph = int((x2 - x1) * .08), int((y2 - y1) * .08)
            crop = frame[max(0, y1 - ph):min(h, y2 + ph), max(0, x1 - pw):min(w, x2 + pw)]
            k = max_side / max(crop.shape[:2])
            if k < 1.0:
                crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
            return buf.tobytes() if ok else None
        except Exception:
            return None

    def update(self, cam_id, result, frame, ts=None) -> None:
        if cam_id not in CAMS:
            return
        now = ts or time.time()
        fh, fw = frame.shape[:2]
        rw, rh = getattr(result, "frame_w", 0) or fw, getattr(result, "frame_h", 0) or fh
        sx, sy = fw / rw, fh / rh
        dets = []
        for o in getattr(result, "objects", None) or []:
            if o["c"] in VEHICLE_CLASSES:
                x1, y1, x2, y2 = o["b"]
                b = (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
                if (b[2] - b[0]) * (b[3] - b[1]) >= MIN_AREA_FRAC * fw * fh:
                    dets.append((o["c"], b))
        with self._lock:
            cands = self._cand.setdefault(cam_id, [])
            used = set()
            for cls, b in dets:
                best, bi = 0.0, None
                for i, c in enumerate(cands):
                    if i in used:
                        continue
                    v = _match(c["anchor"], b)
                    if v > best:
                        best, bi = v, i
                if bi is not None and best >= MIN_IOU:
                    c = cands[bi]
                    used.add(bi)
                    c["last"] = now
                    c["anchor"] = tuple(int(0.85 * p + 0.15 * q) for p, q in zip(c["anchor"], b))
                    c["hits"] += 1
                    c["cls"][cls] += 1
                    self._maybe_register(cam_id, c, frame, fw, fh, now)
                else:
                    cands.append({"cls": Counter({cls: 1}), "anchor": b, "first": now, "last": now,
                                  "hits": 1, "rec": None, "saved": 0.0})
            self._gc(cam_id, now)

    def _maybe_register(self, cam_id, c, frame, fw, fh, now) -> None:
        if c["rec"] is None:
            if now - c["first"] >= MIN_PARKED_S and c["hits"] >= 3:
                cls = c["cls"].most_common(1)[0][0]
                b = c["anchor"]
                for other in self._cand.get(cam_id, []):
                    if other is not c and other["rec"] is not None and _match(other["anchor"], b) >= 0.3:
                        other["last"] = max(other["last"], c["last"])
                        other["first"] = min(other["first"], c["first"])
                        c["dup"] = True      # es el mismo vehiculo: no se registra otra vez
                        return
                with self.db._lock:
                    cur = self.db._conn.execute(
                        "INSERT INTO parked_vehicles (cam_id, cls, first_ts, last_ts, state, box, frame_w, frame_h, thumb) "
                        "VALUES (?, ?, ?, ?, 'parked', ?, ?, ?, ?)",
                        (cam_id, cls, c["first"], now, ",".join(map(str, b)), fw, fh, self._thumb(frame, b)))
                    self.db._conn.commit()
                    c["rec"] = cur.lastrowid
                c["saved"] = now
                logger.info("ParkedTracker: %s estacionado en %s (id=%d)", cls, cam_id, c["rec"])
        elif now - c["saved"] >= 60:
            with self.db._lock:
                self.db._conn.execute("UPDATE parked_vehicles SET last_ts=? WHERE id=?", (now, c["rec"]))
                self.db._conn.commit()
            c["saved"] = now

    def _gc(self, cam_id, now) -> None:
        cands = self._cand.get(cam_id, [])
        keep = []
        for c in cands:
            if c.get("dup"):
                continue
            idle = now - c["last"]
            if c["rec"] is not None and idle > GONE_S:
                with self.db._lock:
                    self.db._conn.execute("UPDATE parked_vehicles SET state='left', left_ts=?, last_ts=? WHERE id=?",
                                          (c["last"], c["last"], c["rec"]))
                    self.db._conn.commit()
                logger.info("ParkedTracker: vehiculo %d se fue de %s tras %.0f min", c["rec"], cam_id, (c["last"] - c["first"]) / 60)
            elif c["rec"] is None and idle > 120:
                pass
            else:
                keep.append(c)
        self._cand[cam_id] = keep
        if now - self._last_gc > 86400:
            self._last_gc = now
            with self.db._lock:
                self.db._conn.execute("DELETE FROM parked_vehicles WHERE state='left' AND left_ts < ?", (now - RETENTION_DAYS * 86400,))
                self.db._conn.commit()


def list_vehicles(db, state=None, cam=None, since=None, limit=100) -> list:
    sql = ("SELECT id, cam_id, cls, first_ts, last_ts, left_ts, state, plate, plate_conf, note, (thumb IS NOT NULL) "
           "FROM parked_vehicles WHERE 1=1")
    args: list = []
    if state in ("parked", "left"):
        sql += " AND state=?"
        args.append(state)
    if cam:
        sql += " AND cam_id=?"
        args.append(cam)
    if since:
        sql += " AND last_ts>=?"
        args.append(since)
    sql += " ORDER BY (state='parked') DESC, first_ts DESC LIMIT ?"
    args.append(min(int(limit), 500))
    now = time.time()
    with db._lock:
        rows = db._conn.execute(sql, args).fetchall()
    out = []
    for rid, cam_id, cls, first, last, left, st, plate, pc, note, has in rows:
        end = (left or last) if st == "left" else now
        out.append({"id": rid, "cam_id": cam_id, "cls": cls, "first_ts": first, "last_ts": last, "left_ts": left,
                    "state": st, "duration_s": max(0, round(end - first)), "plate": plate, "plate_conf": pc,
                    "note": note, "has_thumb": bool(has)})
    return out
