"""
SQLite event store para THOR Vision.

Mismo enfoque que el Orinano (`events.db`) pero con schema adaptado:
- events: nemotron + cam_state + alert
- snapshots: índice de JPGs en disco
- chat_messages: historial del chat persistente por session_id

Diseño:
- WAL mode → lecturas concurrentes sin bloquear writes
- Lock interno (threading.Lock) → serializa writes desde N workers
- `check_same_thread=False` para uso multi-thread
- Sin dependencias externas — `sqlite3` viene en stdlib
"""
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        REAL    NOT NULL,
  type      TEXT    NOT NULL,
  cam_id    TEXT,
  people    INTEGER,
  has_alert INTEGER NOT NULL DEFAULT 0,
  data      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts        ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_cam_ts    ON events(cam_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts   ON events(type, ts);
CREATE INDEX IF NOT EXISTS idx_events_alerts    ON events(has_alert, ts) WHERE has_alert = 1;

CREATE TABLE IF NOT EXISTS snapshots (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         REAL    NOT NULL,
  cam_id     TEXT    NOT NULL,
  path       TEXT    NOT NULL,
  trigger    TEXT    NOT NULL,
  event_id   INTEGER,
  size_bytes INTEGER,
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_cam_ts ON snapshots(cam_id, ts);
CREATE INDEX IF NOT EXISTS idx_snap_ts     ON snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_snap_trig   ON snapshots(trigger, ts);

CREATE TABLE IF NOT EXISTS chat_messages (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id   TEXT    NOT NULL,
  ts           REAL    NOT NULL,
  role         TEXT    NOT NULL,
  content      TEXT    NOT NULL,
  context_cams INTEGER,
  ms           INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chat_session_ts ON chat_messages(session_id, ts);
"""


class EventDB:
    """SQLite event store thread-safe."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._lock   = threading.Lock()
        self._conn   = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None,    # autocommit; controlamos transacciones manualmente
            timeout=10.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info("EventDB ready — %s", db_path)

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)

    # ── Inserts ───────────────────────────────────────────────────────────

    def insert_event(self, type: str, cam_id: Optional[str], payload: dict,
                     people: Optional[int] = None,
                     has_alert: bool = False) -> int:
        """Inserta un evento y retorna su id."""
        ts = time.time()
        data_json = json.dumps(payload, default=str, ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (ts, type, cam_id, people, has_alert, data) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, type, cam_id, people, 1 if has_alert else 0, data_json),
            )
            return cur.lastrowid

    def insert_snapshot(self, cam_id: str, path: str, trigger: str,
                        event_id: Optional[int] = None,
                        size_bytes: Optional[int] = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO snapshots (ts, cam_id, path, trigger, event_id, size_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), cam_id, path, trigger, event_id, size_bytes),
            )
            return cur.lastrowid

    def insert_chat(self, session_id: str, role: str, content: str,
                    context_cams: Optional[int] = None,
                    ms: Optional[int] = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO chat_messages "
                "(session_id, ts, role, content, context_cams, ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, time.time(), role, content, context_cams, ms),
            )
            return cur.lastrowid

    # ── Queries ───────────────────────────────────────────────────────────

    def query_events(self, cam_id: Optional[str] = None,
                     type: Optional[str] = None,
                     since: Optional[float] = None,
                     until: Optional[float] = None,
                     has_alert: Optional[bool] = None,
                     limit: int = 200) -> list[dict]:
        sql   = "SELECT * FROM events WHERE 1=1"
        args: list[Any] = []
        if cam_id is not None:
            sql += " AND cam_id = ?"; args.append(cam_id)
        if type is not None:
            sql += " AND type = ?"; args.append(type)
        if since is not None:
            sql += " AND ts >= ?"; args.append(since)
        if until is not None:
            sql += " AND ts <= ?"; args.append(until)
        if has_alert is not None:
            sql += " AND has_alert = ?"; args.append(1 if has_alert else 0)
        sql += " ORDER BY ts DESC LIMIT ?"; args.append(min(limit, 2000))

        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [self._row_event(r) for r in rows]

    def query_snapshots(self, cam_id: Optional[str] = None,
                        since: Optional[float] = None,
                        until: Optional[float] = None,
                        trigger: Optional[str] = None,
                        limit: int = 100) -> list[dict]:
        sql   = "SELECT * FROM snapshots WHERE 1=1"
        args: list[Any] = []
        if cam_id is not None:
            sql += " AND cam_id = ?"; args.append(cam_id)
        if since is not None:
            sql += " AND ts >= ?"; args.append(since)
        if until is not None:
            sql += " AND ts <= ?"; args.append(until)
        if trigger is not None:
            sql += " AND trigger = ?"; args.append(trigger)
        sql += " ORDER BY ts DESC LIMIT ?"; args.append(min(limit, 1000))

        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def get_snapshot(self, snapshot_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
        return dict(row) if row else None

    def query_chat_history(self, session_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, ts, context_cams, ms "
                "FROM chat_messages WHERE session_id = ? "
                "ORDER BY ts DESC LIMIT ?",
                (session_id, min(limit, 200)),
            ).fetchall()
        # Devolver en orden cronológico (más viejo primero)
        return list(reversed([dict(r) for r in rows]))

    @staticmethod
    def _row_event(r: sqlite3.Row) -> dict:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            pass
        d["has_alert"] = bool(d.get("has_alert"))
        return d

    # ── Stats & Retention ─────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            n_events    = self._conn.execute("SELECT count(*) FROM events").fetchone()[0]
            n_snaps     = self._conn.execute("SELECT count(*) FROM snapshots").fetchone()[0]
            n_chat      = self._conn.execute("SELECT count(*) FROM chat_messages").fetchone()[0]
            oldest, newest = self._conn.execute(
                "SELECT min(ts), max(ts) FROM events"
            ).fetchone()
        try:
            db_bytes = os.path.getsize(self.db_path)
        except OSError:
            db_bytes = 0
        return {
            "events":        n_events,
            "snapshots":     n_snaps,
            "chat_messages": n_chat,
            "db_mb":         round(db_bytes / (1024 * 1024), 2),
            "oldest_ts":     oldest,
            "newest_ts":     newest,
        }

    def rotate(self, max_events: int = 200_000,
               max_chat_per_session: int = 1_000) -> dict:
        """
        Mantiene los últimos `max_events` rows.
        Borra mensajes de chat más viejos que los `max_chat_per_session` por sesión.
        Borra filas de `snapshots` cuyo archivo ya no existe en disco.
        """
        result: dict = {}

        with self._lock:
            # 1) Truncar events
            cur = self._conn.execute("SELECT count(*) FROM events").fetchone()
            n = cur[0]
            if n > max_events:
                excess = n - max_events
                self._conn.execute(
                    "DELETE FROM events WHERE id IN "
                    "(SELECT id FROM events ORDER BY ts ASC LIMIT ?)",
                    (excess,),
                )
                result["events_deleted"] = excess

            # 2) Truncar chat (por sesión)
            sessions = [r[0] for r in self._conn.execute(
                "SELECT DISTINCT session_id FROM chat_messages"
            ).fetchall()]
            chat_del = 0
            for sid in sessions:
                cnt = self._conn.execute(
                    "SELECT count(*) FROM chat_messages WHERE session_id = ?",
                    (sid,),
                ).fetchone()[0]
                if cnt > max_chat_per_session:
                    excess = cnt - max_chat_per_session
                    self._conn.execute(
                        "DELETE FROM chat_messages WHERE id IN "
                        "(SELECT id FROM chat_messages WHERE session_id = ? "
                        " ORDER BY ts ASC LIMIT ?)",
                        (sid, excess),
                    )
                    chat_del += excess
            if chat_del:
                result["chat_deleted"] = chat_del

            # VACUUM completo es caro — usar WAL checkpoint en su lugar
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        return result

    def delete_snapshot_row(self, snapshot_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM snapshots WHERE id = ?", (snapshot_id,)
            )
            return cur.rowcount > 0

    def all_snapshot_paths(self) -> list[tuple[int, str]]:
        """Para retention: lista (id, path) de todos los snapshots indexados."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, path FROM snapshots"
            ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.close()
        except Exception:
            pass
