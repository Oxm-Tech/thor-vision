"""Reglas de alertas: estadisticas por tipo con etiquetas de revision."""
import json
import sqlite3
import threading
import time

from app.api import routes_rules as rr


class DB:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts REAL, type TEXT, cam_id TEXT, has_alert INT, review_label TEXT, data TEXT)")


def test_stats_group_by_type_cam_and_review():
    db, now = DB(), time.time()
    rows = [("cam-1", "noise"), ("cam-1", "important"), ("cam-2", None), ("cam-1", None)]
    for cam, lab in rows:
        db._conn.execute("INSERT INTO events (ts, type, cam_id, has_alert, review_label, data) VALUES (?,?,?,?,?,?)",
                         (now, "nemotron", cam, 1, lab, json.dumps({"alert_types": ["merodeo"]})))
    s = rr._stats(db)["merodeo"]
    assert s["total"] == 4 and s["noise"] == 1 and s["important"] == 1 and s["sin"] == 2 and s["cams"] == {"cam-1": 3, "cam-2": 1}
