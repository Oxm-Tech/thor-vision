"""Eventos IoT por MQTT (solo lectura): estado, alertas de puerta abierta, abierta mucho tiempo y bateria baja."""
import json
import sqlite3
import threading
import time

from app.iot import listener as li


class FakeDB:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:")
        self.events = []

    def insert_event(self, type, cam_id, payload, people=None, has_alert=False):
        self.events.append((type, cam_id, payload, has_alert))
        return len(self.events)


class FakeSnaps:
    def __init__(self):
        self.saved = []

    def save(self, cam_id, frame, trigger, event_id=None):
        self.saved.append((cam_id, trigger, event_id))


class FakeBuf:
    def peek_latest(self):
        return object()


def make():
    db, sn = FakeDB(), FakeSnaps()
    m = li.IotListener(db, sn, {"cam-113": FakeBuf()}, {"cam-113": "Escaleras entrada"})
    m.cfg = {"alert_open_minutes": 10, "low_battery_pct": 15}
    m.devices = {"D1": {"name": "Recepcion Puerta", "kind": "door", "cam": "cam-113", "confirmed": False, "open_code": "doorcontact_state", "open_value": True},
                 "C1": {"name": "Camara", "kind": "camera", "cam": None}}
    return m, db, sn


def msg(dev, changes, ts=None):
    return json.dumps({"device_id": dev, "ts": ts or time.time(), "changes": changes}).encode()


def test_repo_map_parses_and_has_the_sensors():
    cfg = li.load_map("config/iot.yml")
    assert cfg["devices"]["ebd84e19bf42731470j1ao"]["kind"] == "door" and cfg["alert_open_minutes"] == 10


def test_is_open():
    d = {"open_code": "doorcontact_state", "open_value": True}
    assert li.is_open(d, {"doorcontact_state": True}) is True and li.is_open(d, {"doorcontact_state": False}) is False
    assert li.is_open(d, {"battery_percentage": 50}) is None


def test_startup_state_and_retained_never_alert_but_are_stored():
    m, db, sn = make()
    m.handle("oxm/tuya/D1/last", msg("D1", {"doorcontact_state": True}), retained=True)
    m.handle("oxm/tuya/D1/status", msg("D1", {"doorcontact_state": True}))            # primer estado conocido
    assert db.events == [] and m.state["D1"]["open"] is True
    assert {r["source"] for r in m.recent()} == {"sync", "event"}


def test_opening_creates_alert_with_snapshot_and_closing_does_not():
    m, db, sn = make()
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": False}))
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": True}))
    assert len(db.events) == 1
    typ, cam, p, has_alert = db.events[0]
    assert typ == "nemotron" and cam == "cam-113" and has_alert and p["source"] == "iot"
    assert p["alert_types"] == ["puerta_abierta"] and p["iot"]["state"] == "open" and p["iot"]["cam_confirmed"] is False
    assert sn.saved == [("cam-113", "puerta", 1)]
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": False}))                  # cerrarse no alerta
    assert len(db.events) == 1 and m.state["D1"]["open"] is False


def test_open_too_long_alerts_once_per_interval():
    m, db, sn = make()
    t0 = 1_000_000.0
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": False}, t0))
    m.handle("t/D1/status", msg("D1", {"doorcontact_state": True}, t0 + 10))
    n = len(db.events)
    m.check_open_too_long(t0 + 10 + 300)                                                # 5 min: aun no
    assert len(db.events) == n
    m.check_open_too_long(t0 + 10 + 11 * 60)
    assert len(db.events) == n + 1 and "min abierta" in db.events[-1][2]["activity"]
    m.check_open_too_long(t0 + 10 + 12 * 60)                                            # no repite enseguida
    assert len(db.events) == n + 1


def test_low_battery_alerts_once_a_day_and_unknown_devices_are_ignored():
    m, db, sn = make()
    m.handle("t/D1/status", msg("D1", {"battery_percentage": 1}))
    m.handle("t/D1/status", msg("D1", {"battery_percentage": 1}))
    assert [e[2]["alert_types"] for e in db.events] == [["sensor_bateria_baja"]]
    m.handle("t/XX/status", msg("XX", {"doorcontact_state": True}))
    assert len(db.events) == 1 and "XX" not in m.state


def test_garbage_messages_are_ignored():
    m, db, _ = make()
    m.handle("t/D1/status", b"no es json")
    m.handle("t/D1/status", msg("D1", {}))
    assert db.events == []


def test_usage_alert_once_per_threshold_and_never_from_retained():
    m, db, _ = make()
    msg = lambda t, p: json.dumps({"ts": time.time(), "pct": p, "threshold": t, "quota_gb": 5}).encode()
    m.handle("oxm/tuya/_usage", msg(50, 51.0), retained=True)          # estado viejo al arrancar: no alerta
    assert db.events == []
    m.handle("oxm/tuya/_usage", msg(80, 82.0))
    m.handle("oxm/tuya/_usage", msg(80, 83.0))                         # mismo umbral: una sola vez
    assert [e[2]["alert_types"] for e in db.events] == [["consumo_video_tuya"]] and db.events[0][2]["severity"] == "medium"


def _im(cmd="ipc_motion", t=1791154788):
    import base64
    return base64.b64encode(json.dumps({"v": "4.0", "cmd": cmd, "time": t, "alarm": True}).encode()).decode()


def test_camera_message_is_decoded_deduped_and_alerts_once_per_cooldown(monkeypatch):
    m, db, sn = make()
    grabbed = []
    monkeypatch.setattr(m, "_grab_frame", lambda *a: grabbed.append(a))
    t = time.time()
    for _ in range(2):                                              # la nube entrega cada mensaje duplicado
        m.handle("t/C1/status", msg("C1", {"initiative_message": _im(), "dp239": "motion"}, ts=t))
    codes = [r["code"] for r in m.recent("C1")]
    assert codes.count("ipc_motion") == 1 and codes.count("dp239") == 1
    assert len(db.events) == 1 and db.events[0][2]["alert_types"] == ["movimiento_tuya"]
    m.handle("t/C1/status", msg("C1", {"initiative_message": _im("ipc_bang")}, ts=t + 30))   # dentro del enfriamiento: sin alerta nueva
    assert len(db.events) == 1
    m.handle("t/C1/status", msg("C1", {"initiative_message": _im("ipc_bang")}, ts=t + 500))
    assert len(db.events) == 2 and db.events[1][2]["alert_types"] == ["ruido_tuya"]
